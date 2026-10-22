#!/usr/bin/env python3
"""Read-only consistency audit for event-root refined media versus originals."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path


VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".avi"}
EDIT_SUFFIX_RE = re.compile(
    r"(?:[-_ .]*(?:编辑|精修|修图|调色|成片|样片|样张|最终|final|edited?|retouched?|enhanced?|copy|副本|导出|export))+$",
    re.I,
)


def normalized_stem(name: str) -> str:
    stem = unicodedata.normalize("NFKC", Path(name).stem).casefold().strip()
    previous = None
    while previous != stem:
        previous = stem
        stem = EDIT_SUFFIX_RE.sub("", stem).strip("-_ .")
    return stem


def sha256(path: Path) -> str | None:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def is_video(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_EXTS


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root-metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    rows = json.loads(args.root_metadata.read_text(encoding="utf-8"))
    library = Path("/Volumes/photo")
    indexes: dict[tuple[Path, str], dict] = {}

    def get_index(event: Path, media_type: str) -> dict:
        key = (event, media_type)
        if key in indexes:
            return indexes[key]
        source_dir = event / ("video" if media_type == "video" else "photo")
        files = []
        try:
            for root, dirs, names in os.walk(source_dir):
                dirs[:] = [name for name in dirs if name != "@eaDir"]
                files.extend(Path(root) / name for name in names if name != ".DS_Store")
        except OSError:
            pass
        by_name: dict[str, list[Path]] = defaultdict(list)
        by_stem: dict[str, list[Path]] = defaultdict(list)
        by_size: dict[int, list[Path]] = defaultdict(list)
        for path in files:
            by_name[path.name.casefold()].append(path)
            by_stem[normalized_stem(path.name)].append(path)
            try:
                by_size[path.stat().st_size].append(path)
            except OSError:
                pass
        result = {"files": files, "by_name": by_name, "by_stem": by_stem, "by_size": by_size}
        indexes[key] = result
        return result

    matches = []
    stats = Counter()
    for index, row in enumerate(rows, 1):
        root_path = Path(row["SourceFile"])
        event = root_path.parent
        media_type = "video" if is_video(root_path) else "photo"
        source_index = get_index(event, media_type)
        candidates = source_index["by_name"].get(root_path.name.casefold(), [])
        method = "exact_name" if candidates else ""
        if not candidates:
            candidates = source_index["by_stem"].get(normalized_stem(root_path.name), [])
            method = "normalized_stem" if candidates else ""

        # A root-level copy may have been renamed.  For unmatched files, hash
        # only same-size candidates in the corresponding source folder.
        if not candidates:
            try:
                same_size = source_index["by_size"].get(root_path.stat().st_size, [])
            except OSError:
                same_size = []
            if same_size:
                root_hash = sha256(root_path)
                candidates = [path for path in same_size if root_hash and sha256(path) == root_hash]
                method = "exact_sha256" if candidates else ""

        stats[method or "unmatched"] += 1
        if len(candidates) > 1:
            stats["ambiguous_multiple"] += 1
        matches.append(
            {
                "root_path": str(root_path),
                "relative_to_library": str(root_path.relative_to(library)),
                "event": event.name,
                "media_type": media_type,
                "match_method": method or "unmatched",
                "candidate_paths": [str(path) for path in candidates],
                "candidate_count": len(candidates),
                "normalized_stem": normalized_stem(root_path.name),
            }
        )
        if index % 250 == 0 or index == len(rows):
            print(f"indexed={index}/{len(rows)}", flush=True)

    (args.output / "stage1_matches.json").write_text(
        json.dumps(matches, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    summary = {
        "root_media": len(matches),
        "source_media_indexed": sum(len(value["files"]) for value in indexes.values()),
        "events_and_media_indexes": len(indexes),
        "match_counts": dict(stats),
    }
    (args.output / "stage1_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
