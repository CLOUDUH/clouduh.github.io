#!/usr/bin/env python3
"""Run a prepared 2022 photo repair plan directly on the Synology NAS."""

from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path


ROOT = Path("/volume2/photo")
PLAN_PATH = Path("/tmp/codex_2022_plan.json")
RESULT_PATH = Path("/tmp/codex_2022_result.json")


def run(command: list[str]) -> None:
    result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip())


def write_date(path: Path, value: datetime) -> None:
    exif = value.strftime("%Y:%m:%d %H:%M:%S")
    run([
        "exiv2",
        f"-Mset Exif.Photo.DateTimeOriginal {exif}",
        f"-Mset Exif.Photo.DateTimeDigitized {exif}",
        f"-Mset Exif.Image.DateTime {exif}",
        str(path),
    ])
    os.utime(path, (value.timestamp(), value.timestamp()))


def related(primary: Path) -> list[tuple[Path, str]]:
    result = [(primary, "photo")]
    album = primary.parents[1]
    root_copy = album / primary.name
    if root_copy.is_file():
        result.append((root_copy, "root-selected"))
    pattern = str(primary.parent / f"{primary.stem}__selected*{primary.suffix}")
    result.extend((Path(value), "photo-selected") for value in glob.glob(pattern) if Path(value).is_file())
    return result


def unique_target(target: Path, source: Path) -> Path:
    if target == source or not target.exists():
        return target
    for number in range(1, 1000):
        candidate = target.with_name(f"{target.stem}_{number:02d}{target.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"No collision-free target for {target}")


def main() -> None:
    plan = json.loads(PLAN_PATH.read_text())
    date_writes = []
    moves = []
    renames = []
    synced = 0
    errors = []

    for index, action in enumerate(plan["actions"], 1):
        primary = ROOT / action["relativePath"]
        if not primary.is_file():
            errors.append({"path": action["relativePath"], "error": "source missing"})
            continue
        copies = related(primary)
        corrected = datetime.strptime(action["correctionDate"], "%Y-%m-%d %H:%M:%S") if action.get("correctionDate") else None
        effective = datetime.strptime(action["effectiveDate"], "%Y-%m-%d %H:%M:%S") if action.get("effectiveDate") else None
        try:
            if corrected:
                for path, kind in copies:
                    write_date(path, corrected)
                    date_writes.append({"path": str(path.relative_to(ROOT)), "kind": kind, "date": action["correctionDate"], "basis": action.get("basis", "")})
            elif effective and not action.get("unresolved"):
                for path, _ in copies:
                    os.utime(path, (effective.timestamp(), effective.timestamp()))
                    synced += 1

            if action.get("targetFolder") or action.get("newName"):
                for path, kind in copies:
                    destination_album = ROOT / (action.get("targetFolder") or action["relativePath"].split("/", 1)[0])
                    destination_dir = destination_album / "photo" if kind != "root-selected" else destination_album
                    destination_dir.mkdir(parents=True, exist_ok=True)
                    if action.get("newName"):
                        new_name_path = Path(action["newName"])
                        if kind == "photo-selected":
                            replacement = new_name_path.stem + path.stem[len(primary.stem):] + path.suffix
                        else:
                            replacement = action["newName"]
                    else:
                        replacement = path.name
                    target = unique_target(destination_dir / replacement, path)
                    old_rel = str(path.relative_to(ROOT))
                    if target != path:
                        shutil.move(str(path), str(target))
                    new_rel = str(target.relative_to(ROOT))
                    if path.parent != target.parent:
                        moves.append({"from": old_rel, "to": new_rel, "kind": kind})
                    if path.name != target.name:
                        renames.append({"from": old_rel, "to": new_rel, "kind": kind})
        except Exception as error:
            errors.append({"path": action["relativePath"], "error": str(error)})
        if index % 100 == 0:
            print(f"PROGRESS {index}/{len(plan['actions'])}", flush=True)

    result = {
        "status": "ok" if not errors else "partial",
        "actions": len(plan["actions"]),
        "dateWritesIncludingSelected": len(date_writes),
        "filesystemTimesSynced": synced,
        "movesIncludingSelected": len(moves),
        "renamesIncludingSelected": len(renames),
        "manualReview": plan["manualReview"],
        "dateWrites": date_writes,
        "moves": moves,
        "renames": renames,
        "errors": errors,
    }
    RESULT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({key: value for key, value in result.items() if not isinstance(value, list)}, ensure_ascii=False))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
