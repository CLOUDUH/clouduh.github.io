#!/usr/bin/env python3
"""Apply explicit album moves, synchronized root picks, and folder merges."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path


NAS = Path("/Volumes/photo")
ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "public/favorite-picker/manifest.json"
LOG = ROOT / "tools-data/album-merges-and-moves.json"
EXIFTOOL = "/opt/homebrew/bin/exiftool"

MERGES = [
    ("181126_车队轴心", "181013_车队轴心"),
    ("190317_港西绿地", "190302_大二下开学"),
    ("191026_大三比赛后", "191201_比赛之后"),
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def unique(path: Path, suffix: str = "__merged") -> Path:
    if not path.exists():
        return path
    for index in range(1, 10_000):
        candidate = path.with_name(f"{path.stem}{suffix}_{index}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"No unique target for {path}")


def parse_name_time(name: str) -> datetime | None:
    match = re.search(r"(20\d{2})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})", name)
    if not match:
        return None
    return datetime(*map(int, match.groups()))


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


def set_file_times(paths: list[Path]) -> None:
    for start in range(0, len(paths), 300):
        chunk = paths[start:start + 300]
        result = subprocess.run([EXIFTOOL, "-overwrite_original_in_place",
                                 "-FileCreateDate<DateTimeOriginal", "-FileModifyDate<DateTimeOriginal",
                                 *map(str, chunk)], text=True, capture_output=True)
        if result.returncode:
            raise RuntimeError(result.stderr or result.stdout)


def move_photo(source_rel: str, target_folder: str, value: datetime, journal: list[dict], final_paths: list[Path]) -> None:
    source = NAS / source_rel
    if not source.exists():
        raise FileNotFoundError(source)
    source_folder = Path(source_rel).parts[0]
    write_dates(source, value)
    target = NAS / target_folder / "photo" / source.name
    target.parent.mkdir(parents=True, exist_ok=True)
    target = unique(target, "__moved") if target.exists() else target
    source.rename(target)
    final_paths.append(target)
    record = {"kind": "photo_move", "source": source_rel, "target": str(target.relative_to(NAS)),
              "datetime": value.strftime("%Y-%m-%d %H:%M:%S")}

    root_source = NAS / source_folder / Path(source_rel).name
    if root_source.exists():
        write_dates(root_source, value)
        root_target = NAS / target_folder / target.name
        root_target = unique(root_target, "__selected") if root_target.exists() else root_target
        root_source.rename(root_target)
        final_paths.append(root_target)
        record["rootPickTarget"] = str(root_target.relative_to(NAS))
    journal.append(record)


def merge_folder(source_name: str, target_name: str, journal: list[dict]) -> None:
    source = NAS / source_name
    target = NAS / target_name
    if not source.is_dir() or not target.is_dir():
        raise FileNotFoundError(f"Merge folder missing: {source} or {target}")
    moved = 0
    exact_duplicates = 0
    renamed_conflicts = 0
    files = [path for path in source.rglob("*") if path.is_file() and "@eaDir" not in path.parts]
    for path in files:
        relative = path.relative_to(source)
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if path.stat().st_size == destination.stat().st_size and sha256(path) == sha256(destination):
                path.unlink()
                exact_duplicates += 1
                continue
            destination = unique(destination, f"__merged_{source_name[:6]}")
            renamed_conflicts += 1
        path.rename(destination)
        moved += 1
    for directory in sorted([path for path in source.rglob("*") if path.is_dir()], key=lambda p: len(p.parts), reverse=True):
        try:
            directory.rmdir()
        except OSError:
            pass
    source.rmdir()
    journal.append({"kind": "folder_merge", "source": source_name, "target": target_name,
                    "moved": moved, "exactDuplicatesRecycled": exact_duplicates,
                    "renamedConflicts": renamed_conflicts})


def main() -> None:
    manifest = json.loads(MANIFEST.read_text())
    school = next(folder for folder in manifest["folders"] if folder["event"] == "180906_大二开学")
    names = [photo["filename"] for photo in school["photos"]]
    start = names.index("IMG_20180928_201453.jpg")
    end = names.index("IMG_20180930_084936.jpg")
    interval = school["photos"][start:end + 1]

    explicit = {
        "13f4f9ffbbf692c9.jpg": datetime(2018, 9, 29, 17, 17, 42),
        "5c9250beffabfb0.jpg": datetime(2018, 9, 29, 9, 7, 56),
        "CLOUDUH_180929210953.jpg": datetime(2018, 9, 29, 21, 9, 53),
        "qq_pic_merged_1538461404727.jpg": datetime(2018, 9, 29, 19, 56, 30),
    }
    planned = [
        ("171204_大一冬天/photo/2017-09-15(88).jpg", "170904_开学", datetime(2017, 9, 15, 21, 16, 8)),
        ("190710_锦州旅行/photo/IMG_4172.JPG", "150000_高中生活", datetime(2015, 7, 15, 22, 31, 58)),
        ("190710_锦州旅行/photo/IMG_4173.JPG", "150000_高中生活", datetime(2015, 7, 15, 22, 32, 7)),
    ]
    for name, value in explicit.items():
        planned.append((f"180906_大二开学/photo/{name}", "180930_国庆游玩", value))
    for photo in interval:
        value = parse_name_time(photo["filename"])
        if not value:
            raise RuntimeError(f"Cannot parse interval filename: {photo['filename']}")
        planned.append((photo["relativePath"], "180930_国庆游玩", value))

    if (NAS / "180929_国庆游玩").exists():
        raise RuntimeError("180929_国庆游玩 already exists")
    missing = [source for source, _, _ in planned if not (NAS / source).exists()]
    if missing:
        raise SystemExit(json.dumps({"missing": missing}, ensure_ascii=False, indent=2))

    journal: list[dict] = []
    final_paths: list[Path] = []
    for source, target, value in planned:
        move_photo(source, target, value, journal, final_paths)
    set_file_times(final_paths)

    for source, target in MERGES:
        merge_folder(source, target, journal)

    old_trip = NAS / "180930_国庆游玩"
    new_trip = NAS / "180929_国庆游玩"
    old_trip.rename(new_trip)
    for record in journal:
        if record.get("target", "").startswith("180930_国庆游玩/"):
            record["target"] = "180929_国庆游玩/" + record["target"].split("/", 1)[1]
        if record.get("rootPickTarget", "").startswith("180930_国庆游玩/"):
            record["rootPickTarget"] = "180929_国庆游玩/" + record["rootPickTarget"].split("/", 1)[1]

    errors = []
    for record in journal:
        if record["kind"] == "photo_move" and not (NAS / record["target"]).exists():
            errors.append({"path": record["target"], "error": "missing after move"})
        if record["kind"] == "folder_merge" and (NAS / record["source"]).exists():
            errors.append({"folder": record["source"], "error": "source folder remains"})
    report = {"explicitPhotoMoves": len(planned),
              "rootPicksMovedWithPhotos": sum("rootPickTarget" in row for row in journal),
              "folderMerges": [row for row in journal if row["kind"] == "folder_merge"],
              "tripFolderRenamed": "180930_国庆游玩 -> 180929_国庆游玩",
              "journal": journal, "errors": errors, "status": "ok" if not errors else "failed"}
    LOG.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({key: report[key] for key in ["explicitPhotoMoves", "rootPicksMovedWithPhotos", "folderMerges", "tripFolderRenamed", "errors", "status"]}, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
