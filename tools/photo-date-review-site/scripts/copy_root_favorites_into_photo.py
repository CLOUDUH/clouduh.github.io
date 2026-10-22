#!/usr/bin/env python3
"""Copy every root-level favorite into its album's photo directory without overwriting."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path


NAS = Path("/Volumes/photo")
ROOT = Path(__file__).resolve().parents[1]
PLAN = Path("/private/tmp/root-favorites-copy-plan.json")
LOG = ROOT / "tools-data/root-favorites-copy-result.json"
EXIFTOOL = "/opt/homebrew/bin/exiftool"
SKIP = {"#recycle", "170900_备份"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".gif", ".webp", ".tif", ".tiff", ".avif"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def same_file(a: Path, b: Path) -> bool:
    return a.stat().st_size == b.stat().st_size and sha256(a) == sha256(b)


def selected_target(photo_dir: Path, source: Path) -> tuple[Path | None, str]:
    direct = photo_dir / source.name
    if not direct.exists():
        return direct, "missing"
    if same_file(source, direct):
        return None, "already-identical"
    candidates = [direct.with_name(f"{direct.stem}__selected{direct.suffix}"),
                  *sorted(photo_dir.glob(f"{direct.stem}__selected_*{direct.suffix}"))]
    for candidate in candidates:
        if candidate.exists() and same_file(source, candidate):
            return None, "already-selected-copy"
    target = candidates[0]
    if not target.exists():
        return target, "edited-version"
    for index in range(1, 10_000):
        target = direct.with_name(f"{direct.stem}__selected_{index}{direct.suffix}")
        if not target.exists():
            return target, "edited-version"
    raise RuntimeError(f"No unique selected target for {source}")


def build_plan() -> dict:
    copies = []
    already = 0
    root_count = 0
    for top in sorted(NAS.iterdir(), key=lambda path: path.name):
        if not top.is_dir() or top.name in SKIP or top.name.startswith(("@", ".")):
            continue
        roots = [path for path in top.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_EXTS]
        if not roots:
            continue
        photo_dir = top / "photo"
        for source in roots:
            root_count += 1
            target, reason = selected_target(photo_dir, source) if photo_dir.exists() else (photo_dir / source.name, "missing-photo-directory")
            if target is None:
                already += 1
                continue
            copies.append({"source": str(source.relative_to(NAS)), "target": str(target.relative_to(NAS)),
                           "bytes": source.stat().st_size, "reason": reason})
        if root_count and root_count % 500 < len(roots):
            print(f"PROGRESS plan roots {root_count} copies {len(copies)}", flush=True)
    result = {"generatedAt": datetime.now().astimezone().isoformat(), "rootFavorites": root_count,
              "alreadyInPhoto": already, "copies": copies,
              "copiesNeeded": len(copies), "bytes": sum(row["bytes"] for row in copies)}
    PLAN.write_text(json.dumps(result, ensure_ascii=False))
    print(json.dumps({"rootFavorites": root_count, "alreadyInPhoto": already,
                      "copiesNeeded": len(copies), "gib": round(result["bytes"] / 1024 ** 3, 3)}, ensure_ascii=False, indent=2))
    return result


def set_copy_times(paths: list[Path]) -> None:
    for start in range(0, len(paths), 300):
        chunk = paths[start:start + 300]
        first = subprocess.run([EXIFTOOL, "-overwrite_original_in_place",
                                "-FileCreateDate<FileModifyDate", *map(str, chunk)], text=True, capture_output=True)
        if first.returncode:
            raise RuntimeError(first.stderr or first.stdout)
        second = subprocess.run([EXIFTOOL, "-overwrite_original_in_place", "-if", "$DateTimeOriginal",
                                 "-FileCreateDate<DateTimeOriginal", "-FileModifyDate<DateTimeOriginal",
                                 *map(str, chunk)], text=True, capture_output=True)
        if second.returncode:
            raise RuntimeError(second.stderr or second.stdout)


def apply_plan() -> None:
    plan = json.loads(PLAN.read_text())
    copied, skipped, errors = [], [], []
    targets = []
    for index, row in enumerate(plan["copies"], start=1):
        source = NAS / row["source"]
        target = NAS / row["target"]
        if not source.exists():
            errors.append({**row, "error": "source missing"})
            continue
        if target.exists():
            if same_file(source, target):
                skipped.append({**row, "reason": "became identical before apply"})
                targets.append(target)
                continue
            errors.append({**row, "error": "target collision appeared"})
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.codex-copying")
        temporary.unlink(missing_ok=True)
        try:
            shutil.copy2(source, temporary)
            if temporary.stat().st_size != source.stat().st_size:
                raise IOError("size mismatch after copy")
            os.replace(temporary, target)
            copied.append(row)
            targets.append(target)
        except Exception as exc:
            temporary.unlink(missing_ok=True)
            errors.append({**row, "error": str(exc)})
        if index % 50 == 0:
            print(f"PROGRESS copy {index}/{len(plan['copies'])}", flush=True)
    if targets:
        set_copy_times(targets)
    missing_after = [str(path.relative_to(NAS)) for path in targets if not path.exists()]
    if missing_after:
        errors.extend({"target": path, "error": "missing after copy"} for path in missing_after)
    report = {"generatedAt": datetime.now().astimezone().isoformat(),
              "rootFavorites": plan["rootFavorites"], "alreadyInPhotoBefore": plan["alreadyInPhoto"],
              "copied": len(copied), "skipped": len(skipped), "bytesCopied": sum(row["bytes"] for row in copied),
              "errors": errors, "status": "ok" if not errors else "failed"}
    LOG.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.plan:
        build_plan()
    elif args.apply:
        apply_plan()
    else:
        raise SystemExit("Pass --plan or --apply")


if __name__ == "__main__":
    main()
