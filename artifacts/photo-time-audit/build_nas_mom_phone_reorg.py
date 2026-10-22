#!/usr/bin/env python3
import datetime as dt
import json
import re
import subprocess
from pathlib import Path

MOUNT = Path('/Volumes/photo')
SOURCE = MOUNT / '170408_妈妈手机照片'
OUT = Path(__file__).with_name('nas_mom_phone_reorg.py')
IMAGE_EXTS = {'.jpg', '.jpeg', '.heic', '.png', '.gif'}
VIDEO_EXTS = {'.mp4', '.mov'}


def parse_date(value):
    match = re.match(r'^(\d{4})[:\-](\d{2})[:\-](\d{2})[ T](\d{2}):(\d{2}):(\d{2})', str(value or ''))
    if not match:
        return None
    try:
        return dt.datetime(*map(int, match.groups()))
    except ValueError:
        return None


def event_spec(path):
    match = re.match(r'^(\d{6})_', path.name)
    if not match:
        return None
    prefix = match.group(1)
    year, month, day = 2000 + int(prefix[:2]), int(prefix[2:4]), int(prefix[4:6])
    if month == 0 and day == 0:
        return ('year', year, None)
    if 1 <= month <= 12 and day == 0:
        return ('month', year, month)
    try:
        return ('date', dt.datetime.strptime(prefix, '%y%m%d').date(), None)
    except ValueError:
        return None


specs = [(event_spec(path), path.name) for path in MOUNT.iterdir() if path.is_dir() and path != SOURCE and path.name != '170901_备份']
specs = [(spec, name) for spec, name in specs if spec]
dated_events = [(spec[1], name) for spec, name in specs if spec[0] == 'date']
month_buckets = {(spec[1], spec[2]): name for spec, name in specs if spec[0] == 'month'}
year_buckets = {spec[1]: name for spec, name in specs if spec[0] == 'year'}

command = ['exiftool', '-json', '-r']
for ext in sorted(IMAGE_EXTS | VIDEO_EXTS):
    command += ['-ext', ext.lstrip('.')]
for field in ['DateTimeOriginal', 'MediaCreateDate', 'FileModifyDate', 'FileName', 'Directory']:
    command.append('-' + field)
command.append(str(SOURCE))
rows = json.loads(subprocess.check_output(command, text=True))

operations = []
excluded = []
for row in rows:
    source_path = Path(row['SourceFile'])
    suffix = source_path.suffix.lower()
    if suffix in IMAGE_EXTS:
        capture = parse_date(row.get('DateTimeOriginal')) or parse_date(row.get('FileModifyDate'))
        kind = 'photo'
        date_source = 'DateTimeOriginal' if parse_date(row.get('DateTimeOriginal')) else 'FileModifyDate'
    elif suffix in VIDEO_EXTS:
        capture = parse_date(row.get('MediaCreateDate'))
        kind = 'video'
        date_source = 'MediaCreateDate'
        if capture and capture.year >= 2025:
            excluded.append(str(source_path.relative_to(SOURCE)))
            continue
    else:
        continue
    if not capture:
        excluded.append(str(source_path.relative_to(SOURCE)))
        continue
    target_date, nearest_event = min(
        dated_events,
        key=lambda item: (
            abs((item[0] - capture.date()).days),
            item[0] > capture.date(),
            item[0],
        ),
    )
    distance = abs((target_date - capture.date()).days)
    bucket = month_buckets.get((capture.year, capture.month))
    if distance <= 7:
        event = nearest_event
    elif bucket:
        event = bucket
        distance = 0
    elif distance <= 31:
        event = nearest_event
    elif capture.year in year_buckets:
        event = year_buckets[capture.year]
        distance = 0
    else:
        event = nearest_event
    operations.append([
        str(source_path.relative_to(SOURCE)),
        event,
        kind,
        capture.isoformat(' '),
        date_source,
        distance,
    ])

assert len(operations) == 474, len(operations)
assert len(excluded) == 18, len(excluded)

existing_names = {path.name for path in MOUNT.iterdir() if path.is_dir()}
new_events = sorted({op[1] for op in operations if op[1] not in existing_names})
payload = {'operations': operations, 'excluded': excluded, 'newEvents': new_events}
template = r'''#!/usr/bin/env python3
import argparse, collections, hashlib, json, os, shutil, subprocess, sys, uuid
from pathlib import Path

PHOTO = Path('/volume2/photo')
SOURCE_PREFIX = '170408_'
BACKUP = Path('/volume2/backup/codex-mom-phone-reorg-20260901-v2')
PAYLOAD = __PAYLOAD__


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def unique_target(directory, name, reserved):
    candidate = directory / name
    key = str(candidate).casefold()
    if not candidate.exists() and key not in reserved:
        reserved.add(key)
        return candidate, False
    stem, suffix = Path(name).stem, Path(name).suffix
    number = 1
    while True:
        candidate = directory / f'{stem}__mom_{number:02d}{suffix}'
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
    errors, plan, reserved = [], [], set()
    for rel, event, kind, capture, date_source, distance in PAYLOAD['operations']:
        src = source / rel
        dst_dir = PHOTO / event / kind
        if not src.is_file():
            errors.append(f'missing source: {src}')
            continue
        if not (PHOTO / event).is_dir() and event not in PAYLOAD['newEvents']:
            errors.append(f'missing target event: {event}')
            continue
        dst, collision = unique_target(dst_dir, src.name, reserved)
        plan.append({
            'src': str(src), 'dst': str(dst), 'event': event, 'kind': kind,
            'captureDate': capture, 'dateSource': date_source,
            'dayDistance': distance, 'collisionRenamed': collision,
        })
    excluded_present = []
    for rel in PAYLOAD['excluded']:
        path = source / rel
        if path.is_file():
            excluded_present.append(str(path))
        else:
            errors.append(f'missing excluded video: {path}')
    if len(excluded_present) != 18:
        errors.append(f'expected 18 excluded videos, found {len(excluded_present)}')
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
        'excludedVideos': 18,
        'newEvents': PAYLOAD['newEvents'],
        'collisionsRenamed': sum(op['collisionRenamed'] for op in plan),
        'directoriesToCreate': sorted({str(Path(op['dst']).parent) for op in plan if not Path(op['dst']).parent.is_dir()}),
        'groups': {
            event: {
                'total': len(ops),
                'images': sum(op['kind'] == 'photo' for op in ops),
                'videos': sum(op['kind'] == 'video' for op in ops),
                'maxDayDistance': max(op['dayDistance'] for op in ops),
                'dateRange': [min(op['captureDate'] for op in ops), max(op['captureDate'] for op in ops)],
            }
            for event, ops in sorted(groups.items())
        },
    }


def write_jsonl(stream, row):
    stream.write(json.dumps(row, ensure_ascii=False) + '\n')
    stream.flush(); os.fsync(stream.fileno())


def copy_verified(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    temp = dst.parent / f'.codex-{uuid.uuid4().hex}.tmp'
    shutil.copy2(src, temp)
    digest = sha256(src)
    if sha256(temp) != digest:
        temp.unlink(missing_ok=True)
        raise RuntimeError(f'hash mismatch: {src}')
    os.replace(temp, dst)
    return digest


def apply(plan):
    if BACKUP.exists():
        raise RuntimeError(f'journal directory already exists: {BACKUP}')
    BACKUP.mkdir(parents=True)
    (BACKUP / 'plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2))
    (BACKUP / 'excluded.json').write_text(json.dumps(PAYLOAD['excluded'], ensure_ascii=False, indent=2))
    with open(BACKUP / 'journal.jsonl', 'a', buffering=1) as journal:
        for index, op in enumerate(plan, 1):
            src, dst = Path(op['src']), Path(op['dst'])
            if not src.is_file(): raise RuntimeError(f'source disappeared: {src}')
            if dst.exists(): raise RuntimeError(f'target appeared after preflight: {dst}')
            write_jsonl(journal, {'phase': 'start', 'index': index, **op})
            digest = copy_verified(src, dst)
            src.unlink()
            if not dst.is_file() or sha256(dst) != digest or src.exists():
                raise RuntimeError(f'post-move verification failed: {src} -> {dst}')
            write_jsonl(journal, {'phase': 'done', 'index': index, 'sha256': digest, **op})
            if index % 25 == 0: print(f'completed={index}/{len(plan)}', flush=True)
    affected = sorted({str(Path(op['dst']).parent.parent) for op in plan})
    reindex = []
    for path in affected:
        result = subprocess.run(['synoindex', '-R', path], text=True, capture_output=True)
        reindex.append({'path': path, 'returncode': result.returncode, 'stderr': result.stderr[-1000:]})
    source = next(PHOTO.glob(SOURCE_PREFIX + '*'))
    index_source = subprocess.run(['synoindex', '-R', str(source)], text=True, capture_output=True)
    reindex.append({'path': str(source), 'returncode': index_source.returncode, 'stderr': index_source.stderr[-1000:]})
    result = {
        'completed': len(plan), 'images': sum(op['kind'] == 'photo' for op in plan),
        'videos': sum(op['kind'] == 'video' for op in plan), 'excludedVideosRemaining': 18,
        'reindex': reindex,
    }
    (BACKUP / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print('APPLY_OK ' + json.dumps(result, ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--apply', action='store_true'); args = parser.parse_args()
    plan, errors = build_plan(); print('PREFLIGHT ' + json.dumps(summarize(plan, errors), ensure_ascii=False), flush=True)
    if errors: sys.exit(2)
    if args.apply: apply(plan)


if __name__ == '__main__': main()
'''
OUT.write_text(template.replace('__PAYLOAD__', repr(payload)))
print(json.dumps({'output': str(OUT), 'operations': len(operations), 'excluded': len(excluded), 'newEvents': new_events}, ensure_ascii=False))
