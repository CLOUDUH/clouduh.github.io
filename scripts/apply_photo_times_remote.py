#!/usr/bin/env python3
"""Apply an audited timestamp manifest on the Synology NAS.

Designed to run from the non-indexed backup directory.  It verifies that every
source file still matches the full backup before modifying anything, journals
all changes, writes image EXIF with exiv2, and stream-copies video containers
with ffmpeg.  No media is deleted; the original bytes remain in BACKUP_ROOT.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_EXTS = {".mp4", ".mov", ".m4v"}
TARGET_GLOB = "/volume2/photo/220101_*"
BACKUP_ROOT = Path("/volume2/backup/codex-photo-time-20260831")
BACKUP_MEDIA = BACKUP_ROOT / "original"
JOURNAL = BACKUP_ROOT / "apply-journal.jsonl"


def run(args: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_time(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    if not (2000 <= parsed.year <= 2026):
        raise ValueError(f"Unsafe proposed year: {value}")
    return parsed.replace(microsecond=0)


def exif_value(value: dt.datetime) -> str:
    return value.strftime("%Y:%m:%d %H:%M:%S")


def iso_local(value: dt.datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%S+08:00")


def iso_utc(value: dt.datetime) -> str:
    utc = value - dt.timedelta(hours=8)
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def date_utc(value: dt.datetime) -> str:
    utc = value - dt.timedelta(hours=8)
    return utc.strftime("%Y:%m:%d %H:%M:%S")


def verify_image_tags(path: Path, expected: str) -> None:
    result = run(["exiv2", "-g", "DateTime", "-Pv", str(path)], capture=True)
    values = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if values.count(expected) < 3:
        raise RuntimeError(f"Date tag verification failed for {path}: {values}")


def write_image(path: Path, value: dt.datetime) -> None:
    text = exif_value(value)
    run(
        [
            "exiv2",
            f"-Mset Exif.Photo.DateTimeOriginal Ascii {text}",
            f"-Mset Exif.Photo.DateTimeDigitized Ascii {text}",
            f"-Mset Exif.Image.DateTime Ascii {text}",
            str(path),
        ]
    )
    verify_image_tags(path, text)
    timestamp = value.timestamp()
    os.utime(path, (timestamp, timestamp))


def verify_video_tag(path: Path, expected: str) -> None:
    result = run(["ffmpeg", "-i", str(path), "-f", "ffmetadata", "-"], capture=True)
    marker = f"com.apple.quicktime.creationdate={expected}"
    if marker not in result.stdout:
        raise RuntimeError(f"Video date tag verification failed for {path}")


def write_video(path: Path, value: dt.datetime) -> None:
    temp = path.with_name(f".{path.name}.codex-time-update{path.suffix}")
    if temp.exists():
        raise RuntimeError(f"Stale temporary file exists: {temp}")
    try:
        run(
            [
                "ffmpeg",
                "-nostdin",
                "-y",
                "-v",
                "error",
                "-i",
                str(path),
                "-map",
                "0",
                "-c",
                "copy",
                "-map_metadata",
                "0",
                "-metadata",
                f"creation_time={iso_utc(value)}",
                "-metadata",
                f"com.apple.quicktime.creationdate={iso_local(value)}",
                "-metadata",
                f"Xmp.video.DateUTC={date_utc(value)}",
                "-movflags",
                "use_metadata_tags",
                str(temp),
            ]
        )
        if not temp.is_file() or temp.stat().st_size == 0:
            raise RuntimeError(f"ffmpeg produced no output for {path}")
        verify_video_tag(temp, iso_local(value))
        shutil.copymode(path, temp)
        os.replace(temp, path)
        timestamp = value.timestamp()
        os.utime(path, (timestamp, timestamp))
    except Exception:
        # Leave a failed temp in place for forensic inspection; never remove media.
        raise


def journal(record: dict) -> None:
    with JOURNAL.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--media-type", choices=("photo", "video"))
    parser.add_argument("--extension")
    args = parser.parse_args()

    targets = sorted(Path("/volume2/photo").glob("220101_*"))
    if len(targets) != 1:
        raise SystemExit(f"Expected one target directory, found {len(targets)}")
    target = targets[0]
    if not BACKUP_MEDIA.is_dir():
        raise SystemExit(f"Backup missing: {BACKUP_MEDIA}")

    records = json.loads(args.manifest.read_text(encoding="utf-8"))
    if len(records) != 505:
        raise SystemExit(f"Expected 505 manifest rows, found {len(records)}")
    selected = []
    for item in records:
        rel = Path(item["relative_path"])
        if rel.is_absolute() or ".." in rel.parts:
            raise SystemExit(f"Unsafe relative path: {rel}")
        if args.media_type and item["media_type"] != args.media_type:
            continue
        if args.extension and item["extension"].lower() != args.extension.lower():
            continue
        selected.append(item)
    if args.limit is not None:
        selected = selected[: args.limit]

    print(
        json.dumps(
            {
                "mode": "apply" if args.apply else "preflight",
                "target": str(target),
                "selected": len(selected),
                "journal": str(JOURNAL),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )

    # Preflight every selected item before the first write.
    checked = []
    for index, item in enumerate(selected, 1):
        rel = Path(item["relative_path"])
        live = target / rel
        backup = BACKUP_MEDIA / rel
        if not live.is_file() or not backup.is_file():
            raise SystemExit(f"Missing live or backup media: {rel}")
        live_hash = sha256(live)
        backup_hash = sha256(backup)
        if live_hash != backup_hash:
            raise SystemExit(f"Backup mismatch before write: {rel}")
        value = parse_time(item["proposed_time"])
        checked.append((item, live, backup, live_hash, value))
        if index % 50 == 0 or index == len(selected):
            print(f"preflight={index}/{len(selected)}", flush=True)

    if not args.apply:
        print("PREFLIGHT_OK", flush=True)
        return

    for index, (item, live, backup, before_hash, value) in enumerate(checked, 1):
        started = dt.datetime.now().isoformat(timespec="seconds")
        try:
            extension = live.suffix.lower()
            if extension in IMAGE_EXTS:
                write_image(live, value)
            elif extension in VIDEO_EXTS:
                write_video(live, value)
            else:
                raise RuntimeError(f"Unsupported media extension: {extension}")
            after_hash = sha256(live)
            journal(
                {
                    "status": "ok",
                    "relative_path": item["relative_path"],
                    "proposed_time": item["proposed_time"],
                    "confidence": item["confidence"],
                    "reason": item["reason"],
                    "before_sha256": before_hash,
                    "after_sha256": after_hash,
                    "backup_path": str(backup),
                    "started": started,
                    "finished": dt.datetime.now().isoformat(timespec="seconds"),
                }
            )
        except Exception as exc:
            journal(
                {
                    "status": "error",
                    "relative_path": item["relative_path"],
                    "error": repr(exc),
                    "started": started,
                    "finished": dt.datetime.now().isoformat(timespec="seconds"),
                }
            )
            raise
        if index % 25 == 0 or index == len(checked):
            print(f"applied={index}/{len(checked)}", flush=True)

    print("APPLY_OK", flush=True)


if __name__ == "__main__":
    main()
