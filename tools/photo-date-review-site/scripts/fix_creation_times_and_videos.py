#!/usr/bin/env python3
"""Fix filesystem creation dates and move misplaced videos for 2017-2019 albums.

Dry-run by default. The audit source is the ExifTool JSON generated for the
current mounted library at /private/tmp/photo-creation-audit.json.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path


NAS = Path("/Volumes/photo")
AUDIT = Path("/private/tmp/photo-creation-audit.json")
EXIFTOOL = Path("/opt/homebrew/bin/exiftool")
RUN_NAME = "creation-times-and-videos-20260902"
LOG_ROOT = NAS / "170900_备份/_operation_logs" / RUN_NAME
BACKUP_ROOT = NAS / "170900_备份/metadata-originals" / RUN_NAME
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".avi", ".3gp", ".mpg", ".mpeg"}


@dataclass
class Decision:
    source: str
    final: str
    datetime: str
    basis: str
    write_metadata: bool
    move_video: bool


def parse_dt(value: str | None) -> datetime | None:
    if not value or value.startswith("0000:00:00"):
        return None
    text = value[:19]
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    return None


def folder_anchor(path: Path) -> datetime | None:
    name = path.relative_to(NAS).parts[0]
    if not re.match(r"^\d{6}", name):
        return None
    year, month, day = 2000 + int(name[:2]), max(1, int(name[2:4])), max(1, int(name[4:6]))
    try:
        return datetime(year, month, day)
    except ValueError:
        return None


def plausible(path: Path, value: datetime) -> bool:
    anchor = folder_anchor(path)
    return bool(anchor and abs((value - anchor).days) <= 400)


def filename_datetime(path: Path) -> datetime | None:
    stem = path.stem
    patterns = [
        r"(?<!\d)(20\d{2})[-_]?([01]\d)[-_]?([0-3]\d)[-_ T]?([0-2]\d)[-_:]?([0-5]\d)[-_:]?([0-5]\d)(?!\d)",
        r"(?<!\d)(\d{2})[-_]?([01]\d)[-_]?([0-3]\d)[-_ T]?([0-2]\d)[-_:]?([0-5]\d)[-_:]?([0-5]\d)(?!\d)",
    ]
    for pattern in patterns:
        match = re.search(pattern, stem)
        if not match:
            continue
        values = list(map(int, match.groups()))
        if values[0] < 100:
            values[0] += 2000
        try:
            return datetime(*values)
        except ValueError:
            continue
    return None


def filename_date_only(path: Path, fallback: datetime | None) -> datetime | None:
    match = re.search(r"(?<!\d)(20\d{2})[-_]([01]\d)[-_]([0-3]\d)(?!\d)", path.stem)
    if not match:
        return None
    try:
        date = datetime(*map(int, match.groups()))
    except ValueError:
        return None
    time = fallback.time() if fallback else datetime(2000, 1, 1, 12, 0, 0).time()
    return datetime.combine(date.date(), time)


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(1, 10_000):
        candidate = path.with_name(f"{path.stem}_{index}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"No unique path for {path}")


def renamed_user_override(path: Path, value: datetime) -> Path:
    if path.name != "wechat_190829_235957.jpg":
        return path
    return path.with_name(f"wechat_{value.strftime('%y%m%d_%H%M%S')}{path.suffix.lower()}")


def build_plan(rows: list[dict]) -> tuple[list[Decision], list[str]]:
    decisions: list[Decision] = []
    unresolved: list[str] = []
    for row in rows:
        source = Path(row["SourceFile"])
        relative = str(source.relative_to(NAS))
        mime = row.get("File:MIMEType", "")
        is_video = mime.startswith("video/") or source.suffix.lower() in VIDEO_EXTS
        dto = parse_dt(row.get("ExifIFD:DateTimeOriginal"))
        xmp_dto = parse_dt(row.get("XMP-exif:DateTimeOriginal"))
        user_dto = parse_dt(row.get("UserData:DateTimeOriginal"))
        quicktime = parse_dt(row.get("QuickTime:CreateDate"))
        file_create = parse_dt(row.get("MacOS:FileCreateDate"))
        file_modify = parse_dt(row.get("System:FileModifyDate"))
        name_dt = filename_datetime(source)
        date_only = filename_date_only(source, file_create)
        value = None
        basis = ""
        write_metadata = False

        if source.name == "wechat_190829_235957.jpg":
            value = datetime(2019, 3, 16, 14, 48, 58)
            basis = "用户明确指定2019-03-16；沿用原文件时间14:48:58"
            write_metadata = True
        elif dto:
            value, basis = dto, "EXIF DateTimeOriginal"
            create = parse_dt(row.get("ExifIFD:CreateDate"))
            write_metadata = create is None
        elif user_dto or xmp_dto:
            value = user_dto or xmp_dto
            basis = "视频/图像现有 DateTimeOriginal"
        elif is_video and quicktime and plausible(source, quicktime):
            value, basis = quicktime, "QuickTime CreateDate"
        elif name_dt and plausible(source, name_dt):
            value, basis = name_dt, "可信文件名日期"
            write_metadata = not is_video
        elif date_only and plausible(source, date_only):
            value, basis = date_only, "文件名日期；沿用原创建时分秒"
            write_metadata = not is_video
        elif not is_video and source.name != "IMG_2248.PNG" and file_modify and file_create and file_create.year >= 2026 and plausible(source, file_modify):
            value, basis = file_modify, "创建时间被重置；沿用可信文件修改时间"
        elif not is_video and file_create and file_modify and file_modify.year >= 2026 and plausible(source, file_create):
            value, basis = file_create, "修改时间被重置；沿用可信文件创建时间"

        move_video = is_video and source.parent.name != "video"
        final = source
        if move_video:
            top = source.relative_to(NAS).parts[0]
            final = NAS / top / "video" / source.name
        final = renamed_user_override(final, value) if value else final

        if value:
            decisions.append(Decision(relative, str(final.relative_to(NAS)), value.strftime("%Y-%m-%d %H:%M:%S"),
                                      basis, write_metadata, move_video))
        elif move_video:
            decisions.append(Decision(relative, str(final.relative_to(NAS)), "", "仅整理视频位置；日期无可靠依据",
                                      False, True))
            unresolved.append(relative)
        else:
            unresolved.append(relative)
    return decisions, unresolved


def write_image_metadata(source: Path, value: datetime, backup: Path) -> Path:
    backup.parent.mkdir(parents=True, exist_ok=True)
    working = source
    if source.suffix.lower() in {".jpg", ".jpeg"}:
        with source.open("rb") as fh:
            if fh.read(8) == b"\x89PNG\r\n\x1a\n":
                working = unique_path(source.with_suffix(".png"))
                source.rename(working)
    stamp = value.strftime("%Y:%m:%d %H:%M:%S")
    iso = value.strftime("%Y-%m-%dT%H:%M:%S+08:00")
    result = subprocess.run([
        str(EXIFTOOL), f"-EXIF:DateTimeOriginal={stamp}", f"-EXIF:CreateDate={stamp}",
        f"-EXIF:ModifyDate={stamp}", f"-XMP-exif:DateTimeOriginal={stamp}",
        f"-XMP-xmp:CreateDate={iso}", f"-XMP-xmp:ModifyDate={iso}", str(working),
    ], text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr or result.stdout)
    original = working.with_name(working.name + "_original")
    if not original.exists():
        raise RuntimeError(f"No ExifTool backup for {working}")
    if backup.exists():
        raise RuntimeError(f"Backup exists: {backup}")
    shutil.move(str(original), str(backup))
    return working


def set_explicit_file_times(path: Path, value: datetime) -> None:
    stamp = value.strftime("%Y:%m:%d %H:%M:%S+08:00")
    result = subprocess.run([str(EXIFTOOL), "-overwrite_original_in_place",
                             f"-FileCreateDate={stamp}", f"-FileModifyDate={stamp}", str(path)],
                            text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr or result.stdout)


def set_times_from_tag(paths: list[Path], tag: str, quicktime_utc: bool = False) -> None:
    for start in range(0, len(paths), 400):
        chunk = paths[start:start + 400]
        command = [str(EXIFTOOL), "-overwrite_original_in_place"]
        if quicktime_utc:
            command += ["-api", "QuickTimeUTC=1"]
        command += [f"-FileCreateDate<{tag}", f"-FileModifyDate<{tag}", *map(str, chunk)]
        result = subprocess.run(command, text=True, capture_output=True)
        if result.returncode:
            raise RuntimeError(result.stderr or result.stdout)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    rows = json.loads(AUDIT.read_text())
    decisions, unresolved = build_plan(rows)
    by_source = {row["source"]: row for row in map(asdict, decisions)}
    video_moves = [x for x in decisions if x.move_video]
    metadata_writes = [x for x in decisions if x.write_metadata]
    dated = [x for x in decisions if x.datetime]
    summary = {
        "mode": "apply" if args.apply else "dry-run",
        "scanned": len(rows), "dated": len(dated),
        "metadata_writes": len(metadata_writes), "video_moves": len(video_moves),
        "unresolved": len(unresolved),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not args.apply:
        print(json.dumps({"decisions": [asdict(x) for x in decisions], "unresolved": unresolved}, ensure_ascii=False, indent=2))
        return

    LOG_ROOT.mkdir(parents=True, exist_ok=False)
    BACKUP_ROOT.mkdir(parents=True, exist_ok=False)
    (LOG_ROOT / "audit-before.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2))
    (LOG_ROOT / "plan.json").write_text(json.dumps({"summary": summary, "decisions": [asdict(x) for x in decisions],
                                                     "unresolved": unresolved}, ensure_ascii=False, indent=2))
    journal = LOG_ROOT / "journal.jsonl"
    final_paths: dict[str, Path] = {}
    with journal.open("a") as out:
        for index, decision in enumerate(metadata_writes, start=1):
            source = NAS / decision.source
            value = datetime.strptime(decision.datetime, "%Y-%m-%d %H:%M:%S")
            backup = BACKUP_ROOT / decision.source
            working = write_image_metadata(source, value, backup)
            final_paths[decision.source] = working
            out.write(json.dumps({"kind": "metadata", "source": decision.source,
                                  "working": str(working.relative_to(NAS)), "backup": str(backup.relative_to(NAS)),
                                  "datetime": decision.datetime, "basis": decision.basis}, ensure_ascii=False) + "\n")
            out.flush()
            if index % 20 == 0:
                print(f"PROGRESS metadata {index}/{len(metadata_writes)}", flush=True)

        # Move/rename after internal metadata writes. No file is deleted.
        for decision in decisions:
            source = final_paths.get(decision.source, NAS / decision.source)
            target = NAS / decision.final
            if source.suffix.lower() == ".png" and target.suffix.lower() in {".jpg", ".jpeg"}:
                target = target.with_suffix(".png")
            if target != source:
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    target = unique_path(target)
                source.rename(target)
            final_paths[decision.source] = target
            if decision.move_video or target.name != Path(decision.source).name:
                out.write(json.dumps({"kind": "move", "source": decision.source,
                                      "target": str(target.relative_to(NAS)), "video": decision.move_video}, ensure_ascii=False) + "\n")
                out.flush()

        # Apply filesystem times after every move/rename. Most can be copied
        # from an embedded tag in a few efficient ExifTool batches.
        dto_group, qt_group, explicit_group = [], [], []
        for decision in dated:
            target = final_paths.get(decision.source, NAS / decision.final)
            if decision.write_metadata or "DateTimeOriginal" in decision.basis:
                dto_group.append(target)
            elif decision.basis == "QuickTime CreateDate":
                qt_group.append(target)
            else:
                explicit_group.append((target, datetime.strptime(decision.datetime, "%Y-%m-%d %H:%M:%S")))
        set_times_from_tag(dto_group, "DateTimeOriginal")
        print(f"PROGRESS filesystem DateTimeOriginal {len(dto_group)}", flush=True)
        set_times_from_tag(qt_group, "QuickTime:CreateDate", quicktime_utc=True)
        print(f"PROGRESS filesystem QuickTime {len(qt_group)}", flush=True)
        for target, value in explicit_group:
            set_explicit_file_times(target, value)
        print(f"PROGRESS filesystem explicit {len(explicit_group)}", flush=True)

    # Batch readback verification.
    verify_targets = [str(final_paths.get(x.source, NAS / x.final)) for x in dated]
    result = subprocess.run([str(EXIFTOOL), "-j", "-FileCreateDate", "-FileModifyDate", *verify_targets],
                            text=True, capture_output=True, check=True)
    readback = {row["SourceFile"]: row for row in json.loads(result.stdout)}
    errors = []
    for decision in dated:
        target = str(final_paths.get(decision.source, NAS / decision.final))
        expected = decision.datetime
        row = readback[target]
        for tag in ("FileCreateDate", "FileModifyDate"):
            actual = row.get(tag, "")[:19].replace(":", "-", 2)
            if actual != expected:
                errors.append({"path": str(Path(target).relative_to(NAS)), "tag": tag,
                               "expected": expected, "actual": actual})
    report = {**summary, "checked": len(dated), "errors": errors,
              "status": "ok" if not errors else "failed",
              "video_targets": [str(final_paths[x.source].relative_to(NAS)) for x in video_moves]}
    (LOG_ROOT / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
