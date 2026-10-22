#!/usr/bin/env python3
"""Apply the four explicit follow-up corrections from the user."""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path


NAS = Path("/Volumes/photo")
EXIFTOOL = "/opt/homebrew/bin/exiftool"
RUN = "followup-corrections-20260902"
BACKUP = NAS / "170900_备份/metadata-originals" / RUN
LOG = NAS / "170900_备份/_operation_logs" / RUN

PLAN = [
    {
        "source": "180226_大一下开学/photo/_`(K(J{]1W5R016KYLKK5DH.jpg",
        "target": "171204_大一冬天/photo/_`(K(J{]1W5R016KYLKK5DH.jpg",
        "datetime": "2017-12-15 13:48:48",
        "reason": "用户指定2017年12月；日期取月中，保留原时分秒",
    },
    {
        "source": "180530_焦躁暑期/photo/IMG_2248.PNG",
        "target": "171204_大一冬天/photo/IMG_2248.PNG",
        "datetime": "2018-01-01 17:34:18",
        "reason": "用户明确指定2018-01-01",
    },
    {
        "source": "190302_大二下开学/photo/IMG20190310071120.jpg",
        "target": "190302_大二下开学/photo/IMG20190324071124.jpg",
        "datetime": "2019-03-24 07:11:24",
        "reason": "用户明确指定2019-03-24，并同步文件名",
    },
    {
        "source": "190302_大二下开学/photo/IMG20190310072108.jpg",
        "target": "190302_大二下开学/photo/IMG20190324072111.jpg",
        "datetime": "2019-03-24 07:21:11",
        "reason": "用户明确指定2019-03-24，并同步文件名",
    },
]


def run() -> None:
    missing = [row["source"] for row in PLAN if not (NAS / row["source"]).exists()]
    collisions = [row["target"] for row in PLAN if (NAS / row["target"]).exists() and row["target"] != row["source"]]
    if missing or collisions:
        raise SystemExit(json.dumps({"missing": missing, "collisions": collisions}, ensure_ascii=False, indent=2))
    LOG.mkdir(parents=True, exist_ok=False)
    BACKUP.mkdir(parents=True, exist_ok=False)
    (LOG / "plan.json").write_text(json.dumps(PLAN, ensure_ascii=False, indent=2))
    journal = []
    for row in PLAN:
        source = NAS / row["source"]
        target = NAS / row["target"]
        value = datetime.strptime(row["datetime"], "%Y-%m-%d %H:%M:%S")
        exif = value.strftime("%Y:%m:%d %H:%M:%S")
        xmp = value.strftime("%Y-%m-%dT%H:%M:%S+08:00")
        result = subprocess.run([
            EXIFTOOL, f"-EXIF:DateTimeOriginal={exif}", f"-EXIF:CreateDate={exif}",
            f"-EXIF:ModifyDate={exif}", f"-XMP-exif:DateTimeOriginal={exif}",
            f"-XMP-xmp:CreateDate={xmp}", f"-XMP-xmp:ModifyDate={xmp}", str(source),
        ], text=True, capture_output=True)
        if result.returncode:
            raise RuntimeError(result.stderr or result.stdout)
        original = source.with_name(source.name + "_original")
        backup = BACKUP / row["source"]
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(original), str(backup))
        target.parent.mkdir(parents=True, exist_ok=True)
        if source != target:
            source.rename(target)
        stamp = value.strftime("%Y:%m:%d %H:%M:%S+08:00")
        result = subprocess.run([EXIFTOOL, "-overwrite_original_in_place",
                                 f"-FileCreateDate={stamp}", f"-FileModifyDate={stamp}", str(target)],
                                text=True, capture_output=True)
        if result.returncode:
            raise RuntimeError(result.stderr or result.stdout)
        journal.append({**row, "backup": str(backup.relative_to(NAS))})
    check = subprocess.run([EXIFTOOL, "-j", "-DateTimeOriginal", "-CreateDate",
                            "-FileCreateDate", "-FileModifyDate", *[str(NAS / row["target"]) for row in PLAN]],
                           text=True, capture_output=True, check=True)
    values = json.loads(check.stdout)
    errors = []
    for row, actual in zip(PLAN, values):
        for tag in ("DateTimeOriginal", "CreateDate", "FileCreateDate", "FileModifyDate"):
            got = actual.get(tag, "")[:19].replace(":", "-", 2)
            if got != row["datetime"]:
                errors.append({"path": row["target"], "tag": tag, "expected": row["datetime"], "actual": got})
    report = {"updated": len(PLAN), "errors": errors, "status": "ok" if not errors else "failed"}
    (LOG / "journal.json").write_text(json.dumps(journal, ensure_ascii=False, indent=2))
    (LOG / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    run()
