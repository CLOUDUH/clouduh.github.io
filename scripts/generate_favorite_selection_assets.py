#!/usr/bin/env python3
"""Generate local-only thumbnails and a folder-based favorite selection manifest."""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import hashlib
import json
import os
import re
from pathlib import Path

from PIL import Image, ImageOps


EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".tif", ".tiff"}
EXCLUDED_DIRS = {"@eaDir", "#recycle", "@tmp", ".snapshot", "#snapshot"}


def stable_id(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]


def thumbnail(source: Path, destination: Path, max_size: int) -> bool:
    try:
        with Image.open(source) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            destination.parent.mkdir(parents=True, exist_ok=True)
            image.save(destination, "JPEG", quality=79, optimize=True, progressive=True)
        return True
    except Exception:
        return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--library", type=Path, default=Path("/Volumes/photo"))
    parser.add_argument("--output-public", type=Path, required=True)
    parser.add_argument("--sample-folders", type=int)
    parser.add_argument("--limit-per-folder", type=int)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--max-size", type=int, default=640)
    args = parser.parse_args()

    folders = []
    jobs: dict[str, tuple[Path, Path]] = {}
    asset_root = args.output_public / "selection"
    thumb_root = asset_root / "thumbs"
    events = sorted(
        event for event in args.library.iterdir()
        if event.is_dir() and re.match(r"^\d{6}_", event.name)
    )
    for event in events:
        root_images = [path for path in event.iterdir() if path.is_file() and path.suffix.lower() in EXTENSIONS]
        if root_images:
            continue
        source_root = event / "photo"
        if not source_root.is_dir():
            continue
        photos = []
        for base, dirs, names in os.walk(source_root):
            dirs[:] = [name for name in dirs if name not in EXCLUDED_DIRS]
            for name in names:
                path = Path(base) / name
                if path.suffix.lower() not in EXTENSIONS:
                    continue
                relative = str(path.relative_to(args.library))
                asset_id = stable_id(relative)
                filename = f"{asset_id}.jpg"
                jobs.setdefault(filename, (path, thumb_root / filename))
                try:
                    modified = dt.datetime.fromtimestamp(path.stat().st_mtime).isoformat(sep=" ", timespec="seconds")
                except OSError:
                    modified = ""
                photos.append({
                    "id": asset_id,
                    "relativePath": relative,
                    "filename": path.name,
                    "subfolder": str(path.parent.relative_to(source_root)) if path.parent != source_root else "",
                    "modified": modified,
                    "thumbnail": f"/selection/thumbs/{filename}",
                })
        photos.sort(key=lambda item: (item["modified"], item["relativePath"]))
        if args.limit_per_folder:
            photos = photos[: args.limit_per_folder]
        if photos:
            folders.append({"id": stable_id(event.name), "event": event.name, "count": len(photos), "photos": photos})
        if args.sample_folders and len(folders) >= args.sample_folders:
            break

    selected_ids = {photo["id"] for folder in folders for photo in folder["photos"]}
    jobs = {name: value for name, value in jobs.items() if stable_id(str(value[0].relative_to(args.library))) in selected_ids}
    failures = set()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_names = {executor.submit(thumbnail, src, dest, args.max_size): name for name, (src, dest) in jobs.items()}
        for index, future in enumerate(concurrent.futures.as_completed(future_names), 1):
            name = future_names[future]
            if not future.result():
                failures.add(name)
            if index % 100 == 0 or index == len(future_names):
                print(f"thumbnails={index}/{len(future_names)} failures={len(failures)}", flush=True)

    for folder in folders:
        for photo in folder["photos"]:
            if Path(photo["thumbnail"]).name in failures:
                photo["thumbnail"] = None

    manifest = {
        "version": 1,
        "generatedAt": dt.datetime.now().isoformat(timespec="seconds"),
        "folderCount": len(folders),
        "totalPhotos": sum(folder["count"] for folder in folders),
        "folders": folders,
    }
    asset_root.mkdir(parents=True, exist_ok=True)
    (asset_root / "selection-items.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"folders": manifest["folderCount"], "photos": manifest["totalPhotos"], "thumbnailFiles": len(jobs), "failures": len(failures)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
