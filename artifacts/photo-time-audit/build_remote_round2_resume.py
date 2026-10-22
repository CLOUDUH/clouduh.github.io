#!/usr/bin/env python3
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
plan = json.loads((HERE / 'round2-tag-classification-plan.json').read_text())
moves = []
for row in plan['moves']:
    item = dict(row)
    item['src'] = item['src'].replace('/Volumes/photo/', '/volume2/photo/', 1)
    item['dst'] = item['dst'].replace('/Volumes/photo/', '/volume2/photo/', 1)
    moves.append(item)

payload = {'moves': moves, 'registry': plan['registry']}
template = r'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import hashlib, json, os, subprocess
from pathlib import Path

PAYLOAD = __PAYLOAD__
PHOTO = Path('/volume2/photo')
OPERATION_ROOT = PHOTO / '170901_备份' / '_operation_logs' / 'tagged-classification-20260901-round2'
JOURNAL = OPERATION_ROOT / 'journal.jsonl'


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


done_ids = set()
for line in JOURNAL.read_text().splitlines():
    try:
        row = json.loads(line)
    except json.JSONDecodeError:
        continue
    if row.get('phase') == 'done':
        done_ids.add(row['id'])

verified = recovered = completed = 0
affected = set()
with open(JOURNAL, 'a', buffering=1) as journal:
    def log(row):
        journal.write(json.dumps(row, ensure_ascii=False) + '\n'); journal.flush(); os.fsync(journal.fileno())
    for index, row in enumerate(PAYLOAD['moves'], 1):
        src, dst = Path(row['src']), Path(row['dst'])
        affected.add(str(dst.parent.parent))
        if row['id'] in done_ids:
            if src.exists() or not dst.is_file():
                raise RuntimeError(f'completed state mismatch: {src} -> {dst}')
            verified += 1
            continue
        for temp in dst.parent.glob('.codex-*.tmp') if dst.parent.exists() else []:
            temp.unlink(missing_ok=True)
        if not src.exists() and dst.is_file():
            digest = sha256(dst)
            log({'phase':'done','index':index,'sha256':digest,'recoveredAfterDisconnect':True,**row})
            recovered += 1; done_ids.add(row['id']); continue
        if src.is_file() and dst.is_file():
            if sha256(src) != sha256(dst):
                raise RuntimeError(f'both paths differ: {src} / {dst}')
            src.unlink(); digest = sha256(dst)
            log({'phase':'done','index':index,'sha256':digest,'recoveredDuplicateTarget':True,**row})
            recovered += 1; done_ids.add(row['id']); continue
        if not src.is_file() or dst.exists():
            raise RuntimeError(f'unexpected state: {src} -> {dst}')
        dst.parent.mkdir(parents=True, exist_ok=True)
        digest_before = sha256(src)
        log({'phase':'remote-start','index':index,'sha256Before':digest_before,**row})
        os.rename(src, dst)
        digest_after = sha256(dst)
        if src.exists() or not dst.is_file() or digest_before != digest_after:
            raise RuntimeError(f'remote move verification failed: {src} -> {dst}')
        log({'phase':'done','index':index,'sha256':digest_after,'remoteResume':True,**row})
        completed += 1; done_ids.add(row['id'])
        if len(done_ids) % 100 == 0:
            print(f'moved={len(done_ids)}/{len(PAYLOAD["moves"])}', flush=True)

reindex = []
for path in sorted(affected):
    result = subprocess.run(['synoindex','-R',path],text=True,capture_output=True)
    reindex.append({'path':path,'returncode':result.returncode,'stderr':result.stderr[-1000:]})
result = {
    'total':len(PAYLOAD['moves']),'verifiedPrevious':verified,'recovered':recovered,
    'completedRemote':completed,'done':len(done_ids),
    'destinationMissing':sum(not Path(row['dst']).is_file() for row in PAYLOAD['moves']),
    'sourceStillPresent':sum(Path(row['src']).exists() for row in PAYLOAD['moves']),
    'reindex':reindex,
}
(OPERATION_ROOT/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print('REMOTE_RESUME_OK '+json.dumps(result,ensure_ascii=False),flush=True)
'''
(HERE / 'remote_round2_resume.py').write_text(template.replace('__PAYLOAD__', repr(payload)))
print(HERE / 'remote_round2_resume.py')
