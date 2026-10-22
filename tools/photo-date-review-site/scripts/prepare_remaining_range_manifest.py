#!/usr/bin/env python3
"""Remove fully resolved round-one items while retaining date-uncertain choices."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from scan_range_review import intervals


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "public/range-review/review-items.json"
EXPORTED = Path("/Users/cloudu/Downloads/photo-range-review.json")
JOURNAL = Path("/Volumes/photo/170900_备份/_operation_logs/range-review-round1-20260902/journal.json")


manifest = json.loads(MANIFEST.read_text())
exported = json.loads(EXPORTED.read_text())
journal = json.loads(JOURNAL.read_text())
spans = intervals(manifest["folders"])

resolved = {row["id"] for row in exported["reviews"] if row.get("decision") == "keep"}
for action in journal:
    value = datetime.strptime(action["datetime"], "%Y-%m-%d %H:%M:%S")
    target = action["targetFolder"]
    date_now_reliable = action["metadataChange"]
    date_fits_target = target in spans and spans[target][0] <= value <= spans[target][1]
    if date_now_reliable or date_fits_target:
        resolved.add(action["id"])

before = len(manifest["items"])
manifest["items"] = [item for item in manifest["items"] if item["id"] not in resolved]
manifest["count"] = len(manifest["items"])
manifest["generatedAt"] = datetime.now().astimezone().isoformat()
manifest["previousRoundProcessed"] = before - len(manifest["items"])
MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
print(json.dumps({"before": before, "resolved": before - len(manifest["items"]),
                  "remaining": len(manifest["items"])}, ensure_ascii=False, indent=2))
