#!/usr/bin/env python3
import argparse
import collections
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

PHOTO = Path('/volume2/photo')
BACKUP = Path('/volume2/backup/codex-cloud-memory-reorg-20260901')
SOURCE_PREFIX = '220101_'
CACHE_NAMES = {'.DS_Store', 'Thumbs.db'}
IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.webp'}
VIDEO_EXTS = {'.mp4'}


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def event_date(path):
    match = re.match(r'^(\d{6})_', path.name)
    if not match:
        return None
    try:
        return dt.datetime.strptime(match.group(1), '%y%m%d').date()
    except ValueError:
        return None


def is_cache(path, source):
    rel = path.relative_to(source)
    return path.name in CACHE_NAMES or '@eaDir' in rel.parts


def unique_target(directory, name, reserved):
    candidate = directory / name
    key = str(candidate).casefold()
    if not candidate.exists() and key not in reserved:
        reserved.add(key)
        return candidate, False
    stem, suffix = Path(name).stem, Path(name).suffix
    number = 1
    while True:
        candidate = directory / f'{stem}__cloud_{number:02d}{suffix}'
        key = str(candidate).casefold()
        if not candidate.exists() and key not in reserved:
            reserved.add(key)
            return candidate, True
        number += 1


def build_plan():
    sources = sorted(p for p in PHOTO.glob(SOURCE_PREFIX + '*') if p.is_dir())
    if len(sources) != 1:
        return [], [f'expected one source, found {len(sources)}: {sources}']
    source = sources[0]
    events = []
    for path in PHOTO.iterdir():
        date = event_date(path) if path.is_dir() and path != source else None
        if date:
            events.append((date, path))
    if not events:
        return [], ['no valid dated event folders found']

    files = [
        path for path in source.rglob('*')
        if path.is_file() and not is_cache(path, source)
    ]
    errors = []
    reserved = set()
    plan = []
    for src in sorted(files):
        suffix = src.suffix.lower()
        if suffix in IMAGE_EXTS:
            subdir = 'photo'
        elif suffix in VIDEO_EXTS:
            subdir = 'video'
        else:
            errors.append(f'unsupported media extension: {src}')
            continue
        capture_date = dt.datetime.fromtimestamp(src.stat().st_mtime).date()
        target_date, event = min(
            events,
            key=lambda item: (
                abs((item[0] - capture_date).days),
                item[0] > capture_date,
                item[0],
            ),
        )
        dst_dir = event / subdir
        dst, collision = unique_target(dst_dir, src.name, reserved)
        plan.append({
            'src': str(src),
            'dst': str(dst),
            'event': event.name,
            'kind': subdir,
            'captureDate': capture_date.isoformat(),
            'eventDate': target_date.isoformat(),
            'dayDistance': abs((target_date - capture_date).days),
            'collisionRenamed': collision,
        })
    return plan, errors


def summarize(plan, errors):
    groups = collections.defaultdict(list)
    for op in plan:
        groups[op['event']].append(op)
    return {
        'errors': errors,
        'total': len(plan),
        'images': sum(op['kind'] == 'photo' for op in plan),
        'videos': sum(op['kind'] == 'video' for op in plan),
        'collisionsRenamed': sum(op['collisionRenamed'] for op in plan),
        'directoriesToCreate': sorted({str(Path(op['dst']).parent) for op in plan if not Path(op['dst']).parent.is_dir()}),
        'groups': {
            event: {
                'total': len(ops),
                'images': sum(op['kind'] == 'photo' for op in ops),
                'videos': sum(op['kind'] == 'video' for op in ops),
                'dateRange': [min(op['captureDate'] for op in ops), max(op['captureDate'] for op in ops)],
                'maxDayDistance': max(op['dayDistance'] for op in ops),
            }
            for event, ops in sorted(groups.items())
        },
    }


def write_jsonl(stream, row):
    stream.write(json.dumps(row, ensure_ascii=False) + '\n')
    stream.flush()
    os.fsync(stream.fileno())


def copy_verified(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    temp = dst.parent / f'.codex-{uuid.uuid4().hex}.tmp'
    shutil.copy2(src, temp)
    source_hash = sha256(src)
    if sha256(temp) != source_hash:
        temp.unlink(missing_ok=True)
        raise RuntimeError(f'hash mismatch while copying: {src}')
    os.replace(temp, dst)
    return source_hash


def apply(plan):
    if BACKUP.exists():
        raise RuntimeError(f'journal directory already exists: {BACKUP}')
    BACKUP.mkdir(parents=True)
    (BACKUP / 'plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2))
    with open(BACKUP / 'journal.jsonl', 'a', buffering=1) as journal:
        for index, op in enumerate(plan, 1):
            src, dst = Path(op['src']), Path(op['dst'])
            if not src.is_file():
                raise RuntimeError(f'source disappeared: {src}')
            if dst.exists():
                raise RuntimeError(f'target appeared after preflight: {dst}')
            write_jsonl(journal, {'phase': 'start', 'index': index, **op})
            digest = copy_verified(src, dst)
            src.unlink()
            if not dst.is_file() or sha256(dst) != digest or src.exists():
                raise RuntimeError(f'post-move verification failed: {src} -> {dst}')
            write_jsonl(journal, {'phase': 'done', 'index': index, 'sha256': digest, **op})
            if index % 25 == 0:
                print(f'completed={index}/{len(plan)}', flush=True)

    source = next(PHOTO.glob(SOURCE_PREFIX + '*'), None)
    if source:
        remaining_media = [p for p in source.rglob('*') if p.is_file() and not is_cache(p, source)]
        if remaining_media:
            raise RuntimeError('source still contains media: ' + ', '.join(map(str, remaining_media[:5])))
        shutil.rmtree(source)

    affected = sorted({str(Path(op['dst']).parent.parent) for op in plan})
    reindex = []
    for path in affected:
        result = subprocess.run(['synoindex', '-R', path], text=True, capture_output=True)
        reindex.append({'path': path, 'returncode': result.returncode, 'stderr': result.stderr[-1000:]})
    root_index = subprocess.run(['synoindex', '-R', str(PHOTO)], text=True, capture_output=True)
    reindex.append({'path': str(PHOTO), 'returncode': root_index.returncode, 'stderr': root_index.stderr[-1000:]})
    result = {
        'completed': len(plan),
        'images': sum(op['kind'] == 'photo' for op in plan),
        'videos': sum(op['kind'] == 'video' for op in plan),
        'sourceRemoved': not any(PHOTO.glob(SOURCE_PREFIX + '*')),
        'reindex': reindex,
    }
    (BACKUP / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print('APPLY_OK ' + json.dumps(result, ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    plan, errors = build_plan()
    summary = summarize(plan, errors)
    print('PREFLIGHT ' + json.dumps(summary, ensure_ascii=False), flush=True)
    if errors:
        sys.exit(2)
    if args.apply:
        apply(plan)


if __name__ == '__main__':
    main()
