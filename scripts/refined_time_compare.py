#!/usr/bin/env python3
"""Compare timestamps between refined root media and matched originals."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import os
import re
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from global_root_photo_audit import parse_filename_time, parse_meta_time


VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".avi"}
RAW_PREF = {".cr2": 0, ".cr3": 0, ".nef": 0, ".arw": 0, ".dng": 0, ".tif": 1, ".tiff": 1, ".psd": 2}
VIDEO_MANUAL_OVERRIDES = {
    "/Volumes/photo/231001_太行山/未命名.mov": ("unmatched_video_manual", "none"),
    "/Volumes/photo/250315_开春/IMG_3019.MOV": ("unmatched_video_manual", "none"),
    "/Volumes/photo/251209_里约热内卢/20251210_184418_1.mp4": ("unmatched_video_manual", "none"),
    "/Volumes/photo/260111_寒冷腊月/20260117_143914.mov": ("strong_video_match_manual", "strong"),
}


def capture_time(row: dict | None) -> dt.datetime | None:
    if not row:
        return None
    extension = Path(row["SourceFile"]).suffix.lower()
    keys = (
        ["CreationDate", "MediaCreateDate", "TrackCreateDate", "CreateDate"]
        if extension in VIDEO_EXTS
        else ["DateTimeOriginal", "CreateDate", "ModifyDate"]
    )
    return next((value for key in keys if (value := parse_meta_time(row.get(key)))), None)


def internal_conflict(row: dict) -> bool:
    # Exif.Image.DateTime/ModifyDate legitimately changes when a photo is edited.
    # Only treat the two capture-oriented fields as an internal conflict.
    original = parse_meta_time(row.get("DateTimeOriginal"))
    digitized = parse_meta_time(row.get("CreateDate"))
    return bool(original and digitized and abs((original - digitized).total_seconds()) > 86400)


def parse_duration(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        pass
    match = re.match(r"(?:(\d+):)?(\d+):(\d+(?:\.\d+)?)", text)
    if match:
        hours = int(match.group(1) or 0)
        return hours * 3600 + int(match.group(2)) * 60 + float(match.group(3))
    match = re.search(r"([\d.]+)\s*s", text, re.I)
    return float(match.group(1)) if match else None


def choose_source(paths: list[str], metadata: dict[str, dict]) -> tuple[str | None, bool]:
    if not paths:
        return None, False
    dated = [(path, capture_time(metadata.get(path))) for path in paths]
    dated_values = [value for _, value in dated if value]
    ambiguous = bool(dated_values and (max(dated_values) - min(dated_values)).total_seconds() > 86400)
    ranked = sorted(
        paths,
        key=lambda path: (
            0 if capture_time(metadata.get(path)) else 1,
            RAW_PREF.get(Path(path).suffix.lower(), 3),
            path,
        ),
    )
    return ranked[0], ambiguous


def video_match(root_row: dict, candidates: list[dict]) -> tuple[dict | None, str, float | None]:
    root_duration = parse_duration(root_row.get("Duration"))
    root_width = root_row.get("ImageWidth")
    root_height = root_row.get("ImageHeight")
    root_size = root_row.get("FileSize")
    ranked = []
    for candidate in candidates:
        duration = parse_duration(candidate.get("Duration"))
        if root_duration is None or duration is None:
            continue
        duration_delta = abs(root_duration - duration)
        dimension_penalty = 0 if (root_width, root_height) == (candidate.get("ImageWidth"), candidate.get("ImageHeight")) else 2
        try:
            size_ratio = abs(math.log(max(float(root_size), 1) / max(float(candidate.get("FileSize")), 1)))
        except (TypeError, ValueError):
            size_ratio = 1.0
        score = duration_delta + dimension_penalty + min(size_ratio, 5)
        ranked.append((score, duration_delta, dimension_penalty, size_ratio, candidate))
    if not ranked:
        return None, "unmatched_video", None
    ranked.sort(key=lambda item: item[0])
    score, duration_delta, dimension_penalty, size_ratio, candidate = ranked[0]
    if duration_delta <= 0.15 and dimension_penalty == 0:
        quality = "strong_video_match"
    elif duration_delta <= 1.0 and dimension_penalty <= 2 and size_ratio <= 0.7:
        quality = "probable_video_match"
    else:
        quality = "weak_video_match"
    return candidate, quality, round(score, 4)


def build_contact_sheet(rows: list[dict], output: Path, limit: int = 80) -> None:
    image_rows = [row for row in rows if row["candidate_path"] and row["media_type"] == "photo"][:limit]
    if not image_rows:
        return
    cell_w, cell_h = 360, 270
    sheet = Image.new("RGB", (cell_w * 2, cell_h * len(image_rows)), "#202124")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()

    def place(path: str, x: int, y: int, title: str) -> None:
        try:
            with Image.open(path) as image:
                image = ImageOps.exif_transpose(image).convert("RGB")
                thumb = ImageOps.contain(image, (cell_w - 12, cell_h - 52), Image.Resampling.LANCZOS)
                sheet.paste(thumb, (x + (cell_w - thumb.width) // 2, y + 4))
        except Exception:
            draw.rectangle((x + 5, y + 5, x + cell_w - 5, y + cell_h - 52), outline="red")
        draw.text((x + 5, y + cell_h - 44), title[:58], fill="white", font=font)

    for index, row in enumerate(image_rows):
        y = index * cell_h
        place(row["root_path"], 0, y, f"ROOT {Path(row['root_path']).name} {row['root_capture']}")
        place(row["candidate_path"], cell_w, y, f"SRC {Path(row['candidate_path']).name} {row['source_capture']}")
    sheet.save(output, quality=90)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage1", type=Path, required=True)
    parser.add_argument("--visual", type=Path, required=True)
    parser.add_argument("--root-metadata", type=Path, required=True)
    parser.add_argument("--source-metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    stage1 = json.loads(args.stage1.read_text(encoding="utf-8"))
    visual = {row["root_path"]: row for row in json.loads(args.visual.read_text(encoding="utf-8"))}
    root_meta = {row["SourceFile"]: row for row in json.loads(args.root_metadata.read_text(encoding="utf-8"))}
    source_meta = {row["SourceFile"]: row for row in json.loads(args.source_metadata.read_text(encoding="utf-8"))}
    source_by_event_video = {}
    for row in source_meta.values():
        path = Path(row["SourceFile"])
        if path.suffix.lower() in VIDEO_EXTS and "video" in path.parts:
            video_index = max(index for index, part in enumerate(path.parts) if part == "video")
            if video_index > 0:
                source_by_event_video.setdefault(path.parts[video_index - 1], []).append(row)

    report = []
    for item in stage1:
        root_path = item["root_path"]
        root_row = root_meta.get(root_path)
        if not root_row:
            continue
        method = item["match_method"]
        reliability = "strong" if method in {"exact_name", "normalized_stem", "exact_sha256"} else "none"
        candidate_path = None
        candidate_row = None
        match_score = None
        ambiguous = False

        if method != "unmatched":
            candidate_path, ambiguous = choose_source(item["candidate_paths"], source_meta)
            candidate_row = source_meta.get(candidate_path) if candidate_path else None
        elif item["media_type"] == "photo":
            visual_row = visual.get(root_path)
            classification = visual_row["visual_classification"] if visual_row else "unmatched"
            if classification in {"strong_visual_match", "probable_visual_match"}:
                top = visual_row["visual_candidates"][0]
                candidate_path = top["path"]
                candidate_row = source_meta.get(candidate_path)
                match_score = top["score"]
                reliability = "strong" if classification == "strong_visual_match" else "probable"
                method = classification
            else:
                method = classification
        else:
            candidate_row, method, match_score = video_match(root_row, source_by_event_video.get(item["event"], []))
            if candidate_row:
                candidate_path = candidate_row["SourceFile"]
                reliability = "strong" if method == "strong_video_match" else "probable" if method == "probable_video_match" else "weak"
            if root_path in VIDEO_MANUAL_OVERRIDES:
                override_method, override_reliability = VIDEO_MANUAL_OVERRIDES[root_path]
                method = override_method
                reliability = override_reliability
                if override_reliability == "none":
                    candidate_row = None
                    candidate_path = None
                    match_score = None

        root_capture = capture_time(root_row)
        source_capture = capture_time(candidate_row)
        root_filename = parse_filename_time(Path(root_path).name)
        source_filename = parse_filename_time(Path(candidate_path).name) if candidate_path else None
        delta_seconds = (
            abs((root_capture - source_capture).total_seconds())
            if root_capture and source_capture
            else None
        )

        if ambiguous:
            status = "ambiguous_multiple_sources"
        elif reliability not in {"strong", "probable"}:
            status = "unresolved_no_reliable_match"
        elif root_capture is None:
            status = "root_capture_missing"
        elif source_capture is None:
            status = "source_capture_missing"
        elif delta_seconds <= 2:
            status = "consistent_exact"
        elif delta_seconds <= 60:
            status = "consistent_close"
        elif delta_seconds <= 86400:
            status = "same_day_time_difference"
        else:
            root_filename_ok = root_filename and abs((root_capture - root_filename).total_seconds()) <= 86400
            source_filename_ok = source_filename and abs((source_capture - source_filename).total_seconds()) <= 86400
            shared_filename = (
                root_filename
                and source_filename
                and abs((root_filename - source_filename).total_seconds()) <= 2
            )
            if shared_filename and (root_capture.year, root_capture.month) == (root_filename.year, root_filename.month) and (source_capture.year, source_capture.month) != (source_filename.year, source_filename.month):
                status = "source_metadata_suspect"
            elif shared_filename and (source_capture.year, source_capture.month) == (source_filename.year, source_filename.month) and (root_capture.year, root_capture.month) != (root_filename.year, root_filename.month):
                status = "root_metadata_suspect"
            elif root_filename_ok and not source_filename_ok:
                status = "source_metadata_suspect"
            elif source_filename_ok and not root_filename_ok:
                status = "root_metadata_suspect"
            else:
                status = "date_mismatch_strong" if reliability == "strong" else "date_mismatch_probable"
        if internal_conflict(root_row):
            status += "+root_internal_date_conflict"

        report.append(
            {
                "root_path": root_path,
                "relative_to_library": item["relative_to_library"],
                "event": item["event"],
                "media_type": item["media_type"],
                "match_method": method,
                "match_reliability": reliability,
                "match_score": match_score if match_score is not None else "",
                "candidate_path": candidate_path or "",
                "candidate_count": item["candidate_count"],
                "root_capture": root_capture.isoformat(sep=" ", timespec="seconds") if root_capture else "",
                "source_capture": source_capture.isoformat(sep=" ", timespec="seconds") if source_capture else "",
                "root_filename_time": root_filename.isoformat(sep=" ", timespec="seconds") if root_filename else "",
                "source_filename_time": source_filename.isoformat(sep=" ", timespec="seconds") if source_filename else "",
                "delta_seconds": int(delta_seconds) if delta_seconds is not None else "",
                "delta_days": round(delta_seconds / 86400, 3) if delta_seconds is not None else "",
                "status": status,
            }
        )

    csv_path = args.output / "consistency_report.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(report[0].keys()))
        writer.writeheader()
        writer.writerows(report)

    status_counts = Counter(row["status"] for row in report)
    actionable_statuses = {
        "root_metadata_suspect",
        "date_mismatch_strong",
        "date_mismatch_probable",
        "root_capture_missing",
    }
    anomalies = [
        row for row in report
        if any(row["status"].startswith(value) for value in actionable_statuses)
    ]
    (args.output / "anomalies.json").write_text(
        json.dumps(anomalies, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    build_contact_sheet(anomalies, args.output / "anomaly_contact_sheet.jpg")
    summary = {
        "root_media": len(report),
        "status_counts": dict(status_counts),
        "actionable_anomalies": len(anomalies),
        "reliable_matches": sum(row["match_reliability"] in {"strong", "probable"} for row in report),
    }
    (args.output / "consistency_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
