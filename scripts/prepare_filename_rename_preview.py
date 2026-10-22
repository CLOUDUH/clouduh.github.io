#!/usr/bin/env python3
"""Create a collision-safe, read-only media filename rename preview."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo


TZ = ZoneInfo("Asia/Shanghai")


def parse_date(value: object) -> dt.datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if text.startswith("0000:00:00"):
        return None
    match = re.match(r"(\d{4})[:\-](\d{2})[:\-](\d{2})[ T](\d{2}):(\d{2}):(\d{2})(?:([+\-]\d{2}):?(\d{2}))?", text)
    if not match:
        return None
    values = list(map(int, match.groups()[:6]))
    try:
        value_dt = dt.datetime(*values)
    except ValueError:
        return None
    if match.group(7):
        sign = 1 if match.group(7).startswith("+") else -1
        hours = abs(int(match.group(7)))
        minutes = int(match.group(8) or 0)
        value_dt = value_dt.replace(tzinfo=dt.timezone(sign * dt.timedelta(hours=hours, minutes=minutes))).astimezone(TZ).replace(tzinfo=None)
    return value_dt


def filename_epoch(name: str) -> dt.datetime | None:
    for match in re.finditer(r"(?<!\d)(\d{13}|\d{10})(?!\d)", name):
        raw = match.group(1)
        try:
            stamp = int(raw) / (1000 if len(raw) == 13 else 1)
            value = dt.datetime.fromtimestamp(stamp, TZ).replace(tzinfo=None)
            if 2000 <= value.year <= 2030:
                return value
        except (OSError, OverflowError, ValueError):
            pass
    return None


def choose_time(row: dict, path: Path) -> tuple[dt.datetime | None, str]:
    ordered = [
        ("DateTimeOriginal", row.get("DateTimeOriginal")),
        ("CreationDate", row.get("CreationDate")),
        ("CreateDate", row.get("CreateDate")),
        ("MediaCreateDate", row.get("MediaCreateDate")),
        ("TrackCreateDate", row.get("TrackCreateDate")),
        ("ModifyDate", row.get("ModifyDate")),
    ]
    for label, raw in ordered:
        value = parse_date(raw)
        if value:
            return value, label
    value = filename_epoch(path.stem)
    if value:
        return value, "filename_epoch"
    for label in ("FileModifyDate", "FileCreateDate"):
        value = parse_date(row.get(label))
        if value:
            return value, label
    return None, "missing"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    candidates = json.loads(args.candidates.read_text(encoding="utf-8"))
    metadata = {row["SourceFile"]: row for row in json.loads(args.metadata.read_text(encoding="utf-8"))}
    provisional = []
    missing = []
    for item in candidates:
        old = Path(item["path"])
        value, source = choose_time(metadata.get(str(old), {}), old)
        if not value:
            missing.append(item)
            continue
        base = f"{item['prefix']}_{value.strftime('%y%m%d_%H%M%S')}"
        provisional.append({
            "old_path": str(old),
            "old_relative": item["relative"],
            "prefix": item["prefix"],
            "timestamp": value.isoformat(sep=" ", timespec="seconds"),
            "timestamp_source": source,
            "base": base,
            "extension": old.suffix,
        })

    by_target: dict[str, list[dict]] = defaultdict(list)
    for row in provisional:
        old = Path(row["old_path"])
        key = str(old.parent / f"{row['base']}{row['extension']}").casefold()
        by_target[key].append(row)

    existing_names: dict[Path, set[str]] = {}
    preview = []
    collision_groups = 0
    suffixed = 0
    for key in sorted(by_target):
        group = sorted(by_target[key], key=lambda row: row["old_path"])
        if len(group) > 1:
            collision_groups += 1
        for index, row in enumerate(group):
            old = Path(row["old_path"])
            if old.parent not in existing_names:
                try:
                    existing_names[old.parent] = {path.name.casefold() for path in old.parent.iterdir()}
                except OSError:
                    existing_names[old.parent] = set()
            suffix_index = index
            while True:
                suffix = "" if suffix_index == 0 else f"_{suffix_index:02d}"
                new_name = f"{row['base']}{suffix}{row['extension']}"
                folded = new_name.casefold()
                if folded == old.name.casefold() or folded not in existing_names[old.parent]:
                    break
                suffix_index += 1
            if suffix_index:
                suffixed += 1
            existing_names[old.parent].add(folded)
            preview.append({
                **{k: v for k, v in row.items() if k != "base"},
                "new_path": str(old.with_name(new_name)),
                "new_relative": str(Path(row["old_relative"]).with_name(new_name)),
                "collision_suffix": suffix_index,
            })

    preview.sort(key=lambda row: row["old_relative"])
    (args.output / "rename-preview.json").write_text(json.dumps(preview, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output / "missing-time.json").write_text(json.dumps(missing, ensure_ascii=False, indent=2), encoding="utf-8")
    if preview:
        with (args.output / "rename-preview.csv").open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(preview[0].keys()))
            writer.writeheader(); writer.writerows(preview)
    summary = {
        "candidate_files": len(candidates),
        "ready_to_rename": len(preview),
        "missing_time": len(missing),
        "by_prefix": dict(Counter(row["prefix"] for row in preview)),
        "by_timestamp_source": dict(Counter(row["timestamp_source"] for row in preview)),
        "collision_groups": collision_groups,
        "files_with_suffix": suffixed,
    }
    (args.output / "rename-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    for row in preview[:20]:
        print(row["old_relative"], "=>", row["new_relative"], f"[{row['timestamp_source']}]")


if __name__ == "__main__":
    main()
