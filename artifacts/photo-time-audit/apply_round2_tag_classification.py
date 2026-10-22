#!/usr/bin/env python3
import argparse
import collections
import datetime as dt
import hashlib
import json
import math
import os
import shutil
import sys
import uuid
from pathlib import Path

ROOT = Path('/Volumes/photo')
SITE = Path(__file__).resolve().parents[2] / 'tools/photo-date-review-site'
MANIFEST_PATH = SITE / 'public/timeline/timeline-items.json'
REVIEW_PATH = Path('/Users/cloudu/Downloads/photo-timeline-review (2).json')
PLAN_PATH = Path(__file__).with_name('round2-tag-classification-plan.json')
REGISTRY_PATH = Path(__file__).with_name('classified-event-folders.json')
BACKUP_ROOT = ROOT / '170901_备份'
OPERATION_ROOT = BACKUP_ROOT / '_operation_logs' / 'tagged-classification-20260901-round2'

TAG_FOLDERS = {
    '综办合照': '171021_综办合照', '报到': '170901_报到', '开学': '170904_开学',
    '综办': '180112_综办', '国庆回家': '171002_国庆回家',
    '大一冬天之前': '171022_大一冬天之前', '大一冬天': '171204_大一冬天',
    '大一寒假': '180113_大一寒假', '19年春节': '190204_19年春节',
    '大一下开学': '180226_大一下开学', '港西绿地': '180317_港西绿地',
    '保定实习': '180407_保定实习', '北京': '180428_北京',
    '大一暑假之前': '180428_大一暑假之前', '秦马志愿者': '180512_秦马志愿者',
    '进入暑期': '180530_进入暑期', '大一暑假': '180700_大一暑假',
    '高中': '180725_高中', '大二开学': '180906_大二开学',
    '大二国庆': '180930_大二国庆', '珠海参会': '181126_珠海参会',
    '19比赛': '181116_19比赛', '大二深冬': '181203_大二深冬',
    '大二寒假': '190131_大二寒假', '大二暑假之前': '190217_大二暑假之前',
    '大二下开学': '190302_大二下开学', '长春吉大': '190316_长春吉大',
    '大三深冬': '190417_大三深冬', '大二劳动节': '190430_大二劳动节',
    '大二暑假': '190700_大二暑假', '大三上开学': '190900_大三上开学',
    '大三比赛后': '191026_大三比赛后', '大三下疫情返校': '200911_大三下疫情返校',
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


def unique_target(directory, name, reserved):
    candidate = directory / name
    key = str(candidate).casefold()
    if not candidate.exists() and key not in reserved:
        reserved.add(key); return candidate, False
    stem, suffix = Path(name).stem, Path(name).suffix
    number = 1
    while True:
        candidate = directory / f'{stem}__tagged_{number:02d}{suffix}'
        key = str(candidate).casefold()
        if not candidate.exists() and key not in reserved:
            reserved.add(key); return candidate, True
        number += 1


manifest = json.loads(MANIFEST_PATH.read_text())
review = json.loads(REVIEW_PATH.read_text())
if review.get('sourceGeneratedAt') != manifest.get('generatedAt'):
    raise RuntimeError('review JSON does not match the current timeline manifest')
items = {item['id']: item for item in manifest['items']}
decisions = {row['id']: row for row in review.get('decisions', []) if row.get('id')}
missing_ids = [item_id for item_id in decisions if item_id not in items]
if missing_ids:
    raise RuntimeError(f'{len(missing_ids)} reviewed IDs are missing from the manifest')

hash_groups = collections.defaultdict(list)
for item in items.values():
    hash_groups[item.get('contentHash')].append(item)


def canonical_item(item):
    if item['location'] != 'backup':
        return item
    library = [candidate for candidate in hash_groups[item.get('contentHash')] if candidate['location'] == 'library']
    return max(library, key=lambda value: (value.get('preclassified', False), value.get('width', 0) * value.get('height', 0), value.get('bytes', 0))) if library else item


tagged_assignments = {}
tag_dates = collections.defaultdict(list)
tag_folders = collections.defaultdict(collections.Counter)
for item_id, decision in decisions.items():
    tags = [tag for tag in (decision.get('tags') or []) if tag in TAG_FOLDERS]
    if not tags:
        continue
    source_item = items[item_id]
    item = canonical_item(source_item)
    tag = tags[0]
    tagged_assignments[item['id']] = {'id': item['id'], 'tag': tag, 'reason': 'user-tagged', 'sourceDecisionId': item_id}
    capture = parse_datetime(source_item.get('captureDate'))
    if capture:
        tag_dates[tag].append(capture)
    tag_folders[tag][source_item['currentFolder']] += 1


def percentile(values, fraction):
    values = sorted(values)
    return values[min(len(values) - 1, max(0, round((len(values) - 1) * fraction)))]


tag_stats = {}
for tag, dates in tag_dates.items():
    if not dates:
        continue
    folder_threshold = max(5, math.ceil(len(dates) * .20))
    tag_stats[tag] = {
        'low': percentile(dates, .10), 'median': percentile(dates, .50), 'high': percentile(dates, .90),
        'dominantFolders': [name for name, count in tag_folders[tag].most_common() if count >= folder_threshold],
    }

auto_assignments = {}
unmatched_ids = []
for item in items.values():
    if item['id'] in tagged_assignments or item['location'] != 'library' or item.get('preclassified'):
        continue
    capture = parse_datetime(item.get('captureDate'))
    if not capture:
        unmatched_ids.append(item['id']); continue
    candidates = []
    for tag, stats in tag_stats.items():
        if len(tag_dates[tag]) < 3:
            continue
        low = stats['low'] - dt.timedelta(days=2); high = stats['high'] + dt.timedelta(days=2)
        if not low <= capture <= high:
            continue
        score = abs((capture - stats['median']).total_seconds()) / 86400
        if score > 45:
            continue
        in_dominant_folder = item['currentFolder'] in stats['dominantFolders']
        if not in_dominant_folder and score > 5:
            continue
        if in_dominant_folder:
            score = max(0, score - 2)
        candidates.append((score, tag))
    candidates.sort()
    if candidates and (len(candidates) == 1 or candidates[1][0] - candidates[0][0] >= 2):
        auto_assignments[item['id']] = {'id': item['id'], 'tag': candidates[0][1], 'reason': 'high-confidence-time-match', 'scoreDays': round(candidates[0][0], 2)}
    else:
        unmatched_ids.append(item['id'])

mom_assignments = {}
for item in items.values():
    if item['location'] == 'unassigned' and item['relativePath'].startswith('170408_妈妈手机照片/'):
        mom_assignments[item['id']] = {'id': item['id'], 'tag': None, 'folder': '260424_忙碌四月', 'reason': 'mom-phone-default-date'}

assignments = list(tagged_assignments.values()) + list(auto_assignments.values()) + list(mom_assignments.values())
reserved = set()
moves = []
already = []
for assignment in assignments:
    item = items[assignment['id']]
    src = ROOT / item['relativePath']
    folder = assignment.get('folder') or TAG_FOLDERS[assignment['tag']]
    destination_dir = ROOT / folder / 'photo'
    if src.parent == destination_dir:
        already.append({'id': item['id'], 'path': str(src), **assignment}); continue
    dst, collision = unique_target(destination_dir, src.name, reserved)
    moves.append({'id': item['id'], 'src': str(src), 'dst': str(dst), 'folder': folder, 'collisionRenamed': collision, **assignment})

path_errors = [row['src'] for row in moves if not Path(row['src']).is_file()]
active_tag_folders = sorted({TAG_FOLDERS[row['tag']] for row in tagged_assignments.values() if row.get('tag')})
registry = sorted(set(active_tag_folders) | {item['currentFolder'] for item in items.values() if item.get('preclassified')})
plan = {
    'version': 1, 'sourceReview': str(REVIEW_PATH), 'tagFolders': TAG_FOLDERS,
    'tagStats': {tag: {key: (value.isoformat(' ') if isinstance(value, dt.datetime) else value) for key, value in stats.items()} for tag, stats in tag_stats.items()},
    'taggedAssignments': list(tagged_assignments.values()), 'autoAssignments': list(auto_assignments.values()),
    'momAssignments': list(mom_assignments.values()), 'moves': moves, 'already': already,
    'unmatchedIds': unmatched_ids, 'registry': registry, 'pathErrors': path_errors,
}
PLAN_PATH.write_text(json.dumps(plan, ensure_ascii=False, indent=2))


def summary():
    return {
        'reviewed': len(decisions), 'userTagged': len(tagged_assignments),
        'userTaggedByTag': dict(collections.Counter(row['tag'] for row in tagged_assignments.values())),
        'autoMatched': len(auto_assignments), 'autoMatchedByTag': dict(collections.Counter(row['tag'] for row in auto_assignments.values())),
        'momDefaultDate': len(mom_assignments), 'moves': len(moves), 'alreadyInTarget': len(already),
        'collisionRenamed': sum(row['collisionRenamed'] for row in moves), 'leftForNextRound': len(unmatched_ids),
        'pathErrors': path_errors,
    }


def copy_verified(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    temp = dst.parent / f'.codex-{uuid.uuid4().hex}.tmp'
    shutil.copy2(src, temp)
    digest = sha256(src)
    if sha256(temp) != digest:
        temp.unlink(missing_ok=True); raise RuntimeError(f'hash mismatch: {src}')
    os.replace(temp, dst); return digest


def move_verified(src, dst):
    digest = copy_verified(src, dst); src.unlink()
    if not dst.is_file() or sha256(dst) != digest or src.exists():
        raise RuntimeError(f'move verification failed: {src} -> {dst}')
    return digest


def apply_plan():
    if path_errors:
        raise RuntimeError(f'preflight has {len(path_errors)} missing paths')
    if OPERATION_ROOT.exists():
        raise RuntimeError(f'operation journal already exists: {OPERATION_ROOT}')
    OPERATION_ROOT.mkdir(parents=True)
    (OPERATION_ROOT / 'plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2))
    with open(OPERATION_ROOT / 'journal.jsonl', 'a', buffering=1) as journal:
        for index, row in enumerate(moves, 1):
            src, dst = Path(row['src']), Path(row['dst'])
            journal.write(json.dumps({'phase': 'start', 'index': index, **row}, ensure_ascii=False) + '\n'); journal.flush(); os.fsync(journal.fileno())
            digest = move_verified(src, dst)
            journal.write(json.dumps({'phase': 'done', 'index': index, 'sha256': digest, **row}, ensure_ascii=False) + '\n'); journal.flush(); os.fsync(journal.fileno())
            if index % 100 == 0:
                print(f'moved={index}/{len(moves)}', flush=True)
    REGISTRY_PATH.write_text(json.dumps(registry, ensure_ascii=False, indent=2))
    result = {
        'summary': summary(), 'destinationMissing': sum(not Path(row['dst']).is_file() for row in moves),
        'sourceStillPresent': sum(Path(row['src']).exists() for row in moves),
    }
    (OPERATION_ROOT / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print('APPLY_OK ' + json.dumps(result, ensure_ascii=False), flush=True)


parser = argparse.ArgumentParser(); parser.add_argument('--apply', action='store_true'); args = parser.parse_args()
print('PREFLIGHT ' + json.dumps(summary(), ensure_ascii=False), flush=True)
if path_errors:
    sys.exit(2)
if args.apply:
    apply_plan()
