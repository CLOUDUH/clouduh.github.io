#!/usr/bin/env python3
"""Audit photo dates through the 170701 graduation album."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

from PIL import Image, ImageOps


NAS = Path("/Volumes/photo")
ROOT = Path(__file__).resolve().parents[1]
CACHE = Path("/private/tmp/legacy-date-audit.json")
EXIFTOOL = "/opt/homebrew/bin/exiftool"
PUBLIC = ROOT / "public/range-review"
THUMBS = PUBLIC / "thumbs-legacy"
LOG = ROOT / "tools-data/legacy-date-fixes.json"
PHOTO_EXTS = {".jpg", ".jpeg", ".heic", ".tif", ".tiff", ".webp", ".avif"}
SCREENSHOT = re.compile(r"(?:screenshot|screen[_ -]?shot|截屏|截图)", re.I)

RANGES = {
    "050000_小时候": ("1990-01-01", "2014-12-31"),
    "090000_小学生活": ("1998-01-01", "2014-12-31"),
    "090500_姥姥华东": ("2007-01-01", "2011-12-31"),
    "100324_爸爸汶川": ("2008-01-01", "2012-12-31"),
    "100425_妈妈鹤伴山": ("2008-01-01", "2012-12-31"),
    "101206_广电演出": ("2008-01-01", "2012-12-31"),
    "110600_初中": ("2010-01-01", "2015-12-31"),
    "140200_桂林": ("2012-01-01", "2016-12-31"),
    "140618_小学聚会": ("2012-01-01", "2016-12-31"),
    "150000_高中生活": ("2013-01-01", "2018-12-31"),
    "150800_胶东游": ("2013-01-01", "2018-12-31"),
    "170701_高中毕业": ("2015-01-01", "2019-12-31"),
}


def discover() -> tuple[list[str], list[Path]]:
    folders, files = [], []
    for name in sorted(RANGES):
        photo = NAS / name / "photo"
        if not photo.is_dir():
            continue
        folders.append(name)
        files.extend(path for path in photo.rglob("*")
                     if path.is_file() and path.suffix.lower() in PHOTO_EXTS
                     and not SCREENSHOT.search(path.name) and "@eaDir" not in path.parts)
    return folders, files


def scan() -> None:
    folders, files = discover()
    rows = []
    print(f"SCANNING {len(files)} photos", flush=True)
    for start in range(0, len(files), 500):
        chunk = files[start:start + 500]
        result = subprocess.run([
            EXIFTOOL, "-j", "-G1", "-a", "-s", "-DateTimeOriginal", "-CreateDate",
            "-FileCreateDate", "-FileModifyDate", "-FileType", "-ImageWidth", "-ImageHeight",
            *map(str, chunk),
        ], text=True, capture_output=True, check=True)
        rows.extend(json.loads(result.stdout))
        print(f"PROGRESS {min(start + len(chunk), len(files))}/{len(files)}", flush=True)
    CACHE.write_text(json.dumps({"folders": folders, "rows": rows}, ensure_ascii=False))
    print(json.dumps({"folders": len(folders), "photos": len(rows)}, ensure_ascii=False, indent=2))


def parse(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            value = datetime.strptime(value[:19], fmt)
            return value if 1900 <= value.year <= 2030 else None
        except ValueError:
            pass
    return None


def valid(value: datetime | None, folder: str) -> bool:
    start, end = (datetime.strptime(part, "%Y-%m-%d") for part in RANGES[folder])
    return bool(value and start <= value <= end)


def filename_date(path: Path) -> datetime | None:
    patterns = [
        r"(?<!\d)(20\d{2})[-_]?([01]\d)[-_]?([0-3]\d)[-_ T]?([0-2]\d)[-_.:]?([0-5]\d)[-_.:]?([0-5]\d)(?!\d)",
        r"(?<!\d)(\d{2})[-_]?([01]\d)[-_]?([0-3]\d)[-_ T]?([0-2]\d)[-_.:]?([0-5]\d)[-_.:]?([0-5]\d)(?!\d)",
    ]
    for pattern in patterns:
        match = re.search(pattern, path.stem)
        if not match:
            continue
        values = list(map(int, match.groups()))
        if values[0] < 100:
            values[0] += 2000
        try:
            return datetime(*values)
        except ValueError:
            pass
    return None


def sequence_key(name: str) -> tuple[str, int] | None:
    match = re.match(r"^(.*?)(\d{3,5})(?:[^\d].*)?$", Path(name).stem)
    if not match:
        return None
    return match.group(1).lower(), int(match.group(2))


def trusted_filename(path: Path, value: datetime, folder: str) -> bool:
    stem = path.stem
    trusted = bool(re.search(r"(?:^|_)(?:IMG_?20\d{6}|faceu_20\d{6}|CLOUDUH_\d{6})", stem, re.I))
    if not trusted:
        return False
    if folder == "170701_高中毕业":
        return datetime(2017, 5, 1) <= value <= datetime(2017, 9, 15, 23, 59, 59)
    return True


def build_plan(doc: dict) -> tuple[list[dict], list[dict]]:
    actions, acted = [], set()
    for row in doc["rows"]:
        path = Path(row["SourceFile"])
        rel = str(path.relative_to(NAS))
        folder = Path(rel).parts[0]
        dto = parse(row.get("ExifIFD:DateTimeOriginal")) or parse(row.get("XMP-exif:DateTimeOriginal"))
        create = parse(row.get("ExifIFD:CreateDate")) or parse(row.get("XMP-xmp:CreateDate"))
        named = filename_date(path)
        file_create = parse(row.get("MacOS:FileCreateDate"))
        file_modify = parse(row.get("System:FileModifyDate"))
        value, basis = None, ""
        if not valid(dto, folder) and valid(create, folder):
            value, basis = create, "原拍摄时间缺失/越界，但EXIF CreateDate有效"
        elif not valid(dto, folder) and valid(named, folder) and trusted_filename(path, named, folder):
            value, basis = named, "文件名包含完整且符合相册范围的日期"
        if value:
            actions.append({"relativePath": rel, "newDate": value.strftime("%Y-%m-%d %H:%M:%S"), "basis": basis})
            acted.add(rel)

    # Conservative interpolation between close sequence numbers photographed on the same day.
    groups: dict[tuple[str, str, str], list[tuple[int, dict, datetime | None]]] = {}
    for row in doc["rows"]:
        path = Path(row["SourceFile"])
        rel = path.relative_to(NAS)
        seq = sequence_key(path.name)
        if not seq:
            continue
        dto = parse(row.get("ExifIFD:DateTimeOriginal")) or parse(row.get("XMP-exif:DateTimeOriginal"))
        groups.setdefault((rel.parts[0], str(rel.parent), seq[0]), []).append((seq[1], row, dto))
    for (folder, _, _), values in groups.items():
        trusted = [(number, date) for number, _, date in values if valid(date, folder)]
        for number, row, current in values:
            rel = str(Path(row["SourceFile"]).relative_to(NAS))
            if rel in acted or valid(current, folder):
                continue
            lower = [(n, dt) for n, dt in trusted if n < number and number - n <= 6]
            upper = [(n, dt) for n, dt in trusted if n > number and n - number <= 6]
            if not lower or not upper:
                continue
            lo_n, lo_dt = max(lower, key=lambda pair: pair[0])
            hi_n, hi_dt = min(upper, key=lambda pair: pair[0])
            if lo_dt.date() != hi_dt.date() or hi_dt < lo_dt or hi_dt - lo_dt > timedelta(hours=16):
                continue
            ratio = (number - lo_n) / (hi_n - lo_n)
            inferred = (lo_dt + (hi_dt - lo_dt) * ratio).replace(microsecond=0)
            actions.append({"relativePath": rel, "newDate": inferred.strftime("%Y-%m-%d %H:%M:%S"),
                            "basis": f"相邻编号{lo_n}与{hi_n}同日插值"})
            acted.add(rel)

    candidates = []
    for row in doc["rows"]:
        path = Path(row["SourceFile"])
        rel = str(path.relative_to(NAS))
        if rel in acted:
            continue
        folder = Path(rel).parts[0]
        dto = parse(row.get("ExifIFD:DateTimeOriginal")) or parse(row.get("XMP-exif:DateTimeOriginal"))
        if valid(dto, folder):
            continue
        create = parse(row.get("ExifIFD:CreateDate")) or parse(row.get("XMP-xmp:CreateDate"))
        current = dto or create
        candidates.append({
            "row": row,
            "id": hashlib.sha1(rel.encode()).hexdigest()[:20],
            "relativePath": rel,
            "filename": path.name,
            "currentFolder": folder,
            "captureDate": current.strftime("%Y-%m-%d %H:%M:%S") if current else None,
            "dateSource": "DateTimeOriginal" if dto else ("CreateDate" if create else "无拍摄日期"),
            "fileCreateDate": row.get("MacOS:FileCreateDate"),
            "fileModifyDate": row.get("System:FileModifyDate"),
            "expectedStart": RANGES[folder][0],
            "expectedEnd": RANGES[folder][1],
            "suggestedFolder": folder,
            "reason": "没有拍摄日期" if not current else "拍摄日期明显超出相册范围",
        })
    return actions, candidates


def write_dates(path: Path, value: datetime) -> None:
    exif = value.strftime("%Y:%m:%d %H:%M:%S")
    xmp = value.strftime("%Y-%m-%dT%H:%M:%S+08:00")
    result = subprocess.run([
        EXIFTOOL, "-overwrite_original_in_place", f"-EXIF:DateTimeOriginal={exif}",
        f"-EXIF:CreateDate={exif}", f"-EXIF:ModifyDate={exif}",
        f"-XMP-exif:DateTimeOriginal={exif}", f"-XMP-xmp:CreateDate={xmp}",
        f"-XMP-xmp:ModifyDate={xmp}", f"-FileCreateDate={exif}+08:00",
        f"-FileModifyDate={exif}+08:00", str(path),
    ], text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr or result.stdout)


def make_thumb(source: Path, target: Path) -> bool:
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with Image.open(source) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            image.thumbnail((1400, 1400), Image.Resampling.LANCZOS)
            image.save(target, "JPEG", quality=84, optimize=True)
        return True
    except Exception:
        result = subprocess.run(["/usr/bin/sips", "-Z", "1400", "-s", "format", "jpeg",
                                 str(source), "--out", str(target)], text=True, capture_output=True)
        return result.returncode == 0 and target.exists()


def analyze() -> None:
    doc = json.loads(CACHE.read_text())
    actions, candidates = build_plan(doc)
    print(json.dumps({"scanned": len(doc["rows"]), "autoFix": len(actions),
                      "manualReview": len(candidates),
                      "missingDate": sum(item["captureDate"] is None for item in candidates),
                      "wrongDate": sum(item["captureDate"] is not None for item in candidates)},
                     ensure_ascii=False, indent=2))
    for action in actions[:100]:
        print(json.dumps(action, ensure_ascii=False))


def apply() -> None:
    doc = json.loads(CACHE.read_text())
    actions, candidates = build_plan(doc)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text(json.dumps({"generatedAt": datetime.now().astimezone().isoformat(),
                               "actions": actions}, ensure_ascii=False, indent=2))
    for index, action in enumerate(actions, start=1):
        write_dates(NAS / action["relativePath"], datetime.strptime(action["newDate"], "%Y-%m-%d %H:%M:%S"))
        if index % 20 == 0:
            print(f"PROGRESS fixes {index}/{len(actions)}", flush=True)
    if actions:
        result = subprocess.run([
            EXIFTOOL, "-overwrite_original_in_place",
            "-FileCreateDate<DateTimeOriginal", "-FileModifyDate<DateTimeOriginal",
            *[str(NAS / action["relativePath"]) for action in actions],
        ], text=True, capture_output=True)
        if result.returncode:
            raise RuntimeError(result.stderr or result.stdout)
    items = []
    for item in candidates:
        item.pop("row")
        item["thumbnail"] = "http://127.0.0.1:3002/media/" + quote(item["relativePath"], safe="/") + "?size=1400"
        items.append(item)
    manifest = {
        "version": 3,
        "generatedAt": datetime.now().astimezone().isoformat(),
        "range": "through-170701",
        "ignoredFolders": [],
        "folderCount": len(doc["folders"]),
        "scanned": len(doc["rows"]),
        "cameraFilesFixed": len(actions),
        "autoFixed": len(actions),
        "count": len(items),
        "folders": doc["folders"],
        "items": sorted(items, key=lambda item: (item["currentFolder"], item["filename"])),
    }
    PUBLIC.mkdir(parents=True, exist_ok=True)
    (PUBLIC / "review-items.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))

    errors = []
    for action in actions:
        result = subprocess.run([EXIFTOOL, "-j", "-DateTimeOriginal", "-CreateDate", "-FileCreateDate", "-FileModifyDate",
                                 str(NAS / action["relativePath"])], text=True, capture_output=True, check=True)
        row = json.loads(result.stdout)[0]
        for tag in ("DateTimeOriginal", "CreateDate", "FileCreateDate", "FileModifyDate"):
            actual = row.get(tag, "")[:19].replace(":", "-", 2)
            if actual != action["newDate"]:
                errors.append({"path": action["relativePath"], "tag": tag,
                               "expected": action["newDate"], "actual": actual})
    result = {"scanned": len(doc["rows"]), "autoFixed": len(actions),
              "manualReview": len(items), "missingDate": sum(x["captureDate"] is None for x in items),
              "wrongDate": sum(x["captureDate"] is not None for x in items),
              "missingThumbnails": sum(x["thumbnail"] is None for x in items),
              "errors": errors, "status": "ok" if not errors else "failed"}
    (PUBLIC / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scan", action="store_true")
    parser.add_argument("--analyze", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.scan:
        scan()
    elif args.analyze:
        analyze()
    elif args.apply:
        apply()
    else:
        raise SystemExit("Pass --scan, --analyze, or --apply")


if __name__ == "__main__":
    main()
