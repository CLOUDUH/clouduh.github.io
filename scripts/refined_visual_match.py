#!/usr/bin/env python3
"""Perceptually match unmatched event-root images within the same event."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import os
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps


SUPPORTED = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}


def dct_matrix(size: int) -> np.ndarray:
    matrix = np.empty((size, size), dtype=np.float32)
    factor = math.pi / (2 * size)
    for k in range(size):
        scale = math.sqrt(1 / size) if k == 0 else math.sqrt(2 / size)
        for n in range(size):
            matrix[k, n] = scale * math.cos((2 * n + 1) * k * factor)
    return matrix


DCT32 = dct_matrix(32)


def bit_hash(bits: np.ndarray) -> int:
    value = 0
    for bit in bits.flatten():
        value = (value << 1) | int(bit)
    return value


def phash(image: Image.Image) -> int:
    pixels = np.asarray(image.convert("L"), dtype=np.float32)
    coeff = DCT32 @ pixels @ DCT32.T
    low = coeff[:8, :8].flatten()
    return bit_hash(low > float(np.median(low[1:])))


def feature(path: Path) -> dict | None:
    try:
        with Image.open(path) as original:
            image = ImageOps.exif_transpose(original).convert("RGB")
            width, height = image.size
            contained = Image.new("RGB", (32, 32), "white")
            thumb = ImageOps.contain(image, (32, 32), Image.Resampling.LANCZOS)
            contained.paste(thumb, ((32 - thumb.width) // 2, (32 - thumb.height) // 2))
            fitted = ImageOps.fit(image, (32, 32), Image.Resampling.LANCZOS)
            dh = np.asarray(image.resize((9, 8), Image.Resampling.LANCZOS).convert("L"))
            colors = np.asarray(image.resize((8, 8), Image.Resampling.LANCZOS), dtype=np.float32)
            mean = colors.mean(axis=(0, 1))
            # A normalized low-resolution luminance vector handles recompression
            # and mild color grading better than a hash alone.
            low = np.asarray(fitted.convert("L"), dtype=np.float32).reshape(-1)
            low = (low - low.mean()) / (low.std() + 1e-6)
            return {
                "path": str(path),
                "phash_contain": phash(contained),
                "phash_fit": phash(fitted),
                "dhash": bit_hash(dh[:, :-1] > dh[:, 1:]),
                "mean": mean.tolist(),
                "low": low.tolist(),
                "aspect": width / max(height, 1),
            }
    except Exception:
        return None


def distance(root: dict, candidate: dict) -> dict:
    pc = (root["phash_contain"] ^ candidate["phash_contain"]).bit_count()
    pf = (root["phash_fit"] ^ candidate["phash_fit"]).bit_count()
    dh = (root["dhash"] ^ candidate["dhash"]).bit_count()
    color = float(np.linalg.norm(np.asarray(root["mean"]) - np.asarray(candidate["mean"])))
    low_a = np.asarray(root["low"], dtype=np.float32)
    low_b = np.asarray(candidate["low"], dtype=np.float32)
    low_rmse = float(np.sqrt(np.mean((low_a - low_b) ** 2)))
    aspect = abs(math.log(max(root["aspect"], 1e-6) / max(candidate["aspect"], 1e-6)))
    score = min(pc, pf) + 0.30 * dh + 1.8 * low_rmse + 0.018 * color + 2.0 * min(aspect, 2.0)
    return {
        "score": round(score, 4),
        "phash_contain": pc,
        "phash_fit": pf,
        "dhash": dh,
        "color_distance": round(color, 3),
        "low_rmse": round(low_rmse, 4),
        "aspect_delta": round(aspect, 4),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage1", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    stage1 = json.loads(args.stage1.read_text(encoding="utf-8"))
    unmatched = [row for row in stage1 if row["match_method"] == "unmatched" and row["media_type"] == "photo"]
    by_event: dict[str, list[dict]] = defaultdict(list)
    for row in unmatched:
        by_event[row["event"]].append(row)

    source_by_event: dict[str, list[Path]] = {}
    all_paths: set[Path] = set()
    for event, rows in by_event.items():
        source_dir = Path("/Volumes/photo") / event / "photo"
        sources = []
        try:
            for root, dirs, names in os.walk(source_dir):
                dirs[:] = [name for name in dirs if name != "@eaDir"]
                sources.extend(
                    Path(root) / name
                    for name in names
                    if name != ".DS_Store" and Path(name).suffix.lower() in SUPPORTED
                )
        except OSError:
            pass
        source_by_event[event] = sources
        all_paths.update(sources)
        all_paths.update(Path(row["root_path"]) for row in rows)

    paths = sorted(all_paths, key=str)
    features: dict[str, dict] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_to_path = {executor.submit(feature, path): path for path in paths}
        for index, future in enumerate(concurrent.futures.as_completed(future_to_path), 1):
            path = future_to_path[future]
            value = future.result()
            if value:
                features[str(path)] = value
            if index % 250 == 0 or index == len(paths):
                print(f"features={index}/{len(paths)} usable={len(features)}", flush=True)

    results = []
    counts = Counter()
    for index, row in enumerate(unmatched, 1):
        root = features.get(row["root_path"])
        candidates = []
        if root:
            for source_path in source_by_event.get(row["event"], []):
                source = features.get(str(source_path))
                if source:
                    metric = distance(root, source)
                    candidates.append({"path": str(source_path), **metric})
            candidates.sort(key=lambda item: item["score"])
        top = candidates[:5]
        if not source_by_event.get(row["event"]):
            classification = "no_source_images"
        elif not root:
            classification = "root_decode_failed"
        elif not top:
            classification = "source_decode_failed"
        elif top[0]["score"] <= 8 and min(top[0]["phash_contain"], top[0]["phash_fit"]) <= 6:
            classification = "strong_visual_match"
        elif top[0]["score"] <= 14 and min(top[0]["phash_contain"], top[0]["phash_fit"]) <= 10:
            classification = "probable_visual_match"
        else:
            classification = "weak_visual_match"
        counts[classification] += 1
        results.append({**row, "visual_classification": classification, "visual_candidates": top})
        if index % 100 == 0 or index == len(unmatched):
            print(f"matched={index}/{len(unmatched)}", flush=True)

    (args.output / "visual_matches.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    summary = {
        "unmatched_photos": len(unmatched),
        "events": len(by_event),
        "feature_paths_requested": len(paths),
        "usable_features": len(features),
        "classifications": dict(counts),
    }
    (args.output / "visual_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
