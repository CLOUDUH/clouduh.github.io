#!/usr/bin/env python3
"""Conservative second-pass date audit for real photos only."""

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

from scan_range_review import folder_key, folder_anchor, filename_dt


NAS = Path("/Volumes/photo")
ROOT = Path(__file__).resolve().parents[1]
CACHE = Path("/private/tmp/photo-date-v2-audit.json")
EXIFTOOL = "/opt/homebrew/bin/exiftool"
RUN = "photo-date-v2-20260902"
LOG = NAS / "170900_备份/_operation_logs" / RUN
BACKUP = NAS / "170900_备份/metadata-originals" / RUN
PUBLIC = ROOT / "public/range-review"
THUMBS = PUBLIC / "thumbs-v2"
IGNORE = {"200928_常州行", "201023_祖山骑行"}
PHOTO_EXTS = {".jpg", ".jpeg", ".heic", ".tif", ".tiff", ".webp", ".avif"}
CAMERA = re.compile(r"^IMG_(\d{4})\.(?:JPE?G|HEIC)$", re.I)
SCREENSHOT = re.compile(r"(?:screenshot|screen[_ -]?shot|截屏|截图)", re.I)


def discover() -> tuple[list[str], list[Path]]:
    folders, files = [], []
    for top in NAS.iterdir():
        key = folder_key(top.name)
        if not top.is_dir() or key is None or not 190710 <= key <= 210900 or top.name in IGNORE:
            continue
        folders.append(top.name)
        for path in top.rglob("*"):
            if not path.is_file() or "@eaDir" in path.parts:
                continue
            if path.suffix.lower() not in PHOTO_EXTS or SCREENSHOT.search(path.name):
                continue
            files.append(path)
    return sorted(folders, key=lambda name: (folder_key(name), name)), files


def scan() -> None:
    folders, files = discover()
    print(f"SCANNING {len(files)} photos in {len(folders)} folders", flush=True)
    rows = []
    for start in range(0, len(files), 500):
        chunk = files[start:start + 500]
        result = subprocess.run([
            EXIFTOOL, "-j", "-G1", "-a", "-s", "-DateTimeOriginal", "-CreateDate",
            "-FileCreateDate", "-FileModifyDate", "-FileType", "-MIMEType",
            "-ImageWidth", "-ImageHeight", *map(str, chunk),
        ], text=True, capture_output=True, check=True)
        rows.extend(json.loads(result.stdout))
        print(f"PROGRESS scan {min(start + len(chunk), len(files))}/{len(files)}", flush=True)
    CACHE.write_text(json.dumps({"folders": folders, "rows": rows}, ensure_ascii=False))
    print(json.dumps({"folders": len(folders), "photos": len(rows), "cache": str(CACHE)}, ensure_ascii=False, indent=2))


def parse(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            date = datetime.strptime(value[:19], fmt)
            return date if 1990 <= date.year <= 2030 else None
        except ValueError:
            pass
    return None


def embedded(row: dict) -> tuple[datetime | None, str]:
    for key, label in [
        ("ExifIFD:DateTimeOriginal", "EXIF DateTimeOriginal"),
        ("XMP-exif:DateTimeOriginal", "XMP DateTimeOriginal"),
        ("ExifIFD:CreateDate", "EXIF CreateDate"),
        ("XMP-xmp:CreateDate", "XMP CreateDate"),
    ]:
        value = parse(row.get(key))
        if value:
            return value, label
    return None, "无拍摄日期"


def preferred(rows: list[dict]) -> set[str]:
    photo_names = set()
    for row in rows:
        path = Path(row["SourceFile"]).relative_to(NAS)
        if len(path.parts) >= 3 and path.parts[1] == "photo":
            photo_names.add((path.parts[0], path.name.lower()))
    result = set()
    for row in rows:
        path = Path(row["SourceFile"]).relative_to(NAS)
        if len(path.parts) >= 3 and path.parts[1] == "photo":
            result.add(str(path))
        elif len(path.parts) == 2 and (path.parts[0], path.name.lower()) not in photo_names:
            result.add(str(path))
    return result


def valid(value: datetime | None, folder: str, spans: dict[str, tuple[datetime, datetime]]) -> bool:
    return bool(value and spans[folder][0] <= value <= spans[folder][1])


def obvious_intervals(folders: list[str]) -> dict[str, tuple[datetime, datetime]]:
    """Use generous semantic windows so only clearly wrong dates are flagged."""
    broad_words = ("之前", "之后", "疫情", "寒假", "暑假", "开学", "回家")
    result = {}
    for folder in folders:
        anchor = folder_anchor(folder)
        if any(word in folder for word in broad_words):
            result[folder] = (anchor - timedelta(days=90), anchor + timedelta(days=210))
        else:
            result[folder] = (anchor - timedelta(days=45), anchor + timedelta(days=120))
    return result


def high_confidence_window(value: datetime, folder: str) -> bool:
    anchor = folder_anchor(folder)
    before, after = 60, 120
    if "疫情" in folder:
        before, after = 120, 240
    elif "开学之前" in folder:
        before, after = 60, 90
    elif "之前" in folder or "之后" in folder:
        before, after = 90, 120
    elif "回家" in folder:
        before, after = 60, 100
    return anchor - timedelta(days=before) <= value <= anchor + timedelta(days=after)


def interpolation_actions(rows: list[dict], spans: dict[str, tuple[datetime, datetime]], already: set[str]) -> list[dict]:
    groups: dict[tuple[str, str], list[tuple[int, dict, datetime | None]]] = {}
    for row in rows:
        path = Path(row["SourceFile"])
        match = CAMERA.match(path.name)
        if not match:
            continue
        rel = path.relative_to(NAS)
        folder = rel.parts[0]
        value, _ = embedded(row)
        groups.setdefault((folder, str(rel.parent)), []).append((int(match.group(1)), row, value))
    actions = []
    for (folder, _), values in groups.items():
        values.sort(key=lambda item: item[0])
        trusted = [(number, value) for number, _, value in values if valid(value, folder, spans)]
        for number, row, current in values:
            rel = str(Path(row["SourceFile"]).relative_to(NAS))
            if rel in already or valid(current, folder, spans):
                continue
            lower = [(n, dt) for n, dt in trusted if n < number and number - n <= 8]
            upper = [(n, dt) for n, dt in trusted if n > number and n - number <= 8]
            if not lower or not upper:
                continue
            lo_n, lo_dt = max(lower, key=lambda item: item[0])
            hi_n, hi_dt = min(upper, key=lambda item: item[0])
            if lo_dt.date() != hi_dt.date() or hi_dt < lo_dt or hi_dt - lo_dt > timedelta(hours=18):
                continue
            ratio = (number - lo_n) / (hi_n - lo_n)
            inferred = lo_dt + (hi_dt - lo_dt) * ratio
            actions.append({
                "relativePath": rel,
                "newDate": inferred.replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S"),
                "basis": f"相邻编号 IMG_{lo_n:04d} 与 IMG_{hi_n:04d} 同日插值",
                "confidence": "high",
            })
    return actions


def build_plan(doc: dict) -> tuple[list[dict], list[dict]]:
    folders, rows = doc["folders"], doc["rows"]
    spans = obvious_intervals(folders)
    selected = preferred(rows)
    actions = []
    acted = set()
    for row in rows:
        path = Path(row["SourceFile"])
        rel = str(path.relative_to(NAS))
        if rel not in selected:
            continue
        folder = Path(rel).parts[0]
        current, _ = embedded(row)
        named = filename_dt(path)
        if named and valid(named, folder, spans) and high_confidence_window(named, folder) and not valid(current, folder, spans):
            actions.append({"relativePath": rel, "newDate": named.strftime("%Y-%m-%d %H:%M:%S"),
                            "basis": "文件名包含完整日期且落在已确认文件夹范围内", "confidence": "high"})
            acted.add(rel)
            continue
        file_create = parse(row.get("MacOS:FileCreateDate"))
        file_modify = parse(row.get("System:FileModifyDate"))
        if not current and file_create and file_modify and abs((file_create - file_modify).total_seconds()) <= 2 and high_confidence_window(file_modify, folder):
            actions.append({"relativePath": rel, "newDate": file_modify.strftime("%Y-%m-%d %H:%M:%S"),
                            "basis": "文件创建与修改时间一致，且落在已确认文件夹范围内", "confidence": "high"})
            acted.add(rel)
    for action in interpolation_actions(rows, spans, acted):
        actions.append(action)
        acted.add(action["relativePath"])

    candidates = []
    for row in rows:
        path = Path(row["SourceFile"])
        rel = str(path.relative_to(NAS))
        if rel not in selected or rel in acted:
            continue
        folder = Path(rel).parts[0]
        value, source = embedded(row)
        if valid(value, folder, spans):
            continue
        start, end = spans[folder]
        candidates.append({
            "row": row,
            "id": hashlib.sha1(rel.encode()).hexdigest()[:20],
            "relativePath": rel,
            "filename": path.name,
            "currentFolder": folder,
            "captureDate": value.strftime("%Y-%m-%d %H:%M:%S") if value else None,
            "dateSource": source,
            "fileCreateDate": row.get("MacOS:FileCreateDate"),
            "fileModifyDate": row.get("System:FileModifyDate"),
            "expectedStart": start.strftime("%Y-%m-%d"),
            "expectedEnd": end.strftime("%Y-%m-%d"),
            "suggestedFolder": folder,
            "reason": "没有拍摄日期" if not value else "拍摄日期明显超出已确认文件夹范围",
        })
    return actions, candidates


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
        raise RuntimeError(f"No metadata backup for {path}")
    shutil.move(str(original), str(backup))
    stamp = value.strftime("%Y:%m:%d %H:%M:%S+08:00")
    result = subprocess.run([EXIFTOOL, "-overwrite_original_in_place", f"-FileCreateDate={stamp}",
                             f"-FileModifyDate={stamp}", str(path)], text=True, capture_output=True)
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
    print(json.dumps({"scanned": len(doc["rows"]), "highConfidence": len(actions),
                      "manualReview": len(candidates),
                      "missingDate": sum(item["captureDate"] is None for item in candidates),
                      "wrongDate": sum(item["captureDate"] is not None for item in candidates)},
                     ensure_ascii=False, indent=2))
    for action in actions[:80]:
        print(json.dumps(action, ensure_ascii=False))


def apply() -> None:
    doc = json.loads(CACHE.read_text())
    actions, candidates = build_plan(doc)
    LOG.mkdir(parents=True, exist_ok=False)
    BACKUP.mkdir(parents=True, exist_ok=False)
    (LOG / "audit.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2))
    (LOG / "high-confidence-plan.json").write_text(json.dumps(actions, ensure_ascii=False, indent=2))
    journal = []
    for index, action in enumerate(actions, start=1):
        path = NAS / action["relativePath"]
        value = datetime.strptime(action["newDate"], "%Y-%m-%d %H:%M:%S")
        backup = BACKUP / action["relativePath"]
        write_metadata(path, value, backup)
        journal.append({**action, "backup": str(backup.relative_to(NAS))})
        if index % 20 == 0:
            print(f"PROGRESS metadata {index}/{len(actions)}", flush=True)

    public_items = []
    for index, item in enumerate(candidates, start=1):
        row = item.pop("row")
        thumb = THUMBS / f'{item["id"]}.jpg'
        item["thumbnail"] = f'/range-review/thumbs-v2/{item["id"]}.jpg' if make_thumb(NAS / item["relativePath"], thumb) else None
        public_items.append(item)
        if index % 100 == 0:
            print(f"PROGRESS thumbs {index}/{len(candidates)}", flush=True)
    public_items.sort(key=lambda item: (item["currentFolder"], item["filename"]))
    manifest = {
        "version": 2,
        "generatedAt": datetime.now().astimezone().isoformat(),
        "range": "190710-210900",
        "ignoredFolders": sorted(IGNORE),
        "folderCount": len(doc["folders"]),
        "scanned": len(doc["rows"]),
        "cameraFilesFixed": len(actions),
        "autoFixed": len(actions),
        "count": len(public_items),
        "folders": doc["folders"],
        "items": public_items,
    }
    PUBLIC.mkdir(parents=True, exist_ok=True)
    (PUBLIC / "review-items.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    (LOG / "journal.json").write_text(json.dumps(journal, ensure_ascii=False, indent=2))

    errors = []
    for action in actions:
        result = subprocess.run([EXIFTOOL, "-j", "-DateTimeOriginal", "-CreateDate", "-FileCreateDate", "-FileModifyDate",
                                 str(NAS / action["relativePath"])], text=True, capture_output=True, check=True)
        row = json.loads(result.stdout)[0]
        expected = action["newDate"]
        for tag in ("DateTimeOriginal", "CreateDate", "FileCreateDate", "FileModifyDate"):
            actual = row.get(tag, "")[:19].replace(":", "-", 2)
            if actual != expected:
                errors.append({"path": action["relativePath"], "tag": tag, "expected": expected, "actual": actual})
    report = {"scanned": len(doc["rows"]), "autoFixed": len(actions), "manualReview": len(public_items),
              "missingDate": sum(item["captureDate"] is None for item in public_items),
              "wrongDate": sum(item["captureDate"] is not None for item in public_items),
              "missingThumbnails": sum(item["thumbnail"] is None for item in public_items),
              "errors": errors, "status": "ok" if not errors else "failed"}
    (LOG / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))
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
