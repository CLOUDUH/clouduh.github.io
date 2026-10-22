#!/usr/bin/env python3
"""Audit 190710-210900 albums, repair camera file dates, and build review data."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from PIL import Image, ImageOps


NAS = Path("/Volumes/photo")
ROOT = Path(__file__).resolve().parents[1]
CACHE = Path("/private/tmp/photo-range-190710-210900-audit.json")
EXIFTOOL = "/opt/homebrew/bin/exiftool"
RUN = "range-audit-190710-210900-20260902"
LOG_ROOT = NAS / "170900_备份/_operation_logs" / RUN
PUBLIC = ROOT / "public/range-review"
THUMBS = PUBLIC / "thumbs"
IGNORE = {"200928_常州行", "201023_祖山骑行"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".gif", ".webp", ".tif", ".tiff", ".avif"}
CAMERA_NAME = re.compile(r"^IMG_\d{4}\.(?:JPE?G|HEIC)$", re.I)


def folder_key(name: str) -> int | None:
    try:
        return int(name[:6])
    except ValueError:
        return None


def folder_anchor(name: str) -> datetime:
    key = int(name[:6])
    year, month, day = 2000 + key // 10000, (key // 100) % 100, key % 100
    return datetime(year, max(1, month), max(1, day))


def scan_paths() -> tuple[list[str], list[str]]:
    folders = []
    files = []
    for top in NAS.iterdir():
        key = folder_key(top.name)
        if not top.is_dir() or key is None or not 190710 <= key <= 210900 or top.name in IGNORE:
            continue
        folders.append(top.name)
        for path in top.rglob("*"):
            if path.is_file() and path.suffix.lower() in IMAGE_EXTS and "@eaDir" not in path.parts:
                files.append(str(path))
    return sorted(folders, key=lambda name: (folder_key(name), name)), files


def run_scan() -> None:
    folders, files = scan_paths()
    print(f"SCANNING {len(files)} images in {len(folders)} folders", flush=True)
    rows = []
    for start in range(0, len(files), 500):
        chunk = files[start:start + 500]
        result = subprocess.run([
            EXIFTOOL, "-j", "-G1", "-a", "-s",
            "-DateTimeOriginal", "-CreateDate", "-FileCreateDate", "-FileModifyDate",
            "-FileType", "-MIMEType", "-ImageWidth", "-ImageHeight", *chunk,
        ], text=True, capture_output=True, check=True)
        rows.extend(json.loads(result.stdout))
        print(f"PROGRESS scan {min(start + len(chunk), len(files))}/{len(files)}", flush=True)
    CACHE.write_text(json.dumps({"folders": folders, "rows": rows}, ensure_ascii=False))
    print(json.dumps({"folders": len(folders), "images": len(rows), "cache": str(CACHE)}, ensure_ascii=False, indent=2))


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value[:19]
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            value = datetime.strptime(text, fmt)
            return value if 1990 <= value.year <= 2030 else None
        except ValueError:
            pass
    return None


def filename_dt(path: Path) -> datetime | None:
    patterns = [
        r"(?<!\d)(20\d{2})[-_]?([01]\d)[-_]?([0-3]\d)[-_ T]?([0-2]\d)[-_:]?([0-5]\d)[-_:]?([0-5]\d)(?!\d)",
        r"(?<!\d)(\d{2})[-_]?([01]\d)[-_]?([0-3]\d)[-_ T]?([0-2]\d)[-_:]?([0-5]\d)[-_:]?([0-5]\d)(?!\d)",
    ]
    for pattern in patterns:
        match = re.search(pattern, path.stem)
        if match:
            values = list(map(int, match.groups()))
            if values[0] < 100:
                values[0] += 2000
            try:
                return datetime(*values)
            except ValueError:
                pass
    return None


def capture(row: dict) -> tuple[datetime | None, str]:
    for key, label in [
        ("ExifIFD:DateTimeOriginal", "EXIF DateTimeOriginal"),
        ("XMP-exif:DateTimeOriginal", "XMP DateTimeOriginal"),
        ("ExifIFD:CreateDate", "EXIF CreateDate"),
        ("XMP-xmp:CreateDate", "XMP CreateDate"),
    ]:
        value = parse_dt(row.get(key))
        if value:
            return value, label
    value = filename_dt(Path(row["SourceFile"]))
    return (value, "文件名") if value else (None, "无可靠日期")


def intervals(folders: list[str]) -> dict[str, tuple[datetime, datetime]]:
    distinct = sorted({folder_key(name) for name in folders})
    anchors = {key: folder_anchor(f"{key:06d}") for key in distinct}
    result = {}
    for name in folders:
        key = folder_key(name)
        anchor = anchors[key]
        next_values = [anchors[value] for value in distinct if value > key]
        next_anchor = min(next_values) if next_values else anchor + timedelta(days=150)
        day = key % 100
        start = anchor - timedelta(days=90 if day == 0 else 21)
        end = next_anchor + timedelta(days=7)
        result[name] = (start, end)
    return result


def suggested_folder(value: datetime, folders: list[str], spans: dict[str, tuple[datetime, datetime]]) -> str:
    matches = [name for name in folders if spans[name][0] <= value <= spans[name][1]]
    if matches:
        return min(matches, key=lambda name: abs((folder_anchor(name) - value).days))
    return min(folders, key=lambda name: abs((folder_anchor(name) - value).days))


def relative_preference(rows: list[dict]) -> set[str]:
    """Prefer photo/ originals over intentional root-level selected copies."""
    photo_keys = set()
    for row in rows:
        path = Path(row["SourceFile"]).relative_to(NAS)
        if len(path.parts) >= 3 and path.parts[1] == "photo":
            photo_keys.add((path.parts[0], path.name.lower()))
    selected = set()
    for row in rows:
        path = Path(row["SourceFile"]).relative_to(NAS)
        key = (path.parts[0], path.name.lower())
        if len(path.parts) >= 3 and path.parts[1] == "photo":
            selected.add(str(path))
        elif len(path.parts) == 2 and key not in photo_keys:
            selected.add(str(path))
    return selected


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


def apply_and_build() -> None:
    doc = json.loads(CACHE.read_text())
    folders, rows = doc["folders"], doc["rows"]
    spans = intervals(folders)
    camera = []
    for row in rows:
        path = Path(row["SourceFile"])
        value = parse_dt(row.get("ExifIFD:DateTimeOriginal"))
        file_create = parse_dt(row.get("MacOS:FileCreateDate"))
        file_modify = parse_dt(row.get("System:FileModifyDate"))
        if CAMERA_NAME.match(path.name) and value and (file_create != value or file_modify != value):
            camera.append(path)

    LOG_ROOT.mkdir(parents=True, exist_ok=False)
    (LOG_ROOT / "audit.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2))
    (LOG_ROOT / "camera-fixes.json").write_text(json.dumps([str(path.relative_to(NAS)) for path in camera], ensure_ascii=False, indent=2))
    for start in range(0, len(camera), 400):
        chunk = camera[start:start + 400]
        result = subprocess.run([EXIFTOOL, "-overwrite_original_in_place",
                                 "-FileCreateDate<DateTimeOriginal", "-FileModifyDate<DateTimeOriginal",
                                 *map(str, chunk)], text=True, capture_output=True)
        if result.returncode:
            raise RuntimeError(result.stderr or result.stdout)
        print(f"PROGRESS camera {min(start + len(chunk), len(camera))}/{len(camera)}", flush=True)

    preferred = relative_preference(rows)
    candidates = []
    for row in rows:
        path = Path(row["SourceFile"])
        relative = str(path.relative_to(NAS))
        if relative not in preferred:
            continue
        value, source = capture(row)
        if not value:
            continue
        folder = Path(relative).parts[0]
        start, end = spans[folder]
        if start <= value <= end:
            continue
        item_id = hashlib.sha1(relative.encode()).hexdigest()[:20]
        thumb = THUMBS / f"{item_id}.jpg"
        has_thumb = make_thumb(path, thumb)
        candidates.append({
            "id": item_id,
            "relativePath": relative,
            "filename": path.name,
            "currentFolder": folder,
            "captureDate": value.strftime("%Y-%m-%d %H:%M:%S"),
            "dateSource": source,
            "fileCreateDate": row.get("MacOS:FileCreateDate"),
            "fileModifyDate": row.get("System:FileModifyDate"),
            "expectedStart": start.strftime("%Y-%m-%d"),
            "expectedEnd": end.strftime("%Y-%m-%d"),
            "suggestedFolder": suggested_folder(value, folders, spans),
            "reason": f"拍摄日期超出 {folder} 的宽松时间范围",
            "thumbnail": f"/range-review/thumbs/{item_id}.jpg" if has_thumb else None,
        })
    candidates.sort(key=lambda item: (item["currentFolder"], item["captureDate"], item["filename"]))
    PUBLIC.mkdir(parents=True, exist_ok=True)
    manifest = {
        "version": 1,
        "generatedAt": datetime.now().astimezone().isoformat(),
        "range": "190710-210900",
        "ignoredFolders": sorted(IGNORE),
        "folderCount": len(folders),
        "scanned": len(rows),
        "cameraFilesFixed": len(camera),
        "count": len(candidates),
        "folders": folders,
        "items": candidates,
    }
    (PUBLIC / "review-items.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))

    # Verify camera file times after the write.
    errors = []
    for start in range(0, len(camera), 500):
        chunk = camera[start:start + 500]
        check = subprocess.run([EXIFTOOL, "-j", "-DateTimeOriginal", "-FileCreateDate", "-FileModifyDate", *map(str, chunk)],
                               text=True, capture_output=True, check=True)
        for row in json.loads(check.stdout):
            expected = row.get("DateTimeOriginal", "")[:19]
            for tag in ("FileCreateDate", "FileModifyDate"):
                actual = row.get(tag, "")[:19]
                if actual != expected:
                    errors.append({"path": row["SourceFile"], "tag": tag, "expected": expected, "actual": actual})
    report = {"scanned": len(rows), "cameraFilesFixed": len(camera), "reviewItems": len(candidates),
              "verificationErrors": errors, "status": "ok" if not errors else "failed"}
    (LOG_ROOT / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scan", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.scan:
        run_scan()
    elif args.apply:
        apply_and_build()
    else:
        raise SystemExit("Pass --scan or --apply")


if __name__ == "__main__":
    main()
