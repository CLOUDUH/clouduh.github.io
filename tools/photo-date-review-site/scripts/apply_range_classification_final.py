#!/usr/bin/env python3
"""Apply all folder classifications from photo-range-review (1).json."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path


NAS = Path("/Volumes/photo")
ROOT = Path(__file__).resolve().parents[1]
INPUT = Path("/Users/cloudu/Downloads/photo-range-review (1).json")
MANIFEST = ROOT / "public/range-review/review-items.json"
EXIFTOOL = "/opt/homebrew/bin/exiftool"
RUN = "range-classification-final-20260902"
LOG = NAS / "170900_备份/_operation_logs" / RUN


def unique(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(1, 10_000):
        candidate = path.with_name(f"{path.stem}_{index}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"No unique destination for {path}")


def parse(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value[:19]
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    return None


def set_from_dto(paths: list[Path]) -> None:
    for start in range(0, len(paths), 400):
        chunk = paths[start:start + 400]
        result = subprocess.run([EXIFTOOL, "-overwrite_original_in_place",
                                 "-FileCreateDate<DateTimeOriginal", "-FileModifyDate<DateTimeOriginal",
                                 *map(str, chunk)], text=True, capture_output=True)
        if result.returncode:
            raise RuntimeError(result.stderr or result.stdout)


def set_explicit(path: Path, value: datetime) -> None:
    stamp = value.strftime("%Y:%m:%d %H:%M:%S+08:00")
    result = subprocess.run([EXIFTOOL, "-overwrite_original_in_place",
                             f"-FileCreateDate={stamp}", f"-FileModifyDate={stamp}", str(path)],
                            text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr or result.stdout)


def main() -> None:
    exported = json.loads(INPUT.read_text())
    manifest = json.loads(MANIFEST.read_text())
    move_rows = [row for row in exported["reviews"]
                 if row.get("targetFolder") and row["targetFolder"] != row["currentFolder"]]
    missing = [row["relativePath"] for row in move_rows if not (NAS / row["relativePath"]).exists()]
    if missing:
        raise SystemExit(json.dumps({"missing": missing}, ensure_ascii=False, indent=2))

    LOG.mkdir(parents=True, exist_ok=False)
    # Capture original filesystem and embedded dates before the SMB moves.
    metadata = {}
    for start in range(0, len(move_rows), 500):
        chunk = [str(NAS / row["relativePath"]) for row in move_rows[start:start + 500]]
        result = subprocess.run([EXIFTOOL, "-j", "-DateTimeOriginal", "-FileCreateDate", "-FileModifyDate", *chunk],
                                text=True, capture_output=True, check=True)
        for item in json.loads(result.stdout):
            metadata[str(Path(item["SourceFile"]).relative_to(NAS))] = item
    (LOG / "plan.json").write_text(json.dumps({"moves": move_rows, "metadataBefore": metadata}, ensure_ascii=False, indent=2))

    manifest_by_id = {item["id"]: item for item in manifest["items"]}
    journal = []
    for index, row in enumerate(move_rows, start=1):
        source = NAS / row["relativePath"]
        target_dir = NAS / row["targetFolder"] / "photo"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = unique(target_dir / source.name)
        source.rename(target)
        before = metadata[row["relativePath"]]
        dto = parse(before.get("DateTimeOriginal"))
        fallback = parse(row.get("currentCapture"))
        expected = dto or fallback
        record = {
            "id": row["id"],
            "source": row["relativePath"],
            "target": str(target.relative_to(NAS)),
            "targetFolder": row["targetFolder"],
            "dateBasis": "DateTimeOriginal" if dto else "exported currentCapture",
            "expectedFileTime": expected.strftime("%Y-%m-%d %H:%M:%S") if expected else "",
        }
        journal.append(record)
        item = manifest_by_id.get(row["id"])
        if item:
            item["relativePath"] = record["target"]
            item["filename"] = target.name
            item["currentFolder"] = row["targetFolder"]
        if index % 100 == 0:
            print(f"PROGRESS move {index}/{len(move_rows)}", flush=True)

    dto_paths, fallback_rows = [], []
    for record in journal:
        if record["dateBasis"] == "DateTimeOriginal":
            dto_paths.append(NAS / record["target"])
        elif record["expectedFileTime"]:
            fallback_rows.append(record)
    set_from_dto(dto_paths)
    for record in fallback_rows:
        set_explicit(NAS / record["target"], parse(record["expectedFileTime"]))

    # Read back all destination paths and confirm both existence and timestamps.
    errors = []
    values = {}
    targets = [NAS / record["target"] for record in journal]
    for start in range(0, len(targets), 500):
        chunk = targets[start:start + 500]
        result = subprocess.run([EXIFTOOL, "-j", "-FileCreateDate", "-FileModifyDate", *map(str, chunk)],
                                text=True, capture_output=True, check=True)
        for item in json.loads(result.stdout):
            values[str(Path(item["SourceFile"]).relative_to(NAS))] = item
    for record in journal:
        actual = values.get(record["target"])
        if not actual:
            errors.append({"path": record["target"], "error": "destination missing"})
            continue
        expected = record["expectedFileTime"]
        if expected:
            for tag in ("FileCreateDate", "FileModifyDate"):
                got = actual.get(tag, "")[:19].replace(":", "-", 2)
                if got != expected:
                    errors.append({"path": record["target"], "tag": tag, "expected": expected, "actual": got})

    manifest["generatedAt"] = datetime.now().astimezone().isoformat()
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    (LOG / "journal.json").write_text(json.dumps(journal, ensure_ascii=False, indent=2))
    report = {
        "requestedReviews": len(exported["reviews"]),
        "moved": len(journal),
        "keptInCurrentFolder": len(exported["reviews"]) - len(journal),
        "nameCollisionsSafelySuffixed": sum(Path(row["source"]).name != Path(row["target"]).name for row in journal),
        "errors": errors,
        "status": "ok" if not errors else "failed",
    }
    (LOG / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
