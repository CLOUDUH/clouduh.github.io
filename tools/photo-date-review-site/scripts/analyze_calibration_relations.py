#!/usr/bin/env python3
"""Find visually related calibration images from the generated thumbnail set."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "public/calibration/calibration-items.json"
REVIEWS = Path("/Users/cloudu/Downloads/photo-date-calibration-review.json")
THUMBS = ROOT / "public/calibration/thumbs"
NAS = Path("/Volumes/photo")

TARGET_NAMES = {
    "wechat_171021_133439__tagged_01.jpg",
    "wechat_180905_000142.jpg",
    "35b160778ffbc315.jpg",
    "41e4cfbf8bdd47a0.jpg",
    "IMG_20180508_111113.jpg",
    "731793d224b3f60.jpg",
    "2083bc3e2d016cd6.jpg",
    "-77642798907296aa.jpg",
    "IMG_2245.PNG",
    "wechat_190829_235704.jpg",
    "IMG_20190209_130855.jpg",
}


def bits_hash(gray: np.ndarray, direction: str) -> np.ndarray:
    if direction == "dhash":
        return (gray[:, 1:] > gray[:, :-1]).ravel()
    return (gray > gray.mean()).ravel()


def load_features(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        fitted = ImageOps.fit(im, (96, 96), method=Image.Resampling.LANCZOS)
        rgb = np.asarray(fitted, dtype=np.float32) / 255.0
        gray_im = ImageOps.grayscale(fitted).resize((17, 16), Image.Resampling.LANCZOS)
        gray = np.asarray(gray_im, dtype=np.float32)
        ah_im = ImageOps.grayscale(fitted).resize((16, 16), Image.Resampling.LANCZOS)
        ah = np.asarray(ah_im, dtype=np.float32)
        hist = np.concatenate([
            np.histogram(rgb[:, :, c], bins=32, range=(0.0, 1.0), density=True)[0]
            for c in range(3)
        ]).astype(np.float32)
        hist /= max(hist.sum(), 1e-9)
        return rgb, bits_hash(gray, "dhash"), bits_hash(ah, "ahash"), hist


def distance(a, b) -> float:
    rgb_a, dh_a, ah_a, hist_a = a
    rgb_b, dh_b, ah_b, hist_b = b
    dh = np.mean(dh_a != dh_b)
    ah = np.mean(ah_a != ah_b)
    hist = np.abs(hist_a - hist_b).sum()
    mae = np.abs(rgb_a - rgb_b).mean()
    return float(0.34 * dh + 0.21 * ah + 0.15 * hist + 0.30 * mae)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    manifest = json.loads(MANIFEST.read_text())
    reviews_doc = json.loads(REVIEWS.read_text())
    reviews = {row["relativePath"]: row for row in reviews_doc["reviews"]}
    items = manifest["items"]

    features = {}
    for item in items:
        thumb = THUMBS / f'{item["id"]}.jpg'
        if thumb.exists():
            features[item["relativePath"]] = load_features(thumb)

    targets = [i for i in items if i["filename"] in TARGET_NAMES]
    out = []
    for target in targets:
        rel = target["relativePath"]
        folder = target["currentFolder"]
        pool = [
            x for x in items
            if x["relativePath"] != rel
            and x["relativePath"] in features
            and (x["currentFolder"] == folder or target["filename"] in {
                "wechat_190829_235704.jpg", "IMG_20190209_130855.jpg"
            })
        ]
        ranked = sorted(pool, key=lambda x: distance(features[rel], features[x["relativePath"]]))[:12]
        tpath = NAS / rel
        result = {
            "target": rel,
            "currentCapture": target.get("captureDate"),
            "notes": reviews.get(rel, {}).get("notes", ""),
            "sha256": sha256(tpath) if tpath.exists() else None,
            "size": tpath.stat().st_size if tpath.exists() else None,
            "matches": [],
        }
        for match in ranked:
            mrel = match["relativePath"]
            mpath = NAS / mrel
            result["matches"].append({
                "relativePath": mrel,
                "captureDate": match.get("captureDate"),
                "distance": round(distance(features[rel], features[mrel]), 6),
                "sha256": sha256(mpath) if mpath.exists() else None,
                "size": mpath.stat().st_size if mpath.exists() else None,
            })
        out.append(result)

    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
