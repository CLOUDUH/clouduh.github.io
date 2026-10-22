#!/usr/bin/env python3
"""Move labeled daily folders into event/date folders on FATCLOUD."""

from __future__ import annotations

import json
import shutil
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


ROOT = Path("/Volumes/FATCLOUD")
SOURCE = Path("/Users/cloudu/Downloads/yanxiang-photo-review (2).json")
DAILY = ROOT / "燕翔相册_按日期整理"
DEST = ROOT / "燕翔相册_按事件整理"
LOG = Path("/Users/cloudu/Documents/document/05_Note/clouduh.github.io/tools/photo-date-review-site/tools-data/yanxiang-event-classification.json")


def main() -> None:
    data = json.loads(SOURCE.read_text())
    by_date: dict[str, list[dict]] = defaultdict(list)
    for item in data["items"]:
        by_date[item["folderDate"]].append(item)
    decisions: dict[str, str] = {}
    ambiguous = []
    for date, items in by_date.items():
        tags = {tag for item in items for tag in item.get("tags", [])}
        if len(tags) != 1:
            if tags:
                ambiguous.append({"date": date, "tags": sorted(tags)})
            continue
        label = next(iter(tags))
        decisions[date] = "未采用" if label in {"舍弃", "文件夹舍弃"} else label

    if DEST.exists():
        raise SystemExit(f"Refusing to overwrite existing destination: {DEST}")
    DEST.mkdir(parents=True)
    moved = []
    for date in sorted(decisions):
        source = DAILY / date
        if not source.is_dir():
            raise RuntimeError(f"Missing daily folder: {source}")
        label = decisions[date]
        target = DEST / label / date.replace("-", "") [2:]
        if target.exists():
            raise RuntimeError(f"Target already exists: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
        moved.append({"date": date, "label": label, "target": str(target.relative_to(ROOT))})

    summary = Counter(item["label"] for item in moved)
    result = {
        "status": "ok",
        "source": str(DAILY),
        "destination": str(DEST),
        "labeledDates": len(moved),
        "unlabeledDates": sorted(set(by_date) - set(decisions)),
        "ambiguousDates": ambiguous,
        "labels": dict(summary),
        "moved": moved,
        "originalsDeleted": 0,
    }
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({key: value for key, value in result.items() if key not in {"moved", "unlabeledDates"}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
