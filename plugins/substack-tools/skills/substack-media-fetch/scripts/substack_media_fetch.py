#!/usr/bin/env python3
"""
Download media referenced by substack-fetch normalized content JSON.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable


KNOWN_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".mp4", ".mov"}
DEFAULT_EXT = ".jpg"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
TIMEOUT = 30


def is_media_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    return parsed.scheme in {"file", "http", "https"}


def canonical_media_key(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if "substackcdn.com" not in parsed.netloc or "/image/fetch/" not in parsed.path:
        return url
    marker = "/https%3A%2F%2F"
    if marker not in parsed.path:
        return url
    encoded = "https%3A%2F%2F" + parsed.path.rsplit(marker, 1)[-1]
    return urllib.parse.unquote(encoded)


def read_input(path: str) -> dict[str, Any]:
    raw = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("input must be a substack-fetch content JSON object")
    if "content" in data and isinstance(data["content"], dict):
        return data["content"]
    return data


def extract_urls_from_media_node(node: Any) -> Iterable[str]:
    if node is None:
        return
    if isinstance(node, str):
        if is_media_url(node):
            yield node
        return
    if isinstance(node, list):
        for item in node:
            yield from extract_urls_from_media_node(item)
        return
    if not isinstance(node, dict):
        return

    for key in ("source_url", "url", "src", "href"):
        value = node.get(key)
        if isinstance(value, str) and is_media_url(value):
            yield value

    for key in ("media", "images", "items"):
        if key in node:
            yield from extract_urls_from_media_node(node[key])


def collect_media_urls(payload: dict[str, Any]) -> list[str]:
    urls = list(extract_urls_from_media_node(payload.get("media")))
    seen = set()
    unique_urls = []
    for url in urls:
        key = canonical_media_key(url)
        if key not in seen:
            seen.add(key)
            unique_urls.append(url)
    return unique_urls


def extension_from_headers(headers: Any) -> str | None:
    content_type = headers.get("content-type") if hasattr(headers, "get") else None
    if not content_type:
        return None
    content_type = content_type.split(";", 1)[0].strip().lower()
    ext = mimetypes.guess_extension(content_type)
    if ext == ".jpe":
        return ".jpg"
    if ext in KNOWN_EXTENSIONS:
        return ext
    return None


def detect_extension(url: str, headers: Any | None = None) -> str:
    if headers is not None:
        ext = extension_from_headers(headers)
        if ext:
            return ext

    parsed = urllib.parse.urlparse(url)
    _, ext = os.path.splitext(urllib.parse.unquote(parsed.path))
    ext = ext.lower()
    if ext in KNOWN_EXTENSIONS:
        return ext
    return DEFAULT_EXT


def download_bytes(url: str) -> tuple[bytes, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.read(), response.headers


def media_type_for_extension(ext: str) -> str:
    if ext in {".mp4", ".mov"}:
        return "video"
    return "image"


def filename_for_index(prefix: str, index: int, ext: str) -> str:
    if index == 0:
        return f"{prefix}-cover{ext}"
    return f"{prefix}-img{index:02d}{ext}"


def download_media(urls: list[str], output_dir: Path, prefix: str) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    downloaded = []
    failed = []

    for index, url in enumerate(urls):
        try:
            data, headers = download_bytes(url)
            ext = detect_extension(url, headers)
            filename = filename_for_index(prefix, index, ext)
            path = output_dir / filename

            if path.exists():
                existing = path.read_bytes()
                downloaded.append(
                    {
                        "source_url": url,
                        "filename": filename,
                        "path": str(path),
                        "media_type": media_type_for_extension(ext),
                        "bytes": len(existing),
                        "sha256": hashlib.sha256(existing).hexdigest(),
                        "skipped": True,
                    }
                )
                continue

            path.write_bytes(data)
            downloaded.append(
                {
                    "source_url": url,
                    "filename": filename,
                    "path": str(path),
                    "media_type": media_type_for_extension(ext),
                    "bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
            )
        except Exception as exc:
            failed.append({"source_url": url, "error": str(exc)})

    return {"ok": not failed, "downloaded": downloaded, "failed": failed, "count": len(downloaded)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download media from substack-fetch JSON")
    subparsers = parser.add_subparsers(dest="command", required=True)

    download = subparsers.add_parser("download", help="Download media and print a JSON manifest")
    source = download.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", help="Path to substack-fetch content JSON, or '-' for stdin")
    source.add_argument("--urls", nargs="+", help="Explicit media URLs to download")
    download.add_argument("--output-dir", required=True, help="Directory for downloaded media")
    download.add_argument("--prefix", required=True, help="Filename prefix")
    download.add_argument("--pretty", action="store_true", help="Pretty-print manifest JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        urls = collect_media_urls(read_input(args.input)) if args.input else list(args.urls)
        manifest = download_media(urls, Path(args.output_dir), args.prefix)
    except Exception as exc:
        manifest = {"ok": False, "downloaded": [], "failed": [{"error": str(exc)}], "count": 0}
        print(json.dumps(manifest, ensure_ascii=False, indent=2 if args.pretty else None))
        return 1

    print(json.dumps(manifest, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0 if manifest["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
