#!/usr/bin/env python3
import argparse
import collections
import datetime as dt
import hashlib
import itertools
import json
import math
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

ROOT = Path('/Volumes/photo')
SITE = Path(__file__).resolve().parents[2] / 'tools/photo-date-review-site'
MANIFEST_PATH = SITE / 'public/timeline/timeline-items.json'
REVIEW_PATH = Path('/Users/cloudu/Downloads/photo-timeline-review (1).json')
PLAN_PATH = Path(__file__).with_name('tagged-timeline-dedup-plan.json')
BACKUP_ROOT = ROOT / '170901_备份'
OPERATION_ROOT = BACKUP_ROOT / '_operation_logs' / 'tagged-timeline-dedup-20260901-v2'
EXIFTOOL = '/opt/homebrew/bin/exiftool'

TAG_ORDER = ['报到', '开学', '国庆回家', '综办合照', '大一冬天之前', '大一冬天', '综办', '大一寒假', '大一下开学', '港西绿地', '保定实习', '19年春节']
TAG_CONFIG = {
    '报到': ('170901_报到', dt.datetime(2017, 9, 1, 8), dt.datetime(2017, 9, 3, 23, 59, 59)),
    '开学': ('170904_开学', dt.datetime(2017, 9, 4, 8), dt.datetime(2017, 10, 1, 23, 59, 59)),
    '国庆回家': ('171002_国庆回家', dt.datetime(2017, 10, 2, 8), dt.datetime(2017, 10, 8, 23, 59, 59)),
    '综办合照': ('171021_综办合照', dt.datetime(2017, 10, 21, 18), dt.datetime(2017, 10, 21, 22)),
    '大一冬天之前': ('171022_大一冬天之前', dt.datetime(2017, 10, 22, 8), dt.datetime(2017, 12, 3, 23, 59, 59)),
    '大一冬天': ('171204_大一冬天', dt.datetime(2017, 12, 4, 8), dt.datetime(2018, 1, 11, 23, 59, 59)),
    '综办': ('180112_综办', dt.datetime(2018, 1, 12, 8), dt.datetime(2018, 1, 12, 22)),
    '大一寒假': ('180113_大一寒假', dt.datetime(2018, 1, 13, 8), dt.datetime(2018, 2, 9, 23, 59, 59)),
    '大一下开学': ('180226_大一下开学', dt.datetime(2018, 2, 26, 8), dt.datetime(2018, 4, 14, 23, 59, 59)),
    '港西绿地': ('180317_港西绿地', dt.datetime(2018, 3, 17, 8), dt.datetime(2018, 3, 18, 23, 59, 59)),
    '保定实习': ('180407_保定实习', dt.datetime(2018, 4, 7, 8), dt.datetime(2018, 4, 13, 23, 59, 59)),
    '19年春节': ('190204_19年春节', dt.datetime(2019, 2, 4, 8), dt.datetime(2019, 2, 10, 23, 59, 59)),
}


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def parse_datetime(value):
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace('Z', '+00:00')).replace(tzinfo=None)
    except ValueError:
        return None


def filename_datetime(name):
    for pattern, has_time in [
        (r'(?<!\d)(20\d{2})[-_]?([01]\d)[-_]?([0-3]\d)[_\- ]?([0-2]\d)[.\-:]?([0-5]\d)[.\-:]?([0-5]\d)', True),
        (r'(?<!\d)(20\d{2})[-_]([01]\d)[-_]([0-3]\d)', False),
        (r'(?<!\d)(\d{2})([01]\d)([0-3]\d)[_\- ]([0-2]\d)([0-5]\d)([0-5]\d)', True),
    ]:
        match = re.search(pattern, name)
        if not match:
            continue
        values = list(map(int, match.groups()))
        if len(values) == 6 and values[0] < 100:
            values[0] += 2000
        if not has_time:
            values += [12, 0, 0]
        try:
            return dt.datetime(*values)
        except ValueError:
            pass
    return None


def visual_array(item):
    thumbnail = item.get('thumbnail')
    if not thumbnail:
        return None
    path = SITE / 'public' / thumbnail.lstrip('/')
    if not path.is_file():
        return None
    with Image.open(path) as image:
        return np.asarray(ImageOps.fit(image.convert('RGB'), (128, 128)), dtype=np.float32)


def visual_duplicate(left, right):
    a, b = visual_array(left), visual_array(right)
    if a is None or b is None:
        return False, None
    raw_mad = float(np.mean(np.abs(a - b)))
    gray_a = np.mean(a, axis=2); gray_b = np.mean(b, axis=2)
    edge_a = np.diff(gray_a, axis=1); edge_b = np.diff(gray_b, axis=1)
    edge_mad = float(np.mean(np.abs(edge_a - edge_b)))
    color_delta = float(np.sum(np.abs(np.mean(a, axis=(0, 1)) - np.mean(b, axis=(0, 1)))))
    accepted = raw_mad <= 12 or (edge_mad <= 10 and color_delta <= 22)
    return accepted, {'rawMad': round(raw_mad, 2), 'edgeMad': round(edge_mad, 2), 'colorDelta': round(color_delta, 2)}


class UnionFind:
    def __init__(self, values):
        self.parent = {value: value for value in values}
    def find(self, value):
        while self.parent[value] != value:
            self.parent[value] = self.parent[self.parent[value]]
            value = self.parent[value]
        return value
    def union(self, left, right):
        left, right = self.find(left), self.find(right)
        if left != right:
            self.parent[right] = left


def unique_target(directory, name, tag, reserved):
    candidate = directory / name
    key = str(candidate).casefold()
    if not candidate.exists() and key not in reserved:
        reserved.add(key); return candidate
    stem, suffix = Path(name).stem, Path(name).suffix
    number = 1
    while True:
        candidate = directory / f'{stem}__{tag}_{number:02d}{suffix}'
        key = str(candidate).casefold()
        if not candidate.exists() and key not in reserved:
            reserved.add(key); return candidate
        number += 1


manifest = json.loads(MANIFEST_PATH.read_text())
review = json.loads(REVIEW_PATH.read_text())
if review.get('sourceGeneratedAt') != manifest.get('generatedAt'):
    raise RuntimeError('review JSON does not match the current timeline manifest')
items = {item['id']: item for item in manifest['items']}
decisions = {row['id']: row for row in review.get('decisions', []) if row.get('id')}
missing_review_ids = [item_id for item_id in decisions if item_id not in items]
if missing_review_ids:
    raise RuntimeError(f'{len(missing_review_ids)} reviewed IDs are missing from the manifest')

uf = UnionFind(items)
visual_checks = []
accepted_visual_group_ids = set()
for group in manifest['duplicateGroups']:
    member_ids = [item_id for item_id in group['memberIds'] if item_id in items]
    if group['type'] == 'exact':
        for member_id in member_ids[1:]:
            uf.union(member_ids[0], member_id)
        continue
    group_accepted = False
    for left_id, right_id in itertools.combinations(member_ids, 2):
        accepted, metrics = visual_duplicate(items[left_id], items[right_id])
        visual_checks.append({'groupId': group['id'], 'left': left_id, 'right': right_id, 'accepted': accepted, 'metrics': metrics})
        if accepted:
            uf.union(left_id, right_id); group_accepted = True
    if group_accepted:
        accepted_visual_group_ids.add(group['id'])

components = collections.defaultdict(list)
for item_id in items:
    components[uf.find(item_id)].append(item_id)
components = {root: members for root, members in components.items() if len(members) > 1}


def quality_rank(item):
    area = int(item.get('width') or 0) * int(item.get('height') or 0)
    sharpness = float((item.get('visual') or {}).get('sharpness') or 0)
    return (area, sharpness, int(item.get('bytes') or 0), item.get('location') == 'library')


canonical_by_member = {}
component_rows = []
for component_index, member_ids in enumerate(components.values(), 1):
    members = [items[item_id] for item_id in member_ids]
    explicit_keep = [item for item in members if decisions.get(item['id'], {}).get('duplicateAction') == 'keep']
    candidates = explicit_keep or [item for item in members if decisions.get(item['id'], {}).get('duplicateAction') != 'backup'] or members
    library_candidates = [item for item in candidates if item['location'] == 'library']
    top_all = max(candidates, key=quality_rank)
    if library_candidates:
        top_library = max(library_candidates, key=quality_rank)
        all_area = quality_rank(top_all)[0]; library_area = quality_rank(top_library)[0]
        canonical = top_all if top_all['location'] != 'library' and all_area > library_area * 1.1 else top_library
    else:
        canonical = top_all
    for item_id in member_ids:
        canonical_by_member[item_id] = canonical['id']
    component_rows.append({'id': f'dup-{component_index:04d}', 'members': member_ids, 'canonicalId': canonical['id'], 'explicitKeepIds': [item['id'] for item in explicit_keep]})

tags_by_canonical = collections.defaultdict(set)
for item_id, decision in decisions.items():
    for tag in decision.get('tags') or []:
        if tag in TAG_CONFIG:
            tags_by_canonical[canonical_by_member.get(item_id, item_id)].add(tag)


def choose_tag(item, tags):
    capture = parse_datetime(item.get('captureDate'))
    containing = [tag for tag in tags if capture and TAG_CONFIG[tag][1] <= capture <= TAG_CONFIG[tag][2]]
    if containing:
        return min(containing, key=TAG_ORDER.index)
    if capture:
        return min(tags, key=lambda tag: abs((capture - (TAG_CONFIG[tag][1] + (TAG_CONFIG[tag][2] - TAG_CONFIG[tag][1]) / 2)).total_seconds()))
    return min(tags, key=TAG_ORDER.index)


tag_by_canonical = {item_id: choose_tag(items[item_id], tags) for item_id, tags in tags_by_canonical.items()}
used_seconds = collections.defaultdict(set)


def corrected_timestamp(item, tag):
    _, start, end = TAG_CONFIG[tag]
    current = parse_datetime(item.get('captureDate'))
    if current and start <= current <= end:
        candidate = current.replace(microsecond=0)
        reason = 'kept-in-range-capture'
    else:
        named = filename_datetime(item['filename'])
        if named and start.date() <= named.date() <= end.date():
            candidate = named.replace(microsecond=0)
            reason = 'used-filename-date'
        else:
            span = max(1, int((end - start).total_seconds()))
            offset = int(hashlib.sha256(item['id'].encode()).hexdigest()[:12], 16) % span
            candidate = (start + dt.timedelta(seconds=offset)).replace(microsecond=0)
            reason = 'assigned-inside-tag-window'
    epoch = int(candidate.timestamp())
    while epoch in used_seconds[tag]:
        candidate += dt.timedelta(seconds=1); epoch += 1
        if candidate > end:
            candidate = start + dt.timedelta(seconds=len(used_seconds[tag])); epoch = int(candidate.timestamp())
    used_seconds[tag].add(epoch)
    return candidate, reason


reserved = set()
duplicate_moves = []
for component in component_rows:
    canonical_id = component['canonicalId']
    for item_id in component['members']:
        if item_id == canonical_id:
            continue
        item = items[item_id]
        if item['location'] == 'backup':
            continue
        src = ROOT / item['relativePath']
        destination_dir = BACKUP_ROOT / 'duplicates' / item['currentFolder']
        dst = unique_target(destination_dir, src.name, 'duplicate', reserved)
        duplicate_moves.append({'id': item_id, 'src': str(src), 'dst': str(dst), 'canonicalId': canonical_id, 'reason': 'lower-quality-duplicate'})

classification_moves = []
metadata_edits = []
metadata_backups = []
for canonical_id, tag in sorted(tag_by_canonical.items(), key=lambda row: (TAG_ORDER.index(row[1]), row[0])):
    item = items[canonical_id]
    src = ROOT / item['relativePath']
    folder_name, _, _ = TAG_CONFIG[tag]
    subdir = 'video' if item['kind'] == 'video' else 'photo'
    destination_dir = ROOT / folder_name / subdir
    dst = unique_target(destination_dir, src.name, 'tagged', reserved)
    timestamp, reason = corrected_timestamp(item, tag)
    classification_moves.append({'id': canonical_id, 'tag': tag, 'src': str(src), 'dst': str(dst), 'sourceLocation': item['location']})
    metadata_backup_dir = BACKUP_ROOT / 'metadata-originals' / folder_name
    metadata_backup = unique_target(metadata_backup_dir, dst.name, 'original', reserved)
    metadata_backups.append({'id': canonical_id, 'srcAfterMove': str(dst), 'dst': str(metadata_backup)})
    metadata_edits.append({'id': canonical_id, 'pathAfterMove': str(dst), 'timestamp': timestamp.strftime('%Y:%m:%d %H:%M:%S'), 'isoTimestamp': timestamp.isoformat(' '), 'tag': tag, 'reason': reason, 'kind': item['kind']})

path_errors = []
for row in duplicate_moves + classification_moves:
    if not Path(row['src']).is_file():
        path_errors.append(row['src'])

plan = {
    'version': 1,
    'sourceReview': str(REVIEW_PATH),
    'tagOrder': TAG_ORDER,
    'tagFolders': {tag: {'folder': TAG_CONFIG[tag][0], 'start': TAG_CONFIG[tag][1].isoformat(' '), 'end': TAG_CONFIG[tag][2].isoformat(' ')} for tag in TAG_ORDER},
    'visualChecks': visual_checks,
    'acceptedVisualGroupIds': sorted(accepted_visual_group_ids),
    'components': component_rows,
    'duplicateMoves': duplicate_moves,
    'classificationMoves': classification_moves,
    'metadataBackups': metadata_backups,
    'metadataEdits': metadata_edits,
    'pathErrors': path_errors,
}
PLAN_PATH.write_text(json.dumps(plan, ensure_ascii=False, indent=2))


def summary():
    return {
        'reviewed': len(decisions),
        'taggedRaw': sum(bool(row.get('tags')) for row in decisions.values()),
        'classifiedBestVersions': len(classification_moves),
        'classifiedByTag': dict(collections.Counter(row['tag'] for row in classification_moves)),
        'duplicateComponents': len(component_rows),
        'lowerQualityLibraryMoves': len(duplicate_moves),
        'exactGroups': sum(group['type'] == 'exact' for group in manifest['duplicateGroups']),
        'visualGroupsTotal': sum(group['type'] == 'visual' for group in manifest['duplicateGroups']),
        'visualGroupsAccepted': len(accepted_visual_group_ids),
        'visualPairsAccepted': sum(check['accepted'] for check in visual_checks),
        'visualPairsRejected': sum(not check['accepted'] for check in visual_checks),
        'metadataEdits': len(metadata_edits),
        'newTagFolders': [TAG_CONFIG[tag][0] for tag in TAG_ORDER],
        'pathErrors': path_errors,
    }


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


def move_verified(src, dst):
    digest = copy_verified(src, dst)
    src.unlink()
    if not dst.is_file() or sha256(dst) != digest or src.exists():
        raise RuntimeError(f'move verification failed: {src} -> {dst}')
    return digest


def exiftool_update(row):
    path = row['pathAfterMove']; timestamp = row['timestamp']
    fields = [f'-DateTimeOriginal={timestamp}', f'-CreateDate={timestamp}', f'-ModifyDate={timestamp}', f'-FileModifyDate={timestamp}']
    if row['kind'] == 'video':
        fields += [f'-MediaCreateDate={timestamp}', f'-TrackCreateDate={timestamp}']
    command = [EXIFTOOL, '-overwrite_original', '-P', *fields, path]
    result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f'exiftool failed for {path}: {result.stderr}')
    check = json.loads(subprocess.check_output([EXIFTOOL, '-json', '-DateTimeOriginal', '-CreateDate', '-MediaCreateDate', '-TrackCreateDate', '-FileModifyDate', path], text=True))[0]
    create = check.get('CreateDate') or check.get('MediaCreateDate')
    if create and not str(create).startswith(timestamp):
        raise RuntimeError(f'metadata verification failed for {path}: {check}')
    return check


def apply_plan():
    if path_errors:
        raise RuntimeError(f'preflight has {len(path_errors)} missing paths')
    if OPERATION_ROOT.exists():
        raise RuntimeError(f'operation journal already exists: {OPERATION_ROOT}')
    OPERATION_ROOT.mkdir(parents=True)
    (OPERATION_ROOT / 'plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2))
    journal_path = OPERATION_ROOT / 'journal.jsonl'
    current_paths = {item_id: ROOT / item['relativePath'] for item_id, item in items.items()}
    with open(journal_path, 'a', buffering=1) as journal:
        def log(row):
            journal.write(json.dumps(row, ensure_ascii=False) + '\n'); journal.flush(); os.fsync(journal.fileno())
        for index, row in enumerate(duplicate_moves, 1):
            src, dst = Path(row['src']), Path(row['dst'])
            log({'phase': 'duplicate-start', 'index': index, **row})
            digest = move_verified(src, dst)
            current_paths[row['id']] = dst
            log({'phase': 'duplicate-done', 'index': index, 'sha256': digest, **row})
        for index, row in enumerate(classification_moves, 1):
            src = current_paths[row['id']]; dst = Path(row['dst'])
            if src != Path(row['src']):
                raise RuntimeError(f'canonical path changed unexpectedly: {row["id"]}')
            log({'phase': 'classification-start', 'index': index, **row})
            digest = move_verified(src, dst)
            current_paths[row['id']] = dst
            log({'phase': 'classification-done', 'index': index, 'sha256': digest, **row})
        for index, row in enumerate(metadata_backups, 1):
            src = current_paths[row['id']]; dst = Path(row['dst'])
            log({'phase': 'metadata-backup-start', 'index': index, **row})
            digest = copy_verified(src, dst)
            log({'phase': 'metadata-backup-done', 'index': index, 'sha256': digest, **row})
        for index, row in enumerate(metadata_edits, 1):
            path = current_paths[row['id']]
            actual = {**row, 'pathAfterMove': str(path)}
            log({'phase': 'metadata-start', 'index': index, **actual})
            check = exiftool_update(actual)
            log({'phase': 'metadata-done', 'index': index, 'sha256': sha256(path), 'check': check, **actual})
            if index % 50 == 0:
                print(f'metadata={index}/{len(metadata_edits)}', flush=True)
    result = {
        'summary': summary(),
        'duplicateDestMissing': sum(not Path(row['dst']).is_file() for row in duplicate_moves),
        'classifiedDestMissing': sum(not Path(row['dst']).is_file() for row in classification_moves),
        'metadataBackupMissing': sum(not Path(row['dst']).is_file() for row in metadata_backups),
        'sourceStillPresent': sum(Path(row['src']).exists() for row in duplicate_moves + classification_moves),
    }
    (OPERATION_ROOT / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print('APPLY_OK ' + json.dumps(result, ensure_ascii=False), flush=True)


parser = argparse.ArgumentParser()
parser.add_argument('--apply', action='store_true')
args = parser.parse_args()
print('PREFLIGHT ' + json.dumps(summary(), ensure_ascii=False), flush=True)
if path_errors:
    sys.exit(2)
if args.apply:
    apply_plan()
