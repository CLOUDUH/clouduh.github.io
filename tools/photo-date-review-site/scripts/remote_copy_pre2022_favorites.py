#!/usr/bin/env python3
"""Copy pre-2022 root-level favorites into chronological batches on the NAS."""

from __future__ import annotations

import json
import shutil
from pathlib import Path


ROOT = Path("/volume2/photo")
PLAN = Path("/tmp/codex_pre2022_favorites_plan.json")


def main() -> None:
    plan = json.loads(PLAN.read_text())
    target = ROOT / plan["target"]
    if target.exists():
        raise SystemExit(f"Refusing to overwrite existing target: {target}")
    target.mkdir(parents=True)
    copied = 0
    copied_bytes = 0
    for index, item in enumerate(plan["items"], 1):
        source = ROOT / item["source"]
        destination = target / item["batch"] / item["filename"]
        if not source.is_file():
            raise RuntimeError(f"Missing source: {source}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        if destination.stat().st_size != source.stat().st_size:
            raise RuntimeError(f"Size mismatch: {destination}")
        copied += 1
        copied_bytes += destination.stat().st_size
        if index % 50 == 0:
            print(f"PROGRESS {index}/{len(plan['items'])}", flush=True)
    batches = sorted(path for path in target.iterdir() if path.is_dir())
    counts = [sum(1 for path in batch.iterdir() if path.is_file()) for batch in batches]
    result = {
        "status": "ok",
        "target": str(target),
        "copied": copied,
        "bytes": copied_bytes,
        "batches": len(batches),
        "batchCounts": counts,
    }
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
