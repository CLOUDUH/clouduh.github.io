#!/usr/bin/env python3
"""Synchronize root favorites with moved photo originals and relocate two clear outliers."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path


NAS = Path("/Volumes/photo")
ROOT = Path(__file__).resolve().parents[1]
SOURCE_LOG = ROOT / "tools-data/legacy-review-final.json"
OUTPUT_LOG = ROOT / "tools-data/sync-root-picks-and-ranges.json"
EXIFTOOL = "/opt/homebrew/bin/exiftool"

OUTLIERS = [
    {
        "source": "170701_高中毕业/photo/406de43c0cd55668.jpg",
        "target": "150000_高中生活/photo/406de43c0cd55668.jpg",
        "datetime": "2015-08-11 16:50:27",
        "reason": "2015-08-11明显属于高中生活",
    },
    {
        "source": "170701_高中毕业/photo/faceu_20171004173037.jpg",
        "target": "171002_国庆回家/photo/faceu_20171004173037.jpg",
        "datetime": "2017-10-04 17:30:37",
        "reason": "2017-10-04明显属于国庆回家",
    },
]


def write_dates(path: Path, value: datetime) -> None:
    exif = value.strftime("%Y:%m:%d %H:%M:%S")
    xmp = value.strftime("%Y-%m-%dT%H:%M:%S+08:00")
    result = subprocess.run([
        EXIFTOOL, "-overwrite_original_in_place", f"-EXIF:DateTimeOriginal={exif}",
        f"-EXIF:CreateDate={exif}", f"-EXIF:ModifyDate={exif}",
        f"-XMP-exif:DateTimeOriginal={exif}", f"-XMP-xmp:CreateDate={xmp}",
        f"-XMP-xmp:ModifyDate={xmp}", str(path),
    ], text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr or result.stdout)


def set_times(paths: list[Path]) -> None:
    result = subprocess.run([EXIFTOOL, "-overwrite_original_in_place",
                             "-FileCreateDate<DateTimeOriginal", "-FileModifyDate<DateTimeOriginal",
                             *map(str, paths)], text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr or result.stdout)


def main() -> None:
    prior = json.loads(SOURCE_LOG.read_text())
    root_sync = []
    for action in prior["actions"]:
        source = Path(action["source"])
        target = Path(action["actualTarget"])
        if source.parts[0] == target.parts[0]:
            continue
        root_source = NAS / source.parts[0] / source.name
        if not root_source.exists():
            continue
        root_target = NAS / target.parts[0] / target.name
        root_sync.append({
            "source": str(root_source.relative_to(NAS)),
            "target": str(root_target.relative_to(NAS)),
            "datetime": action["datetime"],
            "reason": "photo原片已跨文件夹，根目录精选同步移动",
        })

    actions = [*root_sync, *OUTLIERS]
    missing = [row["source"] for row in actions if not (NAS / row["source"]).exists()]
    collisions = [row["target"] for row in actions if (NAS / row["target"]).exists()]
    if missing or collisions:
        raise SystemExit(json.dumps({"missing": missing, "collisions": collisions}, ensure_ascii=False, indent=2))

    journal = []
    final_paths = []
    for row in actions:
        source = NAS / row["source"]
        target = NAS / row["target"]
        value = datetime.strptime(row["datetime"], "%Y-%m-%d %H:%M:%S")
        write_dates(source, value)
        target.parent.mkdir(parents=True, exist_ok=True)
        source.rename(target)
        final_paths.append(target)
        journal.append(row)
    set_times(final_paths)

    errors = []
    result = subprocess.run([EXIFTOOL, "-j", "-DateTimeOriginal", "-CreateDate", "-FileCreateDate", "-FileModifyDate",
                             *map(str, final_paths)], text=True, capture_output=True, check=True)
    for action, actual in zip(journal, json.loads(result.stdout)):
        for tag in ("DateTimeOriginal", "CreateDate", "FileCreateDate", "FileModifyDate"):
            got = actual.get(tag, "")[:19].replace(":", "-", 2)
            if got != action["datetime"]:
                errors.append({"path": action["target"], "tag": tag,
                               "expected": action["datetime"], "actual": got})
    report = {
        "rootFavoritesSynchronized": len(root_sync),
        "dateRangeRelocations": len(OUTLIERS),
        "actions": journal,
        "errors": errors,
        "status": "ok" if not errors else "failed",
    }
    OUTPUT_LOG.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({key: report[key] for key in ["rootFavoritesSynchronized", "dateRangeRelocations", "errors", "status"]}, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
