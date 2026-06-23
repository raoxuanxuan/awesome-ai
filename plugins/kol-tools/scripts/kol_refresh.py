#!/usr/bin/env python3
"""Refresh KOL raw tweet archives through twitter-fetch and tweet-pool.

This script is the KOL-owned layer above twitter-fetch:
- twitter-fetch obtains normalized X/Twitter data.
- tweet-pool stores canonical tweet JSON for cross-workflow reuse.
- kol-refresh writes KOL raw Markdown and KOL-owned backfill state.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kol_common import DEFAULT_VAULT, raw_tweets_dir


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def state_path(vault: Path, handle: str) -> Path:
    return vault / handle / "raw" / ".backfill_state.json"


def legacy_state_path(vault: Path, handle: str) -> Path:
    return vault / handle / "raw" / "tweets" / ".backfill_state.json"


def load_state(vault: Path, handle: str) -> dict[str, Any]:
    for path in (state_path(vault, handle), legacy_state_path(vault, handle)):
        if not path.exists():
            continue
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def default_twitter_fetch_bin() -> Path | None:
    plugins_dir = Path(__file__).resolve().parents[2]
    candidates = [
        plugins_dir / "twitter-tools" / "skills" / "twitter-fetch" / "bin" / "twitter-fetch",
    ]
    cache_root = Path.home() / ".codex" / "plugins" / "cache" / "awesome-ai" / "twitter-tools"
    if cache_root.exists():
        candidates.extend(
            sorted(cache_root.glob("*/skills/twitter-fetch/bin/twitter-fetch"), reverse=True)
        )
    claude_cache = Path.home() / ".claude" / "plugins" / "cache" / "awesome-ai" / "twitter-tools"
    if claude_cache.exists():
        candidates.extend(
            sorted(claude_cache.glob("*/skills/twitter-fetch/bin/twitter-fetch"), reverse=True)
        )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    found = shutil.which("twitter-fetch")
    return Path(found) if found else None


def default_tweet_pool_bin() -> Path | None:
    plugins_dir = Path(__file__).resolve().parents[2]
    candidates = [
        plugins_dir / "twitter-tools" / "skills" / "tweet-pool" / "bin" / "tweet-pool",
    ]
    cache_root = Path.home() / ".codex" / "plugins" / "cache" / "awesome-ai" / "twitter-tools"
    if cache_root.exists():
        candidates.extend(
            sorted(cache_root.glob("*/skills/tweet-pool/bin/tweet-pool"), reverse=True)
        )
    claude_cache = Path.home() / ".claude" / "plugins" / "cache" / "awesome-ai" / "twitter-tools"
    if claude_cache.exists():
        candidates.extend(
            sorted(claude_cache.glob("*/skills/tweet-pool/bin/tweet-pool"), reverse=True)
        )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    found = shutil.which("tweet-pool")
    return Path(found) if found else None


def tweet_text(item: dict[str, Any]) -> str:
    article = item.get("article") or {}
    article_text = article.get("full_text") or article.get("text")
    return str(item.get("full_text") or item.get("text") or article_text or "").strip()


def author_screen_name(item: dict[str, Any], fallback: str) -> str:
    author = item.get("author")
    if isinstance(author, dict):
        return str(author.get("screen_name") or author.get("username") or fallback)
    return str(item.get("screen_name") or author or fallback)


def scalar(value: Any) -> str:
    if value is None:
        return '""'
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


def source_type(item: dict[str, Any]) -> str:
    explicit = item.get("source_type") or item.get("source")
    if explicit in {"x_public", "x_reply", "x_quote", "x_subscriber", "manual_article"}:
        return str(explicit)
    if item.get("is_reply"):
        return "x_reply"
    if item.get("is_quote"):
        return "x_quote"
    return "x_public"


def item_to_markdown(item: dict[str, Any], handle: str) -> str:
    text = tweet_text(item)
    stats = item.get("stats") or {}
    screen_name = author_screen_name(item, handle)
    tweet_id = str(item.get("id") or "").strip()
    frontmatter = {
        "id": tweet_id,
        "url": item.get("url") or f"https://x.com/{screen_name}/status/{tweet_id}",
        "author_screen_name": screen_name,
        "created_at": item.get("created_at") or item.get("date") or "",
        "lang": item.get("lang") or "unknown",
        "is_reply": bool(item.get("is_reply")),
        "in_reply_to": item.get("in_reply_to") or item.get("reply_to") or "",
        "is_quote": bool(item.get("is_quote")),
        "quoted_tweet_id": (item.get("quote") or {}).get("id", "") if isinstance(item.get("quote"), dict) else "",
        "is_retweet": bool(item.get("is_retweet")),
        "is_thread_part": bool(item.get("is_thread_part")),
        "conversation_id": item.get("conversation_id") or tweet_id,
        "favorite_count": stats.get("likes") or item.get("favorite_count") or 0,
        "retweet_count": stats.get("retweets") or item.get("retweet_count") or 0,
        "reply_count": stats.get("replies") or item.get("reply_count") or 0,
        "view_count": stats.get("views") or item.get("view_count") or 0,
        "media_count": item.get("media_count") or 0,
        "full_text_length": len(text),
        "source_type": source_type(item),
        "visibility": "private" if source_type(item) != "x_subscriber" else "subscriber_private",
    }
    lines = ["---"]
    lines.extend(f"{key}: {scalar(value)}" for key, value in frontmatter.items())
    lines.append("---")
    lines.append(text)
    return "\n".join(lines).rstrip() + "\n"


def load_jsonl(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    items = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if line.strip():
                items.append(json.loads(line))
    return items, {}


def load_json_payload(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload, {}
    if not payload.get("ok", True):
        raise RuntimeError(json.dumps(payload.get("error") or payload, ensure_ascii=False))
    return list(payload.get("items") or []), dict(payload.get("meta") or {})


def fetch_envelope_from_items(
    args: argparse.Namespace,
    items: list[dict[str, Any]],
    meta: dict[str, Any],
    *,
    source: str,
) -> dict[str, Any]:
    return {
        "ok": True,
        "mode": "history",
        "source": source,
        "fetched_at": now_iso(),
        "input": {"user": args.handle},
        "items": items,
        "meta": meta,
        "error": None,
    }


def payload_items_meta(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not payload.get("ok", True):
        raise RuntimeError(json.dumps(payload.get("error") or payload, ensure_ascii=False))
    return list(payload.get("items") or []), dict(payload.get("meta") or {})


def root_tweet_ids(payload: dict[str, Any]) -> list[str]:
    ids = []
    for item in payload.get("items") or []:
        tweet_id = str(item.get("id") or "").strip()
        if tweet_id:
            ids.append(tweet_id)
    return ids


def tweet_pool_runtime_args(args: argparse.Namespace) -> list[str]:
    if args.tweet_pool_runtime:
        return ["--runtime", str(args.tweet_pool_runtime)]
    return []


def run_tweet_pool(
    args: argparse.Namespace,
    command: list[str],
    *,
    input_payload: dict[str, Any] | None = None,
    timeout: int | None = None,
) -> dict[str, Any]:
    binary = Path(args.tweet_pool_bin) if args.tweet_pool_bin else default_tweet_pool_bin()
    if binary is None:
        raise FileNotFoundError("tweet-pool binary not found; pass --tweet-pool-bin")

    proc = subprocess.run(
        [str(binary), *tweet_pool_runtime_args(args), *command],
        input=json.dumps(input_payload, ensure_ascii=False) if input_payload is not None else None,
        capture_output=True,
        text=True,
        timeout=timeout or args.timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or f"tweet-pool rc={proc.returncode}")
    payload = json.loads(proc.stdout)
    if not payload.get("ok", False):
        raise RuntimeError(json.dumps(payload.get("error") or payload, ensure_ascii=False))
    return payload


def ingest_tweet_pool(args: argparse.Namespace, payload: dict[str, Any]) -> dict[str, Any]:
    return run_tweet_pool(args, ["ingest", "--input", "-"], input_payload=payload)


def export_tweet_pool(args: argparse.Namespace, tweet_ids: list[str]) -> list[dict[str, Any]]:
    if not tweet_ids:
        return []
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as fh:
            json.dump(tweet_ids, fh, ensure_ascii=False)
            tmp_path = Path(fh.name)
        payload = run_tweet_pool(args, ["export", "--tweet-ids-file", str(tmp_path)])
        return list(payload.get("items") or [])
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


def set_tweet_pool_consumer_status(
    args: argparse.Namespace,
    tweet_id: str,
    status: str,
    *,
    output_path: str = "",
    reason: str = "",
) -> dict[str, Any]:
    cmd = [
        "consumer",
        "set",
        "--consumer",
        args.tweet_pool_consumer,
        "--tweet-id",
        tweet_id,
        "--status",
        status,
    ]
    if output_path:
        cmd.extend(["--output", output_path])
    if reason:
        cmd.extend(["--reason", reason])
    return run_tweet_pool(args, cmd)


def run_twitter_fetch(args: argparse.Namespace, state: dict[str, Any]) -> dict[str, Any]:
    binary = Path(args.twitter_fetch_bin) if args.twitter_fetch_bin else default_twitter_fetch_bin()
    if binary is None:
        raise FileNotFoundError("twitter-fetch binary not found; pass --twitter-fetch-bin")

    cmd = [
        str(binary),
        "history",
        "--user",
        args.handle,
        "--months",
        str(args.months),
        "--max-pages",
        str(args.max_pages),
        "--page-size",
        str(args.page_size),
        "--sleep",
        str(args.sleep),
    ]
    if args.mock:
        cmd.append("--mock")
    if args.incremental and state.get("newest_id"):
        cmd.extend(["--since-id", str(state["newest_id"])])
    elif not args.incremental and state.get("cursor"):
        cmd.extend(["--cursor", str(state["cursor"])])

    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=args.timeout)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or f"twitter-fetch rc={proc.returncode}")
    payload = json.loads(proc.stdout)
    if not payload.get("ok", False):
        raise RuntimeError(json.dumps(payload.get("error") or payload, ensure_ascii=False))
    return payload


def write_items(vault: Path, handle: str, items: list[dict[str, Any]], overwrite: bool) -> dict[str, Any]:
    out_dir = raw_tweets_dir(vault, handle)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    skipped = 0
    statuses = []
    for item in items:
        tweet_id = str(item.get("id") or "").strip()
        if not tweet_id:
            skipped += 1
            continue
        out = out_dir / f"{tweet_id}.md"
        if out.exists() and not overwrite:
            skipped += 1
            statuses.append({"tweet_id": tweet_id, "status": "raw_exists", "output": str(out)})
            continue
        out.write_text(item_to_markdown(item, handle), encoding="utf-8")
        written += 1
        statuses.append({"tweet_id": tweet_id, "status": "raw_written", "output": str(out)})
    return {"written": written, "skipped": skipped, "items": statuses}


def update_consumer_statuses(args: argparse.Namespace, write_stats: dict[str, Any]) -> int:
    updated = 0
    for item in write_stats.get("items") or []:
        set_tweet_pool_consumer_status(
            args,
            str(item["tweet_id"]),
            str(item["status"]),
            output_path=str(item.get("output") or ""),
        )
        updated += 1
    return updated


def update_state(vault: Path, handle: str, previous: dict[str, Any], items: list[dict[str, Any]], meta: dict[str, Any]) -> dict[str, Any]:
    ids = [int(str(item["id"])) for item in items if str(item.get("id") or "").isdigit()]
    newest_id = str(max(ids)) if ids else previous.get("newest_id")
    oldest_id = str(min(ids)) if ids else previous.get("oldest_id")
    next_cursor = meta.get("next_cursor")
    total_files = len(list(raw_tweets_dir(vault, handle).glob("*.md")))
    state = {
        **previous,
        "handle": handle,
        "updated_at": now_iso(),
        "newest_id": meta.get("newest_id") or newest_id,
        "oldest_id": meta.get("oldest_id") or oldest_id,
        "cursor": next_cursor,
        "total_fetched": total_files,
        "last_page_count": meta.get("page_count"),
        "reached_cutoff": bool(meta.get("reached_cutoff", False)),
        "reached_since_id": bool(meta.get("reached_since_id", False)),
        "exhausted": bool(meta.get("exhausted", False)),
    }
    out = state_path(vault, handle)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return state


def build_result(args: argparse.Namespace, items: list[dict[str, Any]], meta: dict[str, Any], previous: dict[str, Any], write_stats: dict[str, Any] | None) -> dict[str, Any]:
    ids = [str(item.get("id")) for item in items if item.get("id")]
    return {
        "handle": args.handle,
        "status": "dry_run" if args.dry_run else "written",
        "items": len(items),
        "new_items": len(set(ids)),
        "write": write_stats or {"written": 0, "skipped": 0},
        "state_path": str(state_path(args.vault, args.handle)),
        "previous_newest_id": previous.get("newest_id"),
        "proposed_newest_id": meta.get("newest_id") or (max(ids, key=int) if ids else previous.get("newest_id")),
        "next_cursor": meta.get("next_cursor"),
        "meta": meta,
        "tweet_pool": getattr(args, "tweet_pool_result", None),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh KOL raw archive through twitter-fetch.")
    parser.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    parser.add_argument("--handle", required=True)
    parser.add_argument("--incremental", action="store_true")
    parser.add_argument("--months", type=int, default=6)
    parser.add_argument("--max-pages", type=int, default=1)
    parser.add_argument("--page-size", type=int, default=40)
    parser.add_argument("--sleep", type=float, default=1.5)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--twitter-fetch-bin")
    parser.add_argument("--tweet-pool-bin")
    parser.add_argument("--tweet-pool-runtime", type=Path)
    parser.add_argument("--tweet-pool-consumer", default="kol-tools")
    parser.add_argument("--input-jsonl", type=Path)
    parser.add_argument("--input-json", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--mock", action="store_true")
    args = parser.parse_args(argv)

    previous = load_state(args.vault, args.handle)
    try:
        if args.input_jsonl:
            items, meta = load_jsonl(args.input_jsonl)
            payload = fetch_envelope_from_items(args, items, meta, source="kol-refresh-input-jsonl")
        elif args.input_json:
            items, meta = load_json_payload(args.input_json)
            payload = fetch_envelope_from_items(args, items, meta, source="kol-refresh-input-json")
        else:
            payload = run_twitter_fetch(args, previous)
            items, meta = payload_items_meta(payload)

        write_stats = None
        args.tweet_pool_result = {"status": "skipped_dry_run"} if args.dry_run else None
        if not args.dry_run:
            ingest_result = ingest_tweet_pool(args, payload)
            items = export_tweet_pool(args, root_tweet_ids(payload))
            write_stats = write_items(args.vault, args.handle, items, args.overwrite)
            consumer_updated = update_consumer_statuses(args, write_stats)
            update_state(args.vault, args.handle, previous, items, meta)
            args.tweet_pool_result = {
                "status": "ingested",
                "runtime": ingest_result.get("runtime"),
                "ingested": ingest_result.get("ingested"),
                "tweet_ids": ingest_result.get("tweet_ids"),
                "consumer": args.tweet_pool_consumer,
                "consumer_updated": consumer_updated,
            }
        print(json.dumps(build_result(args, items, meta, previous, write_stats), ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"handle": args.handle, "status": "error", "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
