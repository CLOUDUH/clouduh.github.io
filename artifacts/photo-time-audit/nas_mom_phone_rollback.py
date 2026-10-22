#!/usr/bin/env python3
import hashlib, json, os, shutil, uuid
from pathlib import Path

BACKUP = Path('/volume2/backup/codex-mom-phone-reorg-20260901')
PLAN = json.loads((BACKUP / 'plan.json').read_text())


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def copy_verified(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    temp = dst.parent / f'.codex-rollback-{uuid.uuid4().hex}.tmp'
    shutil.copy2(src, temp)
    digest = sha256(src)
    if sha256(temp) != digest:
        temp.unlink(missing_ok=True)
        raise RuntimeError(f'rollback hash mismatch: {src}')
    os.replace(temp, dst)
    return digest


restored = skipped = 0
with open(BACKUP / 'rollback.jsonl', 'a', buffering=1) as journal:
    for op in reversed(PLAN):
        src, dst = Path(op['src']), Path(op['dst'])
        if src.is_file() and not dst.exists():
            skipped += 1
            continue
        if dst.is_file() and not src.exists():
            digest = copy_verified(dst, src)
            dst.unlink()
            if not src.is_file() or sha256(src) != digest or dst.exists():
                raise RuntimeError(f'rollback verification failed: {dst} -> {src}')
            row = {'phase': 'restored', 'src': str(src), 'dst': str(dst), 'sha256': digest}
            journal.write(json.dumps(row, ensure_ascii=False) + '\n'); journal.flush(); os.fsync(journal.fileno())
            restored += 1
            continue
        if src.is_file() and dst.is_file():
            if sha256(src) != sha256(dst):
                raise RuntimeError(f'both paths differ during rollback: {src} / {dst}')
            dst.unlink()
            restored += 1
            continue
        raise RuntimeError(f'both paths missing during rollback: {src} / {dst}')

source_missing = sum(not Path(op['src']).is_file() for op in PLAN)
targets_left = sum(Path(op['dst']).exists() for op in PLAN)
result = {'restored': restored, 'untouched': skipped, 'sourceMissing': source_missing, 'targetsLeft': targets_left}
(BACKUP / 'rollback-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
print('ROLLBACK_OK ' + json.dumps(result, ensure_ascii=False))
if source_missing or targets_left:
    raise SystemExit(2)
