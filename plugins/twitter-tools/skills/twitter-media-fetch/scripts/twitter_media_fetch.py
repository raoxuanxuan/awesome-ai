#!/usr/bin/env python3
"""
Download media referenced by normalized twitter-fetch JSON.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
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


def detect_extension(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)
    if "format" in query and query["format"]:
        ext = "." + query["format"][0].lower().lstrip(".")
        if ext in KNOWN_EXTENSIONS:
            return ext

    _, ext = os.path.splitext(parsed.path)
    ext = ext.lower()
    if ext in KNOWN_EXTENSIONS:
        return ext
    return DEFAULT_EXT


def is_media_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme in {"file", "http", "https"}:
        return True
    return False


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

    for key in ("url", "media_url_https", "media_url", "source_url"):
        value = node.get(key)
        if isinstance(value, str) and is_media_url(value):
            yield value

    for key in ("images", "photos", "media", "variants"):
        if key in node:
            yield from extract_urls_from_media_node(node[key])


def iter_items(payload: dict[str, Any]) -> Iterable[dict[str, Any]]:
    for item in payload.get("items") or []:
        if isinstance(item, dict):
            yield item


def collect_media_urls(payload: dict[str, Any]) -> list[str]:
    urls: list[str] = []

    def add_from_item(item: dict[str, Any]) -> None:
        article = item.get("article")
        if isinstance(article, dict):
            urls.extend(extract_urls_from_media_node(article.get("images")))
            urls.extend(extract_urls_from_media_node(article.get("media")))

        urls.extend(extract_urls_from_media_node(item.get("media")))

        thread = item.get("thread")
        if isinstance(thread, dict):
            for thread_item in thread.get("items") or []:
                if isinstance(thread_item, dict):
                    add_from_item(thread_item)

        quote = item.get("quote")
        if isinstance(quote, dict):
            add_from_item(quote)

    for item in iter_items(payload):
        add_from_item(item)

    seen = set()
    unique_urls = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)
    return unique_urls


def read_input(path: str) -> dict[str, Any]:
    if path == "-":
        raw = sys.stdin.read()
    else:
        raw = Path(path).read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("input must be a twitter-fetch JSON envelope object")
    return data


def download_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.read()


def media_type_for_extension(ext: str) -> str:
    if ext in {".mp4", ".mov"}:
        return "video"
    return "image"


def download_media(urls: list[str], output_dir: Path, prefix: str) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    downloaded = []
    failed = []

    for index, url in enumerate(urls):
        ext = detect_extension(url)
        if index == 0:
            filename = f"{prefix}-cover{ext}"
        else:
            filename = f"{prefix}-img{index:02d}{ext}"
        path = output_dir / filename

        try:
            if path.exists():
                data = path.read_bytes()
                downloaded.append(
                    {
                        "source_url": url,
                        "filename": filename,
                        "path": str(path),
                        "media_type": media_type_for_extension(ext),
                        "bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                        "skipped": True,
                    }
                )
                continue

            data = download_bytes(url)
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

    return {
        "ok": not failed,
        "downloaded": downloaded,
        "failed": failed,
        "count": len(downloaded),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download media from twitter-fetch JSON")
    subparsers = parser.add_subparsers(dest="command", required=True)

    download = subparsers.add_parser("download", help="Download media and print a JSON manifest")
    source = download.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", help="Path to twitter-fetch JSON envelope, or '-' for stdin")
    source.add_argument("--urls", nargs="+", help="Explicit media URLs to download")
    download.add_argument("--output-dir", required=True, help="Directory for downloaded media")
    download.add_argument("--prefix", required=True, help="Filename prefix")
    download.add_argument("--pretty", action="store_true", help="Pretty-print manifest JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.input:
            urls = collect_media_urls(read_input(args.input))
        else:
            urls = list(args.urls)

        manifest = download_media(urls, Path(args.output_dir), args.prefix)
    except Exception as exc:
        manifest = {
            "ok": False,
            "downloaded": [],
            "failed": [{"error": str(exc)}],
            "count": 0,
        }
        print(json.dumps(manifest, ensure_ascii=False, indent=2 if args.pretty else None))
        return 1

    print(json.dumps(manifest, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0 if manifest["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
