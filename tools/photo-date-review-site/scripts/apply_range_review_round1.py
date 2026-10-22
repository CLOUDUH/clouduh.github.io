#!/usr/bin/env python3
"""Apply the first reviewed subset from photo-range-review.json."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path


NAS = Path("/Volumes/photo")
ROOT = Path(__file__).resolve().parents[1]
INPUT = Path("/Users/cloudu/Downloads/photo-range-review.json")
MANIFEST = ROOT / "public/range-review/review-items.json"
EXIFTOOL = "/opt/homebrew/bin/exiftool"
RUN = "range-review-round1-20260902"
LOG = NAS / "170900_备份/_operation_logs" / RUN
BACKUP = NAS / "170900_备份/metadata-originals" / RUN


def parse_dt(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


def note_date(note: str, current: datetime) -> datetime | None:
    compact = note.replace(" ", "")
    if "20190709" in compact:
        return current.replace(year=2019, month=7, day=9)
    if "18/11/18" in compact:
        return current.replace(year=2018, month=11, day=18)
    if "19/3/17" in compact:
        return current.replace(year=2019, month=3, day=17)
    return None


def note_folder(note: str) -> str | None:
    if "车队轴心" in note or "18/11/18" in note:
        return "181126_车队轴心"
    if "19/3/17" in note:
        return "190317_港西绿地"
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
    raise RuntimeError(f"No unique destination for {path}")


def write_dates(source: Path, value: datetime, backup: Path) -> None:
    backup.parent.mkdir(parents=True, exist_ok=True)
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
    if not original.exists():
        raise RuntimeError(f"No ExifTool backup for {source}")
    shutil.move(str(original), str(backup))


def set_file_times(path: Path, value: datetime) -> None:
    stamp = value.strftime("%Y:%m:%d %H:%M:%S+08:00")
    result = subprocess.run([EXIFTOOL, "-overwrite_original_in_place",
                             f"-FileCreateDate={stamp}", f"-FileModifyDate={stamp}", str(path)],
                            text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr or result.stdout)


def main() -> None:
    exported = json.loads(INPUT.read_text())
    manifest = json.loads(MANIFEST.read_text())
    items = {item["relativePath"]: item for item in manifest["items"]}
    actions = []
    for row in exported["reviews"]:
        note = row.get("notes", "").strip()
        current = parse_dt(row["currentCapture"])
        new_date = note_date(note, current)
        target_folder = note_folder(note)
        if not target_folder and row.get("decision") == "apply" and row.get("targetFolder") and row["targetFolder"] != row["currentFolder"]:
            target_folder = row["targetFolder"]
        if not new_date and not target_folder:
            continue
        source = row["relativePath"]
        folder = target_folder or row["currentFolder"]
        filename = rename_timestamp(Path(source).name, new_date) if new_date else Path(source).name
        actions.append({
            "id": row["id"],
            "source": source,
            "targetFolder": folder,
            "targetName": filename,
            "datetime": new_date.strftime("%Y-%m-%d %H:%M:%S") if new_date else row["currentCapture"],
            "metadataChange": bool(new_date),
            "note": note,
            "decision": row.get("decision", "unset"),
        })

    missing = [row["source"] for row in actions if not (NAS / row["source"]).exists()]
    if missing:
        raise SystemExit(json.dumps({"missing": missing}, ensure_ascii=False, indent=2))
    LOG.mkdir(parents=True, exist_ok=False)
    BACKUP.mkdir(parents=True, exist_ok=False)
    (LOG / "plan.json").write_text(json.dumps(actions, ensure_ascii=False, indent=2))
    journal = []
    item_by_id = {item["id"]: item for item in manifest["items"]}
    for row in actions:
        source = NAS / row["source"]
        value = parse_dt(row["datetime"])
        if row["metadataChange"]:
            backup = BACKUP / row["source"]
            write_dates(source, value, backup)
        target_dir = NAS / row["targetFolder"] / "photo"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / row["targetName"]
        if target != source:
            target = unique(target)
            source.rename(target)
        set_file_times(target, value)
        record = {**row, "target": str(target.relative_to(NAS))}
        journal.append(record)
        item = item_by_id.get(row["id"])
        if item:
            item["relativePath"] = record["target"]
            item["filename"] = target.name
            item["currentFolder"] = row["targetFolder"]
            if row["metadataChange"]:
                item["captureDate"] = row["datetime"]
                item["dateSource"] = "用户备注"
                item["fileCreateDate"] = value.strftime("%Y:%m:%d %H:%M:%S+08:00")
                item["fileModifyDate"] = value.strftime("%Y:%m:%d %H:%M:%S+08:00")
    manifest["generatedAt"] = datetime.now().astimezone().isoformat()
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    (LOG / "journal.json").write_text(json.dumps(journal, ensure_ascii=False, indent=2))

    verify = subprocess.run([EXIFTOOL, "-j", "-DateTimeOriginal", "-FileCreateDate", "-FileModifyDate",
                             *[str(NAS / row["target"]) for row in journal]], text=True, capture_output=True, check=True)
    values = json.loads(verify.stdout)
    errors = []
    for action, actual in zip(journal, values):
        expected = action["datetime"]
        for tag in ("FileCreateDate", "FileModifyDate"):
            got = actual.get(tag, "")[:19].replace(":", "-", 2)
            if got != expected:
                errors.append({"path": action["target"], "tag": tag, "expected": expected, "actual": got})
        if action["metadataChange"]:
            got = actual.get("DateTimeOriginal", "")[:19].replace(":", "-", 2)
            if got != expected:
                errors.append({"path": action["target"], "tag": "DateTimeOriginal", "expected": expected, "actual": got})
    report = {
        "actions": len(actions),
        "moves": sum(row["source"] != row["target"] for row in journal),
        "metadataChanges": sum(row["metadataChange"] for row in actions),
        "errors": errors,
        "status": "ok" if not errors else "failed",
    }
    (LOG / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
