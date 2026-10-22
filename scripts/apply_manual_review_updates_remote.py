#!/usr/bin/env python3
"""Back up and apply 22 updates derived from the user's review export."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path


LIBRARY = Path("/volume2/photo")
BACKUP_ROOT = Path("/volume2/backup/codex-photo-time-manual-review-20260831")
BACKUP_MEDIA = BACKUP_ROOT / "original"
BACKUP_LOG = BACKUP_ROOT / "backup-manifest.jsonl"
APPLY_LOG = BACKUP_ROOT / "apply-journal.jsonl"
sys.path.insert(0, "/volume2/backup/codex-photo-time-20260831")
import apply_photo_times_remote as core  # noqa: E402


def append(path: Path, record: dict) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def load(path: Path) -> list[dict]:
    records = json.loads(path.read_text(encoding="utf-8"))
    if len(records) != 22:
        raise SystemExit(f"Expected 22 updates, found {len(records)}")
    seen = set()
    for item in records:
        rel = Path(item["relative_to_library"])
        if rel.is_absolute() or ".." in rel.parts or rel in seen:
            raise SystemExit(f"Unsafe or duplicate path: {rel}")
        seen.add(rel)
        core.parse_time(item["proposed_time"])
    return records


def create_backup(records: list[dict]) -> None:
    if BACKUP_ROOT.exists():
        raise SystemExit(f"Refusing to overwrite backup: {BACKUP_ROOT}")
    BACKUP_MEDIA.mkdir(parents=True, mode=0o700)
    for item in records:
        rel = Path(item["relative_to_library"])
        live, saved = LIBRARY / rel, BACKUP_MEDIA / rel
        if not live.is_file():
            raise SystemExit(f"Missing live media: {rel}")
        saved.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["cp", "-a", str(live), str(saved)], check=True)
        before, copied = core.sha256(live), core.sha256(saved)
        if before != copied:
            raise SystemExit(f"Backup mismatch: {rel}")
        append(BACKUP_LOG, {"relative_path": str(rel), "sha256": before, "size": live.stat().st_size})
        print(f"backed_up={rel}", flush=True)
    print("BACKUP_OK", flush=True)


def preflight(records: list[dict]) -> list[tuple]:
    checked = []
    for item in records:
        rel = Path(item["relative_to_library"])
        live, saved = LIBRARY / rel, BACKUP_MEDIA / rel
        if not live.is_file() or not saved.is_file():
            raise SystemExit(f"Missing live or backup media: {rel}")
        before, copied = core.sha256(live), core.sha256(saved)
        if before != copied:
            raise SystemExit(f"Preflight mismatch: {rel}")
        checked.append((item, live, saved, before, core.parse_time(item["proposed_time"])))
        print(f"preflight={rel}", flush=True)
    print("PREFLIGHT_OK", flush=True)
    return checked


def apply(checked: list[tuple]) -> None:
    for item, live, saved, before_hash, value in checked:
        started = dt.datetime.now().isoformat(timespec="seconds")
        try:
            core.write_image(live, value)
            append(
                APPLY_LOG,
                {
                    "status": "ok",
                    "relative_path": item["relative_to_library"],
                    "proposed_time": item["proposed_time"],
                    "reason": item["reason"],
                    "note": item["note"],
                    "review_decision": item["review_decision"],
                    "before_sha256": before_hash,
                    "after_sha256": core.sha256(live),
                    "backup_path": str(saved),
                    "started": started,
                    "finished": dt.datetime.now().isoformat(timespec="seconds"),
                },
            )
            print(f"applied={item['relative_to_library']}", flush=True)
        except Exception as exc:
            append(APPLY_LOG, {"status": "error", "relative_path": item["relative_to_library"], "error": repr(exc)})
            raise
    print("APPLY_OK", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--backup", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    records = load(args.manifest)
    if args.backup:
        create_backup(records)
        return
    checked = preflight(records)
    if args.apply:
        apply(checked)


if __name__ == "__main__":
    main()
