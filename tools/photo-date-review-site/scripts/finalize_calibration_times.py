#!/usr/bin/env python3
"""Restore filesystem dates after SMB moves and verify the final calibration run."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


NAS = Path("/Volumes/photo")
LOG_ROOT = NAS / "170900_备份/_operation_logs/calibration-final-20260902"
JOURNAL = LOG_ROOT / "journal.jsonl"
EXIFTOOL = "/opt/homebrew/bin/exiftool"


def normalized(value: str | None) -> str:
    if not value:
        return ""
    return value[:19].replace(":", "-", 2)


rows = [json.loads(line) for line in JOURNAL.read_text().splitlines() if line.strip()]
metadata = [row for row in rows if row.get("kind") == "metadata_move"]
targets = [NAS / row["target"] for row in metadata]
missing = [str(path) for path in targets if not path.exists()]
if missing:
    raise SystemExit("Missing final targets:\n" + "\n".join(missing))

result = subprocess.run([
    EXIFTOOL,
    "-overwrite_original_in_place",
    "-FileCreateDate<DateTimeOriginal",
    "-FileModifyDate<DateTimeOriginal",
    *map(str, targets),
], text=True, capture_output=True)
print(result.stdout, end="")
if result.returncode != 0:
    raise SystemExit(result.stderr or result.stdout)

readback = subprocess.run([
    EXIFTOOL, "-j", "-DateTimeOriginal", "-CreateDate",
    "-FileCreateDate", "-FileModifyDate", *map(str, targets),
], text=True, capture_output=True, check=True)
values = json.loads(readback.stdout)
by_source = {Path(row["SourceFile"]): row for row in values}
errors = []
for journal_row, path in zip(metadata, targets):
    expected = journal_row["datetime"]
    row = by_source[path]
    for tag in ["DateTimeOriginal", "CreateDate", "FileCreateDate", "FileModifyDate"]:
        actual = normalized(row.get(tag))
        if actual != expected:
            errors.append({"path": str(path.relative_to(NAS)), "tag": tag,
                           "expected": expected, "actual": actual})

report = {
    "checked": len(targets),
    "errors": errors,
    "status": "ok" if not errors else "failed",
}
(LOG_ROOT / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
print(json.dumps(report, ensure_ascii=False, indent=2))
if errors:
    raise SystemExit(1)
