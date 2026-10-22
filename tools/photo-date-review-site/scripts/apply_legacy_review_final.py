#!/usr/bin/env python3
"""Apply grouped and per-photo notes from photo-range-review (3).json."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path


NAS = Path("/Volumes/photo")
ROOT = Path(__file__).resolve().parents[1]
INPUT = Path("/Users/cloudu/Downloads/photo-range-review (3).json")
MANIFEST = ROOT / "public/range-review/review-items.json"
LOG = ROOT / "tools-data/legacy-review-final.json"
EXIFTOOL = "/opt/homebrew/bin/exiftool"


def stable_time(relative: str) -> tuple[int, int, int]:
    digest = hashlib.sha1(relative.encode()).digest()
    return 9 + digest[0] % 12, digest[1] % 60, digest[2] % 60


def at_date(relative: str, year: int, month: int, day: int, base: datetime | None = None) -> datetime:
    hour, minute, second = (base.hour, base.minute, base.second) if base else stable_time(relative)
    return datetime(year, month, day, hour, minute, second)


def parse_current(value: str | None) -> datetime | None:
    if not value or value == "无":
        return None
    try:
        return datetime.strptime(value[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def filename_date(path: str) -> datetime | None:
    stem = Path(path).stem
    patterns = [
        r"(?<!\d)(20\d{2})[-_]?([01]\d)[-_]?([0-3]\d)[-_ T]?([0-2]\d)[-_.:]?([0-5]\d)[-_.:]?([0-5]\d)(?!\d)",
        r"(?<!\d)(\d{2})[-_]?([01]\d)[-_]?([0-3]\d)[-_ T]?([0-2]\d)[-_.:]?([0-5]\d)[-_.:]?([0-5]\d)(?!\d)",
    ]
    for pattern in patterns:
        match = re.search(pattern, stem)
        if match:
            values = list(map(int, match.groups()))
            if values[0] < 100:
                values[0] += 2000
            try:
                return datetime(*values)
            except ValueError:
                pass
    match = re.search(r"(?<!\d)(20\d{2})[-_]([01]\d)[-_]([0-3]\d)(?!\d)", stem)
    if match:
        try:
            return datetime(*map(int, match.groups()))
        except ValueError:
            pass
    return None


def month_value(relative: str, year: int, month: int, base: datetime | None = None, preferred_day: int | None = None) -> datetime:
    named = filename_date(relative)
    day = preferred_day or (named.day if named and named.month == month else 15)
    return at_date(relative, year, month, day, base)


def explicit_text_date(relative: str, text: str, base: datetime | None, default_year: int) -> datetime | None:
    compact = text.replace(" ", "")
    if not compact:
        return None
    if "七夕" in compact:
        return at_date(relative, 2014, 8, 2, base)
    if "国庆回家" in compact:
        return datetime(2017, 10, 3, 20, 0, 10)
    if "报到文件夹" in compact:
        return at_date(relative, 2017, 9, 1, base)
    if "按名字的日期" in compact or "按标题的日期" in compact or "标签日期" in compact:
        return filename_date(relative)
    full_patterns = [
        r"(?P<y>\d{2})年(?P<m>\d{1,2})月(?P<d>\d{1,2})(?:日)?",
        r"(?P<y>\d{2})/(?P<m>\d{1,2})月(?P<d>\d{1,2})(?:日)?",
        r"(?P<y>\d{2})[/-](?P<m>\d{1,2})[/-](?P<d>\d{1,2})(?:日)?",
        r"(?P<y>\d{2})-(?P<m>\d{1,2})-(?P<d>\d{1,2})",
    ]
    for pattern in full_patterns:
        match = re.search(pattern, compact)
        if match:
            return at_date(relative, 2000 + int(match.group("y")), int(match.group("m")), int(match.group("d")), base)
    month_match = re.search(r"(?P<y>\d{2})(?:年|/)(?P<m>\d{1,2})月", compact)
    if month_match:
        return month_value(relative, 2000 + int(month_match.group("y")), int(month_match.group("m")), base)
    match = re.search(r"(?<!\d)(?P<m>\d{1,2})/(?P<d>\d{1,2})(?!\d)", compact)
    if match and int(match.group("m")) <= 12:
        return at_date(relative, default_year, int(match.group("m")), int(match.group("d")), base)
    match = re.search(r"(?:(\d{2})年)(\d{1,2})月", compact)
    if match:
        return month_value(relative, 2000 + int(match.group(1)), int(match.group(2)), base)
    return None


def special_150000(relative: str, text: str, base: datetime | None) -> datetime | None:
    name = Path(relative).name
    if name == "CLOUDUH_220112241608.jpg" or name == "1512318720010.jpeg":
        return month_value(relative, 2017, 7, base)
    if name == "CLOUDUH_220112241620.jpg":
        return at_date(relative, 2017, 7, 27, base)
    if name == "CLOUDUH_220123253238.jpg":
        return at_date(relative, 2015, 10, 1, base)
    if name in {"CLOUDUH_220112241633.jpg", "wechat_180503_144657.jpg"}:
        return at_date(relative, 2016, 2, 8, base)
    if name in {"wechat_180503_144638.jpg", "wechat_180503_144651.jpg"}:
        return filename_date(relative)
    value = explicit_text_date(relative, text, base, 2015)
    if value:
        return value
    return filename_date(relative)


def build_plan() -> tuple[list[dict], list[dict]]:
    exported = json.loads(INPUT.read_text())
    actions, unresolved = [], []
    rows = exported["reviews"]
    for index, row in enumerate(rows):
        rel = row["relativePath"]
        folder = row["currentFolder"]
        text = row.get("timeText", "") or ""
        base = parse_current(row.get("currentCapture"))
        target = row.get("targetFolder") or folder
        value = None

        if folder == "050000_小时候":
            unresolved.append({"path": rel, "reason": "没有备注或整组日期规则"})
            continue
        if folder == "090000_小学生活":
            if target == "110600_初中":
                value = base or filename_date(rel)
            else:
                value = at_date(rel, 2010, 6, 1, base)
        elif folder == "101206_广电演出":
            value = at_date(rel, 2010, 11, 8, base)
            target = "101108_广电演出"
        elif folder == "110600_初中":
            if "大二暑假" in text:
                value = at_date(rel, 2018, 8, 15, base)
                target = "180700_大一暑假"
            elif target == "150000_高中生活" or "15年的7月" in text:
                value = month_value(rel, 2015, 7, base)
                target = "150000_高中生活"
            else:
                value = explicit_text_date(rel, text, base, 2014) or at_date(rel, 2014, 7, 1, base)
        elif folder == "140618_小学聚会":
            value = at_date(rel, 2014, 6, 18, base)
        elif folder == "150000_高中生活":
            value = special_150000(rel, text, base)
        elif folder == "150800_胶东游":
            value = at_date(rel, 2015, 8, 31, base)
        elif folder == "170701_高中毕业":
            value = explicit_text_date(rel, text, base, 2017)
            if "国庆回家" in text:
                target = "171002_国庆回家"
            elif "报到文件夹" in text:
                target = "170901_报到"

        if not value:
            unresolved.append({"path": rel, "reason": f"无法解析：{text}"})
            continue
        new_name = rename_timestamp(Path(rel).name, value)
        if folder == "101206_广电演出":
            destination = str(Path(rel).with_name(new_name))
        elif target == folder:
            destination = str(Path(rel).with_name(new_name))
        else:
            destination = str(Path(target) / "photo" / new_name)
        actions.append({
            "id": row["id"], "source": rel, "target": destination,
            "targetFolder": target, "datetime": value.strftime("%Y-%m-%d %H:%M:%S"),
            "timeText": text, "index": index,
        })
    return actions, unresolved


def rename_timestamp(filename: str, value: datetime) -> str:
    stem, suffix = os.path.splitext(filename)
    patterns = [
        (re.compile(r"(?<!\d)(20\d{2})-(\d{2})-(\d{2})(?!\d)"), value.strftime("%Y-%m-%d")),
        (re.compile(r"(?<!\d)(20\d{2})_(\d{2})_(\d{2})(?!\d)"), value.strftime("%Y_%m_%d")),
        (re.compile(r"(?<!\d)(20\d{2})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})(?!\d)"), value.strftime("%Y%m%d_%H%M%S")),
        (re.compile(r"(?<!\d)(20\d{2})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})(?!\d)"), value.strftime("%Y%m%d%H%M%S")),
        (re.compile(r"(?<!\d)(\d{2})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})(?!\d)"), value.strftime("%y%m%d_%H%M%S")),
    ]
    for pattern, replacement in patterns:
        match = pattern.search(stem)
        if match:
            return stem[:match.start()] + replacement + stem[match.end():] + suffix
    return filename


def unique(path: Path, source: Path) -> Path:
    if not path.exists() or path == source:
        return path
    for number in range(1, 10_000):
        candidate = path.with_name(f"{path.stem}_{number}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"No unique path for {path}")


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


def apply(actions: list[dict], unresolved: list[dict]) -> None:
    missing = [row["source"] for row in actions if not (NAS / row["source"]).exists()]
    if missing:
        raise SystemExit(json.dumps({"missing": missing}, ensure_ascii=False, indent=2))
    LOG.parent.mkdir(parents=True, exist_ok=True)
    journal = []
    for index, row in enumerate(actions, start=1):
        source = NAS / row["source"]
        value = datetime.strptime(row["datetime"], "%Y-%m-%d %H:%M:%S")
        write_dates(source, value)
        target = NAS / row["target"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target = unique(target, source)
        if target != source:
            source.rename(target)
        journal.append({**row, "actualTarget": str(target.relative_to(NAS))})
        if index % 50 == 0:
            print(f"PROGRESS {index}/{len(actions)}", flush=True)

    # The event date is 2010-11-08, so rename the entire album prefix once all
    # files have been processed. It preserves existing root picks and videos.
    old_folder = NAS / "101206_广电演出"
    new_folder = NAS / "101108_广电演出"
    if old_folder.exists():
        if new_folder.exists():
            raise RuntimeError(f"Target folder already exists: {new_folder}")
        old_folder.rename(new_folder)
        for row in journal:
            if row["actualTarget"].startswith("101108_广电演出/"):
                continue
            if row["actualTarget"].startswith("101206_广电演出/"):
                row["actualTarget"] = "101108_广电演出/" + row["actualTarget"].split("/", 1)[1]

    final_paths = [NAS / row["actualTarget"] for row in journal]
    set_file_times(final_paths)
    errors = []
    for start in range(0, len(final_paths), 300):
        chunk = final_paths[start:start + 300]
        result = subprocess.run([EXIFTOOL, "-j", "-DateTimeOriginal", "-CreateDate", "-FileCreateDate", "-FileModifyDate", *map(str, chunk)],
                                text=True, capture_output=True, check=True)
        for action, actual in zip(journal[start:start + 300], json.loads(result.stdout)):
            for tag in ("DateTimeOriginal", "CreateDate", "FileCreateDate", "FileModifyDate"):
                got = actual.get(tag, "")[:19].replace(":", "-", 2)
                if got != action["datetime"]:
                    errors.append({"path": action["actualTarget"], "tag": tag,
                                   "expected": action["datetime"], "actual": got})
    LOG.write_text(json.dumps({"generatedAt": datetime.now().astimezone().isoformat(),
                               "actions": journal, "unresolved": unresolved, "errors": errors,
                               "status": "ok" if not errors else "failed"}, ensure_ascii=False, indent=2))
    manifest = json.loads(MANIFEST.read_text())
    unresolved_paths = {row["path"] for row in unresolved}
    manifest["items"] = [item for item in manifest["items"] if item["relativePath"] in unresolved_paths]
    manifest["count"] = len(manifest["items"])
    manifest["generatedAt"] = datetime.now().astimezone().isoformat()
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(json.dumps({"updated": len(journal),
                      "movedOrRenamed": sum(row["source"] != row["actualTarget"] for row in journal),
                      "albumRenamed": "101206_广电演出 -> 101108_广电演出",
                      "unresolved": len(unresolved),
                      "errors": errors, "status": "ok" if not errors else "failed"}, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    actions, unresolved = build_plan()
    print(json.dumps({"actions": len(actions), "unresolved": unresolved}, ensure_ascii=False, indent=2))
    if args.apply:
        apply(actions, unresolved)


if __name__ == "__main__":
    main()
