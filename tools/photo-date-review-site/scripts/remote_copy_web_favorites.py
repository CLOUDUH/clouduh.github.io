#!/usr/bin/env python3
"""Copy missing web-picked photos from album photo/ folders to album roots."""

from __future__ import annotations

import json
import shutil
from pathlib import Path


ROOT = Path("/volume2/photo")
PLAN = Path("/tmp/web-favorites-pre2022-copy-plan.json")


def main() -> None:
    plan = json.loads(PLAN.read_text())
    copied = 0
    copied_bytes = 0
    errors = []
    for index, item in enumerate(plan["items"], 1):
        source = ROOT / item["source"]
        target = ROOT / item["target"]
        try:
            if not source.is_file():
                raise RuntimeError("source missing")
            if target.exists():
                raise RuntimeError("target already exists; refusing to overwrite")
            shutil.copy2(source, target)
            if target.stat().st_size != source.stat().st_size:
                raise RuntimeError("size mismatch after copy")
            copied += 1
            copied_bytes += target.stat().st_size
        except Exception as error:
            errors.append({"source": item["source"], "target": item["target"], "error": str(error)})
        if index % 50 == 0:
            print(f"PROGRESS {index}/{len(plan['items'])}", flush=True)
    result = {
        "status": "ok" if not errors else "partial",
        "planned": len(plan["items"]),
        "copied": copied,
        "bytes": copied_bytes,
        "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
