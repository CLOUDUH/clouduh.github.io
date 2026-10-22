#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import hashlib
import json
import os
from pathlib import Path

ROOT = Path('/Volumes/photo')
SITE = Path(__file__).resolve().parents[2] / 'tools/photo-date-review-site'
MANIFEST_PATH = SITE / 'public/timeline/timeline-items.json'
REVIEW_PATH = Path('/Users/cloudu/Downloads/photo-timeline-review (3).json')
PLAN_PATH = Path(__file__).with_name('round3-tag-classification-plan.json')
OUT_PATH = Path(__file__).with_name('remote_round3_classification.py')

TAG_FOLDERS = {
    '综办合照': '171021_综办合照', '报到': '170901_报到', '开学': '170904_开学',
    '综办': '180112_综办', '国庆回家': '171002_国庆回家', '大一冬天之前': '171022_大一冬天之前',
    '大一冬天': '171204_大一冬天', '大一寒假': '180113_大一寒假', '19年春节': '190204_19年春节',
    '大一下开学': '180226_大一下开学', '港西绿地': '180317_港西绿地', '保定实习': '180407_保定实习',
    '北京': '180428_北京', '大一暑假之前': '180428_大一暑假之前', '秦马志愿者': '180512_秦马志愿者',
    '进入暑期': '180530_进入暑期', '大一暑假': '180700_大一暑假', '高中': '180725_高中',
    '大二开学': '180906_大二开学', '大二国庆': '180930_大二国庆', '珠海参会': '181126_珠海参会',
    '19比赛': '181116_19比赛', '大二深冬': '181203_大二深冬', '大二寒假': '190131_大二寒假',
    '大二暑假之前': '190217_大二暑假之前', '大二下开学': '190302_大二下开学', '长春吉大': '190316_长春吉大',
    '大三深冬': '190417_大三深冬', '大二劳动节': '190430_大二劳动节', '大二暑假': '190700_大二暑假',
    '大三上开学': '190900_大三上开学', '大三比赛后': '191026_大三比赛后',
    '大三下疫情返校': '200911_大三下疫情返校', '高中毕业': '170701_高中毕业',
}


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


manifest = json.loads(MANIFEST_PATH.read_text())
review = json.loads(REVIEW_PATH.read_text())
if review.get('sourceGeneratedAt') != manifest.get('generatedAt'):
    raise RuntimeError('review JSON does not match current manifest')
items = {item['id']: item for item in manifest['items']}
decisions = [row for row in review.get('decisions', []) if row.get('id')]
missing_ids = [row['id'] for row in decisions if row['id'] not in items]
if missing_ids:
    raise RuntimeError(f'{len(missing_ids)} decision IDs missing from manifest')

reserved = set()
moves, already, deletes = [], [], []


def unique_target(directory, name):
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


for decision in decisions:
    tags = decision.get('tags') or []
    if not tags:
        continue
    item = items[decision['id']]
    src = ROOT / item['relativePath']
    if '这个删除' in tags:
        if not src.is_file():
            raise RuntimeError(f'delete source missing: {src}')
        deletes.append({'id': item['id'], 'src': str(src), 'sha256': sha256(src), 'tags': tags})
        continue
    tag = next((value for value in tags if value in TAG_FOLDERS), None)
    if not tag:
        raise RuntimeError(f'no target mapping for tags: {tags}')
    folder = TAG_FOLDERS[tag]
    destination_dir = ROOT / folder / 'photo'
    if src.parent == destination_dir:
        already.append({'id': item['id'], 'path': str(src), 'tag': tag, 'folder': folder})
        continue
    dst, collision = unique_target(destination_dir, src.name)
    moves.append({'id': item['id'], 'src': str(src), 'dst': str(dst), 'tag': tag, 'folder': folder, 'collisionRenamed': collision})

path_errors = [row['src'] for row in moves + deletes if not Path(row['src']).is_file()]
plan = {'moves': moves, 'already': already, 'deletes': deletes, 'pathErrors': path_errors, 'tagFolders': TAG_FOLDERS}
PLAN_PATH.write_text(json.dumps(plan, ensure_ascii=False, indent=2))


def remote_path(value):
    return value.replace('/Volumes/photo/', '/volume2/photo/', 1)


payload = {
    'moves': [{**row, 'src': remote_path(row['src']), 'dst': remote_path(row['dst'])} for row in moves],
    'deletes': [{**row, 'src': remote_path(row['src'])} for row in deletes],
}
template = r'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import hashlib, json, os, re, shutil, subprocess
from pathlib import Path

PAYLOAD = __PAYLOAD__
PHOTO = Path('/volume2/photo')
BACKUP = PHOTO / '170901_备份'
OPERATION = BACKUP / '_operation_logs' / 'tagged-classification-20260902-round3'
MEDIA_EXTS = {'.jpg','.jpeg','.png','.heic','.webp','.gif','.dng','.tif','.tiff','.mp4','.mov','.avi','.mkv','.m4v','.3gp'}
CACHE_NAMES = {'.DS_Store','Thumbs.db'}


def sha256(path):
    digest = hashlib.sha256()
    with open(path,'rb') as stream:
        for block in iter(lambda:stream.read(8*1024*1024),b''):
            digest.update(block)
    return digest.hexdigest()


if OPERATION.exists():
    raise RuntimeError(f'operation exists: {OPERATION}')
OPERATION.mkdir(parents=True)
(OPERATION/'plan.json').write_text(json.dumps(PAYLOAD,ensure_ascii=False,indent=2))
affected = set(); deleted_files = []; removed_folders = []
with open(OPERATION/'journal.jsonl','a',buffering=1) as journal:
    def log(row):
        journal.write(json.dumps(row,ensure_ascii=False)+'\n'); journal.flush(); os.fsync(journal.fileno())
    for index,row in enumerate(PAYLOAD['moves'],1):
        src,dst=Path(row['src']),Path(row['dst']); dst.parent.mkdir(parents=True,exist_ok=True)
        if not src.is_file() or dst.exists(): raise RuntimeError(f'unexpected move state: {src} -> {dst}')
        before=sha256(src); log({'phase':'move-start','index':index,'sha256':before,**row})
        os.rename(src,dst); after=sha256(dst)
        if src.exists() or not dst.is_file() or before!=after: raise RuntimeError(f'move verification failed: {src} -> {dst}')
        log({'phase':'move-done','index':index,'sha256':after,**row}); affected.add(str(dst.parent.parent))
        if index%50==0: print(f'moved={index}/{len(PAYLOAD["moves"])}',flush=True)
    for index,row in enumerate(PAYLOAD['deletes'],1):
        src=Path(row['src'])
        if not src.is_file() or sha256(src)!=row['sha256']: raise RuntimeError(f'delete verification failed: {src}')
        log({'phase':'delete-start','index':index,**row}); src.unlink()
        if src.exists(): raise RuntimeError(f'delete failed: {src}')
        deleted_files.append(row); log({'phase':'delete-done','index':index,**row}); affected.add(str(src.parent.parent))

for folder in sorted(PHOTO.iterdir()):
    if not folder.is_dir() or folder.name in {'170901_备份','#recycle'} or not re.match(r'^\d{6}_',folder.name): continue
    files=[path for path in folder.rglob('*') if path.is_file()]
    media=[path for path in files if path.suffix.lower() in MEDIA_EXTS and '@eaDir' not in path.parts]
    meaningful=[path for path in files if path.name not in CACHE_NAMES and '@eaDir' not in path.parts]
    if not media and not meaningful:
        removed_folders.append(str(folder)); shutil.rmtree(folder)

reindex=[]
for path in sorted(affected|{str(PHOTO)}):
    result=subprocess.run(['synoindex','-R',path],text=True,capture_output=True)
    reindex.append({'path':path,'returncode':result.returncode,'stderr':result.stderr[-1000:]})
result={
    'moved':len(PAYLOAD['moves']),'deletedFiles':deleted_files,'removedFolders':removed_folders,
    'destinationMissing':sum(not Path(row['dst']).is_file() for row in PAYLOAD['moves']),
    'sourceStillPresent':sum(Path(row['src']).exists() for row in PAYLOAD['moves']),
    'deletedStillPresent':sum(Path(row['src']).exists() for row in PAYLOAD['deletes']),'reindex':reindex,
}
(OPERATION/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print('ROUND3_OK '+json.dumps(result,ensure_ascii=False),flush=True)
'''
OUT_PATH.write_text(template.replace('__PAYLOAD__', repr(payload)))
summary = {
    'decisions': len(decisions), 'moves': len(moves), 'already': len(already), 'deletes': len(deletes),
    'collisionRenamed': sum(row['collisionRenamed'] for row in moves), 'pathErrors': path_errors,
    'byTag': dict(__import__('collections').Counter(row['tag'] for row in moves + already)),
}
print('PREFLIGHT ' + json.dumps(summary, ensure_ascii=False))
