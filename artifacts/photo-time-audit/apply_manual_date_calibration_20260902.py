#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse, collections, datetime as dt, hashlib, json, os, re, shutil, subprocess, sys, uuid
from pathlib import Path

ROOT = Path('/Volumes/photo')
BACKUP = ROOT / '170900_备份' / 'metadata-originals' / 'manual-calibration-20260902'
OPERATION = ROOT / '170900_备份' / '_operation_logs' / 'manual-calibration-20260902'
EXIFTOOL = '/opt/homebrew/bin/exiftool'


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def parse_exif(value):
    if not value: return None
    match = re.match(r'^(\d{4}):(\d{2}):(\d{2}) (\d{2}):(\d{2}):(\d{2})', str(value))
    return dt.datetime(*map(int, match.groups())) if match else None


def metadata(path):
    return json.loads(subprocess.check_output([EXIFTOOL,'-json','-DateTimeOriginal','-CreateDate','-FileModifyDate',str(path)],text=True))[0]


def find_main(stem, preferred=None):
    preferred_roots=[ROOT/value for value in (preferred or [])]
    for root in preferred_roots:
        matches=[path for path in root.rglob('*') if path.is_file() and '@eaDir' not in path.parts and path.stem==stem] if root.is_dir() else []
        if len(matches)==1: return matches[0]
        if len(matches)>1: raise RuntimeError(f'multiple preferred files for {stem}: {matches}')
    roots=[p for p in ROOT.iterdir() if p.is_dir() and p.name!='#recycle' and '备份' not in p.name and not p.name.startswith('.')]
    matches=[]
    for root in roots:
        if not root.is_dir(): continue
        for path in root.rglob('*'):
            if path.is_file() and '@eaDir' not in path.parts and path.stem == stem:
                matches.append(path)
    unique=[]
    for path in matches:
        if path not in unique: unique.append(path)
    if len(unique)!=1: raise RuntimeError(f'expected one main file for {stem}, found {unique}')
    return unique[0]


assignments={}


def add(path, timestamp, reason):
    current=assignments.get(str(path))
    row={'path':str(path),'timestamp':timestamp.strftime('%Y:%m:%d %H:%M:%S'),'reason':reason}
    if current and current['timestamp']!=row['timestamp']:
        raise RuntimeError(f'conflicting assignment for {path}: {current} / {row}')
    assignments[str(path)]=row


group_oct26=['39a91eaa38b6d398','2e31476c5694bee5','-17d581f569350f7','-2d2e0d51153d163']
for index,stem in enumerate(group_oct26):
    add(find_main(stem,['171022_大一冬天之前']),dt.datetime(2017,10,26,20,0,index*10),'宿舍KTV-2017-10-26')

reference=find_main('IMG_20171029_190937',['171022_大一冬天之前'])
ref_time=parse_exif(metadata(reference).get('DateTimeOriginal')) or dt.datetime(2017,10,29,19,9,39)
for index,stem in enumerate(['-71c1d6ce95ae0384','77525c4cd59b92e9','49ea055d6b6ece47','-b18e776823b2aec']):
    add(find_main(stem,['171022_大一冬天之前']),ref_time+dt.timedelta(seconds=index+1),'综办KTV-参考IMG_20171029_190937')

nov9=dt.datetime(2017,11,9,15,46,30)
for stem in ['74638e15850b267b','-5947d0186547cca8']:
    add(find_main(stem,['171022_大一冬天之前']),nov9,'同一照片-2017-11-09')

gif=find_main('1509689474232',['171022_大一冬天之前'])
gif_current=parse_exif(metadata(gif).get('DateTimeOriginal')) or dt.datetime(2017,11,3,7,4,31)
add(gif,gif_current.replace(year=2017,month=11,day=3),'与IMG_20171103_120305同日')

explicit_names={
    'CLOUDUH_171231194801':(dt.datetime(2017,12,31,19,48,1),['171204_大一冬天']),
    'IMG_20171216_225921__tagged_01':(dt.datetime(2017,12,16,22,59,21),['171204_大一冬天']),
    'IMG_20171102_164459__tagged_01':(dt.datetime(2017,11,2,16,44,59),['171022_大一冬天之前']),
    'IMG_20171012_153327':(dt.datetime(2017,10,12,15,33,27),['171022_大一冬天之前']),
    'IMG_20180213_211746':(dt.datetime(2018,2,13,21,17,46),['180113_大一寒假']),
}
for stem,(value,preferred) in explicit_names.items(): add(find_main(stem,preferred),value,'文件名时间')

folder_180112=ROOT/'180112_综办'/'photo'
for path in sorted(p for p in folder_180112.iterdir() if p.is_file() and p.name!='.DS_Store'):
    named=re.search(r'(?:IMG_)?20171202_(\d{2})(\d{2})(\d{2})',path.stem)
    if named:
        h,m,s=map(int,named.groups())
    elif path.stem.startswith('CLOUDUH_171201194801'):
        h,m,s=19,48,1
    else:
        row=metadata(path); current=parse_exif(row.get('DateTimeOriginal')) or parse_exif(row.get('CreateDate'))
        h,m,s=(current.hour,current.minute,current.second) if current else (12,0,0)
    add(path,dt.datetime(2017,12,2,h,m,s),'180112_综办统一为2017-12-02')

folder_180113=ROOT/'180113_大一寒假'/'photo'
for path in sorted(p for p in folder_180113.iterdir() if p.is_file() and p.name!='.DS_Store'):
    named=re.match(r'IMG_(20\d{2})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})',path.stem)
    if named:
        add(path,dt.datetime(*map(int,named.groups())),'IMG文件名时间')

for stem in ['IMG_1588','IMG_1583','IMG_1590','IMG_1584','IMG_1580','IMG_1589','IMG_1586']:
    path=find_main(stem,['180113_大一寒假']); row=metadata(path)
    current=parse_exif(row.get('DateTimeOriginal')) or parse_exif(row.get('CreateDate')) or dt.datetime(2018,2,16,12)
    add(path,current.replace(year=2018,month=2,day=16),'指定为2018-02-16')

specific_wechat={
    'wechat_180513_185353':dt.datetime(2018,2,16,18,53,53),
    'CLOUDUH_180213211746':dt.datetime(2018,2,13,21,17,46),
    'wechat_180503_144757':dt.datetime(2018,2,17,14,47,57),
    'wechat_180517_224243':dt.datetime(2018,2,17,22,42,43),
    'wechat_180521_070145':dt.datetime(2018,2,18,7,1,45),
    'wechat_180129_081215':dt.datetime(2018,2,6,8,12,15),
    'wechat_180521_220425':dt.datetime(2018,2,14,22,4,25),
}
for stem,value in specific_wechat.items(): add(find_main(stem,['180113_大一寒假']),value,'用户指定日期')
for stem in ['wechat_180208_232822','wechat_180208_232824','wechat_180208_232825','wechat_180208_234943','wechat_180208_234947','wechat_180208_234952','wechat_180209_120553','wechat_180209_120557']:
    match=re.match(r'wechat_(\d{2})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})',stem)
    yy,mo,day,h,mi,s=map(int,match.groups()); add(find_main(stem,['180113_大一寒假']),dt.datetime(2000+yy,mo,day,h,mi,s),'微信文件名时间')

plan=list(assignments.values())
missing=[row['path'] for row in plan if not Path(row['path']).is_file()]
summary={'files':len(plan),'byReason':dict(collections.Counter(row['reason'] for row in plan)),'missing':missing,'canonicalOnly':'171022_大一冬天之前/photo/-f99a1253919574_mr1510808091258.jpg'}
print('PREFLIGHT '+json.dumps(summary,ensure_ascii=False))
if missing: sys.exit(2)


def backup_target(src):
    rel=src.relative_to(ROOT); dst=BACKUP/rel
    if not dst.exists(): return dst
    stem,suffix=dst.stem,dst.suffix; number=1
    while dst.exists(): dst=dst.with_name(f'{stem}__original_{number:02d}{suffix}'); number+=1
    return dst


def copy_verified(src,dst):
    dst.parent.mkdir(parents=True,exist_ok=True); temp=dst.parent/f'.codex-{uuid.uuid4().hex}.tmp'
    shutil.copy2(src,temp); digest=sha256(src)
    if sha256(temp)!=digest: temp.unlink(missing_ok=True); raise RuntimeError(f'backup hash mismatch: {src}')
    os.replace(temp,dst); return digest


def apply_plan():
    if OPERATION.exists(): raise RuntimeError(f'operation exists: {OPERATION}')
    OPERATION.mkdir(parents=True); (OPERATION/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2))
    with open(OPERATION/'journal.jsonl','a',buffering=1) as journal:
        def log(row): journal.write(json.dumps(row,ensure_ascii=False)+'\n'); journal.flush(); os.fsync(journal.fileno())
        for index,row in enumerate(plan,1):
            path=Path(row['path']); dst=backup_target(path); before=sha256(path)
            log({'phase':'start','index':index,'sha256Before':before,'backup':str(dst),**row})
            copy_verified(path,dst)
            timestamp=row['timestamp']
            result=subprocess.run([EXIFTOOL,'-overwrite_original','-P',f'-DateTimeOriginal={timestamp}',f'-CreateDate={timestamp}',f'-ModifyDate={timestamp}',f'-FileModifyDate={timestamp}',str(path)],text=True,capture_output=True)
            if result.returncode!=0: raise RuntimeError(f'exiftool failed: {path}: {result.stderr}')
            check=metadata(path); observed=check.get('DateTimeOriginal') or check.get('CreateDate')
            if not observed or not str(observed).startswith(timestamp): raise RuntimeError(f'verification failed: {path}: {check}')
            log({'phase':'done','index':index,'sha256After':sha256(path),'check':check,'backup':str(dst),**row})
            if index%20==0: print(f'updated={index}/{len(plan)}',flush=True)
    result={'updated':len(plan),'missingAfter':sum(not Path(row['path']).is_file() for row in plan),'backupRoot':str(BACKUP)}
    (OPERATION/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)); print('APPLY_OK '+json.dumps(result,ensure_ascii=False))


parser=argparse.ArgumentParser(); parser.add_argument('--apply',action='store_true'); args=parser.parse_args()
if args.apply: apply_plan()
