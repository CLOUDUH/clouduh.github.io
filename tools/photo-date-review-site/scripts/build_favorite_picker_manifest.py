#!/usr/bin/env python3
"""Build a lazy-loading manifest for selecting favorites across every album."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from urllib.parse import quote


NAS = Path("/Volumes/photo")
ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public/favorite-picker"
PREVIEWS = PUBLIC / "converted"
SKIP = {"#recycle", "170900_备份"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".gif", ".webp", ".tif", ".tiff", ".avif"}
CONVERT_EXTS = {".heic", ".tif", ".tiff"}
CONVERT_JOBS: list[tuple[Path, Path]] = []
CONVERT_TARGETS: set[Path] = set()


def item_id(relative: str) -> str:
    return hashlib.sha1(relative.encode()).hexdigest()[:20]


def direct_url(relative: str) -> str:
    return "http://127.0.0.1:3002/media/" + quote(relative, safe="/")


def preview_url(path: Path, relative: str) -> str | None:
    return direct_url(relative)


def walk_images(root: Path) -> list[Path]:
    result = []
    for directory, dirs, files in os.walk(root):
        dirs[:] = [name for name in dirs if name != "@eaDir"]
        for name in files:
            if Path(name).suffix.lower() in IMAGE_EXTS:
                result.append(Path(directory) / name)
    return result


def convert_one(job: tuple[Path, Path]) -> tuple[Path, bool]:
    source, target = job
    target.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(["/usr/bin/sips", "-Z", "1600", "-s", "format", "jpeg",
                             str(source), "--out", str(target)], text=True, capture_output=True)
    return target, result.returncode == 0 and target.exists()


def main() -> None:
    folders = []
    all_tops = sorted(
        [path for path in NAS.iterdir() if path.is_dir() and path.name not in SKIP and not path.name.startswith(("@", "."))],
        key=lambda path: path.name,
    )
    total_photos = 0
    total_existing = 0
    converted = 0
    missing_previews = 0
    for folder_index, top in enumerate(all_tops, start=1):
        photo_dir = top / "photo"
        if not photo_dir.is_dir():
            continue
        photo_paths = sorted(walk_images(photo_dir), key=lambda path: str(path.relative_to(photo_dir)).lower())
        root_paths = sorted(
            [path for path in top.iterdir() if path.suffix.lower() in IMAGE_EXTS and path.is_file()],
            key=lambda path: path.name.lower(),
        )
        photos = []
        by_name: dict[str, list[str]] = {}
        by_direct_name: dict[str, list[str]] = {}
        by_selected_name: dict[str, list[str]] = {}
        for path in photo_paths:
            relative = str(path.relative_to(NAS))
            ident = item_id(relative)
            preview = preview_url(path, relative)
            entry = {
                "id": ident,
                "relativePath": relative,
                "filename": path.name,
                "subfolder": str(path.parent.relative_to(photo_dir)) if path.parent != photo_dir else "",
                "modified": "",
                "preview": preview,
            }
            photos.append(entry)
            by_name.setdefault(path.name.lower(), []).append(ident)
            if path.parent == photo_dir:
                by_direct_name.setdefault(path.name.lower(), []).append(ident)
            selected_match = re.match(r"^(.*)__selected(?:_\d+)?(\.[^.]+)$", path.name, re.I)
            if selected_match:
                original_name = (selected_match.group(1) + selected_match.group(2)).lower()
                by_selected_name.setdefault(original_name, []).append(ident)

        existing = []
        initial = []
        for path in root_paths:
            relative = str(path.relative_to(NAS))
            edited_matches = by_selected_name.get(path.name.lower(), [])
            direct_matches = by_direct_name.get(path.name.lower(), [])
            matches = by_name.get(path.name.lower(), [])
            matched = edited_matches[0] if edited_matches else (direct_matches[0] if direct_matches else (matches[0] if len(matches) == 1 else None))
            if matched:
                initial.append(matched)
            preview = preview_url(path, relative)
            existing.append({
                "id": "existing-" + item_id(relative),
                "relativePath": relative,
                "filename": path.name,
                "preview": preview,
                "matchedPhotoId": matched,
            })

        folders.append({
            "id": item_id(top.name),
            "event": top.name,
            "count": len(photos),
            "existingCount": len(existing),
            "initialSelectedIds": sorted(set(initial)),
            "existingPicks": existing,
            "photos": photos,
        })
        total_photos += len(photos)
        total_existing += len(existing)
        if len(folders) % 20 == 0:
            print(f"PROGRESS folders {len(folders)} photos {total_photos}", flush=True)

    failed = set()
    if CONVERT_JOBS:
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = [pool.submit(convert_one, job) for job in CONVERT_JOBS]
            for index, future in enumerate(as_completed(futures), start=1):
                target, ok = future.result()
                if not ok:
                    failed.add(target.name)
                if index % 50 == 0:
                    print(f"PROGRESS converted {index}/{len(futures)}", flush=True)
    converted = len(CONVERT_TARGETS) - len(failed)
    missing_previews = len(failed)
    if failed:
        for folder in folders:
            for entry in [*folder["photos"], *folder["existingPicks"]]:
                if entry.get("preview") and Path(entry["preview"]).name in failed:
                    entry["preview"] = None

    manifest = {
        "version": 2,
        "generatedAt": datetime.now().astimezone().isoformat(),
        "folderCount": len(folders),
        "totalPhotos": total_photos,
        "existingFavorites": total_existing,
        "convertedPreviews": converted,
        "missingPreviews": missing_previews,
        "folders": folders,
    }
    PUBLIC.mkdir(parents=True, exist_ok=True)
    (PUBLIC / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, separators=(",", ":")))
    print(json.dumps({key: manifest[key] for key in ["folderCount", "totalPhotos", "existingFavorites", "convertedPreviews", "missingPreviews"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
