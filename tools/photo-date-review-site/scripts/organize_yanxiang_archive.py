#!/usr/bin/env python3
"""Select and copy Yanxiang team camera media into daily folders."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


ROOT = Path("/Volumes/FATCLOUD")
YEARS = ("2017", "2018", "2019", "2020")
OUTPUT = ROOT / "燕翔相册_按日期整理"
CACHE = Path("/private/tmp/yanxiang-media-metadata.json")
PLAN = Path("/private/tmp/yanxiang-media-plan.json")
LOG = Path("/Users/cloudu/Documents/document/05_Note/clouduh.github.io/tools/photo-date-review-site/tools-data/yanxiang-archive-result.json")
EXIFTOOL = "/opt/homebrew/bin/exiftool"

PHOTO_EXTS = {".jpg", ".jpeg", ".heic", ".tif", ".tiff", ".cr2", ".cr3", ".nef", ".arw", ".dng", ".raf", ".orf", ".rw2"}
RAW_EXTS = {".cr2", ".cr3", ".nef", ".arw", ".dng", ".raf", ".orf", ".rw2"}
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".avi", ".mts", ".m2ts", ".wmv", ".mpg", ".mpeg"}

DESIGN = re.compile(r"(?:海报|展板|logo|标识|标志|设计报告|招商方案|成本报告|邀请函|幕布|案例分析|证明材料|队服|明信片|纪念品|喷绘|名片|字体|document fonts|links|排版|封面|画册|手册|模板|icon|图标)", re.I)
PHOTO_CONTEXT = re.compile(r"(?:照片|摄影|日常|赛场|招新|发布会|练车|合影|毕业|加工|车展|采访|参观|比赛|聚餐|例会|换届|跑动|车队|队员|活动|试车|装车|调车|赛车)", re.I)
CAMERA_NAME = re.compile(r"^(?:IMG[_-]?|DSC[NF]?[_-]?|_MG_|YX0_|MVI_|SAM_|GOPR|DJI_|C\d{4}|P\d{7}|20\d{6}[_-]\d{6})", re.I)
VIDEO_RAW = re.compile(r"(?:视频素材|剪辑素材|原片|片段|镜头|工程|premiere|after effects|\bAE\b|缓存|代理|草稿|临时|序列|prproj|素材包|车载视频|动态视频|云台|山狗|yxrt|零碎|不正经)", re.I)
VIDEO_FINAL = re.compile(r"(?:成片|成品|最终|final|完成版|完整版|宣传片|纪录片|回顾|总结|官方视频|参赛视频|剪辑版|正片|预告片|视频作品|燕翔飞扬|跑动视频\d*)", re.I)
VIDEO_GENERIC = re.compile(r"^(?:IMG_|MVI_|YX\d_|YX0_|C\d{4}|GOPR|000\d|VID_|DSC_|20\d{6}[_-]|2016_)", re.I)


def discover() -> tuple[list[Path], list[Path]]:
    photos, videos = [], []
    for year in YEARS:
        for path in (ROOT / year).rglob("*"):
            if not path.is_file() or path.name.startswith("._") or "@eaDir" in path.parts:
                continue
            suffix = path.suffix.lower()
            if suffix in PHOTO_EXTS:
                if DESIGN.search(str(path.relative_to(ROOT))):
                    continue
                photos.append(path)
            elif suffix in VIDEO_EXTS:
                videos.append(path)
    return photos, videos


def scan() -> None:
    photos, videos = discover()
    files = photos + videos
    rows = []
    print(f"SCANNING {len(photos)} photos and {len(videos)} videos", flush=True)
    for start in range(0, len(files), 400):
        chunk = files[start:start + 400]
        result = subprocess.run([
            EXIFTOOL, "-j", "-G1", "-a", "-s",
            "-DateTimeOriginal", "-CreateDate", "-MediaCreateDate", "-TrackCreateDate",
            "-FileModifyDate", "-Make", "-Model", "-FileType", "-MIMEType",
            "-ImageWidth", "-ImageHeight", "-Duration#", "-VideoFrameRate", *map(str, chunk),
        ], text=True, capture_output=True)
        if result.stdout.strip():
            try:
                rows.extend(json.loads(result.stdout))
            except json.JSONDecodeError:
                print(f"WARNING unreadable metadata chunk at {start}; retrying individually", flush=True)
                for path in chunk:
                    single = subprocess.run([
                        EXIFTOOL, "-j", "-G1", "-a", "-s", "-DateTimeOriginal", "-CreateDate",
                        "-MediaCreateDate", "-TrackCreateDate", "-FileModifyDate", "-Make", "-Model",
                        "-FileType", "-MIMEType", "-ImageWidth", "-ImageHeight", "-Duration#",
                        "-VideoFrameRate", str(path),
                    ], text=True, capture_output=True)
                    try:
                        rows.extend(json.loads(single.stdout))
                    except json.JSONDecodeError:
                        rows.append({"SourceFile": str(path), "ScanError": (single.stderr or "unreadable metadata").strip()})
        print(f"PROGRESS {min(start + len(chunk), len(files))}/{len(files)}", flush=True)
    CACHE.write_text(json.dumps({"photos": len(photos), "videos": len(videos), "rows": rows}, ensure_ascii=False))
    print(json.dumps({"photos": len(photos), "videos": len(videos), "rows": len(rows)}, ensure_ascii=False))


def parse(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            result = datetime.strptime(value[:19], fmt)
            if 1990 <= result.year <= 2026:
                return result
        except ValueError:
            pass
    return None


def values(row: dict, suffix: str) -> list[str]:
    return [str(value) for key, value in row.items() if key.split(":")[-1] == suffix and value]


def first_date(row: dict, suffixes: tuple[str, ...]) -> tuple[datetime | None, str]:
    for suffix in suffixes:
        for raw in values(row, suffix):
            result = parse(raw)
            if result:
                return result, suffix
    return None, ""


def filename_date(path: Path) -> datetime | None:
    for pattern in (
        r"(?<!\d)(20\d{2})[-_.]?(\d{2})[-_.]?(\d{2})[-_ T]?(\d{2})[-_.:]?(\d{2})[-_.:]?(\d{2})(?!\d)",
        r"(?<!\d)(20\d{2})[-_.](\d{1,2})[-_.](\d{1,2})(?!\d)",
    ):
        match = re.search(pattern, path.stem)
        if not match:
            continue
        parts = list(map(int, match.groups()))
        while len(parts) < 6:
            parts.append(12 if len(parts) == 3 else 0)
        try:
            return datetime(*parts)
        except ValueError:
            pass
    return None


def path_date(path: Path) -> datetime | None:
    text = "/".join(path.relative_to(ROOT).parts[:-1])
    match = re.search(r"(?<!\d)(20(?:1[0-9]|20))[.年_-](\d{1,2})[.月_-](\d{1,2})(?:日)?(?!\d)", text)
    if match:
        try:
            return datetime(*map(int, match.groups()), 12)
        except ValueError:
            pass
    year = int(path.relative_to(ROOT).parts[0])
    matches = re.findall(r"(?:^|[/ ])(1[0-2]|0?[1-9])[.月-]([0-3]?\d)(?:日)?(?:$|[/ ])", text)
    if matches:
        month, day = map(int, matches[-1])
        try:
            return datetime(year, month, day, 12)
        except ValueError:
            pass
    return None


def capture_date(row: dict, path: Path, video: bool) -> tuple[datetime | None, str]:
    if video and is_final_video(path):
        named = filename_date(path) or path_date(path)
        if named:
            return named, "成片文件名/目录日期"
    suffixes = ("MediaCreateDate", "TrackCreateDate", "CreateDate", "DateTimeOriginal") if video else ("DateTimeOriginal", "CreateDate")
    value, source = first_date(row, suffixes)
    if value:
        # QuickTime UTC zero dates are not useful.
        if not (video and value.year == 1904):
            source_year = int(path.relative_to(ROOT).parts[0])
            folder = path_date(path)
            if video and folder and abs(value.year - source_year) > 1:
                return folder, "目录日期（相机年份明显错误）"
            return value, source
    named = filename_date(path)
    if named:
        return named, "文件名"
    folder = path_date(path)
    if folder:
        return folder, "目录日期"
    modified, source = first_date(row, ("FileModifyDate",))
    source_year = int(path.relative_to(ROOT).parts[0])
    if modified and abs(modified.year - source_year) <= 1:
        return modified, source
    return None, ""


def camera_metadata(row: dict) -> bool:
    return bool(values(row, "Make") or values(row, "Model"))


def is_final_video(path: Path) -> bool:
    return bool(VIDEO_FINAL.search(path.name) or re.search(r"(?:完成后|第二版|定稿|终稿)", str(path.parent), re.I))


def classify(row: dict, videos_in_parent: int = 0) -> tuple[bool, str, datetime | None, str]:
    path = Path(row["SourceFile"])
    relative = str(path.relative_to(ROOT))
    suffix = path.suffix.lower()
    is_video = suffix in VIDEO_EXTS
    date, date_source = capture_date(row, path, is_video)
    if not date:
        return False, "没有可靠日期", None, ""
    if suffix in RAW_EXTS:
        return True, "RAW相机原片", date, date_source
    if is_video:
        if path.name.startswith("2016_0101") and int(path.relative_to(ROOT).parts[0]) >= 2018:
            return False, "相机默认2016-01-01日期且无法可靠定位", date, date_source
        if is_final_video(path):
            return True, "明确的剪辑成片/正式视频", date, date_source
        if VIDEO_RAW.search(relative):
            return False, "剪辑素材/零碎片段目录", date, date_source
        duration_values = values(row, "Duration")
        try:
            duration = float(duration_values[0]) if duration_values else 0
        except ValueError:
            duration = 0
        if videos_in_parent > 3 and VIDEO_GENERIC.search(path.name):
            return False, "批量目录中的相机编号零碎视频", date, date_source
        if camera_metadata(row) or CAMERA_NAME.search(path.name) or PHOTO_CONTEXT.search(relative):
            if duration and duration < 3:
                return False, "少于3秒的零碎视频", date, date_source
            return True, "活动目录中的相机视频", date, date_source
        return False, "无法确认是相机视频或成片", date, date_source

    if DESIGN.search(relative):
        return False, "设计/海报/展板相关目录", date, date_source
    if camera_metadata(row):
        return True, "包含相机厂商或型号元数据", date, date_source
    width_values, height_values = values(row, "ImageWidth"), values(row, "ImageHeight")
    try:
        width, height = int(float(width_values[0])), int(float(height_values[0]))
    except (ValueError, IndexError):
        width = height = 0
    if CAMERA_NAME.search(path.name) and PHOTO_CONTEXT.search(relative) and width >= 640 and height >= 480:
        return True, "活动照片目录中的相机式文件名", date, date_source
    return False, "缺少相机依据或疑似设计图片", date, date_source


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def analyze() -> None:
    doc = json.loads(CACHE.read_text())
    included, excluded = [], []
    video_counts = Counter(str(Path(row["SourceFile"]).parent) for row in doc["rows"] if Path(row["SourceFile"]).suffix.lower() in VIDEO_EXTS)
    for row in doc["rows"]:
        path = Path(row["SourceFile"])
        keep, reason, date, source = classify(row, video_counts[str(path.parent)])
        item = {
            "source": str(path.relative_to(ROOT)), "kind": "video" if path.suffix.lower() in VIDEO_EXTS else "photo",
            "date": date.strftime("%Y-%m-%d %H:%M:%S") if date else None, "dateSource": source,
            "reason": reason, "size": path.stat().st_size,
        }
        (included if keep else excluded).append(item)

    # Exact-byte deduplication, hashing only repeated sizes.
    by_size: dict[int, list[dict]] = defaultdict(list)
    for item in included:
        by_size[item["size"]].append(item)
    deduped, duplicates = [], []
    for size, group in by_size.items():
        if len(group) == 1:
            deduped.append(group[0])
            continue
        by_hash: dict[str, list[dict]] = defaultdict(list)
        for item in group:
            by_hash[file_sha(ROOT / item["source"])].append(item)
        for digest, same in by_hash.items():
            same.sort(key=lambda item: (DESIGN.search(item["source"]) is not None, len(Path(item["source"]).parts), item["source"]))
            deduped.append(same[0])
            duplicates.extend({"duplicate": item["source"], "kept": same[0]["source"], "sha256": digest} for item in same[1:])

    deduped.sort(key=lambda item: (item["date"], item["kind"], item["source"]))
    plan = {
        "generatedAt": datetime.now().astimezone().isoformat(), "output": str(OUTPUT),
        "summary": {
            "scanned": len(doc["rows"]), "includedBeforeDedup": len(included), "included": len(deduped),
            "photos": sum(item["kind"] == "photo" for item in deduped), "videos": sum(item["kind"] == "video" for item in deduped),
            "duplicatesSkipped": len(duplicates), "excluded": len(excluded),
            "bytes": sum(item["size"] for item in deduped), "days": len({item["date"][:10] for item in deduped}),
        },
        "items": deduped, "duplicates": duplicates,
        "excludedSummary": dict(Counter(item["reason"] for item in excluded)),
        "excludedSamples": excluded[:1000],
    }
    PLAN.write_text(json.dumps(plan, ensure_ascii=False, indent=2))
    print(json.dumps(plan["summary"], ensure_ascii=False, indent=2))
    print(json.dumps(plan["excludedSummary"], ensure_ascii=False, indent=2))


def unique_target(path: Path) -> tuple[Path, bool]:
    if not path.exists():
        return path, False
    for number in range(2, 1000):
        candidate = path.with_name(f"{path.stem}__{number}{path.suffix}")
        if not candidate.exists():
            return candidate, True
    raise RuntimeError(f"No collision-free name for {path}")


def apply(resume: bool = False) -> None:
    plan = json.loads(PLAN.read_text())
    if OUTPUT.exists() and not resume:
        raise SystemExit(f"Refusing to overwrite existing output: {OUTPUT}")
    copied, renamed, errors = [], [], []
    skipped_existing = 0
    OUTPUT.mkdir(parents=True, exist_ok=resume)
    name_counts: Counter[tuple[str, str, str]] = Counter()
    for index, item in enumerate(plan["items"], 1):
        source = ROOT / item["source"]
        destination_dir = OUTPUT / item["date"][:10] / item["kind"]
        destination_dir.mkdir(parents=True, exist_ok=True)
        key = (item["date"][:10], item["kind"], source.name.lower())
        name_counts[key] += 1
        ordinal = name_counts[key]
        destination = destination_dir / (source.name if ordinal == 1 else f"{source.stem}__{ordinal}{source.suffix}")
        collided = ordinal > 1
        try:
            if resume and destination.exists():
                if destination.stat().st_size == source.stat().st_size:
                    skipped_existing += 1
                    continue
                destination.unlink()
            shutil.copy2(source, destination)
            if destination.stat().st_size != source.stat().st_size:
                raise RuntimeError("size mismatch")
            copied.append({"source": item["source"], "target": str(destination.relative_to(ROOT)), "date": item["date"], "reason": item["reason"]})
            if collided:
                renamed.append({"source": item["source"], "targetName": destination.name})
        except Exception as error:
            errors.append({"source": item["source"], "error": str(error)})
        if index % 200 == 0:
            print(f"PROGRESS {index}/{len(plan['items'])}", flush=True)
    result = {
        "generatedAt": datetime.now().astimezone().isoformat(), "status": "ok" if not errors else "partial",
        **plan["summary"], "copied": len(copied), "skippedExisting": skipped_existing,
        "renamedForCollision": len(renamed), "errors": errors,
        "excludedSummary": plan["excludedSummary"], "duplicatesSkipped": len(plan["duplicates"]),
    }
    LOG.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scan", action="store_true")
    parser.add_argument("--analyze", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if args.scan:
        scan()
    elif args.analyze:
        analyze()
    elif args.apply:
        apply()
    elif args.resume:
        apply(resume=True)
    else:
        raise SystemExit("Pass --scan, --analyze, or --apply")


if __name__ == "__main__":
    main()
