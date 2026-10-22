#!/usr/bin/env python3
import hashlib, json, os, runpy, shutil, uuid
from pathlib import Path

MOUNT = Path('/Volumes/photo')
SOURCE_SCRIPT = Path(__file__).with_name('nas_mom_phone_reorg.py')
LOG = Path(__file__).with_name('mom-videos-to-photo-local-result.json')


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


payload = runpy.run_path(str(SOURCE_SCRIPT))['PAYLOAD']
rows = [op for op in payload['operations'] if op[2] == 'video']
assert len(rows) == 18, len(rows)
result = []
for rel, event, kind, capture, date_source, distance in rows:
    name = Path(rel).name
    src = MOUNT / event / 'video' / name
    if not src.is_file():
        raise RuntimeError(f'missing video: {src}')
    dst = MOUNT / event / 'photo' / name
    if dst.exists():
        stem, suffix = dst.stem, dst.suffix
        number = 1
        while dst.exists():
            dst = dst.with_name(f'{stem}__mom_{number:02d}{suffix}')
            number += 1
    temp = dst.parent / f'.codex-{uuid.uuid4().hex}.tmp'
    shutil.copy2(src, temp)
    digest = sha256(src)
    if sha256(temp) != digest:
        temp.unlink(missing_ok=True)
        raise RuntimeError(f'hash mismatch: {src}')
    os.replace(temp, dst)
    src.unlink()
    if not dst.is_file() or sha256(dst) != digest or src.exists():
        raise RuntimeError(f'post-move verification failed: {src} -> {dst}')
    result.append({'src': str(src), 'dst': str(dst), 'sha256': digest})
LOG.write_text(json.dumps({'completed': len(result), 'operations': result}, ensure_ascii=False, indent=2))
print(json.dumps({'completed': len(result), 'sourceMissing': sum(Path(x['src']).exists() for x in result), 'destinationMissing': sum(not Path(x['dst']).is_file() for x in result)}, ensure_ascii=False))
