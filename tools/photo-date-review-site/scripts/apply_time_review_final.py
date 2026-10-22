#!/usr/bin/env python3
"""Apply free-text date corrections from photo-range-review (2).json."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path


NAS = Path("/Volumes/photo")
ROOT = Path(__file__).resolve().parents[1]
INPUT = Path("/Users/cloudu/Downloads/photo-range-review (2).json")
AUDIT = Path("/private/tmp/photo-date-v2-audit.json")
MANIFEST = ROOT / "public/range-review/review-items.json"
EXIFTOOL = "/opt/homebrew/bin/exiftool"
RUN = "time-review-final-20260902"
LOG = NAS / "170900_备份/_operation_logs" / RUN
BACKUP = NAS / "170900_备份/metadata-originals" / RUN

EXACT_DUPLICATES = {
    "190901_比赛之前/0.jpg": "191201_比赛之后/photo/0.jpg",
    "210209_虎年回家/IMG_20211111_191516_1.jpg": "200300_新年与疫情/photo/IMG_20211111_191516_1.jpg",
}
SPECIAL_DATES = {
    "200300_新年与疫情/photo/IMG_20211111_191516_1.jpg": datetime(2020, 1, 30, 19, 15, 16),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_datetime(value: str | None) -> datetime | None:
    if not value or value == "无":
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y:%m:%d %H:%M:%S"):
        try:
            return datetime.strptime(value[:19], fmt)
        except ValueError:
            pass
    return None


def audit_fallbacks() -> dict[str, datetime]:
    doc = json.loads(AUDIT.read_text())
    result = {}
    for row in doc["rows"]:
        rel = str(Path(row["SourceFile"]).relative_to(NAS))
        value = parse_datetime(row.get("System:FileModifyDate")) or parse_datetime(row.get("MacOS:FileCreateDate"))
        if value:
            result[rel] = value
    return result


def filename_clock(path: Path, date: datetime) -> tuple[int, int, int] | None:
    match = re.search(r"(20\d{2})-(\d{2})-(\d{2})[ _](\d{2})[.:](\d{2})[.:](\d{2})", path.stem)
    if not match:
        return None
    year, month, day, hour, minute, second = map(int, match.groups())
    if (year, month, day) != (date.year, date.month, date.day):
        return None
    return hour, minute, second


def resolve_text(path: str, text: str, base: datetime) -> datetime | None:
    if path in SPECIAL_DATES:
        return SPECIAL_DATES[path]
    compact = text.replace(" ", "")
    if "当前拍摄时间正确" in compact:
        return None
    if path.startswith("200300_新年与疫情/photo/IMG_") and not compact:
        number = re.search(r"IMG_(\d{4})", Path(path).name)
        if number and 2203 <= int(number.group(1)) <= 2309:
            return base.replace(year=2020)
    if "改为19年相同的日期" in compact:
        return base.replace(year=2019)

    patterns = [
        r"(?P<y>\d{2})年(?P<m>\d{1,2})月(?P<d>\d{1,2})日",
        r"(?P<y>\d{2})年(?P<m>\d{1,2})/(?P<d>\d{1,2})",
        r"(?P<y>\d{2})/(?P<m>\d{1,2})/(?P<d>\d{1,2})",
    ]
    for pattern in patterns:
        match = re.search(pattern, compact)
        if not match:
            continue
        year = 2000 + int(match.group("y"))
        result = base.replace(year=year, month=int(match.group("m")), day=int(match.group("d")))
        clock = filename_clock(Path(path), result)
        if clock:
            result = result.replace(hour=clock[0], minute=clock[1], second=clock[2])
        return result

    year_match = re.search(r"(?<!\d)(19|20|21)年", compact)
    if year_match:
        return base.replace(year=2000 + int(year_match.group(1)))
    return None


def rename_timestamp(filename: str, value: datetime) -> str:
    stem, suffix = os.path.splitext(filename)
    patterns = [
        (re.compile(r"(?<!\d)(20\d{2})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})(?!\d)"), value.strftime("%Y%m%d_%H%M%S")),
        (re.compile(r"(?<!\d)(20\d{2})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})(?!\d)"), value.strftime("%Y%m%d%H%M%S")),
        (re.compile(r"(?<!\d)(\d{2})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})(?!\d)"), value.strftime("%y%m%d_%H%M%S")),
        (re.compile(r"(?<!\d)(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})(?!\d)"), value.strftime("%y%m%d%H%M%S")),
    ]
    for pattern, replacement in patterns:
        match = pattern.search(stem)
        if not match:
            continue
        year = int(match.group(1))
        if year < 100:
            year += 2000
        try:
            old = datetime(year, int(match.group(2)), int(match.group(3)))
        except ValueError:
            continue
        if old.date() == value.date():
            return filename
        return stem[:match.start()] + replacement + stem[match.end():] + suffix
    return filename


def unique(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(1, 10_000):
        candidate = path.with_name(f"{path.stem}_{index}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"No unique path for {path}")


def build_plan() -> tuple[list[dict], list[dict], list[dict]]:
    exported = json.loads(INPUT.read_text())
    fallbacks = audit_fallbacks()
    rows_by_path = {row["relativePath"]: row for row in exported["reviews"]}
    # The more specific duplicate note supplies the date for the canonical copy.
    rows_by_path["200300_新年与疫情/photo/IMG_20211111_191516_1.jpg"]["timeText"] = "20/1/30"

    actions, unresolved = [], []
    for row in exported["reviews"]:
        path = row["relativePath"]
        if path in EXACT_DUPLICATES:
            continue
        if row.get("decision") == "keep":
            continue
        base = parse_datetime(row.get("currentCapture")) or fallbacks.get(path)
        if not base:
            unresolved.append({"path": path, "reason": "无可用于保留时分秒的基础时间"})
            continue
        text = row.get("timeText", "") or ""
        value = resolve_text(path, text, base)
        if not value:
            unresolved.append({"path": path, "reason": f"无法解析时间说明：{text}"})
            continue
        target_folder = row.get("targetFolder") or row["currentFolder"]
        target_name = rename_timestamp(Path(path).name, value)
        if target_folder == row["currentFolder"]:
            target = str(Path(path).with_name(target_name))
        else:
            target = str(Path(target_folder) / "photo" / target_name)
        actions.append({
            "id": row["id"], "source": path, "target": target,
            "datetime": value.strftime("%Y-%m-%d %H:%M:%S"),
            "timeText": text, "targetFolder": target_folder,
        })

    duplicate_deletes = []
    for drop, keep in EXACT_DUPLICATES.items():
        if not (NAS / drop).exists() or not (NAS / keep).exists():
            unresolved.append({"path": drop, "reason": "重复项或保留项缺失"})
            continue
        drop_hash, keep_hash = sha256(NAS / drop), sha256(NAS / keep)
        if drop_hash != keep_hash:
            unresolved.append({"path": drop, "reason": "预期重复项的SHA-256不一致"})
            continue
        duplicate_deletes.append({"path": drop, "keep": keep, "sha256": drop_hash})
    return actions, duplicate_deletes, unresolved


def write_metadata(path: Path, value: datetime, backup: Path) -> None:
    backup.parent.mkdir(parents=True, exist_ok=True)
    exif = value.strftime("%Y:%m:%d %H:%M:%S")
    xmp = value.strftime("%Y-%m-%dT%H:%M:%S+08:00")
    result = subprocess.run([
        EXIFTOOL, f"-EXIF:DateTimeOriginal={exif}", f"-EXIF:CreateDate={exif}",
        f"-EXIF:ModifyDate={exif}", f"-XMP-exif:DateTimeOriginal={exif}",
        f"-XMP-xmp:CreateDate={xmp}", f"-XMP-xmp:ModifyDate={xmp}", str(path),
    ], text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr or result.stdout)
    original = path.with_name(path.name + "_original")
    if not original.exists():
        raise RuntimeError(f"No ExifTool backup for {path}")
    shutil.move(str(original), str(backup))


def set_file_times(path: Path, value: datetime) -> None:
    stamp = value.strftime("%Y:%m:%d %H:%M:%S+08:00")
    result = subprocess.run([EXIFTOOL, "-overwrite_original_in_place",
                             f"-FileCreateDate={stamp}", f"-FileModifyDate={stamp}", str(path)],
                            text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr or result.stdout)


def apply(actions: list[dict], deletes: list[dict]) -> None:
    missing = [row["source"] for row in actions if not (NAS / row["source"]).exists()]
    if missing:
        raise SystemExit(json.dumps({"missing": missing}, ensure_ascii=False, indent=2))
    LOG.mkdir(parents=True, exist_ok=False)
    BACKUP.mkdir(parents=True, exist_ok=False)
    (LOG / "plan.json").write_text(json.dumps({"actions": actions, "duplicateDeletes": deletes}, ensure_ascii=False, indent=2))
    journal = []
    for index, row in enumerate(actions, start=1):
        source = NAS / row["source"]
        value = parse_datetime(row["datetime"])
        backup = BACKUP / row["source"]
        write_metadata(source, value, backup)
        target = NAS / row["target"]
        target.parent.mkdir(parents=True, exist_ok=True)
        if target != source:
            target = unique(target)
            source.rename(target)
        set_file_times(target, value)
        journal.append({**row, "actualTarget": str(target.relative_to(NAS)),
                        "backup": str(backup.relative_to(NAS))})
        if index % 20 == 0:
            print(f"PROGRESS {index}/{len(actions)}", flush=True)

    # Exact duplicate sources are removed only after their canonical copies
    # have been updated successfully. Synology's recycle bin remains recoverable.
    for row in deletes:
        path = NAS / row["path"]
        if sha256(path) != row["sha256"]:
            raise RuntimeError(f"Duplicate changed before deletion: {path}")
        path.unlink()

    errors = []
    for row in journal:
        result = subprocess.run([EXIFTOOL, "-j", "-DateTimeOriginal", "-CreateDate", "-FileCreateDate", "-FileModifyDate",
                                 str(NAS / row["actualTarget"])], text=True, capture_output=True, check=True)
        actual = json.loads(result.stdout)[0]
        for tag in ("DateTimeOriginal", "CreateDate", "FileCreateDate", "FileModifyDate"):
            got = actual.get(tag, "")[:19].replace(":", "-", 2)
            if got != row["datetime"]:
                errors.append({"path": row["actualTarget"], "tag": tag,
                               "expected": row["datetime"], "actual": got})
    for row in deletes:
        if (NAS / row["path"]).exists():
            errors.append({"path": row["path"], "error": "duplicate still present"})

    manifest = json.loads(MANIFEST.read_text())
    manifest["items"] = []
    manifest["count"] = 0
    manifest["generatedAt"] = datetime.now().astimezone().isoformat()
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    (LOG / "journal.json").write_text(json.dumps(journal, ensure_ascii=False, indent=2))
    report = {"metadataChanges": len(actions),
              "movedOrRenamed": sum(row["source"] != row["actualTarget"] for row in journal),
              "exactDuplicatesRecycled": len(deletes), "errors": errors,
              "status": "ok" if not errors else "failed"}
    (LOG / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    actions, deletes, unresolved = build_plan()
    summary = {"actions": len(actions), "duplicateDeletes": len(deletes), "unresolved": unresolved}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if unresolved:
        raise SystemExit(2)
    if args.apply:
        apply(actions, deletes)


if __name__ == "__main__":
    main()
