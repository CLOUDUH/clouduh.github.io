#!/usr/bin/env python3
import collections
import concurrent.futures
import datetime as dt
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

ROOT = Path('/Volumes/photo')
SITE = Path(__file__).resolve().parents[2] / 'tools/photo-date-review-site'
OUT_DIR = SITE / 'public/timeline'
THUMB_DIR = OUT_DIR / 'thumbs'
MANIFEST = OUT_DIR / 'timeline-items.json'
SELECTION_MANIFEST = SITE / 'public/selection/selection-items.json'
IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.heic', '.webp', '.gif', '.dng', '.tif', '.tiff'}
VIDEO_EXTS = {'.mp4', '.mov'}
ALL_EXTS = IMAGE_EXTS | VIDEO_EXTS
CLASSIFIED_RELATIVE_PATHS = set()
first_plan = Path(__file__).with_name('tagged-timeline-dedup-plan.json')
if first_plan.is_file():
    for row in json.loads(first_plan.read_text()).get('classificationMoves', []):
        value = row.get('dst', '')
        if value.startswith('/Volumes/photo/'):
            CLASSIFIED_RELATIVE_PATHS.add(value.removeprefix('/Volumes/photo/'))
second_plan = Path(__file__).with_name('round2-tag-classification-plan.json')
if second_plan.is_file():
    data = json.loads(second_plan.read_text())
    for row in data.get('moves', []):
        value = row.get('dst', '')
        if value.startswith('/Volumes/photo/'):
            CLASSIFIED_RELATIVE_PATHS.add(value.removeprefix('/Volumes/photo/'))
    for row in data.get('already', []):
        value = row.get('path', '')
        if value.startswith('/Volumes/photo/'):
            CLASSIFIED_RELATIVE_PATHS.add(value.removeprefix('/Volumes/photo/'))
third_plan = Path(__file__).with_name('round3-tag-classification-plan.json')
if third_plan.is_file():
    data = json.loads(third_plan.read_text())
    for row in data.get('moves', []):
        value = row.get('dst', '')
        if value.startswith('/Volumes/photo/'):
            CLASSIFIED_RELATIVE_PATHS.add(value.removeprefix('/Volumes/photo/'))
    for row in data.get('already', []):
        value = row.get('path', '')
        if value.startswith('/Volumes/photo/'):
            CLASSIFIED_RELATIVE_PATHS.add(value.removeprefix('/Volumes/photo/'))


def parse_prefix(name):
    match = re.match(r'^(\d{6})_', name)
    if not match:
        return None
    value = match.group(1)
    year, month, day = 2000 + int(value[:2]), int(value[2:4]), int(value[4:6])
    try:
        return dt.date(year, month or 1, day or 1)
    except ValueError:
        return None


def parse_datetime(value):
    match = re.match(r'^(\d{4})[:\-](\d{2})[:\-](\d{2})[ T](\d{2}):(\d{2}):(\d{2})', str(value or ''))
    if not match:
        return None
    try:
        return dt.datetime(*map(int, match.groups()))
    except ValueError:
        return None


def filename_datetime(name):
    for pattern, short_year in [
        (r'(?<!\d)(20\d{2})[-_]?([01]\d)[-_]?([0-3]\d)[_\- ]?([0-2]\d)[.\-:]?([0-5]\d)[.\-:]?([0-5]\d)', False),
        (r'(?<!\d)(\d{2})([01]\d)([0-3]\d)[_\- ]([0-2]\d)([0-5]\d)([0-5]\d)', True),
    ]:
        match = re.search(pattern, name)
        if match:
            values = list(map(int, match.groups()))
            if short_year:
                values[0] += 2000
            try:
                return dt.datetime(*values)
            except ValueError:
                pass
    return None


def stable_id(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()[:20]


def sha256(path):
    for attempt in range(3):
        try:
            digest = hashlib.sha256()
            with open(path, 'rb') as stream:
                for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
                    digest.update(block)
            return digest.hexdigest()
        except OSError:
            if attempt == 2:
                raise
            time.sleep(.25 * (attempt + 1))


event_dirs = []
for path in ROOT.iterdir():
    date = parse_prefix(path.name) if path.is_dir() else None
    match = re.match(r'^(\d{6})_', path.name)
    if date and match and 170901 <= int(match.group(1)) <= 190613 and path.name != '170901_备份':
        event_dirs.append((date, path))
event_dirs.sort()
event_names = [path.name for _, path in event_dirs]

records = []
scan_dirs = []
for _, event in event_dirs:
    for subdir in ('photo', 'video'):
        directory = event / subdir
        if not directory.is_dir():
            continue
        scan_dirs.append(directory)
        for path in directory.rglob('*'):
            if path.is_file() and '@eaDir' not in path.parts and path.suffix.lower() in ALL_EXTS:
                relative_path = str(path.relative_to(ROOT))
                records.append({'path': path, 'relativePath': relative_path, 'currentFolder': event.name, 'location': 'library', 'subdir': subdir, 'preclassified': relative_path in CLASSIFIED_RELATIVE_PATHS})

backup = ROOT / '170901_备份'
if backup.is_dir():
    scan_dirs.append(backup)
    for path in backup.rglob('*'):
        if not path.is_file() or '@eaDir' in path.parts or path.suffix.lower() not in IMAGE_EXTS:
            continue
        rel = path.relative_to(backup)
        if any(part in {'_operation_logs', 'metadata-originals', 'duplicates'} for part in rel.parts):
            continue
        category = rel.parts[0] if len(rel.parts) > 1 else '未分类'
        records.append({'path': path, 'relativePath': str(path.relative_to(ROOT)), 'currentFolder': category, 'location': 'backup', 'subdir': 'backup', 'preclassified': False})

unassigned = ROOT / '170408_妈妈手机照片' / 'video'
if unassigned.is_dir():
    scan_dirs.append(unassigned)
    for path in unassigned.rglob('*'):
        if path.is_file() and '@eaDir' not in path.parts and path.suffix.lower() in VIDEO_EXTS:
            records.append({'path': path, 'relativePath': str(path.relative_to(ROOT)), 'currentFolder': '待确认视频', 'location': 'unassigned', 'subdir': 'video', 'preclassified': False})

record_by_source = {str(record['path']): record for record in records}
command = ['exiftool', '-json', '-n']
for ext in sorted(ALL_EXTS):
    command += ['-ext', ext.lstrip('.')]
for field in ['DateTimeOriginal', 'CreateDate', 'MediaCreateDate', 'TrackCreateDate', 'FileModifyDate', 'ImageWidth', 'ImageHeight', 'FileTypeExtension', 'MIMEType']:
    command.append('-' + field)
command += [str(path) for path in scan_dirs]
metadata = json.loads(subprocess.check_output(command, text=True))
metadata_by_source = {str(Path(row['SourceFile'])): row for row in metadata}

OUT_DIR.mkdir(parents=True, exist_ok=True)
THUMB_DIR.mkdir(parents=True, exist_ok=True)
selection_thumbs = {}
if SELECTION_MANIFEST.is_file():
    selection_data = json.loads(SELECTION_MANIFEST.read_text())
    for folder in selection_data.get('folders', []):
        if folder.get('event') != '170408_妈妈手机照片':
            continue
        for photo in folder.get('photos', []):
            thumb = photo.get('thumbnail')
            if thumb:
                selection_thumbs[photo.get('filename')] = SITE / 'public' / thumb.lstrip('/')


def expected_folder(capture):
    if not capture:
        return None
    date = capture.date()
    prior = [entry for entry in event_dirs if entry[0] <= date]
    return (prior[-1] if prior else event_dirs[0])[1].name


def create_thumbnail(record):
    path = record['path']
    if record.get('preclassified'):
        return None, None
    item_id = stable_id(record['location'] + ':' + record['relativePath'])
    output = THUMB_DIR / f'{item_id}.jpg'
    heic_quicklook = Path('/tmp/codex-timeline-heic-20260901') / f'{path.name}.png'
    old_thumb = selection_thumbs.get(path.name) if path.suffix.lower() == '.heic' else None
    if path.suffix.lower() == '.heic' and heic_quicklook.is_file():
        with Image.open(heic_quicklook) as image:
            image = ImageOps.exif_transpose(image).convert('RGB'); image.thumbnail((520, 520)); image.save(output, 'JPEG', quality=82, optimize=True)
    elif old_thumb and old_thumb.is_file():
        shutil.copy2(old_thumb, output)
    elif output.is_file():
        pass
    elif path.suffix.lower() in VIDEO_EXTS:
        quicklook = Path('/tmp/codex-mom-video-thumbs-20260901') / f'{path.name}.png'
        if quicklook.is_file():
            with Image.open(quicklook) as image:
                image = ImageOps.exif_transpose(image).convert('RGB'); image.thumbnail((520, 520)); image.save(output, 'JPEG', quality=82, optimize=True)
        else:
            return None, None
    elif path.suffix.lower() == '.heic':
        result = subprocess.run(['sips', '-s', 'format', 'jpeg', '-Z', '520', str(path), '--out', str(output)], capture_output=True, text=True)
        if result.returncode != 0 or not output.is_file():
            return None, None
    else:
        try:
            with Image.open(path) as image:
                image = ImageOps.exif_transpose(image).convert('RGB'); image.thumbnail((520, 520)); image.save(output, 'JPEG', quality=82, optimize=True)
        except Exception:
            return None, None
    try:
        with Image.open(output) as image:
            rgb = image.convert('RGB')
            gray = np.asarray(rgb.convert('L').resize((9, 8)), dtype=np.int16)
            dhash = 0
            for bit in (gray[:, 1:] > gray[:, :-1]).flatten():
                dhash = (dhash << 1) | int(bit)
            small = np.asarray(rgb.convert('L').resize((8, 8)), dtype=np.float32)
            ahash = 0
            for bit in (small > small.mean()).flatten():
                ahash = (ahash << 1) | int(bit)
            color = tuple(int(value) for value in np.asarray(rgb.resize((1, 1)))[0, 0])
            sharp = float(np.var(np.diff(np.asarray(rgb.convert('L').resize((96, 96)), dtype=np.float32), axis=0)))
        return '/timeline/thumbs/' + output.name, {'dhash': dhash, 'ahash': ahash, 'color': color, 'sharpness': round(sharp, 2)}
    except Exception:
        return '/timeline/thumbs/' + output.name, None


items = []
for index, record in enumerate(records, 1):
    path = record['path']; row = metadata_by_source.get(str(path), {})
    is_video = path.suffix.lower() in VIDEO_EXTS
    dto = parse_datetime(row.get('DateTimeOriginal'))
    create = parse_datetime(row.get('CreateDate'))
    media = parse_datetime(row.get('MediaCreateDate')) or parse_datetime(row.get('TrackCreateDate'))
    modified = parse_datetime(row.get('FileModifyDate'))
    named = filename_datetime(path.name)
    candidates = [('MediaCreateDate', media), ('CreateDate', create), ('filename', named), ('FileModifyDate', modified)] if is_video else [('DateTimeOriginal', dto), ('CreateDate', create), ('filename', named), ('FileModifyDate', modified)]
    date_source, capture = next(((source, value) for source, value in candidates if value), ('none', None))
    bulk_anomaly = record['location'] == 'unassigned' and capture and capture.date() == dt.date(2026, 4, 8)
    if bulk_anomaly:
        metadata_status = 'bulk-date-anomaly'
    elif not capture:
        metadata_status = 'missing'
    elif dto and create and abs((dto - create).total_seconds()) > 86400:
        metadata_status = 'capture-create-conflict'
    elif date_source in {'FileModifyDate', 'filename'}:
        metadata_status = 'fallback-date'
    else:
        metadata_status = 'consistent'
    thumb, visual = create_thumbnail(record)
    width = int(row.get('ImageWidth') or 0); height = int(row.get('ImageHeight') or 0)
    item = {
        'id': stable_id(record['location'] + ':' + record['relativePath']),
        'relativePath': record['relativePath'], 'filename': path.name,
        'currentFolder': record['currentFolder'], 'location': record['location'], 'subdir': record['subdir'],
        'preclassified': bool(record.get('preclassified')),
        'kind': 'video' if is_video else 'image', 'format': path.suffix.lower().lstrip('.'),
        'bytes': path.stat().st_size, 'width': width, 'height': height,
        'captureDate': capture.isoformat(' ') if capture else None,
        'createDate': create.isoformat(' ') if create else None,
        'fileModifyDate': modified.isoformat(' ') if modified else None,
        'dateSource': date_source, 'metadataStatus': metadata_status,
        'expectedFolder': None if bulk_anomaly else expected_folder(capture),
        'timelineMismatch': bool(record['location'] == 'library' and capture and expected_folder(capture) != record['currentFolder']),
        'thumbnail': thumb, 'visual': visual,
    }
    items.append(item)
    if index % 200 == 0:
        print(f'thumbnails={index}/{len(records)}', flush=True)


def hash_item(item):
    return item['id'], sha256(ROOT / item['relativePath'])


item_by_id = {item['id']: item for item in items}
for index, item in enumerate(items, 1):
    if item.get('preclassified'):
        item['contentHash'] = 'preclassified-' + item['id']
        continue
    hash_path = ROOT / item['relativePath']
    try:
        item['contentHash'] = sha256(hash_path)
    except OSError:
        fallback = subprocess.run(['/usr/bin/shasum', '-a', '256', str(hash_path)], capture_output=True, text=True)
        if fallback.returncode == 0 and fallback.stdout:
            item['contentHash'] = fallback.stdout.split()[0]
        else:
            item['contentHash'] = 'unreadable-' + item['id']
            item['hashError'] = True
            print(f'hash_error={item["relativePath"]}', flush=True)
    if index % 250 == 0:
        print(f'hashes={index}/{len(items)}', flush=True)

exact_groups = []
hash_groups = collections.defaultdict(list)
for item in items:
    hash_groups[item['contentHash']].append(item)
for digest, members in hash_groups.items():
    if len(members) < 2:
        continue
    locations = {member['location'] for member in members}
    exact_groups.append({
        'id': 'exact-' + digest[:16], 'type': 'exact', 'memberIds': [member['id'] for member in members],
        'recommendedId': max(members, key=lambda member: (member['location'] == 'library', member['width'] * member['height'], member['bytes']))['id'],
        'intentionalBackup': 'library' in locations and 'backup' in locations,
    })

visual_items = [item for item in items if item['kind'] == 'image' and item['visual']]
parent = {item['id']: item['id'] for item in visual_items}


def find(value):
    while parent[value] != value:
        parent[value] = parent[parent[value]]; value = parent[value]
    return value


def union(left, right):
    left, right = find(left), find(right)
    if left != right:
        parent[right] = left


for i, left in enumerate(visual_items):
    lv = left['visual']; lar = left['width'] / left['height'] if left['height'] else 0
    for right in visual_items[i + 1:]:
        if left['contentHash'] == right['contentHash']:
            continue
        rar = right['width'] / right['height'] if right['height'] else 0
        if lar and rar and abs(lar - rar) / max(lar, rar) > .025:
            continue
        rv = right['visual']
        if (lv['dhash'] ^ rv['dhash']).bit_count() > 4 or (lv['ahash'] ^ rv['ahash']).bit_count() > 6:
            continue
        if sum(abs(a - b) for a, b in zip(lv['color'], rv['color'])) > 35:
            continue
        union(left['id'], right['id'])

near_clusters = collections.defaultdict(list)
for item in visual_items:
    near_clusters[find(item['id'])].append(item)
visual_groups = []
for root_id, members in near_clusters.items():
    if len(members) < 2 or len({member['contentHash'] for member in members}) < 2:
        continue
    recommended = max(members, key=lambda member: (member['width'] * member['height'], member['visual']['sharpness'], member['location'] == 'library', member['bytes']))
    visual_groups.append({
        'id': 'visual-' + stable_id('|'.join(sorted(member['id'] for member in members))),
        'type': 'visual', 'memberIds': [member['id'] for member in members], 'recommendedId': recommended['id'],
        'intentionalBackup': False,
    })

for group in exact_groups + visual_groups:
    for member_id in group['memberIds']:
        item_by_id[member_id].setdefault('duplicateGroupIds', []).append(group['id'])

stats = {
    'items': len(items), 'libraryItems': sum(item['location'] == 'library' for item in items),
    'backupItems': sum(item['location'] == 'backup' for item in items),
    'unassignedItems': sum(item['location'] == 'unassigned' for item in items),
    'timelineMismatches': sum(item['timelineMismatch'] for item in items),
    'metadataIssues': sum(item['metadataStatus'] != 'consistent' for item in items),
    'exactDuplicateGroups': len(exact_groups), 'visualDuplicateGroups': len(visual_groups),
}
manifest = {
    'version': 1, 'generatedAt': dt.datetime.now().astimezone().isoformat(),
    'range': {'from': '170901', 'to': '190613'}, 'stats': stats,
    'folders': [{'name': path.name, 'startDate': date.isoformat()} for date, path in event_dirs],
    'items': items, 'duplicateGroups': exact_groups + visual_groups,
}
MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, separators=(',', ':')))
print(json.dumps(stats, ensure_ascii=False), flush=True)
