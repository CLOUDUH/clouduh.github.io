#!/usr/bin/env python3
"""Compare iCloud-exported favorites with the NAS favorites copy in Hub."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import numpy as np
from PIL import Image, ImageOps


HUB = Path("/Users/cloudu/Hub/2022年前精选汇总")
ICLOUD = HUB / "icloud"
NAS_COPY = HUB
NAS = Path("/Volumes/photo")
ROOT = Path(__file__).resolve().parents[1]
CACHE = Path("/private/tmp/icloud-nas-favorites-features.json")
PUBLIC = ROOT / "public/favorites-compare"
EXIFTOOL = "/opt/homebrew/bin/exiftool"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".tif", ".tiff", ".webp", ".avif", ".gif"}
VIDEO_EXTS = {".mp4", ".mov", ".m4v"}


def files() -> tuple[list[Path], list[Path], list[Path]]:
    cloud = sorted(path for path in ICLOUD.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_EXTS)
    videos = sorted(path for path in ICLOUD.rglob("*") if path.is_file() and path.suffix.lower() in VIDEO_EXTS)
    nas = []
    for album in NAS.iterdir():
        if not album.is_dir() or len(album.name) < 6 or not album.name[:6].isdigit() or int(album.name[:6]) >= 220000:
            continue
        nas.extend(path for path in album.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_EXTS)
    nas.sort()
    return cloud, nas, videos


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def image_feature(path: Path) -> dict:
    with Image.open(path) as image:
        image.draft("RGB", (192, 192))
        image = ImageOps.exif_transpose(image).convert("RGB")
        width, height = image.size
        contained = ImageOps.contain(image, (96, 96), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (96, 96), tuple(map(int, np.asarray(contained).mean(axis=(0, 1)))))
        canvas.paste(contained, ((96 - contained.width) // 2, (96 - contained.height) // 2))
        gray = np.asarray(canvas.convert("L"), dtype=np.float32) / 255.0
        normalized = (gray - gray.mean()) / (gray.std() + 1e-6)
        small = np.asarray(canvas.convert("L").resize((17, 16), Image.Resampling.LANCZOS))
        dhash = np.packbits((small[:, 1:] > small[:, :-1]).reshape(-1)).tobytes().hex()
        exact_thumb = hashlib.sha256(canvas.tobytes()).hexdigest()
        return {
            "width": width,
            "height": height,
            "dhash": dhash,
            "exactThumb": exact_thumb,
            "feature": np.round(normalized[::4, ::4].reshape(-1), 4).tolist(),
        }


def scan() -> None:
    cloud, nas, videos = files()
    all_files = [("icloud", path) for path in cloud] + [("nas", path) for path in nas]
    rows = []
    for index, (side, path) in enumerate(all_files, 1):
        try:
            feature = image_feature(path)
            error = None
        except Exception as exc:
            feature = {"width": 0, "height": 0, "dhash": "", "exactThumb": "", "feature": []}
            error = str(exc)
        rows.append({
            "side": side,
            "relativePath": str(path.relative_to(HUB if side == "icloud" else NAS)),
            "filename": path.name,
            "size": path.stat().st_size,
            "sha256": sha256(path),
            "error": error,
            **feature,
        })
        if index % 100 == 0:
            print(f"PROGRESS {index}/{len(all_files)}", flush=True)
    CACHE.write_text(json.dumps({
        "rows": rows,
        "videos": [{"relativePath": str(path.relative_to(HUB)), "filename": path.name, "size": path.stat().st_size} for path in videos],
    }, ensure_ascii=False))
    print(json.dumps({"icloudImages": len(cloud), "nasImages": len(nas), "icloudVideos": len(videos), "errors": sum(bool(row["error"]) for row in rows)}, ensure_ascii=False))


def hamming(left: str, right: str) -> int:
    if not left or not right:
        return 999
    return (int(left, 16) ^ int(right, 16)).bit_count()


def feature_distance(left: dict, right: dict) -> float:
    if not left["feature"] or not right["feature"]:
        return 999.0
    a = np.asarray(left["feature"], dtype=np.float32)
    b = np.asarray(right["feature"], dtype=np.float32)
    correlation = float(np.mean(a * b))
    aspect_a = left["width"] / max(1, left["height"])
    aspect_b = right["width"] / max(1, right["height"])
    aspect_penalty = min(2.0, abs(math.log(max(1e-6, aspect_a / aspect_b))))
    return 1.0 - correlation + aspect_penalty * 0.25


def normalized_name(name: str) -> str:
    stem = Path(name).stem.lower()
    stem = re.sub(r"(?:_\d+| copy| 副本)$", "", stem)
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", stem)


def analyze() -> None:
    doc = json.loads(CACHE.read_text())
    cloud = [row for row in doc["rows"] if row["side"] == "icloud"]
    nas = [row for row in doc["rows"] if row["side"] == "nas"]
    by_sha: dict[str, list[int]] = defaultdict(list)
    by_thumb: dict[str, list[int]] = defaultdict(list)
    by_name: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(nas):
        by_sha[row["sha256"]].append(index)
        by_thumb[row["exactThumb"]].append(index)
        by_name[normalized_name(row["filename"])].append(index)

    used: set[int] = set()
    matches = []
    unresolved = []
    for left in cloud:
        candidates: list[tuple[float, int, str]] = []
        for index in by_sha.get(left["sha256"], []):
            candidates.append((0.0, index, "文件哈希完全一致"))
        if not candidates:
            for index in by_thumb.get(left["exactThumb"], []):
                candidates.append((0.01, index, "解码画面完全一致"))
        if not candidates:
            for index in by_name.get(normalized_name(left["filename"]), []):
                candidates.append((0.08 + feature_distance(left, nas[index]), index, "文件名对应且画面相似"))
        if not candidates and left["dhash"]:
            ranked = []
            for index, right in enumerate(nas):
                hd = hamming(left["dhash"], right["dhash"])
                if hd <= 12:
                    ranked.append((feature_distance(left, right) + hd / 128, index, "感知画面相似"))
            candidates.extend(sorted(ranked)[:8])
        candidates.sort()
        available = [item for item in candidates if item[1] not in used]
        if available and available[0][0] <= 0.22:
            score, index, basis = available[0]
            used.add(index)
            matches.append({"icloud": left, "nas": nas[index], "basis": basis, "score": round(score, 5)})
        else:
            unresolved.append({"icloud": left, "candidates": [
                {"nas": nas[index], "score": round(score, 5), "basis": basis}
                for score, index, basis in candidates[:5]
            ]})
    nas_only = [row for index, row in enumerate(nas) if index not in used]
    result = {
        "summary": {
            "icloudImages": len(cloud), "nasImages": len(nas), "icloudVideos": len(doc["videos"]),
            "matched": len(matches), "icloudUnmatched": len(unresolved), "nasUnmatched": len(nas_only),
        },
        "matches": matches,
        "icloudUnmatched": unresolved,
        "nasUnmatched": nas_only,
        "videos": doc["videos"],
    }
    Path("/private/tmp/icloud-nas-favorites-analysis.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scan", action="store_true")
    parser.add_argument("--analyze", action="store_true")
    args = parser.parse_args()
    if args.scan:
        scan()
    elif args.analyze:
        analyze()
    else:
        raise SystemExit("Pass --scan or --analyze")


if __name__ == "__main__":
    main()
