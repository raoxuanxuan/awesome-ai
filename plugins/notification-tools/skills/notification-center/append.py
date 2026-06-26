#!/usr/bin/env python3
"""Append notification events to the local notification center queue."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


CST = timezone(timedelta(hours=8))
VALID_LEVELS = {"critical", "alert", "info"}
DEFAULT_RUNTIME = Path.home() / "vault" / ".notification-center"


def runtime_dir(env: dict[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    override = env.get("NOTIFICATION_CENTER_RUNTIME")
    if override:
        return Path(override).expanduser()
    return DEFAULT_RUNTIME


def now_cst() -> datetime:
    return datetime.now(CST)


def day_path(runtime: Path, now: datetime | None = None) -> Path:
    now = now or now_cst()
    return runtime / f"{now.strftime('%Y-%m-%d')}.jsonl"


def stable_id(source: str, dedupe_key: str, day: str) -> str:
    return hashlib.sha1(f"{source}|{dedupe_key}|{day}".encode("utf-8")).hexdigest()[:16]


def parse_link(value: str) -> dict[str, str]:
    if "=" in value:
        label, url = value.split("=", 1)
        return {"label": label.strip() or "link", "url": url.strip()}
    url = value.strip()
    return {"label": url or "link", "url": url}


def normalize_links(raw: Any) -> list[dict[str, str]]:
    if not raw:
        return []
    links: list[dict[str, str]] = []
    for item in raw:
        if isinstance(item, str):
            link = parse_link(item)
        elif isinstance(item, dict):
            link = {
                "label": str(item.get("label") or "link"),
                "url": str(item.get("url") or ""),
            }
        else:
            continue
        if link["url"]:
            links.append(link)
    return links


def build_entry(data: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    now = now or now_cst()
    day = now.strftime("%Y-%m-%d")
    source = str(data.get("source") or "").strip()
    if not source:
        raise ValueError("source required")
    level = str(data.get("level") or "info").strip()
    if level not in VALID_LEVELS:
        raise ValueError(f"level must be one of {sorted(VALID_LEVELS)}")
    title = str(data.get("title") or "").strip()
    if not title:
        raise ValueError("title required")
    dedupe_key = str(data.get("dedupe_key") or title).strip()
    entry_id = str(data.get("id") or stable_id(source, dedupe_key, day))
    return {
        "schema_version": 1,
        "id": entry_id,
        "dedupe_key": dedupe_key,
        "ts": now.isoformat(timespec="seconds"),
        "source": source,
        "level": level,
        "title": title[:160],
        "summary": str(data.get("summary") or ""),
        "links": normalize_links(data.get("links") or data.get("urls")),
        "paths": [str(path) for path in data.get("paths") or []],
        "meta": data.get("meta") if isinstance(data.get("meta"), dict) else {},
        "targets": list(data.get("targets") or ["feishu"]),
    }


def append_entry(runtime: Path, entry: dict[str, Any]) -> bool:
    runtime.mkdir(parents=True, exist_ok=True)
    path = day_path(runtime, datetime.fromisoformat(entry["ts"]))
    if path.exists():
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    if json.loads(line).get("id") == entry["id"]:
                        return False
                except json.JSONDecodeError:
                    continue
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return True


def iter_stdin_entries() -> list[dict[str, Any]]:
    entries = []
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        loaded = json.loads(line)
        if isinstance(loaded, list):
            entries.extend(loaded)
        else:
            entries.append(loaded)
    return entries


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Append notification events")
    parser.add_argument("--runtime", help="Notification center runtime directory")
    parser.add_argument("--source")
    parser.add_argument("--level", default="info", choices=sorted(VALID_LEVELS))
    parser.add_argument("--title")
    parser.add_argument("--summary", default="")
    parser.add_argument("--dedupe-key")
    parser.add_argument("--id")
    parser.add_argument("--path", action="append", default=[])
    parser.add_argument("--link", action="append", default=[], help="URL or label=URL")
    parser.add_argument("--meta", help="JSON object")
    parser.add_argument("--target", action="append", default=[])
    parser.add_argument("--stdin", action="store_true", help="Read JSON objects or JSON lines")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    runtime = Path(args.runtime).expanduser() if args.runtime else runtime_dir()
    raw_entries: list[dict[str, Any]]
    if args.stdin:
        raw_entries = iter_stdin_entries()
    else:
        meta = json.loads(args.meta) if args.meta else {}
        if args.meta and not isinstance(meta, dict):
            raise ValueError("--meta must be a JSON object")
        raw_entries = [
            {
                "id": args.id,
                "source": args.source,
                "level": args.level,
                "title": args.title,
                "summary": args.summary,
                "dedupe_key": args.dedupe_key,
                "paths": args.path,
                "links": args.link,
                "meta": meta,
                "targets": args.target or ["feishu"],
            }
        ]

    results = []
    for raw in raw_entries:
        entry = build_entry(raw)
        appended = append_entry(runtime, entry)
        results.append({"id": entry["id"], "appended": appended})
    print(json.dumps({"ok": True, "runtime": str(runtime), "results": results}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
