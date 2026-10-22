#!/usr/bin/env python3
"""Build a read-only timestamp proposal for the 220101 cloud-memory album.

The NAS share is intentionally treated as read-only.  This script emits CSV/JSON
reports and contact sheets under a local output directory; it never edits media.
"""

from __future__ import annotations

import argparse
import calendar
import csv
import datetime as dt
import hashlib
import json
import math
import os
import random
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import ExifTags, Image, ImageDraw, ImageFont, ImageOps


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_EXTS = {".mp4", ".mov", ".m4v"}
ALL_MEDIA_EXTS = IMAGE_EXTS | VIDEO_EXTS
DATE_TAGS = {
    "DateTimeOriginal": 36867,
    "DateTimeDigitized": 36868,
    "DateTime": 306,
}
EVENT_RE = re.compile(r"^(?P<date>22\d{4})_")
TS13_RE = re.compile(r"(?P<ts>\d{13})")
IMG_RE = re.compile(r"IMG_(?P<date>\d{8})_(?P<time>\d{6})", re.I)


@dataclass
class Proposal:
    relative_path: str
    media_type: str
    extension: str
    current_mtime: str
    filename_time: str | None
    exif_time: str | None
    proposed_time: str | None
    proposed_month: str | None
    confidence: str
    action: str
    reason: str
    exact_match_events: str
    nearest_visual_event: str | None
    nearest_visual_distance: int | None


def iter_media(base: Path, extensions: set[str] = ALL_MEDIA_EXTS) -> Iterable[Path]:
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d != "@eaDir"]
        for name in files:
            path = Path(root) / name
            if path.suffix.lower() in extensions and name != ".DS_Store":
                yield path


def parse_exif_time(path: Path) -> dt.datetime | None:
    if path.suffix.lower() not in IMAGE_EXTS:
        return None
    try:
        with Image.open(path) as image:
            exif = image.getexif()
            for tag in (DATE_TAGS["DateTimeOriginal"], DATE_TAGS["DateTimeDigitized"], DATE_TAGS["DateTime"]):
                value = exif.get(tag)
                if not value:
                    continue
                text = value.decode(errors="ignore") if isinstance(value, bytes) else str(value)
                for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
                    try:
                        parsed = dt.datetime.strptime(text[:19], fmt)
                        if 2000 <= parsed.year <= 2026:
                            return parsed
                    except ValueError:
                        pass
    except Exception:
        return None
    return None


def parse_filename_time(name: str) -> dt.datetime | None:
    match = TS13_RE.search(name)
    if match:
        try:
            return dt.datetime.fromtimestamp(int(match.group("ts")) / 1000)
        except (OverflowError, OSError, ValueError):
            pass
    match = IMG_RE.search(name)
    if match:
        try:
            return dt.datetime.strptime(match.group("date") + match.group("time"), "%Y%m%d%H%M%S")
        except ValueError:
            pass
    return None


def event_date(path: Path, library_root: Path) -> dt.datetime | None:
    try:
        event = path.relative_to(library_root).parts[0]
    except ValueError:
        return None
    match = EVENT_RE.match(event)
    if not match:
        return None
    try:
        return dt.datetime.strptime(match.group("date"), "%y%m%d")
    except ValueError:
        return None


def stable_random_time(month: dt.datetime, key: str) -> dt.datetime:
    """Generate a deterministic, non-uniform-looking daytime within a month."""
    seed = int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest()[:8], "big")
    rng = random.Random(seed)
    last_day = calendar.monthrange(month.year, month.month)[1]
    day = rng.randint(1, last_day)
    # Most personal photos are taken during waking hours, with occasional late shots.
    hour = rng.choices(range(7, 24), weights=[1, 2, 4, 6, 7, 8, 8, 8, 8, 8, 7, 7, 7, 6, 5, 4, 2])[0]
    return dt.datetime(month.year, month.month, day, hour, rng.randint(0, 59), rng.randint(0, 59))


def dct_matrix(size: int) -> np.ndarray:
    matrix = np.empty((size, size), dtype=np.float32)
    factor = math.pi / (2 * size)
    for k in range(size):
        scale = math.sqrt(1 / size) if k == 0 else math.sqrt(2 / size)
        for n in range(size):
            matrix[k, n] = scale * math.cos((2 * n + 1) * k * factor)
    return matrix


DCT32 = dct_matrix(32)


def visual_hash(path: Path) -> int | None:
    try:
        with Image.open(path) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            # Letterbox instead of stretching, preserving a useful aspect cue.
            canvas = Image.new("RGB", (32, 32), "white")
            thumb = ImageOps.contain(image, (32, 32), Image.Resampling.LANCZOS)
            canvas.paste(thumb, ((32 - thumb.width) // 2, (32 - thumb.height) // 2))
            pixels = np.asarray(canvas.convert("L"), dtype=np.float32)
            coeff = DCT32 @ pixels @ DCT32.T
            low = coeff[:8, :8].flatten()
            median = float(np.median(low[1:]))
            bits = low > median
            value = 0
            for bit in bits:
                value = (value << 1) | int(bit)
            return value
    except Exception:
        return None


def sha256(path: Path) -> str | None:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def event_name(path: Path, library_root: Path) -> str:
    return path.relative_to(library_root).parts[0]


def category(path: Path) -> str:
    name = path.name.lower()
    if name.startswith("wx_camera"):
        return "wx_camera"
    if name.startswith("mmexport"):
        return "mmexport"
    if name.startswith(("micromsg", "mmqrcode")):
        return "wechat_aux"
    if IMG_RE.search(path.name):
        return "img_datetime"
    return "other"


def build_contact_sheet(items: list[tuple[Path, list[tuple[int, Path]]]], output: Path) -> None:
    if not items:
        return
    cell_w, cell_h = 260, 225
    cols = 4
    rows = len(items)
    sheet = Image.new("RGB", (cols * cell_w, rows * cell_h), "#202124")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()

    def place(path: Path, x: int, y: int, title: str) -> None:
        try:
            with Image.open(path) as image:
                image = ImageOps.exif_transpose(image).convert("RGB")
                thumb = ImageOps.contain(image, (cell_w - 12, cell_h - 45), Image.Resampling.LANCZOS)
                sheet.paste(thumb, (x + (cell_w - thumb.width) // 2, y + 5))
        except Exception:
            draw.rectangle((x + 5, y + 5, x + cell_w - 5, y + cell_h - 45), outline="red")
        draw.text((x + 5, y + cell_h - 36), title[:42], fill="white", font=font)

    for row, (target, candidates) in enumerate(items):
        place(target, 0, row * cell_h, "TARGET: " + target.name)
        for col, (distance, candidate) in enumerate(candidates[:3], start=1):
            place(candidate, col * cell_w, row * cell_h, f"d={distance} {candidate.parent.parent.name}/{candidate.name}")
    sheet.save(output, quality=92)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--library", type=Path, default=Path("/Volumes/photo"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    library = args.library.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    target_dirs = sorted(library.glob("220101_*"))
    if len(target_dirs) != 1:
        raise SystemExit(f"Expected one 220101_* target, found {len(target_dirs)}")
    target = target_dirs[0]
    target_media = sorted(iter_media(target))
    target_images = [p for p in target_media if p.suffix.lower() in IMAGE_EXTS]

    source_events = sorted(
        p for p in library.iterdir() if p.is_dir() and EVENT_RE.match(p.name) and p != target
    )
    source_images = [p for event in source_events for p in iter_media(event, IMAGE_EXTS)]

    print(f"target_media={len(target_media)} source_images={len(source_images)}", flush=True)

    # Hash only candidate files with a size seen in the target.
    target_sizes = {p.stat().st_size for p in target_media}
    target_sha: dict[tuple[int, str], list[Path]] = defaultdict(list)
    for index, path in enumerate(target_media, 1):
        digest = sha256(path)
        if digest:
            target_sha[(path.stat().st_size, digest)].append(path)
        if index % 100 == 0:
            print(f"target_sha={index}/{len(target_media)}", flush=True)

    exact_matches: dict[Path, list[Path]] = defaultdict(list)
    for path in source_images:
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size not in target_sizes:
            continue
        digest = sha256(path)
        if not digest:
            continue
        for target_path in target_sha.get((size, digest), []):
            exact_matches[target_path].append(path)

    source_features: list[tuple[Path, int]] = []
    for index, path in enumerate(source_images, 1):
        value = visual_hash(path)
        if value is not None:
            source_features.append((path, value))
        if index % 250 == 0:
            print(f"source_features={index}/{len(source_images)}", flush=True)

    target_features = {path: visual_hash(path) for path in target_images}
    nearest: dict[Path, list[tuple[int, Path]]] = {}
    for path, value in target_features.items():
        if value is None:
            nearest[path] = []
            continue
        ranked = sorted(((value ^ other).bit_count(), candidate) for candidate, other in source_features)
        nearest[path] = ranked[:5]

    proposals: list[Proposal] = []
    uncertain_sheet_items: list[tuple[Path, list[tuple[int, Path]]]] = []

    for path in target_media:
        rel = path.relative_to(target).as_posix()
        ext = path.suffix.lower()
        kind = "video" if ext in VIDEO_EXTS else "photo"
        filename_dt = parse_filename_time(path.name)
        exif_dt = parse_exif_time(path) if kind == "photo" else None
        cat = category(path)
        matches = exact_matches.get(path, [])
        match_events = sorted({event_name(candidate, library) for candidate in matches})
        match_months = {
            event_date(candidate, library).strftime("%Y-%m")
            for candidate in matches
            if event_date(candidate, library)
        }

        ranked = nearest.get(path, []) if kind == "photo" else []
        nearest_event = event_name(ranked[0][1], library) if ranked else None
        nearest_distance = ranked[0][0] if ranked else None
        nearest_months = []
        for distance, candidate in ranked[:3]:
            date = event_date(candidate, library)
            if date and distance <= 12:
                nearest_months.append(date.strftime("%Y-%m"))

        proposed: dt.datetime | None = None
        month: dt.datetime | None = None
        confidence = "low"
        action = "modify"
        reason = ""

        # Existing capture metadata is always the strongest source.
        if exif_dt:
            proposed = exif_dt
            month = exif_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            confidence = "high"
            reason = "preserve existing valid EXIF capture time; synchronize filesystem time"
        elif matches and len(match_months) == 1:
            # Exact bytes in a dated event are a strong cross-folder anchor.  Prefer
            # an explicit source filename time when it falls in the same month.
            source_times = [parse_exif_time(p) or parse_filename_time(p.name) for p in matches]
            source_times = [value for value in source_times if value]
            anchor = source_times[0] if source_times else event_date(matches[0], library)
            if anchor:
                proposed = anchor
                month = anchor.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                confidence = "high"
                reason = "byte-identical copy found in one unambiguous dated event"
        elif cat in {"wx_camera", "wechat_aux"} and filename_dt and ext not in {".png"}:
            proposed = filename_dt.replace(microsecond=0)
            month = proposed.replace(day=1, hour=0, minute=0, second=0)
            confidence = "high"
            reason = "WeChat camera/cache filename contains a plausible Unix-millisecond capture time"
        elif cat == "img_datetime" and filename_dt and ext not in {".png"}:
            proposed = filename_dt
            month = proposed.replace(day=1, hour=0, minute=0, second=0)
            confidence = "high"
            reason = "IMG_YYYYMMDD_HHMMSS filename provides an explicit capture time"
        else:
            # Low-confidence media (mmexport, PNG/screenshots, and generic names):
            # infer only a month, then generate a deterministic varied time.
            visual_vote = Counter(nearest_months)
            if visual_vote and visual_vote.most_common(1)[0][1] >= 2:
                y, m = map(int, visual_vote.most_common(1)[0][0].split("-"))
                month = dt.datetime(y, m, 1)
                reason = "month inferred from multiple visually similar photos in 2022 events"
            elif filename_dt:
                month = filename_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                reason = "month inferred from export/cache filename; day and time intentionally varied"
            elif ranked and ranked[0][0] <= 10:
                anchor = event_date(ranked[0][1], library)
                if anchor:
                    month = anchor.replace(day=1, hour=0, minute=0, second=0)
                    reason = "month inferred from one close visual match in a dated 2022 event"
            if month is None:
                # The user supplied January 2022 as the broad prior for otherwise
                # unplaceable cloud-memory items.
                month = dt.datetime(2022, 1, 1)
                reason = "no reliable duplicate or visual match; used album-level January 2022 prior"
                confidence = "very-low"
            else:
                confidence = "medium" if (visual_vote or filename_dt) else "low"
            proposed = stable_random_time(month, rel)

        # Exact matches spanning multiple dated events are ambiguous unless an
        # independent EXIF value already resolved them.
        if len(match_months) > 1 and not exif_dt:
            if filename_dt:
                month = filename_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                proposed = stable_random_time(month, rel + "|conflict")
                confidence = "low"
                reason = "duplicate appears in multiple event months; used filename month and randomized time"
            else:
                action = "review"
                proposed = None
                confidence = "very-low"
                reason = "duplicate appears in multiple event months and has no independent time clue"

        if kind == "photo" and confidence in {"low", "very-low"}:
            uncertain_sheet_items.append((path, ranked[:3]))

        proposals.append(
            Proposal(
                relative_path=rel,
                media_type=kind,
                extension=ext,
                current_mtime=dt.datetime.fromtimestamp(path.stat().st_mtime).isoformat(sep=" ", timespec="seconds"),
                filename_time=filename_dt.isoformat(sep=" ", timespec="seconds") if filename_dt else None,
                exif_time=exif_dt.isoformat(sep=" ", timespec="seconds") if exif_dt else None,
                proposed_time=proposed.isoformat(sep=" ", timespec="seconds") if proposed else None,
                proposed_month=proposed.strftime("%Y-%m") if proposed else None,
                confidence=confidence,
                action=action,
                reason=reason,
                exact_match_events=" | ".join(match_events),
                nearest_visual_event=nearest_event,
                nearest_visual_distance=nearest_distance,
            )
        )

    csv_path = output / "proposals.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(proposals[0]).keys()))
        writer.writeheader()
        writer.writerows(asdict(item) for item in proposals)

    summary = {
        "library": str(library),
        "target": str(target),
        "target_media": len(target_media),
        "source_2022_images": len(source_images),
        "counts_by_confidence": dict(Counter(item.confidence for item in proposals)),
        "counts_by_action": dict(Counter(item.action for item in proposals)),
        "counts_by_month": dict(sorted(Counter(item.proposed_month for item in proposals if item.proposed_month).items())),
        "exact_match_targets": len(exact_matches),
        "generated_at": dt.datetime.now().isoformat(sep=" ", timespec="seconds"),
    }
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    build_contact_sheet(uncertain_sheet_items, output / "uncertain_contact_sheet.jpg")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
