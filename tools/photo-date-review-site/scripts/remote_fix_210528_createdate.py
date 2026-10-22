#!/usr/bin/env python3
"""Fix the 2020/2021 EXIF year mismatch in the 2021-05-28 graduation set."""

from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path


ROOT = Path("/volume2/photo")
NAME = re.compile(r"^IMG_(\d{4})(?:[^0-9].*)?\.(?:jpe?g|heic)$", re.I)


def value(path: Path, tag: str) -> str:
    result = subprocess.run(["exiv2", "-K", tag, "-Pv", str(path)], text=True, capture_output=True)
    return result.stdout.strip().splitlines()[0] if result.returncode == 0 and result.stdout.strip() else ""


def main() -> None:
    albums = sorted(ROOT.glob("210528_*"))
    groups = []
    for album in albums:
        matches = []
        for path in album.rglob("*"):
            if not path.is_file() or "@eaDir" in path.parts:
                continue
            match = NAME.match(path.name)
            if match and 7602 <= int(match.group(1)) <= 8294:
                matches.append(path)
        groups.append((len(matches), album, matches))
    groups.sort(reverse=True, key=lambda item: item[0])
    if not groups or groups[0][0] == 0 or (len(groups) > 1 and groups[0][0] == groups[1][0]):
        raise SystemExit(f"Could not uniquely select graduation album: {[(count, path.name) for count, path, _ in groups]}")
    _, selected_album, candidates = groups[0]

    changed = []
    timestamps_synced = 0
    skipped = []
    errors = []
    for path in sorted(candidates):
        original = value(path, "Exif.Photo.DateTimeOriginal")
        created = value(path, "Exif.Photo.DateTimeDigitized")
        if not original.startswith("2021:05:28") or not (created.startswith("2020:05:28") or created == original):
            skipped.append({"path": str(path.relative_to(ROOT)), "original": original, "created": created})
            continue
        if created != original:
            result = subprocess.run([
                "exiv2",
                f"-Mset Exif.Photo.DateTimeOriginal {original}",
                f"-Mset Exif.Photo.DateTimeDigitized {original}",
                f"-Mset Exif.Image.DateTime {original}",
                str(path),
            ], text=True, capture_output=True)
            if result.returncode:
                errors.append({"path": str(path.relative_to(ROOT)), "error": (result.stderr or result.stdout).strip()})
                continue
            changed.append({"path": str(path.relative_to(ROOT)), "from": created, "to": original})
        stamp = datetime.strptime(original, "%Y:%m:%d %H:%M:%S").timestamp()
        os.utime(path, (stamp, stamp))
        timestamps_synced += 1

    result = {"status": "ok" if not errors else "partial", "album": selected_album.name, "candidates": len(candidates), "changed": len(changed), "timestampsSynced": timestamps_synced, "skipped": len(skipped), "errors": errors}
    print(json.dumps(result, ensure_ascii=False))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
