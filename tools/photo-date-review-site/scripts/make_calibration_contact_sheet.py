#!/usr/bin/env python3
"""Create labeled contact sheets from calibration thumbnail relative paths."""

from __future__ import annotations

import argparse
import json
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "public/calibration/calibration-items.json"
THUMBS = ROOT / "public/calibration/thumbs"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output")
    parser.add_argument("paths", nargs="*")
    parser.add_argument("--folder")
    args = parser.parse_args()

    data = json.loads(MANIFEST.read_text())
    by_rel = {x["relativePath"]: x for x in data["items"]}
    cells = []
    selected_paths = list(args.paths)
    if args.folder:
        selected_paths.extend(
            x["relativePath"] for x in data["items"]
            if x["currentFolder"] == args.folder
        )
    for rel in selected_paths:
        item = by_rel.get(rel)
        if item:
            cells.append((item, THUMBS / f'{item["id"]}.jpg'))

    cols, cw, ch = 4, 360, 340
    rows = (len(cells) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cw, rows * ch), "white")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=14)
    for idx, (item, path) in enumerate(cells):
        x, y = (idx % cols) * cw, (idx // cols) * ch
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            fitted = ImageOps.contain(im, (cw - 16, 250), Image.Resampling.LANCZOS)
        sheet.paste(fitted, (x + (cw - fitted.width) // 2, y + 4))
        label = f'{idx + 1}. {item["filename"]}\n{item.get("captureDate", "")}'
        lines = []
        for line in label.splitlines():
            lines.extend(textwrap.wrap(line, width=39) or [""])
        draw.multiline_text((x + 8, y + 260), "\n".join(lines[:4]), fill="black", font=font, spacing=2)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=92)
    print(out)


if __name__ == "__main__":
    main()
