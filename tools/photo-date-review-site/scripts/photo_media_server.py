#!/usr/bin/env python3
"""Read-only, no-disk-cache photo preview server for the mounted NAS."""

from __future__ import annotations

import io
import json
import subprocess
import tempfile
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from PIL import Image, ImageOps


NAS = Path("/Volumes/photo").resolve()
HUB = Path("/Users/cloudu/Hub").resolve()
FATCLOUD = Path("/Volumes/FATCLOUD").resolve()
ALLOWED = {".jpg", ".jpeg", ".png", ".heic", ".gif", ".webp", ".tif", ".tiff", ".avif", ".cr2", ".cr3", ".nef", ".arw", ".dng", ".raf", ".orf", ".rw2"}


def safe_path(root: Path, relative: str) -> Path:
    target = (root / relative).resolve()
    if root not in target.parents or target.suffix.lower() not in ALLOWED or not target.is_file():
        raise FileNotFoundError(relative)
    if "#recycle" in target.parts or "170900_备份" in target.parts:
        raise FileNotFoundError(relative)
    return target


@lru_cache(maxsize=96)
def render_jpeg(path_text: str, modified_ns: int, size: int) -> bytes:
    path = Path(path_text)
    try:
        with Image.open(path) as image:
            image = ImageOps.exif_transpose(image)
            if getattr(image, "is_animated", False):
                image.seek(0)
            image = image.convert("RGB")
            image.thumbnail((size, size), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            image.save(output, "JPEG", quality=82, optimize=True)
            return output.getvalue()
    except Exception:
        with tempfile.NamedTemporaryFile(prefix="codex-photo-preview-", suffix=".jpg", delete=False) as handle:
            temporary = Path(handle.name)
        try:
            result = subprocess.run(["/usr/bin/sips", "-Z", str(size), "-s", "format", "jpeg",
                                     str(path), "--out", str(temporary)], capture_output=True)
            if result.returncode != 0:
                raise ValueError(result.stderr.decode("utf-8", "replace"))
            return temporary.read_bytes()
        finally:
            temporary.unlink(missing_ok=True)


class Handler(BaseHTTPRequestHandler):
    server_version = "PhotoPreview/1.0"

    def send_headers(self, status: int, content_type: str, length: int) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            payload = json.dumps({"status": "ok", "nas": str(NAS), "hub": str(HUB), "fatcloud": str(FATCLOUD)}).encode()
            self.send_headers(200, "application/json", len(payload))
            self.wfile.write(payload)
            return
        if parsed.path.startswith("/media/"):
            root = NAS
            relative = unquote(parsed.path[len("/media/"):])
        elif parsed.path.startswith("/hub-media/"):
            root = HUB
            relative = unquote(parsed.path[len("/hub-media/"):])
        elif parsed.path.startswith("/fat-media/"):
            root = FATCLOUD
            relative = unquote(parsed.path[len("/fat-media/"):])
        else:
            self.send_error(404)
            return
        try:
            source = safe_path(root, relative)
            requested = int(parse_qs(parsed.query).get("size", ["1600"])[0])
            size = max(160, min(2400, requested))
            stat = source.stat()
            payload = render_jpeg(str(source), stat.st_mtime_ns, size)
            self.send_headers(200, "image/jpeg", len(payload))
            self.wfile.write(payload)
        except (FileNotFoundError, ValueError, OSError):
            self.send_error(404)

    def log_message(self, format: str, *args) -> None:
        return


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 3002), Handler)
    print("Photo preview server: http://127.0.0.1:3002", flush=True)
    server.serve_forever()
