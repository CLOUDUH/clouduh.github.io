#!/usr/bin/env python3
import json, re, shutil
from pathlib import Path
from PIL import Image, ImageOps

ROOT=Path('/Volumes/photo')
REPO=Path(__file__).resolve().parents[2]
SITE=REPO/'tools/photo-date-review-site'
TIMELINE=SITE/'public/timeline/timeline-items.json'
OUT=SITE/'public/calibration'
THUMBS=OUT/'thumbs'
EXCLUDED={'171022_大一冬天之前','171204_大一冬天','180112_综办','180113_大一寒假'}

data=json.loads(TIMELINE.read_text())
items=[]
for item in data['items']:
    folder=item['currentFolder']; match=re.match(r'^(\d{6})_',folder)
    if item['location']!='library' or item['kind']!='image' or not match: continue
    if not 170909<=int(match.group(1))<=190613 or folder in EXCLUDED: continue
    items.append(item)

OUT.mkdir(parents=True,exist_ok=True); THUMBS.mkdir(parents=True,exist_ok=True)
quicklook=Path('/tmp/codex-timeline-heic-20260901')
for index,item in enumerate(items,1):
    dst=THUMBS/f"{item['id']}.jpg"
    old=SITE/'public/timeline/thumbs'/f"{item['id']}.jpg"
    if old.is_file():
        shutil.copy2(old,dst)
    elif item['format']=='heic' and (quicklook/f"{item['filename']}.png").is_file():
        with Image.open(quicklook/f"{item['filename']}.png") as image:
            image=ImageOps.exif_transpose(image).convert('RGB'); image.thumbnail((720,720)); image.save(dst,'JPEG',quality=84,optimize=True)
    else:
        try:
            with Image.open(ROOT/item['relativePath']) as image:
                image=ImageOps.exif_transpose(image).convert('RGB'); image.thumbnail((720,720)); image.save(dst,'JPEG',quality=84,optimize=True)
        except Exception:
            dst=None
    item['thumbnail']=f"/calibration/thumbs/{item['id']}.jpg" if dst and Path(dst).is_file() else None
    if index%200==0: print(f'thumbnails={index}/{len(items)}',flush=True)

manifest={
    'version':1,'generatedAt':__import__('datetime').datetime.now().astimezone().isoformat(),
    'count':len(items),'folderCount':len(set(item['currentFolder'] for item in items)),
    'excludedFolders':sorted(EXCLUDED),
    'items':[{key:item.get(key) for key in ['id','relativePath','filename','currentFolder','captureDate','createDate','fileModifyDate','dateSource','metadataStatus','thumbnail']} for item in items],
}
(OUT/'calibration-items.json').write_text(json.dumps(manifest,ensure_ascii=False,separators=(',',':')))
print(json.dumps({'items':manifest['count'],'folders':manifest['folderCount'],'missingThumbs':sum(not item['thumbnail'] for item in items)},ensure_ascii=False))
