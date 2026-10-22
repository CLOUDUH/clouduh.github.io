#!/usr/bin/env python3
import argparse, hashlib, json, os, shutil, sys, uuid
from pathlib import Path

SOURCE_PLAN = Path('/volume2/backup/codex-mom-phone-reorg-20260901-v2/plan.json')
JOURNAL = Path('/volume2/backup/codex-mom-videos-to-photo-20260901')


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def unique(directory, name):
    direct = directory / name
    if not direct.exists(): return direct, False
    stem, suffix = Path(name).stem, Path(name).suffix
    number = 1
    while True:
        candidate = directory / f'{stem}__mom_{number:02d}{suffix}'
        if not candidate.exists(): return candidate, True
        number += 1


def plan():
    rows, errors = [], []
    for op in json.loads(SOURCE_PLAN.read_text()):
        if op['kind'] != 'video': continue
        src = Path(op['dst'])
        if not src.is_file(): errors.append(f'missing moved video: {src}'); continue
        dst, collision = unique(src.parent.parent / 'photo', src.name)
        rows.append({'src': str(src), 'dst': str(dst), 'collisionRenamed': collision})
    if len(rows) != 18: errors.append(f'expected 18 videos, found {len(rows)}')
    return rows, errors


def copy_verified(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    temp = dst.parent / f'.codex-{uuid.uuid4().hex}.tmp'
    shutil.copy2(src, temp); digest = sha256(src)
    if sha256(temp) != digest: temp.unlink(missing_ok=True); raise RuntimeError(f'hash mismatch: {src}')
    os.replace(temp, dst); return digest


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--apply', action='store_true'); args = parser.parse_args()
    rows, errors = plan()
    print('PREFLIGHT ' + json.dumps({'errors': errors, 'total': len(rows), 'collisions': sum(r['collisionRenamed'] for r in rows)}, ensure_ascii=False))
    if errors: sys.exit(2)
    if not args.apply: return
    if JOURNAL.exists(): raise RuntimeError(f'journal exists: {JOURNAL}')
    JOURNAL.mkdir(parents=True); (JOURNAL / 'plan.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    done = []
    for row in rows:
        src, dst = Path(row['src']), Path(row['dst'])
        digest = copy_verified(src, dst); src.unlink()
        if not dst.is_file() or sha256(dst) != digest or src.exists(): raise RuntimeError(f'verification failed: {src} -> {dst}')
        done.append({'sha256': digest, **row})
    (JOURNAL / 'result.json').write_text(json.dumps(done, ensure_ascii=False, indent=2))
    print('APPLY_OK ' + json.dumps({'completed': len(done)}, ensure_ascii=False))


if __name__ == '__main__': main()
