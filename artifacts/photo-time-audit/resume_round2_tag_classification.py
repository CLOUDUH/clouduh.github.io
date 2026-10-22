#!/usr/bin/env python3
import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path

ROOT = Path('/Volumes/photo')
OPERATION_ROOT = ROOT / '170901_备份' / '_operation_logs' / 'tagged-classification-20260901-round2'
PLAN = json.loads((OPERATION_ROOT / 'plan.json').read_text())
MOVES = PLAN['moves']
REGISTRY_PATH = Path(__file__).with_name('classified-event-folders.json')
JOURNAL_PATH = OPERATION_ROOT / 'journal.jsonl'


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def copy_verified(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    for temp in dst.parent.glob('.codex-*.tmp'):
        temp.unlink(missing_ok=True)
    temp = dst.parent / f'.codex-{uuid.uuid4().hex}.tmp'
    shutil.copy2(src, temp)
    digest = sha256(src)
    if sha256(temp) != digest:
        temp.unlink(missing_ok=True); raise RuntimeError(f'hash mismatch: {src}')
    os.replace(temp, dst); return digest


done_ids = set()
for line in JOURNAL_PATH.read_text().splitlines():
    try:
        row = json.loads(line)
    except json.JSONDecodeError:
        continue
    if row.get('phase') == 'done':
        done_ids.add(row['id'])

verified_done = recovered = completed = 0
with open(JOURNAL_PATH, 'a', buffering=1) as journal:
    def log(row):
        journal.write(json.dumps(row, ensure_ascii=False) + '\n'); journal.flush(); os.fsync(journal.fileno())
    for index, row in enumerate(MOVES, 1):
        src, dst = Path(row['src']), Path(row['dst'])
        if row['id'] in done_ids:
            if src.exists() or not dst.is_file():
                raise RuntimeError(f'completed move verification failed: {src} -> {dst}')
            verified_done += 1
            continue
        if not src.exists() and dst.is_file():
            digest = sha256(dst)
            log({'phase': 'done', 'index': index, 'sha256': digest, 'recoveredAfterDisconnect': True, **row})
            recovered += 1; done_ids.add(row['id'])
            continue
        if src.is_file() and dst.is_file():
            if sha256(src) != sha256(dst):
                raise RuntimeError(f'both paths differ: {src} / {dst}')
            src.unlink()
            digest = sha256(dst)
            log({'phase': 'done', 'index': index, 'sha256': digest, 'recoveredDuplicateTarget': True, **row})
            recovered += 1; done_ids.add(row['id'])
            continue
        if not src.is_file() or dst.exists():
            raise RuntimeError(f'unexpected path state: {src} -> {dst}')
        log({'phase': 'resume-start', 'index': index, **row})
        digest = copy_verified(src, dst)
        src.unlink()
        if src.exists() or not dst.is_file() or sha256(dst) != digest:
            raise RuntimeError(f'resumed move verification failed: {src} -> {dst}')
        log({'phase': 'done', 'index': index, 'sha256': digest, 'resumed': True, **row})
        completed += 1; done_ids.add(row['id'])
        if len(done_ids) % 100 == 0:
            print(f'moved={len(done_ids)}/{len(MOVES)}', flush=True)

REGISTRY_PATH.write_text(json.dumps(PLAN['registry'], ensure_ascii=False, indent=2))
result = {
    'total': len(MOVES), 'verifiedPrevious': verified_done, 'recovered': recovered,
    'completedThisRun': completed, 'done': len(done_ids),
    'destinationMissing': sum(not Path(row['dst']).is_file() for row in MOVES),
    'sourceStillPresent': sum(Path(row['src']).exists() for row in MOVES),
}
(OPERATION_ROOT / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
print('RESUME_OK ' + json.dumps(result, ensure_ascii=False), flush=True)
