#!/usr/bin/env python3
"""Generate privacy-preserving local thumbnails and review manifest."""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import datetime as dt
import hashlib
import json
import os
import re
from pathlib import Path

from PIL import Image, ImageOps


def stable_id(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]


def event_month(event: str) -> str:
    match = re.match(r"(\d{2})(\d{2})", event)
    if not match or match.group(2) == "00":
        return ""
    return f"20{match.group(1)}-{match.group(2)}"


def make_thumbnail(source: Path, destination: Path, max_size: int) -> bool:
    try:
        with Image.open(source) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            canvas = Image.new("RGB", image.size, "white")
            canvas.paste(image)
            destination.parent.mkdir(parents=True, exist_ok=True)
            canvas.save(destination, "JPEG", quality=80, optimize=True, progressive=True)
        return True
    except Exception:
        return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--visual", type=Path, required=True)
    parser.add_argument("--output-public", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--max-size", type=int, default=720)
    args = parser.parse_args()

    rows = list(csv.DictReader(args.report.open(encoding="utf-8-sig")))
    visual = {row["root_path"]: row for row in json.loads(args.visual.read_text(encoding="utf-8"))}
    unresolved = [
        row for row in rows
        if row["media_type"] == "photo" and row["status"].startswith("unresolved")
    ]
    unresolved.sort(key=lambda row: row["relative_to_library"])
    if args.limit:
        buckets = {}
        for row in unresolved:
            classification = visual.get(row["root_path"], {}).get("visual_classification", "unknown")
            buckets.setdefault(classification, row)
        selected = []
        for key in ("no_source_images", "weak_visual_match", "root_decode_failed", "source_decode_failed"):
            if key in buckets and buckets[key] not in selected:
                selected.append(buckets[key])
        for row in unresolved:
            if len(selected) >= args.limit:
                break
            if row not in selected:
                selected.append(row)
        unresolved = selected[: args.limit]

    review_root = args.output_public / "review"
    thumbs_root = review_root / "thumbs"
    thumbs_root.mkdir(parents=True, exist_ok=True)
    image_jobs: dict[str, tuple[Path, Path]] = {}
    items = []

    def thumbnail_for(path_text: str, role: str) -> str:
        asset_id = stable_id(path_text)
        filename = f"{asset_id}-{role}.jpg"
        image_jobs.setdefault(filename, (Path(path_text), thumbs_root / filename))
        return f"/review/thumbs/{filename}"

    for row in unresolved:
        visual_row = visual.get(row["root_path"], {})
        classification = visual_row.get("visual_classification", "unknown")
        candidates = []
        if classification == "weak_visual_match":
            for candidate in visual_row.get("visual_candidates", [])[:3]:
                source_path = candidate["path"]
                candidates.append(
                    {
                        "relativePath": str(Path(source_path).relative_to("/Volumes/photo")),
                        "thumbnail": thumbnail_for(source_path, "candidate"),
                        "score": candidate.get("score"),
                        "phashDistance": min(candidate.get("phash_contain", 64), candidate.get("phash_fit", 64)),
                    }
                )
        relative = row["relative_to_library"]
        event = row["event"]
        items.append(
            {
                "id": stable_id(relative),
                "relativePath": relative,
                "filename": Path(relative).name,
                "event": event,
                "kind": "PNG / 截图" if Path(relative).suffix.lower() == ".png" else "实拍照片",
                "classification": classification,
                "currentCapture": row["root_capture"],
                "suggestedMonth": event_month(event),
                "thumbnail": thumbnail_for(row["root_path"], "root"),
                "candidates": candidates,
            }
        )

    failures = set()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_to_name = {
            executor.submit(make_thumbnail, source, destination, args.max_size): name
            for name, (source, destination) in image_jobs.items()
        }
        for index, future in enumerate(concurrent.futures.as_completed(future_to_name), 1):
            name = future_to_name[future]
            if not future.result():
                failures.add(name)
            if index % 100 == 0 or index == len(future_to_name):
                print(f"thumbnails={index}/{len(future_to_name)} failures={len(failures)}", flush=True)

    for item in items:
        if Path(item["thumbnail"]).name in failures:
            item["thumbnail"] = None
        for candidate in item["candidates"]:
            if Path(candidate["thumbnail"]).name in failures:
                candidate["thumbnail"] = None

    manifest = {
        "version": 1,
        "generatedAt": dt.datetime.now().isoformat(timespec="seconds"),
        "count": len(items),
        "items": items,
    }
    review_root.mkdir(parents=True, exist_ok=True)
    (review_root / "review-items.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({"items": len(items), "thumbnailFiles": len(image_jobs), "failures": len(failures)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
