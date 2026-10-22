#!/usr/bin/env python3
"""Apply the final photo date calibration review to the mounted NAS.

The script is dry-run by default. Pass --apply to write metadata, move/rename
files, and delete only the explicitly reviewed or pixel-identical duplicates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path


NAS = Path("/Volumes/photo")
ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "public/calibration/calibration-items.json"
REVIEWS = Path("/Users/cloudu/Downloads/photo-date-calibration-review.json")
EXIFTOOL = Path("/opt/homebrew/bin/exiftool")
RUN_NAME = "calibration-final-20260902"
BACKUP_ROOT = NAS / "170900_备份/metadata-originals" / RUN_NAME
LOG_ROOT = NAS / "170900_备份/_operation_logs" / RUN_NAME


@dataclass
class Action:
    source: str
    new_datetime: str
    target_folder: str
    reason: str


def parse_dt(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def exif_dt(dt: datetime) -> str:
    return dt.strftime("%Y:%m:%d %H:%M:%S")


def file_dt(dt: datetime) -> str:
    return dt.strftime("%Y:%m:%d %H:%M:%S+08:00")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(1, 10_000):
        candidate = path.with_name(f"{path.stem}_{index}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Cannot create a unique path for {path}")


def rename_from_datetime(filename: str, dt: datetime) -> str:
    """Replace a visible embedded date/time only when its date is wrong."""
    stem, suffix = os.path.splitext(filename)
    patterns = [
        (re.compile(r"(?<!\d)(20\d{2})_(\d{2})_(\d{2})_(\d{2})_(\d{2})_(\d{2})(?!\d)"),
         dt.strftime("%Y_%m_%d_%H_%M_%S")),
        (re.compile(r"(?<!\d)(20\d{2})-(\d{2})-(\d{2})-(\d{2})-(\d{2})-(\d{2})(?!\d)"),
         dt.strftime("%Y-%m-%d-%H-%M-%S")),
        (re.compile(r"(?<!\d)(20\d{2})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})(?!\d)"),
         dt.strftime("%Y%m%d_%H%M%S")),
        (re.compile(r"(?<!\d)(20\d{2})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})(?!\d)"),
         dt.strftime("%Y%m%d%H%M%S")),
        (re.compile(r"(?<!\d)(\d{2})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})(?!\d)"),
         dt.strftime("%y%m%d_%H%M%S")),
        (re.compile(r"(?<!\d)(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})(?!\d)"),
         dt.strftime("%y%m%d%H%M%S")),
    ]
    for pattern, replacement in patterns:
        match = pattern.search(stem)
        if not match:
            continue
        year = int(match.group(1))
        if year < 100:
            year += 2000
        try:
            embedded = datetime(year, int(match.group(2)), int(match.group(3)))
        except ValueError:
            continue
        if embedded.date() == dt.date():
            return filename
        return stem[: match.start()] + replacement + stem[match.end() :] + suffix
    return filename


def build_plan() -> tuple[list[Action], list[dict]]:
    manifest = json.loads(MANIFEST.read_text())
    review_doc = json.loads(REVIEWS.read_text())
    by_rel = {x["relativePath"]: x for x in manifest["items"]}
    reviews = {x["relativePath"]: x for x in review_doc["reviews"]}
    actions: dict[str, Action] = {}

    def current(rel: str) -> datetime:
        row = reviews.get(rel) or by_rel.get(rel)
        value = row.get("currentCapture") if "currentCapture" in row else row.get("captureDate")
        return parse_dt(value)

    def add(rel: str, dt: datetime, folder: str | None, reason: str) -> None:
        target = folder or rel.split("/", 1)[0]
        actions[rel] = Action(rel, iso(dt), target, reason)

    # National Day 2017: dates supplied by the user; times spread naturally.
    add("171002_国庆回家/photo/-4ab10a8f0fdb0409.jpg", datetime(2017, 10, 3, 20, 0, 0), None, "备注：3号晚上")
    add("171002_国庆回家/photo/1507254611965.jpeg", datetime(2017, 10, 3, 20, 0, 10), None, "备注：3号晚上")
    add("171002_国庆回家/photo/1507254618819.jpeg", datetime(2017, 10, 3, 16, 0, 0), None, "备注：3号下午16点")
    add("171002_国庆回家/photo/CLOUDUH_180120194810.jpeg", datetime(2017, 10, 3, 20, 0, 20), None, "备注：3号晚上")
    add("171002_国庆回家/photo/79adabe93cc35c63.jpg", datetime(2017, 10, 5, 20, 0, 0), None, "备注：5号晚上")
    add("171002_国庆回家/photo/1507254667375.jpeg", datetime(2017, 10, 5, 20, 0, 10), None, "备注：5号晚上")
    add("171002_国庆回家/photo/-4dbc70c520396f9c.jpg", datetime(2017, 10, 5, 20, 0, 20), None, "备注：5号晚上")
    add("171002_国庆回家/photo/1507254624103.jpeg", datetime(2017, 10, 5, 20, 0, 30), None, "备注：5号晚上")

    # The four dorm KTV photos are tied to the trusted 2018-03-02 reference.
    for offset, name in enumerate([
        "39a91eaa38b6d398.jpg", "2e31476c5694bee5.jpg",
        "-17d581f569350f7.jpg", "-2d2e0d51153d163.jpg",
    ]):
        rel = f"171022_大一冬天之前/photo/{name}"
        add(rel, datetime(2018, 3, 2, 20, 19, 27) + timedelta(seconds=offset),
            "180226_大一下开学", "与 IMG_20180302_201927 同场宿舍KTV")

    add("180226_大一下开学/photo/wechat_180905_000142.jpg", datetime(2018, 4, 14, 16, 4, 55),
        "180407_保定实习", "与 -6694c436e2e88279.jpg 为4月14日同场景")

    # Entire Gangxi set belongs to 2019-03-17. Preserve time-of-day.
    for row in manifest["items"]:
        if row["currentFolder"] == "180317_港西绿地":
            old = parse_dt(row["captureDate"])
            add(row["relativePath"], old.replace(year=2019, month=3, day=17),
                "190317_港西绿地", "整组备注：统一为2019-03-17")

    # Beijing trip.
    add("180428_北京/photo/-3ab1ca7270d9dc6a.jpg", datetime(2018, 5, 1, 0, 57, 19), None, "备注：5月1日凌晨")
    add("180428_北京/photo/-44e4f18f3a814b45.jpg", datetime(2018, 4, 29, 3, 22, 0), None, "备注：4月29日凌晨3:22")
    add("180428_北京/photo/-f2246417d8637b6.jpg", datetime(2018, 4, 29, 8, 16, 0), None, "备注：4月29日早上8:16")
    add("180428_北京/photo/2d8750701fe839ad.jpg", datetime(2018, 4, 29, 5, 27, 0), None, "备注：4月29日早上5:27")
    add("180428_北京/photo/731793d224b3f60.jpg", datetime(2018, 4, 29, 5, 27, 1), None, "与2d8750701fe839ad同场自拍")
    add("180428_北京/photo/41e4cfbf8bdd47a0.jpg", datetime(2018, 4, 29, 11, 6, 36), None, "备注：4月29日上午；按同一林地序列")
    add("180428_北京/photo/IMG_20180508_111113.jpg", datetime(2018, 4, 29, 18, 54, 54), None, "现有拍摄时间可信，仅统一元数据并修正文件名")
    collage_names = [
        "pt2018_04_29_23_45_05.jpg", "pt2018_04_29_23_46_38.jpg",
        "pt2018_04_29_23_49_22.jpg", "pt2018_04_29_23_51_38.jpg",
        "pt2018_04_29_23_54_04.jpg", "pt2018_04_29_23_55_55.jpg",
        "pt2018_04_29_23_57_05.jpg", "pt2018_04_29_23_58_50.jpg",
        "pt2018_04_30_22_07_49.jpg", "pt2018_04_30_22_10_02.jpg",
        "pt2018_04_30_22_15_25.jpg",
    ]
    for offset, name in enumerate(collage_names, start=1):
        add(f"180428_北京/photo/{name}", datetime(2018, 5, 1, 21, 26, 54) + timedelta(seconds=offset),
            None, "北京拼图统一到5月1日时间点")

    add("180428_大一暑假之前/photo/d740a285e82a492.jpg", datetime(2018, 5, 18, 15, 18, 6), None, "备注：5月18日")
    add("180512_秦马志愿者/photo/IMG_20211111_194800_1.jpg", datetime(2018, 5, 13, 19, 48, 0), None, "备注：5月13日")

    add("180530_进入暑期/photo/V{@`GZ2{JVIDHMV6PD{N{WA.png", datetime(2018, 7, 28, 16, 30, 0),
        "180700_大一暑假", "备注：2018年7月底")
    add("180530_进入暑期/photo/2083bc3e2d016cd6.jpg", datetime(2018, 6, 13, 22, 52, 45), None,
        "与-77642798907296aa为同场演讲，沿用其日期")
    add("180530_进入暑期/photo/-77642798907296aa.jpg", datetime(2018, 6, 13, 22, 52, 46), None,
        "同场演讲关联")
    add("180530_进入暑期/photo/IMG_2245.PNG", datetime(2018, 6, 5, 18, 9, 37), None,
        "与wechat_180605_180937为同场舞台照片")

    for offset, name in enumerate(["IMG_2426.JPG", "IMG_2428.JPG", "IMG_2429.JPG"]):
        add(f"180725_高中/photo/{name}", datetime(2015, 8, 31, 11, 31, offset * 10),
            "150800_胶东游", "备注：胶东行2015-08-31 11:31")
    add("180725_高中/photo/IMG_2424.JPG", datetime(2015, 2, 15, 14, 50, 53),
        "150000_高中生活", "备注：2015年2月，具体日期不确定")

    add("180906_大二开学/photo/wechat_190829_235620.jpg", datetime(2018, 11, 16, 23, 56, 20), None, "备注：2018-11-16")
    add("180906_大二开学/photo/wechat_190829_235704.jpg", datetime(2018, 11, 18, 23, 11, 18),
        "180930_大二国庆", "与wechat_181118_231119同场车队招新")
    for name in ["-151d0bff29af9462.jpg", "-37a065d07aaa7b28.jpg", "-607e7124cf58bd54.jpg", "-63435da658e6a363.jpg", "13a9be6978607b8c.jpg"]:
        rel = f"180906_大二开学/photo/{name}"
        add(rel, current(rel), "180930_大二国庆", "备注：9月29日国庆骑行")
    add("180930_大二国庆/photo/CLOUDUH_190722124721.jpg", datetime(2018, 9, 29, 12, 47, 21), None, "备注：国庆骑行9月29日")
    add("180930_大二国庆/photo/CLOUDUH_190722194758.jpg", datetime(2018, 9, 29, 19, 47, 58), None, "备注：国庆骑行9月29日")

    add("181116_19比赛/photo/IMG_20181116_110138.jpg", datetime(2019, 11, 12, 11, 1, 40),
        "191112_19比赛", "备注：2019-11-12")
    add("181126_珠海参会/photo/wechat_190829_235734.jpg", datetime(2018, 12, 15, 20, 0, 0),
        "181203_大二深冬", "备注：2018-12-15 20:00")
    add("181126_珠海参会/photo/wechat_190829_235906.jpg", datetime(2019, 3, 10, 23, 59, 6),
        "190302_大二下开学", "备注：2019-03-10")
    add("181126_珠海参会/photo/wechat_190829_235919.jpg", datetime(2019, 3, 10, 23, 59, 19),
        "190302_大二下开学", "备注：2019-03-10")

    for rel, dt in {
        "190217_大二暑假之前/photo/-6b1271a5d085cd09.jpg": datetime(2019, 5, 27, 16, 34, 23),
        "190217_大二暑假之前/photo/-7d19945acbabc249.jpg": datetime(2019, 5, 27, 23, 17, 14),
        "190217_大二暑假之前/photo/-72a680d1017ced5f.jpg": datetime(2019, 5, 27, 2, 3, 33),
        "190217_大二暑假之前/photo/53ce18c71685c111.jpg": datetime(2019, 5, 27, 7, 30, 45),
        "190217_大二暑假之前/photo/-477a049a76ad62f1.jpg": datetime(2019, 5, 20, 7, 31, 22),
        "190217_大二暑假之前/photo/Screenshot_20190703_234548_com.android.gallery3d.jpg": datetime(2019, 5, 25, 23, 45, 48),
        "190217_大二暑假之前/photo/wechat_190725_110240.jpg": datetime(2019, 5, 25, 11, 2, 40),
    }.items():
        add(rel, dt, None, "按备注日期校准")
    add("190217_大二暑假之前/photo/5093283295d1c18.jpg", datetime(2018, 11, 16, 7, 37, 29),
        "180906_大二开学", "备注：2018-11-16")

    add("190302_大二下开学/photo/wechat_190806_091805.jpg", datetime(2018, 11, 2, 9, 18, 5),
        "180906_大二开学", "备注：2018-11-02")
    add("190302_大二下开学/photo/wechat_190901_111557.jpg", datetime(2019, 9, 26, 11, 15, 57),
        "190901_比赛之前", "备注：2019-09-26")
    add("190302_大二下开学/photo/wechat_190926_161246.jpg", datetime(2019, 9, 26, 16, 12, 46),
        "190901_比赛之前", "备注：2019-09-26")
    for rel in [
        "190302_大二下开学/photo/IMG20190310071120.jpg",
        "190302_大二下开学/photo/IMG20190310072108.jpg",
        "190316_长春吉大/photo/IMG_20190324_154220.jpg",
        "190316_长春吉大/photo/IMG_20190324_180124.jpg",
    ]:
        add(rel, current(rel), "190317_港西绿地", "备注：港西绿地练车，归入港西绿地")

    add("190316_长春吉大/photo/wechat_190830_000026.jpg", datetime(2019, 4, 28, 0, 0, 26),
        "190430_大二劳动节", "备注：2019-04-28")
    add("190316_长春吉大/photo/-39f41a10b6376306.jpg", datetime(2019, 4, 13, 0, 51, 35), None, "备注：2019-04-13")
    add("190316_长春吉大/photo/-309fb35bacff9a0d.jpg", datetime(2019, 4, 13, 8, 32, 5), None, "备注：2019-04-13")
    add("190417_大三深冬/photo/IMG20190417190635.jpg", datetime(2019, 12, 31, 19, 6, 38),
        "191201_比赛之后", "备注：2019-12-31")
    add("190417_大三深冬/photo/IMG20190417191719.jpg", datetime(2019, 12, 31, 19, 17, 14),
        "191201_比赛之后", "备注：2019-12-31")
    add("190430_大二劳动节/photo/wechat_190508_142027.jpeg", datetime(2019, 5, 12, 14, 20, 27), None, "备注：2019-05-12")

    explicit_deletes = [
        "180530_进入暑期/photo/IMG_2250.PNG",
        "180530_进入暑期/photo/IMG_2246.PNG",
        "180530_进入暑期/photo/IMG_2247.PNG",
        "180530_进入暑期/photo/IMG_2243.JPG",
        "180530_进入暑期/photo/IMG_2238.JPG",
        "180530_进入暑期/photo/IMG_2212.PNG",
        "180700_大一暑假/photo/IMG_2614.HEIC",
        "180906_大二开学/photo/Screenshot_2018-09-19-10-31-40.png",
        "190131_大二寒假/photo/IMG_3489.JPG",
        "190131_大二寒假/photo/IMG_3490.JPG",
        "190217_大二暑假之前/photo/IMG_3945.PNG",
        "190217_大二暑假之前/photo/IMG_3952.PNG",
        "190217_大二暑假之前/photo/IMG_3953.PNG",
        "190217_大二暑假之前/photo/IMG_3954.HEIC",
        "190430_大二劳动节/photo/IMG_3937.GIF",
        "180428_北京/photo/35b160778ffbc315.jpg",
    ]
    exact_duplicates = {
        "171002_国庆回家/photo/wechat_171021_133439__tagged_01.jpg": "171002_国庆回家/photo/wechat_171021_133439.jpg",
        "171021_综办合照/photo/IMG_20171021_210314__tagged_01.jpg": "171021_综办合照/photo/IMG_20171021_210314.jpg",
        "180407_保定实习/photo/IMG_20180412_134235.jpg": "180407_保定实习/photo/IMG_20180412_134234.jpg",
    }
    deletes = [{"path": rel, "reason": "备注明确要求删除"} for rel in explicit_deletes]
    deletes.extend({"path": rel, "reason": f"逐像素相同；保留 {keep}", "keep": keep}
                   for rel, keep in exact_duplicates.items())
    return list(actions.values()), deletes


def write_metadata(path: Path, dt: datetime, backup: Path) -> tuple[str, str, Path]:
    before = sha256(path)
    backup.parent.mkdir(parents=True, exist_ok=True)
    if backup.exists():
        raise RuntimeError(f"Backup already exists: {backup}")
    # A few downloaded files have a .jpg suffix despite containing PNG bytes.
    # ExifTool refuses those until the extension reflects the real format.
    working = path
    if path.suffix.lower() in {".jpg", ".jpeg"}:
        with path.open("rb") as fh:
            signature = fh.read(8)
        if signature == b"\x89PNG\r\n\x1a\n":
            working = unique_path(path.with_suffix(".png"))
            path.rename(working)
    value = exif_dt(dt)
    command = [
        str(EXIFTOOL),
        f"-EXIF:DateTimeOriginal={value}",
        f"-EXIF:CreateDate={value}",
        f"-EXIF:ModifyDate={value}",
        f"-XMP-exif:DateTimeOriginal={value}",
        f"-XMP-xmp:CreateDate={dt.strftime('%Y-%m-%dT%H:%M:%S+08:00')}",
        f"-XMP-xmp:ModifyDate={dt.strftime('%Y-%m-%dT%H:%M:%S+08:00')}",
        f"-FileCreateDate={file_dt(dt)}",
        f"-FileModifyDate={file_dt(dt)}",
        str(working),
    ]
    result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"ExifTool failed for {working}: {result.stderr or result.stdout}")
    original = working.with_name(working.name + "_original")
    if original.exists():
        shutil.move(str(original), str(backup))
    else:
        raise RuntimeError(f"ExifTool did not create an original backup for {working}")
    after = sha256(working)
    return before, after, working


def verify_exact_duplicate(drop: Path, keep: Path) -> None:
    from PIL import Image, ImageOps
    with Image.open(drop) as a, Image.open(keep) as b:
        a = ImageOps.exif_transpose(a)
        b = ImageOps.exif_transpose(b)
        if a.mode != b.mode or a.size != b.size or a.tobytes() != b.tobytes():
            raise RuntimeError(f"Not pixel-identical: {drop} vs {keep}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    actions, deletes = build_plan()

    completed_sources: set[str] = set()
    completed_deletes: set[str] = set()
    journal_path = LOG_ROOT / "journal.jsonl"
    if journal_path.exists():
        for line in journal_path.read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("kind") == "metadata_move":
                completed_sources.add(row["source"])
            elif row.get("kind") == "delete":
                completed_deletes.add(row["path"])

    missing = [a.source for a in actions if a.source not in completed_sources and not (NAS / a.source).exists()]
    missing += [d["path"] for d in deletes if d["path"] not in completed_deletes and not (NAS / d["path"]).exists()]
    if missing:
        print(json.dumps({"error": "missing paths", "paths": missing}, ensure_ascii=False, indent=2))
        raise SystemExit(2)

    preview = []
    for action in actions:
        dt = parse_dt(action.new_datetime)
        new_name = rename_from_datetime(Path(action.source).name, dt)
        target = f"{action.target_folder}/photo/{new_name}"
        preview.append({**asdict(action), "target": target, "rename": new_name != Path(action.source).name})

    collisions = []
    source_set = {NAS / a.source for a in actions}
    for row in preview:
        target = NAS / row["target"]
        source = NAS / row["source"]
        if target.exists() and target != source and target not in source_set:
            collisions.append(row["target"])

    summary = {
        "mode": "apply" if args.apply else "dry-run",
        "metadata_actions": len(actions),
        "moves": sum(row["source"].split("/", 1)[0] != row["target_folder"] for row in preview),
        "renames": sum(row["rename"] for row in preview),
        "deletes": len(deletes),
        "collisions_to_suffix": collisions,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    if not args.apply:
        print(json.dumps({"actions": preview, "deletes": deletes}, ensure_ascii=False, indent=2))
        return

    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    plan_path = LOG_ROOT / "plan.json"
    if not plan_path.exists():
        plan_path.write_text(json.dumps({"summary": summary, "actions": preview, "deletes": deletes}, ensure_ascii=False, indent=2))

    completed: list[dict] = []
    with journal_path.open("a") as journal:
        for index, row in enumerate(preview, start=1):
            if row["source"] in completed_sources:
                continue
            source = NAS / row["source"]
            dt = parse_dt(row["new_datetime"])
            backup = BACKUP_ROOT / row["source"]
            before, after, source = write_metadata(source, dt, backup)
            target_dir = NAS / row["target_folder"] / "photo"
            target_dir.mkdir(parents=True, exist_ok=True)
            target_name = rename_from_datetime(source.name, dt)
            target = target_dir / target_name
            if target.exists() and target != source:
                target = unique_path(target)
            if target != source:
                source.rename(target)
            record = {"kind": "metadata_move", "index": index, "source": row["source"],
                      "target": str(target.relative_to(NAS)), "datetime": row["new_datetime"],
                      "backup": str(backup.relative_to(NAS)), "sha256_before": before,
                      "sha256_after": after, "reason": row["reason"]}
            journal.write(json.dumps(record, ensure_ascii=False) + "\n")
            journal.flush()
            completed.append(record)
            if index % 20 == 0:
                print(f"PROGRESS metadata {index}/{len(preview)}", flush=True)

        for index, row in enumerate(deletes, start=1):
            if row["path"] in completed_deletes:
                continue
            drop = NAS / row["path"]
            if row.get("keep"):
                verify_exact_duplicate(drop, NAS / row["keep"])
            digest = sha256(drop)
            size = drop.stat().st_size
            drop.unlink()
            record = {"kind": "delete", "index": index, **row, "size": size, "sha256": digest}
            journal.write(json.dumps(record, ensure_ascii=False) + "\n")
            journal.flush()
            completed.append(record)

    # Only remove directories made empty by the moves. Never recurse.
    removed_dirs = []
    source_folders = sorted({a.source.split("/", 1)[0] for a in actions})
    for folder in source_folders:
        photo = NAS / folder / "photo"
        parent = NAS / folder
        try:
            photo.rmdir()
            removed_dirs.append(str(photo.relative_to(NAS)))
        except OSError:
            pass
        try:
            parent.rmdir()
            removed_dirs.append(str(parent.relative_to(NAS)))
        except OSError:
            pass

    final = {**summary, "completed_this_run": len(completed),
             "completed_total": len(completed_sources) + len(completed_deletes) + len(completed),
             "removed_empty_dirs": removed_dirs}
    (LOG_ROOT / "result.json").write_text(json.dumps(final, ensure_ascii=False, indent=2))
    print(json.dumps(final, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
