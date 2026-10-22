#!/usr/bin/env python3
import argparse, collections, hashlib, json, os, re, shutil, subprocess, sys, uuid
from pathlib import Path

PHOTO = Path('/volume2/photo')
CLASSIFIED_BACKUP = PHOTO / '170901_备份'
JOURNAL_DIR = Path('/volume2/backup/codex-root-favorites-consolidation-20260901')
IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.heic', '.webp', '.gif', '.dng', '.tif', '.tiff'}


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def unique_target(directory, name, tag, reserved, source_hash):
    direct = directory / name
    key = str(direct).casefold()
    if direct.is_file() and sha256(direct) == source_hash:
        reserved.add(key)
        return direct, 'already'
    if not direct.exists() and key not in reserved:
        reserved.add(key)
        return direct, 'new'
    stem, suffix = Path(name).stem, Path(name).suffix
    number = 1
    while True:
        candidate = directory / f'{stem}__{tag}_{number:02d}{suffix}'
        key = str(candidate).casefold()
        if candidate.is_file() and sha256(candidate) == source_hash:
            reserved.add(key)
            return candidate, 'already'
        if not candidate.exists() and key not in reserved:
            reserved.add(key)
            return candidate, 'collision-renamed'
        number += 1


def event_in_range(path):
    match = re.match(r'^(\d{6})_', path.name)
    return bool(path.is_dir() and match and 170909 <= int(match.group(1)) <= 190613)


def build_plan():
    if not CLASSIFIED_BACKUP.is_dir():
        return [], [f'missing classified backup folder: {CLASSIFIED_BACKUP}']
    plan, errors = [], []
    photo_reserved, backup_reserved = set(), set()
    for event in sorted(path for path in PHOTO.iterdir() if event_in_range(path)):
        selected = sorted(
            path for path in event.iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_EXTS and path.name not in {'.DS_Store', 'Thumbs.db'}
        )
        for src in selected:
            digest = sha256(src)
            photo_dir = event / 'photo'
            backup_dir = CLASSIFIED_BACKUP / event.name
            photo_dst, photo_status = unique_target(photo_dir, src.name, 'selected', photo_reserved, digest)
            backup_dst, backup_status = unique_target(backup_dir, src.name, 'selected', backup_reserved, digest)
            plan.append({
                'event': event.name, 'src': str(src), 'sha256': digest,
                'photoDst': str(photo_dst), 'photoStatus': photo_status,
                'backupDst': str(backup_dst), 'backupStatus': backup_status,
            })
    return plan, errors


def summary(plan, errors):
    return {
        'errors': errors, 'total': len(plan),
        'events': dict(sorted(collections.Counter(op['event'] for op in plan).items())),
        'photoAlready': sum(op['photoStatus'] == 'already' for op in plan),
        'photoNew': sum(op['photoStatus'] != 'already' for op in plan),
        'photoCollisionRenamed': sum(op['photoStatus'] == 'collision-renamed' for op in plan),
        'backupAlready': sum(op['backupStatus'] == 'already' for op in plan),
        'backupNew': sum(op['backupStatus'] != 'already' for op in plan),
        'backupCollisionRenamed': sum(op['backupStatus'] == 'collision-renamed' for op in plan),
    }


def copy_verified(src, dst, expected_hash):
    dst.parent.mkdir(parents=True, exist_ok=True)
    temp = dst.parent / f'.codex-{uuid.uuid4().hex}.tmp'
    shutil.copy2(src, temp)
    if sha256(temp) != expected_hash:
        temp.unlink(missing_ok=True)
        raise RuntimeError(f'hash mismatch copying {src}')
    os.replace(temp, dst)


def write_jsonl(stream, row):
    stream.write(json.dumps(row, ensure_ascii=False) + '\n'); stream.flush(); os.fsync(stream.fileno())


def apply(plan):
    if JOURNAL_DIR.exists():
        raise RuntimeError(f'journal directory already exists: {JOURNAL_DIR}')
    JOURNAL_DIR.mkdir(parents=True)
    (JOURNAL_DIR / 'plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2))
    affected = set()
    with open(JOURNAL_DIR / 'journal.jsonl', 'a', buffering=1) as journal:
        for index, op in enumerate(plan, 1):
            src = Path(op['src']); photo_dst = Path(op['photoDst']); backup_dst = Path(op['backupDst'])
            if not src.is_file() or sha256(src) != op['sha256']:
                raise RuntimeError(f'source missing or changed: {src}')
            write_jsonl(journal, {'phase': 'start', 'index': index, **op})
            if op['photoStatus'] != 'already':
                if photo_dst.exists(): raise RuntimeError(f'photo target appeared: {photo_dst}')
                copy_verified(src, photo_dst, op['sha256'])
            if op['backupStatus'] != 'already':
                if backup_dst.exists(): raise RuntimeError(f'backup target appeared: {backup_dst}')
                copy_verified(src, backup_dst, op['sha256'])
            if sha256(photo_dst) != op['sha256'] or sha256(backup_dst) != op['sha256']:
                raise RuntimeError(f'destination verification failed: {src}')
            src.unlink()
            if src.exists(): raise RuntimeError(f'root source still exists: {src}')
            write_jsonl(journal, {'phase': 'done', 'index': index, **op})
            affected.add(str(Path(op['photoDst']).parent.parent))
            if index % 20 == 0: print(f'completed={index}/{len(plan)}', flush=True)
    affected.add(str(CLASSIFIED_BACKUP))
    reindex = []
    for path in sorted(affected):
        result = subprocess.run(['synoindex', '-R', path], text=True, capture_output=True)
        reindex.append({'path': path, 'returncode': result.returncode, 'stderr': result.stderr[-1000:]})
    remaining = []
    for event in sorted(path for path in PHOTO.iterdir() if event_in_range(path)):
        remaining += [str(path) for path in event.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_EXTS]
    result = {'completed': len(plan), 'rootSelectionsRemaining': remaining, 'reindex': reindex}
    (JOURNAL_DIR / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print('APPLY_OK ' + json.dumps(result, ensure_ascii=False), flush=True)
    if remaining: raise SystemExit(2)


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--apply', action='store_true'); args = parser.parse_args()
    plan, errors = build_plan(); print('PREFLIGHT ' + json.dumps(summary(plan, errors), ensure_ascii=False), flush=True)
    if errors: sys.exit(2)
    if args.apply: apply(plan)


if __name__ == '__main__': main()
