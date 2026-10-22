#!/usr/bin/env python3
"""Audit 2022 photo albums for export-date contamination and prepare safe repairs."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote


NAS = Path("/Volumes/photo")
ROOT = Path(__file__).resolve().parents[1]
CACHE = Path("/private/tmp/photo-2022-export-audit.json")
PLAN = Path("/private/tmp/photo-2022-export-plan.json")
PIXEL_GROUPS = Path("/private/tmp/photo-2022-pixel-duplicate-groups.json")
PUBLIC = ROOT / "public/range-review"
LOG = ROOT / "tools-data/2022-export-date-fixes.json"
EXIFTOOL = "/opt/homebrew/bin/exiftool"
PHOTO_EXTS = {".jpg", ".jpeg", ".heic", ".tif", ".tiff", ".webp", ".avif"}
SCREENSHOT = re.compile(r"(?:screenshot|screen[_ -]?shot|截屏|截图)", re.I)
EXPORT_DAY = re.compile(r"(?<!\d)(?:20)?211111(?:[_-]?\d{6})?(?!\d)", re.I)


def folder_key(name: str) -> int | None:
    if len(name) < 7 or not name[:6].isdigit() or not name.startswith("22"):
        return None
    return int(name[:6])


def anchor(name: str) -> datetime:
    key = int(name[:6])
    return datetime(2000 + key // 10000, (key // 100) % 100, key % 100)


def discover() -> tuple[list[str], list[Path]]:
    folders: list[str] = []
    files: list[Path] = []
    for top in sorted(NAS.iterdir()):
        if not top.is_dir() or folder_key(top.name) is None:
            continue
        folders.append(top.name)
        photo = top / "photo"
        if not photo.is_dir():
            continue
        files.extend(
            path for path in photo.rglob("*")
            if path.is_file()
            and path.suffix.lower() in PHOTO_EXTS
            and "@eaDir" not in path.parts
            and "__selected" not in path.stem
            and not SCREENSHOT.search(path.name)
        )
    return folders, files


def scan() -> None:
    folders, files = discover()
    rows: list[dict] = []
    print(f"SCANNING {len(files)} photos in {len(folders)} folders", flush=True)
    for start in range(0, len(files), 400):
        chunk = files[start:start + 400]
        result = subprocess.run([
            EXIFTOOL, "-j", "-G1", "-a", "-s",
            "-DateTimeOriginal", "-CreateDate", "-ModifyDate",
            "-FileCreateDate", "-FileModifyDate", "-MediaCreateDate",
            "-TrackCreateDate", "-ImageWidth", "-ImageHeight", "-FileSize#",
            "-Make", "-Model", *map(str, chunk),
        ], text=True, capture_output=True, check=True)
        rows.extend(json.loads(result.stdout))
        print(f"PROGRESS {min(start + len(chunk), len(files))}/{len(files)}", flush=True)
    CACHE.write_text(json.dumps({"folders": folders, "rows": rows}, ensure_ascii=False))
    print(json.dumps({"folders": len(folders), "photos": len(rows), "cache": str(CACHE)}, ensure_ascii=False, indent=2))


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            result = datetime.strptime(value[:19], fmt)
            return result if 1990 <= result.year <= 2035 else None
        except ValueError:
            pass
    return None


def first_date(row: dict, keys: tuple[str, ...]) -> tuple[datetime | None, str]:
    for suffix in keys:
        for key, raw in row.items():
            if key.split(":")[-1] != suffix:
                continue
            value = parse_dt(raw)
            if value:
                return value, key
    return None, ""


def filename_date(path: Path) -> datetime | None:
    patterns = [
        r"(?<!\d)(20\d{2})[-_]?(0[1-9]|1[0-2])[-_]?([0-3]\d)[-_ T]?([0-2]\d)[-_.:]?([0-5]\d)[-_.:]?([0-5]\d)(?!\d)",
        r"(?<!\d)(\d{2})[-_]?(0[1-9]|1[0-2])[-_]?([0-3]\d)[-_ T]?([0-2]\d)[-_.:]?([0-5]\d)[-_.:]?([0-5]\d)(?!\d)",
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


def dto(row: dict) -> datetime | None:
    return first_date(row, ("DateTimeOriginal",))[0]


def dated_img(path: Path) -> datetime | None:
    match = re.match(r"IMG_(20\d{6})_(\d{6})", path.stem, re.I)
    if not match:
        return None
    try:
        return datetime.strptime("".join(match.groups()), "%Y%m%d%H%M%S")
    except ValueError:
        return None


def close_dates(values: list[datetime], seconds: int = 2) -> list[datetime]:
    result: list[datetime] = []
    for value in sorted(values):
        if not result or abs((value - result[-1]).total_seconds()) > seconds:
            result.append(value)
    return result


def canonical_group_date(group: list[str], rows: dict[str, dict]) -> tuple[datetime | None, str]:
    """Pick a date only when a real camera-style source makes it unambiguous."""
    named = close_dates([dated_img(Path(rel)) for rel in group if dated_img(Path(rel))])
    if len(named) == 1:
        return named[0], "同画面中存在唯一的IMG_YYYYMMDD_HHMMSS原片"
    if len(named) > 1:
        known = [dto(rows[rel]) for rel in group if dto(rows[rel])]
        for value in named:
            if known and all(abs((candidate - value).total_seconds()) <= 2 for candidate in known):
                return value, "多个日期文件名冲突，但组内EXIF一致指向该时间"

    camera = [rel for rel in group if re.match(r"IMG_\d{4}(?:_\d+| \d+)?$", Path(rel).stem, re.I)]
    camera_dates = close_dates([dto(rows[rel]) for rel in camera if dto(rows[rel])])
    if len(camera_dates) == 1 and not any(" 2" in Path(rel).stem for rel in camera):
        return camera_dates[0], "同画面中的相机原始编号文件时间"

    cloud_original = [rel for rel in group if re.match(r"CLOUDUH?-\d+$", Path(rel).stem, re.I)]
    cloud_dates = close_dates([dto(rows[rel]) for rel in cloud_original if dto(rows[rel])])
    if len(cloud_dates) == 1:
        return cloud_dates[0], "同画面中较早的相机直出CLOUDU编号文件时间"
    return None, ""


def standard_timestamp_name(path: Path, value: datetime) -> str | None:
    """Rewrite only filenames that already contain an explicit date-time token."""
    stem, suffix = path.stem, path.suffix
    contiguous = re.match(r"^(CLOUDUH_)(\d{12})(.*)$", stem, re.I)
    if contiguous:
        return f"{contiguous.group(1)}{value:%y%m%d_%H%M%S}{contiguous.group(3)}{suffix}"
    separated = re.match(
        r"^([A-Za-z][A-Za-z0-9-]*_)(20\d{6}|\d{6})_(\d{6})(.*)$", stem, re.I
    )
    if separated:
        date = value.strftime("%Y%m%d") if len(separated.group(2)) == 8 else value.strftime("%y%m%d")
        return f"{separated.group(1)}{date}_{value:%H%M%S}{separated.group(4)}{suffix}"
    compact = re.match(r"^([A-Za-z][A-Za-z0-9-]*_)(20\d{12}|\d{12})(.*)$", stem, re.I)
    if compact:
        stamp = value.strftime("%Y%m%d_%H%M%S") if len(compact.group(2)) == 14 else value.strftime("%y%m%d_%H%M%S")
        return f"{compact.group(1)}{stamp}{compact.group(3)}{suffix}"
    return None


def write_date(path: Path, value: datetime) -> None:
    exif = value.strftime("%Y:%m:%d %H:%M:%S")
    xmp = value.strftime("%Y-%m-%dT%H:%M:%S+08:00")
    result = subprocess.run([
        EXIFTOOL, "-overwrite_original_in_place",
        f"-EXIF:DateTimeOriginal={exif}", f"-EXIF:CreateDate={exif}", f"-EXIF:ModifyDate={exif}",
        f"-XMP-exif:DateTimeOriginal={exif}", f"-XMP-xmp:CreateDate={xmp}", f"-XMP-xmp:ModifyDate={xmp}",
        f"-FileCreateDate={exif}+08:00", f"-FileModifyDate={exif}+08:00", str(path),
    ], text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr or result.stdout)


def unique_target(target: Path, source: Path) -> Path:
    if target == source or not target.exists():
        return target
    for number in range(1, 1000):
        candidate = target.with_name(f"{target.stem}_{number:02d}{target.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"No collision-free target for {target}")


def spans(folders: list[str]) -> dict[str, tuple[datetime, datetime]]:
    """Conservative album windows, including overlap with embedded event albums."""
    values = {
        "220115_核酸检测": ("2022-01-01", "2022-01-16"),
        "220117_珠海学院志愿者": ("2022-01-17", "2022-01-19"),
        "220120_核酸四筛": ("2022-01-15", "2022-01-29"),
        "220130_虎年春节": ("2022-01-01", "2022-02-16"),
        "220216_春天封校": ("2022-02-16", "2022-04-30"),
        "220318_三月飘雪": ("2022-03-17", "2022-03-20"),
        "220501_夏天封校": ("2022-05-01", "2022-07-28"),
        "220520_彭晓答辩": ("2022-05-15", "2022-05-31"),
        "220605_北洋园火锅": ("2022-06-01", "2022-06-06"),
        "220607_毕业照": ("2022-06-07", "2022-06-11"),
        "220612_王健毕业照": ("2022-06-12", "2022-07-01"),
        "220702_姥姥生日": ("2022-07-01", "2022-07-28"),
        "220729_北京": ("2022-07-29", "2022-07-29"),
        "220730_石家庄": ("2022-07-30", "2022-07-30"),
        "220731_徐州": ("2022-07-31", "2022-07-31"),
        "220801_骨折摔伤": ("2022-07-31", "2022-09-01"),
        "220902_舒妍汐满月": ("2022-09-02", "2022-09-09"),
        "220910_教师节祝福": ("2022-09-10", "2022-09-16"),
        "220917_秋季封校": ("2022-09-17", "2022-10-21"),
        "221022_团建": ("2022-10-22", "2022-12-15"),
        "221216_贵州": ("2022-12-16", "2022-12-31"),
    }
    result = {}
    for name in folders:
        start, end = values[name]
        result[name] = (
            datetime.strptime(start, "%Y-%m-%d"),
            datetime.strptime(end, "%Y-%m-%d") + timedelta(days=1, seconds=-1),
        )
    return result


def row_dates(row: dict) -> dict[str, tuple[datetime | None, str]]:
    capture = first_date(row, ("DateTimeOriginal",))
    create = first_date(row, ("CreateDate", "MediaCreateDate", "TrackCreateDate"))
    file_create = first_date(row, ("FileCreateDate",))
    file_modify = first_date(row, ("FileModifyDate",))
    return {"capture": capture, "create": create, "fileCreate": file_create, "fileModify": file_modify}


def analyze() -> None:
    doc = json.loads(CACHE.read_text())
    windows = spans(doc["folders"])
    stats = Counter()
    anomalies: list[dict] = []
    for row in doc["rows"]:
        path = Path(row["SourceFile"])
        rel = str(path.relative_to(NAS))
        folder = Path(rel).parts[0]
        values = row_dates(row)
        capture, capture_tag = values["capture"]
        create, create_tag = values["create"]
        named = filename_date(path)
        start, end = windows[folder]
        if capture:
            stats[f"capture_year_{capture.year}"] += 1
        else:
            stats["missing_capture"] += 1
        if named:
            stats[f"filename_year_{named.year}"] += 1
        if EXPORT_DAY.search(path.stem):
            stats["filename_211111"] += 1
        reasons = []
        if capture is None:
            reasons.append("没有DateTimeOriginal")
        elif capture.year != 2022:
            reasons.append(f"拍摄时间为{capture:%Y-%m-%d}")
        elif not start <= capture <= end:
            reasons.append(f"拍摄时间超出该事件的保守范围({start:%m-%d}至{end:%m-%d})")
        if EXPORT_DAY.search(path.stem):
            reasons.append("文件名含211111导出日期")
        if named and named.year != 2022:
            reasons.append(f"文件名日期为{named:%Y-%m-%d}")
        if reasons:
            anomalies.append({
                "relativePath": rel,
                "folder": folder,
                "capture": capture.strftime("%Y-%m-%d %H:%M:%S") if capture else None,
                "captureTag": capture_tag,
                "create": create.strftime("%Y-%m-%d %H:%M:%S") if create else None,
                "createTag": create_tag,
                "fileCreate": values["fileCreate"][0].strftime("%Y-%m-%d %H:%M:%S") if values["fileCreate"][0] else None,
                "fileModify": values["fileModify"][0].strftime("%Y-%m-%d %H:%M:%S") if values["fileModify"][0] else None,
                "filenameDate": named.strftime("%Y-%m-%d %H:%M:%S") if named else None,
                "expectedStart": start.strftime("%Y-%m-%d"),
                "expectedEnd": end.strftime("%Y-%m-%d"),
                "reason": "；".join(reasons),
                "width": row.get("File:ImageWidth") or row.get("EXIF:ImageWidth"),
                "height": row.get("File:ImageHeight") or row.get("EXIF:ImageHeight"),
                "size": row.get("System:FileSize"),
            })
    summary = {
        "scanned": len(doc["rows"]),
        "anomalies": len(anomalies),
        "filename211111": stats["filename_211111"],
        "missingCapture": stats["missing_capture"],
        "captureYearCounts": dict(sorted((k.removeprefix("capture_year_"), v) for k, v in stats.items() if k.startswith("capture_year_"))),
        "filenameYearCounts": dict(sorted((k.removeprefix("filename_year_"), v) for k, v in stats.items() if k.startswith("filename_year_"))),
        "byFolder": dict(Counter(item["folder"] for item in anomalies)),
    }
    PLAN.write_text(json.dumps({"summary": summary, "anomalies": anomalies}, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("SAMPLE")
    for item in anomalies[:80]:
        print(json.dumps(item, ensure_ascii=False))


OLD_EXACT_MOVES = {
    "220130_虎年春节/photo/CLOUDUH_211213054606.jpg": "211130_封校期间",
    "220130_虎年春节/photo/CLOUDUH_211213311814.jpg": "211130_封校期间",
    "220130_虎年春节/photo/CLOUDUH_211215254529.jpg": "211130_封校期间",
    "220130_虎年春节/photo/CLOUDUH_211215313726.jpg": "211130_封校期间",
}


def build_apply_plan(doc: dict) -> dict:
    rows = {str(Path(row["SourceFile"]).relative_to(NAS)): row for row in doc["rows"]}
    groups: list[list[str]] = json.loads(PIXEL_GROUPS.read_text())
    corrections: dict[str, dict] = {}
    unresolved_groups: list[list[str]] = []

    # Identical rendered images inherit the timestamp of a dated camera original.
    for group in groups:
        known = [dto(rows[rel]) for rel in group if dto(rows[rel])]
        named = close_dates([dated_img(Path(rel)) for rel in group if dated_img(Path(rel))])
        disagree = len(known) < len(group) or (known and (max(known) - min(known)).total_seconds() > 120)
        filename_disagree = len(named) > 1
        if not disagree and not filename_disagree:
            continue
        value, basis = canonical_group_date(group, rows)
        if value:
            for rel in group:
                current = dto(rows[rel])
                if not current or abs((current - value).total_seconds()) > 2:
                    corrections[rel] = {"date": value, "basis": basis, "related": group}
        else:
            unresolved_groups.append(group)

    # Every remaining missing DateTimeOriginal has a full IMG filename and a
    # matching filesystem modification time.  This is independent confirmation.
    for rel, row in rows.items():
        if dto(row) or rel in corrections:
            continue
        named = filename_date(Path(rel))
        modified = row_dates(row)["fileModify"][0]
        if named and named.year == 2022 and modified and abs((named - modified).total_seconds()) <= 2:
            corrections[rel] = {
                "date": named,
                "basis": "缺少拍摄字段；完整IMG文件名与原文件修改时间一致",
                "related": [],
            }

    # A few files have exact/pixel-identical originals in the broad daily album.
    moves: dict[str, str] = dict(OLD_EXACT_MOVES)
    exact_groups: list[list[str]] = json.loads(Path("/private/tmp/photo-2022-exact-duplicates.json").read_text())
    for group in exact_groups:
        if any(rel.startswith("220501_夏天封校/") for rel in group):
            for rel in group:
                if rel.startswith("220605_北洋园火锅/"):
                    moves[rel] = "220501_夏天封校"
        if any(rel.startswith("220115_核酸检测/") for rel in group):
            for rel in group:
                if rel.startswith("220117_珠海学院志愿者/"):
                    moves[rel] = "220115_核酸检测"
    for rel in (
        "220605_北洋园火锅/photo/CLOUDUH_220522260030.jpg",
        "220605_北洋园火锅/photo/CLOUDUH_220522260055.jpg",
        "220605_北洋园火锅/photo/CLOUDUH_220522260153.jpg",
        "220605_北洋园火锅/photo/CLOUDUH_220823273859.jpg",
        "220729_北京/photo/IMG_20220827_233859.jpg",
    ):
        moves[rel] = "220501_夏天封校"

    unresolved: list[dict] = []
    unresolved_paths: set[str] = set()
    for group in unresolved_groups:
        representative = max(group, key=lambda rel: int(rows[rel].get("System:FileSize", 0) or 0))
        unresolved_paths.update(group)
        choices = [
            f"{Path(rel).name}={dto(rows[rel]).strftime('%Y-%m-%d %H:%M:%S') if dto(rows[rel]) else '无'}"
            for rel in group
        ]
        unresolved.append({
            "relativePath": representative,
            "relatedPaths": group,
            "reason": "同一画面存在互相冲突的时间，且没有可唯一判定的带日期原片：" + "；".join(choices),
        })

    standalone = {
        "220130_虎年春节/photo/CLOUDUH_211130191517.jpg": "EXIF为2021-08-04，文件名为2021-11-30，未找到同图原片",
        "220917_秋季封校/photo/CLOUDUH_221022080802.jpg": "文件名可解释为10月8日22:08，EXIF为10月8日22:05，未找到同图原片",
    }
    for rel, reason in standalone.items():
        unresolved_paths.add(rel)
        unresolved.append({"relativePath": rel, "relatedPaths": [rel], "reason": reason})

    # Non-CLOUDUH camera-style names with a same-day time conflict are left to
    # the owner unless an identical image already supplied the answer.
    for rel, row in rows.items():
        if rel in corrections or rel in unresolved_paths or not re.match(r"IMG_20\d{6}_\d{6}", Path(rel).stem, re.I):
            continue
        current, named = dto(row), filename_date(Path(rel))
        if current and named and current.date() == named.date() and abs((current - named).total_seconds()) > 120:
            unresolved_paths.add(rel)
            unresolved.append({
                "relativePath": rel,
                "relatedPaths": [rel],
                "reason": f"文件名为{named:%Y-%m-%d %H:%M:%S}，EXIF为{current:%Y-%m-%d %H:%M:%S}，没有同图原片可裁决",
            })

    return {
        "corrections": corrections,
        "moves": moves,
        "unresolved": unresolved,
        "unresolvedPaths": sorted(unresolved_paths),
    }


def related_copies(primary: Path) -> list[tuple[Path, str]]:
    result = [(primary, "photo")]
    album = primary.parents[1]
    root_copy = album / primary.name
    if root_copy.is_file():
        result.append((root_copy, "root-selected"))
    for selected in primary.parent.glob(f"{primary.stem}__selected*{primary.suffix}"):
        if selected.is_file():
            result.append((selected, "photo-selected"))
    return result


def apply() -> None:
    doc = json.loads(CACHE.read_text())
    rows = {str(Path(row["SourceFile"]).relative_to(NAS)): row for row in doc["rows"]}
    plan = build_apply_plan(doc)
    corrections: dict[str, dict] = plan["corrections"]
    moves: dict[str, str] = plan["moves"]
    unresolved_paths = set(plan["unresolvedPaths"])
    changed_dates: list[dict] = []
    renamed: list[dict] = []
    moved: list[dict] = []
    final_primary: dict[str, Path] = {}
    extra_sync: set[Path] = set()

    # First update embedded metadata on every affected original and selected copy.
    for index, (rel, action) in enumerate(sorted(corrections.items()), 1):
        primary = NAS / rel
        for path, kind in related_copies(primary):
            before = dto(rows[rel]).strftime("%Y-%m-%d %H:%M:%S") if dto(rows[rel]) else None
            write_date(path, action["date"])
            changed_dates.append({
                "path": str(path.relative_to(NAS)), "kind": kind, "before": before,
                "after": action["date"].strftime("%Y-%m-%d %H:%M:%S"), "basis": action["basis"],
            })
            extra_sync.add(path)
        if index % 20 == 0:
            print(f"PROGRESS date fixes {index}/{len(corrections)}", flush=True)

    # Then move clear misclassifications and repair timestamp-bearing filenames.
    for rel, row in sorted(rows.items()):
        primary = NAS / rel
        if not primary.exists():
            continue
        effective = corrections.get(rel, {}).get("date") or dto(row)
        target_folder = moves.get(rel)
        manual_old = rel in OLD_EXACT_MOVES
        new_name = None
        if effective and rel not in unresolved_paths:
            candidate = standard_timestamp_name(primary, effective)
            named = filename_date(primary)
            if candidate and (
                rel in corrections or manual_old or named is None
                or abs((named - effective).total_seconds()) > 120
            ):
                new_name = candidate
        if not target_folder and not new_name:
            final_primary[rel] = primary
            continue

        copies = related_copies(primary)
        for path, kind in copies:
            destination_album = NAS / (target_folder or Path(rel).parts[0])
            destination_dir = destination_album / "photo" if kind != "root-selected" else destination_album
            destination_dir.mkdir(parents=True, exist_ok=True)
            if new_name:
                if kind == "photo-selected":
                    replacement = Path(new_name).stem + path.stem[len(primary.stem):] + path.suffix
                else:
                    replacement = new_name
            else:
                replacement = path.name
            target = unique_target(destination_dir / replacement, path)
            old_rel = str(path.relative_to(NAS))
            if target != path:
                shutil.move(str(path), str(target))
            new_rel = str(target.relative_to(NAS))
            if old_rel != new_rel:
                if path.parent != target.parent:
                    moved.append({"from": old_rel, "to": new_rel, "kind": kind})
                if path.name != target.name:
                    renamed.append({"from": old_rel, "to": new_rel, "kind": kind})
            extra_sync.add(target)
            if kind == "photo":
                final_primary[rel] = target

    # Synchronize filesystem creation/modification times to trusted capture time.
    sync_paths: list[Path] = []
    for rel, row in rows.items():
        effective = corrections.get(rel, {}).get("date") or dto(row)
        path = final_primary.get(rel, NAS / rel)
        if effective and effective.year == 2022 and rel not in unresolved_paths and path.exists():
            sync_paths.append(path)
    sync_paths.extend(path for path in extra_sync if path.exists())
    sync_paths = sorted(set(sync_paths))
    for start in range(0, len(sync_paths), 250):
        chunk = sync_paths[start:start + 250]
        result = subprocess.run([
            EXIFTOOL, "-overwrite_original_in_place", "-FileCreateDate<DateTimeOriginal",
            "-FileModifyDate<DateTimeOriginal", *map(str, chunk),
        ], text=True, capture_output=True)
        if result.returncode:
            raise RuntimeError(result.stderr or result.stdout)
        print(f"PROGRESS filesystem times {min(start + len(chunk), len(sync_paths))}/{len(sync_paths)}", flush=True)

    # Build a fresh review manifest with only genuinely undecidable cases.
    review_items = []
    review_by_rel = {item["relativePath"]: item for item in plan["unresolved"]}
    target_folders = sorted(
        top.name for top in NAS.iterdir()
        if top.is_dir() and len(top.name) >= 7 and top.name[:6].isdigit() and top.name[:2] in {"21", "22"}
    )
    for rel, unresolved in sorted(review_by_rel.items()):
        row = rows[rel]
        path = NAS / rel
        current = dto(row)
        item_id = hashlib.sha1(rel.encode()).hexdigest()[:20]
        suggested = "210700_开学之前" if rel.endswith("CLOUDUH_211130191517.jpg") else Path(rel).parts[0]
        review_items.append({
            "id": item_id,
            "relativePath": rel,
            "relatedPaths": unresolved["relatedPaths"],
            "filename": path.name,
            "currentFolder": Path(rel).parts[0],
            "captureDate": current.strftime("%Y-%m-%d %H:%M:%S") if current else None,
            "dateSource": "存在冲突，需人工判断",
            "fileCreateDate": row_dates(row)["fileCreate"][0].strftime("%Y-%m-%d %H:%M:%S") if row_dates(row)["fileCreate"][0] else None,
            "fileModifyDate": row_dates(row)["fileModify"][0].strftime("%Y-%m-%d %H:%M:%S") if row_dates(row)["fileModify"][0] else None,
            "expectedStart": "2022-01-01",
            "expectedEnd": "2022-12-31",
            "suggestedFolder": suggested,
            "reason": unresolved["reason"],
            "thumbnail": "http://127.0.0.1:3002/media/" + quote(rel, safe="/") + "?size=1400",
        })
    manifest = {
        "version": 5,
        "generatedAt": datetime.now().astimezone().isoformat(),
        "range": "2022-export-date-audit",
        "ignoredFolders": [],
        "folderCount": len(doc["folders"]),
        "scanned": len(doc["rows"]),
        "cameraFilesFixed": len(corrections),
        "autoFixed": len(corrections),
        "count": len(review_items),
        "folders": target_folders,
        "items": review_items,
    }
    PUBLIC.mkdir(parents=True, exist_ok=True)
    (PUBLIC / "review-items.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))

    result = {
        "generatedAt": datetime.now().astimezone().isoformat(),
        "scanned": len(doc["rows"]),
        "primaryDateFixes": len(corrections),
        "dateWritesIncludingSelected": len(changed_dates),
        "filesystemTimesSynced": len(sync_paths),
        "primaryMovesPlanned": len(moves),
        "movesIncludingSelected": len(moved),
        "renamesIncludingSelected": len(renamed),
        "manualReview": len(review_items),
        "changedDates": changed_dates,
        "moves": moved,
        "renames": renamed,
        "reviewItems": [{"relativePath": item["relativePath"], "reason": item["reason"]} for item in review_items],
    }
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({key: value for key, value in result.items() if key not in {"changedDates", "moves", "renames", "reviewItems"}}, ensure_ascii=False, indent=2))


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
