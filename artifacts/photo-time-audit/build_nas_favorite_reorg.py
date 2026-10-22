#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXPORT = Path('/Users/cloudu/Downloads/photo-favorite-selection.json')
REVIEW = ROOT / 'artifacts/photo-time-audit/favorite-selection-review'
OUT = ROOT / 'artifacts/photo-time-audit/nas_favorite_reorg.py'

PICKS = {
    '100000_爸爸': [1, 6, 8, 9, 10, 15, 18, 24, 29, 30],
    '090500_姥姥': [3, 5, 7, 10, 12, 21, 28, 35],
    '140200_桂林': [3, 4, 7, 10, 11, 13, 17, 26, 30, 36],
}

IDLE_TARGETS = {
    'Screenshot_2018-09-19-10-31-40.png': '180900_大二上',
    'Screenshot_2020-02-25-16-43-40.png': '200300_新年与疫情',
    'Screenshot_2020-02-25-16-43-55.png': '200300_新年与疫情',
    'Screenshot_2020-02-25-16-43-35.png': '200300_新年与疫情',
    '20180114_133441.jpg': '180100_大一寒假',
    'hdImg_5852b1fac26fd0d195cbad4d148e3ea11515934224115.jpg': '180100_大一寒假',
    'Screenshot_2019-09-21-15-54-41.png': '190901_比赛之前',
    'wechat_180201_111321.jpg': '180200_大一下',
    'wechat_180225_183840.jpg': '180200_大一下',
    'wechat_190219_175607.jpg': '190200_大二下',
    'wechat_190512_114053.jpg': '190512_秦马拉松',
    'wechat_200305_090742.jpeg': '200300_新年与疫情',
    'wechat_200305_092840.jpg': '200300_新年与疫情',
    'wechat_200305_092845.jpg': '200300_新年与疫情',
    'wechat_180127_123228.jpg': '180100_大一寒假',
    'wechat_180127_123342.jpg': '180100_大一寒假',
    'wechat_180127_130201.jpg': '180100_大一寒假',
    'wechat_180127_130341.jpg': '180100_大一寒假',
    'wechat_180127_130412.jpg': '180100_大一寒假',
    'wechat_180127_182450.jpg': '180100_大一寒假',
    'wechat_180129_081215.jpg': '180100_大一寒假',
    'wechat_180219_120638.jpg': '180200_大一下',
    'wechat_190713_192523.jpg': '190700_大二暑假',
    'wechat_190713_192539.jpg': '190700_大二暑假',
    'wechat_190713_192556.jpg': '190700_大二暑假',
}

data = json.loads(EXPORT.read_text())
favorites = [p['relativePath'] for p in data['selectedPhotos']]
for event, indices in PICKS.items():
    candidates = json.loads((REVIEW / f'{event}-candidates.json').read_text())
    favorites.extend(candidates[i - 1]['relativePath'] for i in indices)
favorites = list(dict.fromkeys(favorites))
assert len(favorites) == 63, len(favorites)

payload = {'favorites': favorites, 'idleTargets': IDLE_TARGETS}
template = r'''#!/usr/bin/env python3
import argparse, hashlib, json, os, shutil, subprocess, sys, time, uuid
from pathlib import Path

PHOTO = Path('/volume2/photo')
BACKUP = Path('/volume2/backup/codex-photo-favorite-reorg-20260831')
PAYLOAD = __PAYLOAD__
CACHE_NAMES = {'.DS_Store', 'Thumbs.db'}

def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def unique_target(directory, name, tag):
    target = directory / name
    if not target.exists(): return target, 'new'
    stem, suffix = Path(name).stem, Path(name).suffix
    n = 1
    while True:
        target = directory / f'{stem}__{tag}_{n:02d}{suffix}'
        if not target.exists(): return target, 'renamed'
        n += 1

def is_cache(path, source):
    rel = path.relative_to(source)
    return path.name in CACHE_NAMES or '@eaDir' in rel.parts

def build_plan():
    errors, ops = [], []
    for rel in PAYLOAD['favorites']:
        src = PHOTO / rel
        dst_dir = src.parent.parent
        if not src.is_file(): errors.append(f'missing favorite: {src}'); continue
        if not dst_dir.is_dir(): errors.append(f'missing favorite target: {dst_dir}'); continue
        direct = dst_dir / src.name
        if direct.exists() and sha256(direct) == sha256(src):
            ops.append({'kind':'favorite-copy','src':str(src),'dst':str(direct),'status':'already'})
        else:
            dst, mode = unique_target(dst_dir, src.name, 'fav')
            ops.append({'kind':'favorite-copy','src':str(src),'dst':str(dst),'status':mode})

    middle = PHOTO / '240829_中汽参观'
    middle_dst = PHOTO / '240824_狐狸峪徒步' / 'photo'
    if not middle.is_dir(): errors.append(f'missing middle source: {middle}')
    if not middle_dst.is_dir(): errors.append(f'missing middle target: {middle_dst}')
    if middle.is_dir() and middle_dst.is_dir():
        reserved = set()
        for src in sorted(middle.rglob('*')):
            if not src.is_file() or is_cache(src, middle): continue
            dst, mode = unique_target(middle_dst, src.name, 'merged')
            while str(dst).casefold() in reserved:
                stem, suffix = dst.stem, dst.suffix
                dst = dst.with_name(stem + '_01' + suffix)
                mode = 'renamed'
            reserved.add(str(dst).casefold())
            ops.append({'kind':'middle-move','src':str(src),'dst':str(dst),'status':mode})

    idle = PHOTO / '251107_闲置手机' / 'photo'
    for name, event in PAYLOAD['idleTargets'].items():
        src = idle / name
        dst_dir = PHOTO / event / 'photo'
        if not src.is_file(): errors.append(f'missing idle photo: {src}'); continue
        if not dst_dir.is_dir(): errors.append(f'missing idle target: {dst_dir}'); continue
        dst, mode = unique_target(dst_dir, name, 'idle')
        ops.append({'kind':'idle-move','src':str(src),'dst':str(dst),'status':mode})
    return ops, errors

def write_jsonl(fp, row):
    fp.write(json.dumps(row, ensure_ascii=False) + '\n'); fp.flush(); os.fsync(fp.fileno())

def copy_verified(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    temp = dst.parent / f'.codex-{uuid.uuid4().hex}.tmp'
    shutil.copy2(src, temp)
    source_hash = sha256(src)
    if sha256(temp) != source_hash:
        temp.unlink(missing_ok=True); raise RuntimeError(f'hash mismatch: {src}')
    os.replace(temp, dst)
    return source_hash

def apply(ops):
    if BACKUP.exists():
        raise RuntimeError(f'backup/journal directory already exists: {BACKUP}')
    BACKUP.mkdir(parents=True)
    (BACKUP / 'plan.json').write_text(json.dumps(ops, ensure_ascii=False, indent=2))
    completed = []
    with open(BACKUP / 'journal.jsonl', 'a', buffering=1) as journal:
        for i, op in enumerate(ops, 1):
            src, dst = Path(op['src']), Path(op['dst'])
            if op['status'] == 'already':
                write_jsonl(journal, {'phase':'already','i':i,**op}); completed.append(op); continue
            if dst.exists(): raise RuntimeError(f'target appeared after preflight: {dst}')
            write_jsonl(journal, {'phase':'start','i':i,**op})
            digest = copy_verified(src, dst)
            if op['kind'].endswith('-move'):
                src.unlink()
            if not dst.is_file() or sha256(dst) != digest:
                raise RuntimeError(f'post-write verification failed: {dst}')
            if op['kind'].endswith('-move') and src.exists():
                raise RuntimeError(f'move source still exists: {src}')
            write_jsonl(journal, {'phase':'done','i':i,'sha256':digest,**op})
            completed.append(op)
            if i % 10 == 0: print(f'completed={i}/{len(ops)}', flush=True)

    middle = PHOTO / '240829_中汽参观'
    remaining_media = [p for p in middle.rglob('*') if p.is_file() and not is_cache(p, middle)] if middle.exists() else []
    if remaining_media:
        raise RuntimeError('middle folder still has media: ' + ', '.join(map(str, remaining_media[:5])))
    if middle.exists():
        shutil.rmtree(middle)

    affected = {str(Path(o['dst']).parent) for o in ops}
    affected.add(str(PHOTO))
    reindex = []
    for path in sorted(affected):
        r = subprocess.run(['synoindex','-R',path], text=True, capture_output=True)
        reindex.append({'path':path,'returncode':r.returncode,'stderr':r.stderr[-1000:]})
    result = {
        'completed':len(completed),
        'favoriteCopies':sum(o['kind']=='favorite-copy' for o in completed),
        'middleMoves':sum(o['kind']=='middle-move' for o in completed),
        'idlePhotoMoves':sum(o['kind']=='idle-move' for o in completed),
        'middleFolderRemoved':not middle.exists(),
        'idleVideosUntouched':len([p for p in (PHOTO/'251107_闲置手机'/'video').rglob('*') if p.is_file() and '@eaDir' not in p.parts]),
        'reindex':reindex,
    }
    (BACKUP / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print('APPLY_OK ' + json.dumps(result, ensure_ascii=False), flush=True)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    ops, errors = build_plan()
    summary = {
        'errors':errors,
        'totalOps':len(ops),
        'favoriteCopies':sum(o['kind']=='favorite-copy' for o in ops),
        'middleMoves':sum(o['kind']=='middle-move' for o in ops),
        'idlePhotoMoves':sum(o['kind']=='idle-move' for o in ops),
        'renamedForCollision':sum(o['status']=='renamed' for o in ops),
        'alreadyPresent':sum(o['status']=='already' for o in ops),
    }
    print('PREFLIGHT ' + json.dumps(summary, ensure_ascii=False), flush=True)
    if errors: sys.exit(2)
    if args.apply: apply(ops)

if __name__ == '__main__': main()
'''
OUT.write_text(template.replace('__PAYLOAD__', repr(payload)))
print(json.dumps({'output': str(OUT), 'favorites': len(favorites), 'idlePhotos': len(IDLE_TARGETS)}, ensure_ascii=False))
