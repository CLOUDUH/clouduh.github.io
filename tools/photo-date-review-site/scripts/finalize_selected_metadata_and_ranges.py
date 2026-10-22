#!/usr/bin/env python3
"""Sync edited favorite metadata and relocate late photos from the holiday album."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path


NAS = Path("/Volumes/photo")
ROOT = Path(__file__).resolve().parents[1]
SYNC_PLAN = Path("/private/tmp/selected-metadata-sync.json")
LOG = ROOT / "tools-data/final-selected-metadata-and-ranges.json"
EXIFTOOL = "/opt/homebrew/bin/exiftool"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".gif", ".webp", ".tif", ".tiff", ".avif"}


def parse(value: str) -> datetime:
    return datetime.strptime(value[:19], "%Y:%m:%d %H:%M:%S")


def write_dates(path: Path, value: datetime) -> None:
    exif = value.strftime("%Y:%m:%d %H:%M:%S")
    xmp = value.strftime("%Y-%m-%dT%H:%M:%S+08:00")
    result = subprocess.run([
        EXIFTOOL, "-m", "-overwrite_original_in_place", f"-EXIF:DateTimeOriginal={exif}",
        f"-EXIF:CreateDate={exif}", f"-EXIF:ModifyDate={exif}",
        f"-XMP-exif:DateTimeOriginal={exif}", f"-XMP-xmp:CreateDate={xmp}",
        f"-XMP-xmp:ModifyDate={xmp}", str(path),
    ], text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr or result.stdout)


def set_times(paths: list[Path]) -> None:
    for start in range(0, len(paths), 300):
        chunk = paths[start:start + 300]
        result = subprocess.run([EXIFTOOL, "-overwrite_original_in_place",
                                 "-FileCreateDate<DateTimeOriginal", "-FileModifyDate<DateTimeOriginal",
                                 *map(str, chunk)], text=True, capture_output=True)
        if result.returncode:
            raise RuntimeError(result.stderr or result.stdout)


def unique(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(1, 10_000):
        candidate = path.with_name(f"{path.stem}__moved_{index}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"No unique target for {path}")


def late_holiday_photos() -> list[tuple[Path, datetime]]:
    folder = NAS / "180929_国庆游玩/photo"
    files = [path for path in folder.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_EXTS and "@eaDir" not in path.parts]
    rows = []
    for start in range(0, len(files), 300):
        result = subprocess.run([EXIFTOOL, "-j", "-DateTimeOriginal", "-CreateDate", *map(str, files[start:start + 300])],
                                text=True, capture_output=True, check=True)
        rows.extend(json.loads(result.stdout))
    threshold = datetime(2018, 10, 10, 23, 59, 59)
    late = []
    for row in rows:
        raw = row.get("DateTimeOriginal") or row.get("CreateDate")
        if not raw:
            continue
        value = parse(raw)
        if value > threshold:
            late.append((Path(row["SourceFile"]), value))
    return late


def main() -> None:
    sync_rows = json.loads(SYNC_PLAN.read_text())
    updated_paths = []
    sync_journal = []
    for row in sync_rows:
        value = parse(row["date"])
        targets = [NAS / row["root"], *[NAS / path for path in row["selected"]]]
        for target in targets:
            if not target.exists():
                raise FileNotFoundError(target)
            write_dates(target, value)
            updated_paths.append(target)
        sync_journal.append({**row, "datetime": value.strftime("%Y-%m-%d %H:%M:%S")})

    # One selected file was renamed during the earlier date correction. Align
    # both the root favorite and its copied selected version with that canonical name.
    special_date = datetime(2019, 12, 8, 19, 48, 13)
    special_root = NAS / "191201_比赛之后/IMG_20211111_194813_4.jpg"
    special_copy = NAS / "191201_比赛之后/photo/IMG_20211111_194813_4.jpg"
    special_root_target = NAS / "191201_比赛之后/IMG_20191208_194813_4.jpg"
    special_copy_target = NAS / "191201_比赛之后/photo/IMG_20191208_194813_4__selected.jpg"
    for source, target in [(special_root, special_root_target), (special_copy, special_copy_target)]:
        if not source.exists() or target.exists():
            raise RuntimeError(f"Special sync path conflict: {source} -> {target}")
        write_dates(source, special_date)
        source.rename(target)
        updated_paths.append(target)

    moved = []
    for source, value in late_holiday_photos():
        target = unique(NAS / "181013_车队轴心/photo" / source.name)
        source.rename(target)
        moved.append({"source": str(source.relative_to(NAS)), "target": str(target.relative_to(NAS)),
                      "datetime": value.strftime("%Y-%m-%d %H:%M:%S")})
        updated_paths.append(target)

    set_times(updated_paths)
    errors = []
    if any((NAS / row["source"]).exists() for row in moved):
        errors.append({"error": "some late holiday sources remain"})
    report = {
        "favoritePairsSynchronized": len(sync_rows),
        "favoriteFilesUpdated": sum(1 + len(row["selected"]) for row in sync_rows) + 2,
        "specialFavoriteRenamed": [str(special_root_target.relative_to(NAS)), str(special_copy_target.relative_to(NAS))],
        "holidayPhotosMovedToCarTeam": len(moved),
        "moved": moved,
        "errors": errors,
        "status": "ok" if not errors else "failed",
    }
    LOG.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({key: report[key] for key in ["favoritePairsSynchronized", "favoriteFilesUpdated", "specialFavoriteRenamed", "holidayPhotosMovedToCarTeam", "errors", "status"]}, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
