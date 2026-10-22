#!/usr/bin/env python3
"""Propose timestamps for event-root media that lack capture metadata.

Inputs are local ExifTool JSON reports generated from the read-only SMB mount.
No NAS media is modified by this script.
"""

from __future__ import annotations

import argparse
import calendar
import csv
import datetime as dt
import hashlib
import json
import os
import random
import re
from collections import Counter, defaultdict
from pathlib import Path


VIDEO_EXTS = {".mp4", ".mov", ".m4v"}
PNG_EXTS = {".png"}
EVENT_RE = re.compile(r"^(?P<yy>\d{2})(?P<mm>\d{2})(?P<dd>\d{2})_")


def parse_meta_time(value: object) -> dt.datetime | None:
    match = re.match(
        r"(\d{4}):(\d{2}):(\d{2})[ T](\d{2}):(\d{2}):(\d{2})",
        str(value or ""),
    )
    if not match:
        return None
    try:
        return dt.datetime(*map(int, match.groups()))
    except ValueError:
        return None


def parse_filename_time(name: str) -> dt.datetime | None:
    patterns = [
        r"(?<!\d)(20\d{2})[-_]?([01]\d)[-_]?([0-3]\d)[ T_-]?([0-2]\d)[.:_-]?([0-5]\d)[.:_-]?([0-5]\d)(?!\d)",
        r"(?<!\d)(\d{2})([01]\d)([0-3]\d)([0-2]\d)([0-5]\d)([0-5]\d)(?!\d)",
    ]
    for index, pattern in enumerate(patterns):
        match = re.search(pattern, name)
        if not match:
            continue
        values = list(map(int, match.groups()))
        if index == 1:
            values[0] += 2000
        try:
            return dt.datetime(*values)
        except ValueError:
            pass
    match = re.search(r"(\d{13})", name)
    if match:
        try:
            return dt.datetime.fromtimestamp(int(match.group(1)) / 1000)
        except (OSError, OverflowError, ValueError):
            pass
    match = re.search(r"(?<!\d)(20\d{2})[-_]?([01]\d)[-_]?([0-3]\d)(?!\d)", name)
    if match:
        try:
            year, month, day = map(int, match.groups())
            return dt.datetime(year, month, day, 12, 0, 0)
        except ValueError:
            pass
    # Chinese date names such as "ChatGPT Image 2026年4月26日 23_05_39".
    match = re.search(r"(20\d{2})年(\d{1,2})月(\d{1,2})日(?:\D+(\d{1,2})[_:](\d{2})[_:](\d{2}))?", name)
    if match:
        values = [int(value) if value else default for value, default in zip(match.groups(), (2000, 1, 1, 12, 0, 0))]
        try:
            return dt.datetime(*values)
        except ValueError:
            pass
    return None


def event_anchor(event: str) -> tuple[dt.datetime | None, str]:
    match = EVENT_RE.match(event)
    if not match:
        return None, "none"
    year = 2000 + int(match.group("yy"))
    month = int(match.group("mm"))
    if not month:
        return dt.datetime(year, 1, 1), "year"
    try:
        day = int(match.group("dd"))
        if day:
            return dt.datetime(year, month, day), "day"
        return dt.datetime(year, month, 1), "month"
    except ValueError:
        return None, "none"


def plausible_file_time(value: dt.datetime, event: str) -> bool:
    """Reject obvious import/download times that are far outside an event."""
    anchor, precision = event_anchor(event)
    if anchor is None:
        return False
    delta = (value - anchor).days
    if precision == "day":
        return -90 <= delta <= 120
    if precision == "month":
        # Semester/season folders commonly span into the following year.
        return -90 <= delta <= 400
    # Broad year buckets such as childhood collections are intentionally loose.
    return -366 <= delta <= 3 * 366


def normalize_stem(name: str) -> str:
    stem = Path(name).stem.lower()
    return re.sub(
        r"(?:[-_ ]?(?:编辑|精修|edited?|retouched?|final|copy|副本))+$",
        "",
        stem,
        flags=re.I,
    )


def stable_random_time(month: dt.datetime, key: str) -> dt.datetime:
    seed = int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest()[:8], "big")
    rng = random.Random(seed)
    last_day = calendar.monthrange(month.year, month.month)[1]
    return dt.datetime(
        month.year,
        month.month,
        rng.randint(1, last_day),
        rng.choices(range(7, 24), weights=[1, 2, 4, 6, 7, 8, 8, 8, 8, 8, 7, 7, 7, 6, 5, 4, 2])[0],
        rng.randint(0, 59),
        rng.randint(0, 59),
    )


def capture_time(row: dict) -> dt.datetime | None:
    extension = Path(row["SourceFile"]).suffix.lower()
    keys = (
        ["CreationDate", "MediaCreateDate", "TrackCreateDate", "CreateDate"]
        if extension in VIDEO_EXTS
        else ["DateTimeOriginal", "CreateDate", "ModifyDate"]
    )
    return next((value for key in keys if (value := parse_meta_time(row.get(key)))), None)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root-metadata", type=Path, required=True)
    parser.add_argument("--source-metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    root_rows = json.loads(args.root_metadata.read_text(encoding="utf-8"))
    source_rows = json.loads(args.source_metadata.read_text(encoding="utf-8"))
    source_by_path = {row["SourceFile"]: row for row in source_rows}

    # Recreate the same normalized-name lookup that produced the source list.
    source_lookup: dict[Path, dict[str, list[Path]]] = {}
    proposals = []
    for row in root_rows:
        if capture_time(row):
            continue
        live = Path(row["SourceFile"])
        event_dir = live.parent
        event = event_dir.name
        extension = live.suffix.lower()
        media_type = "video" if extension in VIDEO_EXTS else "photo"
        source_dir = event_dir / ("video" if media_type == "video" else "photo")
        if source_dir not in source_lookup:
            by_stem: dict[str, list[Path]] = defaultdict(list)
            try:
                for path in source_dir.iterdir():
                    if path.is_file():
                        by_stem[normalize_stem(path.name)].append(path)
            except OSError:
                pass
            source_lookup[source_dir] = by_stem
        matches = source_lookup[source_dir].get(normalize_stem(live.name), [])

        source_capture_values = []
        source_modify_values = []
        for match in matches:
            source_row = source_by_path.get(str(match))
            if source_row:
                if value := capture_time(source_row):
                    source_capture_values.append((value, match))
                if value := parse_meta_time(source_row.get("FileModifyDate")):
                    source_modify_values.append((value, match))
            else:
                # Video source matches were not part of the photo-only ExifTool list.
                if value := parse_filename_time(match.name):
                    source_capture_values.append((value, match))

        filename_value = parse_filename_time(live.name)
        file_modify_value = parse_meta_time(row.get("FileModifyDate"))
        folder_anchor, _folder_precision = event_anchor(event)
        folder_month = (
            folder_anchor.replace(day=1, hour=0, minute=0, second=0)
            if folder_anchor
            else None
        )
        reason = ""
        confidence = "low"
        proposed: dt.datetime | None = None
        source_used = ""

        # A strong camera-style filename wins over conflicting edited EXIF.
        # This catches batch-edited files such as CLOUDUH_220317... whose source
        # copy was incorrectly stamped months later.
        if filename_value and not live.name.lower().startswith("mmexport") and extension not in PNG_EXTS:
            proposed = filename_value.replace(microsecond=0)
            confidence = "high"
            reason = "explicit date/time encoded in filename; preferred over potentially edited EXIF"
        elif filename_value and extension in PNG_EXTS:
            month = filename_value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            proposed = stable_random_time(month, str(live) + "|filename-month")
            confidence = "medium"
            reason = "PNG/screenshot filename supplied the month; day and time were intentionally varied"
        elif source_capture_values:
            source_capture_values.sort(key=lambda item: item[0])
            proposed, source_path = source_capture_values[0]
            source_used = str(source_path)
            confidence = "high"
            reason = "inherited capture time from same-event original with matching normalized filename"
        elif filename_value:
            month = filename_value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            proposed = stable_random_time(month, str(live) + "|filename-month")
            confidence = "medium"
            reason = "export/screenshot filename supplied the month; day and time were intentionally varied"
        elif matches and source_modify_values:
            source_modify_values.sort(key=lambda item: item[0])
            plausible_sources = [item for item in source_modify_values if plausible_file_time(item[0], event)]
            if plausible_sources:
                anchor, source_path = plausible_sources[0]
                source_used = str(source_path)
                proposed = stable_random_time(anchor.replace(day=1, hour=0, minute=0, second=0), str(live) + "|source-mtime")
                confidence = "medium"
                reason = "same-event original matched by filename; its file month is inside the event window"
        if proposed is None and file_modify_value and plausible_file_time(file_modify_value, event):
            month = file_modify_value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            proposed = stable_random_time(month, str(live) + "|file-month")
            confidence = "medium"
            reason = "capture EXIF is absent; plausible existing file month was retained with a varied day/time"
        elif proposed is None and folder_month:
            proposed = stable_random_time(folder_month, str(live) + "|event-month")
            confidence = "low"
            reason = "source/file modification time looked like an import time; used event-folder month with a varied day/time"

        if proposed is None:
            raise RuntimeError(f"Could not propose a timestamp for {live}")

        proposals.append(
            {
                "absolute_path": str(live),
                "relative_to_library": str(live.relative_to("/Volumes/photo")),
                "event": event,
                "media_type": media_type,
                "extension": extension,
                "proposed_time": proposed.isoformat(sep=" ", timespec="seconds"),
                "confidence": confidence,
                "reason": reason,
                "source_match": source_used,
                "source_match_count": len(matches),
                "filename_time": filename_value.isoformat(sep=" ", timespec="seconds") if filename_value else "",
                "file_modify_time": file_modify_value.isoformat(sep=" ", timespec="seconds") if file_modify_value else "",
            }
        )

    if len(proposals) != 192:
        raise RuntimeError(f"Expected 192 proposals, generated {len(proposals)}")

    csv_path = args.output / "proposals.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(proposals[0].keys()))
        writer.writeheader()
        writer.writerows(proposals)

    update_keys = ["relative_to_library", "media_type", "extension", "proposed_time", "confidence", "reason"]
    updates = [{key: row[key] for key in update_keys} for row in proposals]
    (args.output / "updates.json").write_text(
        json.dumps(updates, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    summary = {
        "proposals": len(proposals),
        "by_confidence": dict(Counter(row["confidence"] for row in proposals)),
        "by_reason": {" | ".join(key): value for key, value in Counter((row["confidence"], row["reason"]) for row in proposals).items()},
        "by_year": dict(Counter(row["proposed_time"][:4] for row in proposals)),
        "by_event": dict(Counter(row["event"] for row in proposals)),
    }
    (args.output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
