#!/usr/bin/env python3
"""Preflight, atomically rename, verify, and reindex 1700 media files."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path


LIBRARY = Path("/volume2/photo")
AUDIT_ROOT = Path("/volume2/backup/codex-photo-filename-renames-20260831")
HASH_LOG = AUDIT_ROOT / "preflight-hashes.jsonl"
RENAME_LOG = AUDIT_ROOT / "rename-journal.jsonl"
SAVED_MANIFEST = AUDIT_ROOT / "rename-preview.json"
ALLOWED_PREFIXES = {"wechat", "jike", "baidu", "taobao", "faceapp", "camera", "rednote", "idlefish", "cache", "bili"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def append(path: Path, record: dict) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def load(path: Path) -> list[dict]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    if len(rows) != 1700:
        raise SystemExit(f"Expected 1700 rename rows, found {len(rows)}")
    old_seen, new_seen = set(), set()
    for row in rows:
        old_rel, new_rel = Path(row["old_relative"]), Path(row["new_relative"])
        if old_rel.is_absolute() or new_rel.is_absolute() or ".." in old_rel.parts or ".." in new_rel.parts:
            raise SystemExit(f"Unsafe relative path: {old_rel} -> {new_rel}")
        if old_rel.parent != new_rel.parent:
            raise SystemExit(f"Rename changes directory: {old_rel} -> {new_rel}")
        if row["prefix"] not in ALLOWED_PREFIXES or not new_rel.name.startswith(row["prefix"] + "_"):
            raise SystemExit(f"Unexpected target prefix: {new_rel}")
        old_key, new_key = str(old_rel).casefold(), str(new_rel).casefold()
        if old_key in old_seen or new_key in new_seen:
            raise SystemExit(f"Duplicate manifest path: {old_rel} -> {new_rel}")
        old_seen.add(old_key); new_seen.add(new_key)
    return rows


def preflight(manifest_path: Path, rows: list[dict]) -> None:
    if AUDIT_ROOT.exists():
        raise SystemExit(f"Refusing to overwrite audit directory: {AUDIT_ROOT}")
    AUDIT_ROOT.mkdir(parents=True, mode=0o700)
    shutil.copy2(manifest_path, SAVED_MANIFEST)
    for index, row in enumerate(rows, 1):
        old, new = LIBRARY / row["old_relative"], LIBRARY / row["new_relative"]
        if not old.is_file():
            raise SystemExit(f"Missing source file: {old}")
        if new.exists() and old.resolve() != new.resolve():
            raise SystemExit(f"Target already exists: {new}")
        append(HASH_LOG, {
            "old_relative": row["old_relative"],
            "new_relative": row["new_relative"],
            "sha256": sha256(old),
            "size": old.stat().st_size,
            "mode": old.stat().st_mode,
            "mtime": old.stat().st_mtime,
        })
        if index % 100 == 0 or index == len(rows):
            print(f"preflight={index}/{len(rows)}", flush=True)
    print("PREFLIGHT_OK", flush=True)


def load_hashes() -> dict[str, dict]:
    if not HASH_LOG.is_file():
        raise SystemExit(f"Preflight hash log missing: {HASH_LOG}")
    records = [json.loads(line) for line in HASH_LOG.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(records) != 1700:
        raise SystemExit(f"Expected 1700 preflight hashes, found {len(records)}")
    return {record["old_relative"]: record for record in records}


def apply(rows: list[dict]) -> None:
    hashes = load_hashes()
    completed = {
        json.loads(line)["old_relative"]
        for line in RENAME_LOG.read_text(encoding="utf-8").splitlines()
        if line.strip() and json.loads(line).get("status") == "ok"
    } if RENAME_LOG.exists() else set()
    for index, row in enumerate(rows, 1):
        old_rel, new_rel = row["old_relative"], row["new_relative"]
        old, new = LIBRARY / old_rel, LIBRARY / new_rel
        expected = hashes[old_rel]["sha256"]
        if old_rel in completed:
            if not new.is_file() or sha256(new) != expected:
                raise SystemExit(f"Completed rename no longer verifies: {new_rel}")
            continue
        if not old.is_file() or new.exists():
            raise SystemExit(f"Unsafe rename state: old={old.exists()} new={new.exists()} {old_rel} -> {new_rel}")
        os.rename(old, new)
        actual = sha256(new)
        if actual != expected:
            raise SystemExit(f"Content hash changed after rename: {new_rel}")
        append(RENAME_LOG, {
            "status": "ok",
            "old_relative": old_rel,
            "new_relative": new_rel,
            "sha256": actual,
            "renamed_at": dt.datetime.now().isoformat(timespec="seconds"),
        })
        if index % 100 == 0 or index == len(rows):
            print(f"renamed={index}/{len(rows)}", flush=True)
    print("RENAME_OK", flush=True)


def verify(rows: list[dict]) -> None:
    hashes = load_hashes()
    journal = [json.loads(line) for line in RENAME_LOG.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(journal) != 1700 or any(record.get("status") != "ok" for record in journal):
        raise SystemExit(f"Rename journal invalid: {len(journal)} entries")
    bad = []
    for index, row in enumerate(rows, 1):
        old, new = LIBRARY / row["old_relative"], LIBRARY / row["new_relative"]
        if old.exists() or not new.is_file() or sha256(new) != hashes[row["old_relative"]]["sha256"]:
            bad.append(row["old_relative"])
        if index % 100 == 0 or index == len(rows):
            print(f"verified={index}/{len(rows)} bad={len(bad)}", flush=True)
    print("VERIFY_OK" if not bad else f"VERIFY_FAILED {bad[:10]}", flush=True)
    if bad:
        raise SystemExit(1)


def reindex(rows: list[dict]) -> None:
    events = sorted({Path(row["new_relative"]).parts[0] for row in rows})
    for index, event in enumerate(events, 1):
        subprocess.run(["synoindex", "-R", str(LIBRARY / event)], check=True)
        if index % 10 == 0 or index == len(events):
            print(f"reindexed={index}/{len(events)}", flush=True)
    print("REINDEX_OK", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--reindex", action="store_true")
    args = parser.parse_args()
    if sum((args.preflight, args.apply, args.verify, args.reindex)) != 1:
        raise SystemExit("Choose exactly one action")
    rows = load(args.manifest)
    if args.preflight: preflight(args.manifest, rows)
    elif args.apply: apply(rows)
    elif args.verify: verify(rows)
    else: reindex(rows)


if __name__ == "__main__":
    main()
