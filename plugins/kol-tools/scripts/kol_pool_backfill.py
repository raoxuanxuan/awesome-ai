#!/usr/bin/env python3
"""Backfill existing KOL raw tweet Markdown into tweet-pool.

This is a one-time compatibility migration. It preserves historical raw tweet
facts as canonical tweet-pool JSON and consumer status; it does not clean,
index, distill, rewrite raw Markdown, or update KOL refresh state.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kol_common import DEFAULT_VAULT, raw_tweets_dir
from kol_refresh import default_tweet_pool_bin


FM_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.DOTALL)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_scalar(raw: str) -> Any:
    value = raw.strip().strip('"').strip("'")
    low = value.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if low in {"null", "none", ""}:
        return None
    try:
        return int(value)
    except ValueError:
        return value


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    match = FM_RE.match(text)
    if not match:
        return {}, text.strip()
    block, body = match.groups()
    meta: dict[str, Any] = {}
    for line in block.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = parse_scalar(value)
    return meta, body.strip()


def as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def raw_markdown_to_item(path: Path, text: str, handle: str) -> dict[str, Any]:
    meta, body = parse_frontmatter(text)
    tweet_id = str(meta.get("id") or path.stem).strip()
    screen_name = str(meta.get("screen_name") or meta.get("author_screen_name") or handle)
    quoted_tweet_id = str(meta.get("quoted_tweet_id") or "").strip()
    in_reply_to = str(meta.get("in_reply_to") or meta.get("reply_to") or "").strip()
    is_quote = bool(meta.get("is_quote")) or bool(quoted_tweet_id)
    item: dict[str, Any] = {
        "id": tweet_id,
        "url": meta.get("url") or f"https://x.com/{screen_name}/status/{tweet_id}",
        "author": meta.get("author") or meta.get("display_name") or screen_name,
        "screen_name": screen_name,
        "created_at": meta.get("created_at") or meta.get("date") or "",
        "date": meta.get("created_at") or meta.get("date") or "",
        "lang": meta.get("lang") or "unknown",
        "text": body,
        "full_text": body,
        "is_reply": bool(meta.get("is_reply")),
        "in_reply_to": in_reply_to,
        "reply_to": in_reply_to,
        "is_quote": is_quote,
        "quoted_tweet_id": quoted_tweet_id,
        "quote": None,
        "is_retweet": bool(meta.get("is_retweet")),
        "is_thread_part": bool(meta.get("is_thread_part")),
        "conversation_id": str(meta.get("conversation_id") or tweet_id),
        "favorite_count": as_int(meta.get("favorite_count")),
        "retweet_count": as_int(meta.get("retweet_count")),
        "reply_count": as_int(meta.get("reply_count")),
        "quote_count": as_int(meta.get("quote_count")),
        "view_count": as_int(meta.get("view_count")),
        "media_count": as_int(meta.get("media_count")),
        "source_type": meta.get("source_type") or ("x_reply" if bool(meta.get("is_reply")) else "x_quote" if is_quote else "x_public"),
        "visibility": meta.get("visibility") or "private",
        "stats": {
            "likes": as_int(meta.get("favorite_count")),
            "retweets": as_int(meta.get("retweet_count")),
            "replies": as_int(meta.get("reply_count")),
            "quotes": as_int(meta.get("quote_count")),
            "views": as_int(meta.get("view_count")),
        },
        "raw_archive": {
            "path": str(path),
            "handle": handle,
        },
    }
    return item


def iter_handles(vault: Path) -> list[str]:
    handles = []
    if not vault.exists():
        return handles
    for child in sorted(vault.iterdir(), key=lambda p: p.name):
        if child.name.startswith(".") or child.name == "_cross" or not child.is_dir():
            continue
        if raw_tweets_dir(vault, child.name).is_dir():
            handles.append(child.name)
    return handles


def load_raw_items(vault: Path, handle: str, limit: int = 0) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    raw_dir = raw_tweets_dir(vault, handle)
    if not raw_dir.is_dir():
        raise FileNotFoundError(f"raw tweets dir not found: {raw_dir}")
    items: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    paths = sorted(raw_dir.glob("*.md"))
    if limit > 0:
        paths = paths[:limit]
    for path in paths:
        try:
            items.append(raw_markdown_to_item(path, path.read_text(encoding="utf-8"), handle))
        except Exception as exc:  # noqa: BLE001
            errors.append({"path": str(path), "error": str(exc)})
    return items, errors


def envelope(handle: str, items: list[dict[str, Any]], fetched_at: str) -> dict[str, Any]:
    return {
        "ok": True,
        "mode": "history",
        "source": "kol-raw-archive",
        "fetched_at": fetched_at,
        "input": {"user": handle, "migration": "kol-raw-archive"},
        "items": items,
        "meta": {
            "migration": "kol-raw-archive",
            "item_count": len(items),
        },
        "error": None,
    }


def tweet_pool_runtime_args(args: argparse.Namespace) -> list[str]:
    if args.tweet_pool_runtime:
        return ["--runtime", str(args.tweet_pool_runtime)]
    return []


def run_tweet_pool(args: argparse.Namespace, command: list[str], input_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    binary = Path(args.tweet_pool_bin) if args.tweet_pool_bin else default_tweet_pool_bin()
    if binary is None:
        raise FileNotFoundError("tweet-pool binary not found; pass --tweet-pool-bin")
    proc = subprocess.run(
        [str(binary), *tweet_pool_runtime_args(args), *command],
        input=json.dumps(input_payload, ensure_ascii=False) if input_payload is not None else None,
        capture_output=True,
        text=True,
        timeout=args.timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or f"tweet-pool rc={proc.returncode}")
    payload = json.loads(proc.stdout)
    if not payload.get("ok", False):
        raise RuntimeError(json.dumps(payload.get("error") or payload, ensure_ascii=False))
    return payload


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def update_consumer_statuses(runtime: Path, consumer: str, items: list[dict[str, Any]]) -> int:
    path = runtime / "consumers" / f"{consumer}.json"
    state = read_json(path) if path.exists() else {"consumer": consumer, "items": {}}
    state["consumer"] = consumer
    state.setdefault("items", {})
    updated_at = now_iso()
    for item in items:
        tweet_id = str(item["id"])
        output_path = str((item.get("raw_archive") or {}).get("path") or "")
        state["items"][tweet_id] = {
            "status": "raw_backfilled",
            "updated_at": updated_at,
            "output": output_path,
        }
    write_json(path, state)
    return len(items)


def backfill_handle(args: argparse.Namespace, handle: str) -> dict[str, Any]:
    items, errors = load_raw_items(args.vault, handle, args.limit)
    if args.dry_run:
        return {
            "handle": handle,
            "status": "dry_run",
            "found": len(items),
            "errors": errors,
        }

    fetched_at = now_iso()
    result = run_tweet_pool(args, ["ingest", "--input", "-"], input_payload=envelope(handle, items, fetched_at))
    consumer_updated = update_consumer_statuses(Path(result["runtime"]), args.tweet_pool_consumer, items)
    return {
        "handle": handle,
        "status": "backfilled",
        "found": len(items),
        "errors": errors,
        "tweet_pool": result,
        "consumer": args.tweet_pool_consumer,
        "consumer_updated": consumer_updated,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backfill KOL raw tweet Markdown into tweet-pool.")
    parser.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--handle")
    target.add_argument("--all", action="store_true")
    parser.add_argument("--tweet-pool-bin")
    parser.add_argument("--tweet-pool-runtime", type=Path)
    parser.add_argument("--tweet-pool-consumer", default="kol-tools")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        handles = iter_handles(args.vault) if args.all else [str(args.handle)]
        results = [backfill_handle(args, handle) for handle in handles]
        payload = results[0] if len(results) == 1 else {
            "status": "dry_run" if args.dry_run else "backfilled",
            "handles": len(results),
            "found": sum(int(result.get("found") or 0) for result in results),
            "results": results,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
