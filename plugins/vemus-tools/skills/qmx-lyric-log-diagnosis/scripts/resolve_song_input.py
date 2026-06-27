#!/usr/bin/env python3
"""Resolve QMX/Vemus song diagnosis input into traceID, mixsongid, or short link."""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


URL_RE = re.compile(r"https?://[^\s，。、！？）》\]]+")
TRACE_RE = re.compile(r"\btraceID\b\s*[:= ]\s*[\"']?([A-Za-z0-9._:-]+)[\"']?", re.I)
MIXSONGID_RE = re.compile(r"\bmixsongid\b\s*(?:=|:|%3D|%3d)\s*(\d+)", re.I)


def read_input(args: argparse.Namespace) -> str:
    parts: list[str] = []
    if args.text:
        parts.append(args.text)
    if args.file:
        parts.append(Path(args.file).read_text(encoding="utf-8"))
    if not parts and not sys.stdin.isatty():
        parts.append(sys.stdin.read())
    return "\n".join(parts)


def find_mixsongid(text: str) -> tuple[str | None, str | None]:
    direct_number = text.strip()
    if direct_number.isdigit() and len(direct_number) >= 6:
        return direct_number, "direct_number"

    for source_name, candidate in (
        ("raw", text),
        ("url_decoded", urllib.parse.unquote(text)),
    ):
        match = MIXSONGID_RE.search(candidate)
        if match:
            return match.group(1), source_name
    return None, None


def find_trace_id(text: str) -> str | None:
    match = TRACE_RE.search(text)
    return match.group(1) if match else None


def find_url(text: str) -> str | None:
    match = URL_RE.search(text)
    if not match:
        return None
    return match.group(0).rstrip("，。！？）》]")


def fetch_short_link(url: str, timeout: float) -> dict[str, Any]:
    endpoint = "https://vemus-asset.tmeoa.com/v1/qmx_user_song/public/get_short_link_info"
    body = json.dumps({"short_link": url}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = resp.read().decode("utf-8", errors="replace")
    data = json.loads(payload)
    mixsongid = (
        data.get("data", {})
        .get("song_info", {})
        .get("mixsongid")
    )
    return {
        "endpoint": endpoint,
        "raw_response": data,
        "mixsongid": str(mixsongid) if mixsongid else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text", help="Raw user text, share text, URL, mixsongid, or traceID.")
    parser.add_argument("--file", help="Read input from a UTF-8 text file.")
    parser.add_argument("--fetch-short-link", action="store_true", help="Call get_short_link_info for extracted URL.")
    parser.add_argument("--timeout", type=float, default=10.0, help="Short-link API timeout in seconds.")
    args = parser.parse_args()

    text = read_input(args)
    result: dict[str, Any] = {
        "input_length": len(text),
        "trace_id": find_trace_id(text),
        "mixsongid": None,
        "mixsongid_source": None,
        "url": find_url(text),
        "short_link_fetch": None,
        "needs": [],
    }

    mixsongid, source = find_mixsongid(text)
    if mixsongid:
        result["mixsongid"] = mixsongid
        result["mixsongid_source"] = source
    elif result["url"] and args.fetch_short_link:
        try:
            fetch_result = fetch_short_link(result["url"], args.timeout)
            result["short_link_fetch"] = {
                "endpoint": fetch_result["endpoint"],
                "ok": bool(fetch_result["mixsongid"]),
                "error": None,
            }
            result["mixsongid"] = fetch_result["mixsongid"]
            result["mixsongid_source"] = "short_link_api" if fetch_result["mixsongid"] else None
        except Exception as exc:  # noqa: BLE001 - report operational failure as JSON
            result["short_link_fetch"] = {
                "ok": False,
                "error": str(exc),
            }

    if not result["trace_id"] and not result["mixsongid"]:
        if result["url"]:
            result["needs"].append("resolve short link to mixsongid")
        else:
            result["needs"].append("provide mixsongid, traceID, or Vemus share link")
    if result["mixsongid"] and not result["trace_id"]:
        result["needs"].append("provide approximate time range for narrower online log search")

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
