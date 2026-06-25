#!/usr/bin/env python3
"""Normalized X/Twitter fetch cache shared by downstream consumers."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional


DEFAULT_RUNTIME = Path("/Users/saberrao/ai-workspace/content-creation/.tweet-pool")
CACHE_DIRS = (
    "tweets",
    "authors",
    "media",
    "timelines",
    "windows",
    "fetch_state",
    "consumers",
)
COMPLETENESS_KEYS = ("timeline", "single", "thread", "history", "media")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso_datetime(value: str) -> datetime | None:
    if not value:
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def format_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def runtime_dir(env: Optional[Mapping[str, str]] = None) -> Path:
    env = os.environ if env is None else env
    override = env.get("TWEET_POOL_RUNTIME")
    if override:
        return Path(override).expanduser()
    return DEFAULT_RUNTIME


def ensure_runtime(runtime: Path) -> Path:
    runtime.mkdir(parents=True, exist_ok=True)
    for child in CACHE_DIRS:
        (runtime / child).mkdir(parents=True, exist_ok=True)
    return runtime


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def safe_username(username: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", username.strip().lstrip("@")) or "unknown"


def compact_iso(value: str) -> str:
    parsed = parse_iso_datetime(value)
    if parsed is None:
        return re.sub(r"[^A-Za-z0-9]+", "", value) or "unknown"
    return parsed.strftime("%Y%m%dT%H%M%SZ")


def window_snapshot_path(
    runtime: Path, username: str, window_start: str, window_end: str
) -> Path:
    name = f"{compact_iso(window_start)}_{compact_iso(window_end)}.json"
    return runtime / "windows" / safe_username(username) / name


def read_input(path: str) -> Any:
    raw = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return [json.loads(line) for line in raw.splitlines() if line.strip()]


def iter_tweet_items(payload: Any) -> Iterable[dict[str, Any]]:
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                yield from iter_tweet_items(item)
        return
    if not isinstance(payload, dict):
        return

    if isinstance(payload.get("items"), list):
        for item in payload["items"]:
            if isinstance(item, dict):
                yield item
                thread = item.get("thread")
                if isinstance(thread, dict):
                    yield from iter_tweet_items(thread)
                quote = item.get("quote")
                if isinstance(quote, dict) and quote.get("id"):
                    yield quote
        return

    if payload.get("id"):
        yield payload


def nonempty(value: Any) -> bool:
    return value not in (None, "", [], {})


def should_update_field(key: str, existing_value: Any, new_value: Any, merged: dict[str, Any]) -> bool:
    if not nonempty(new_value):
        return key not in merged
    if key in {"text", "full_text"} and isinstance(existing_value, str) and isinstance(new_value, str):
        if len(new_value.strip()) < len(existing_value.strip()):
            return False
    if key == "media_count":
        try:
            if int(existing_value or 0) > 0 and int(new_value or 0) == 0:
                return False
        except (TypeError, ValueError):
            pass
    if key == "is_quote" and existing_value is True and new_value is False and nonempty(merged.get("quote")):
        return False
    return True


def merge_tweet(
    existing: dict[str, Any],
    item: dict[str, Any],
    *,
    mode: str,
    source: str,
    fetched_at: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    merged = {key: value for key, value in existing.items() if key != "_pool"}
    existing_pool = existing.get("_pool", {})
    if not isinstance(existing_pool, dict):
        existing_pool = {}
    field_sources = dict(existing_pool.get("field_sources", {}) or {})
    for key, value in item.items():
        if key == "_pool":
            continue
        if should_update_field(key, merged.get(key), value, merged):
            previous_value = merged.get(key)
            merged[key] = value
            if key not in field_sources or previous_value != value:
                field_sources[key] = {
                    "source": source,
                    "mode": mode,
                    "updated_at": fetched_at or now_iso(),
                }
    return merged, field_sources


def completeness_for(
    existing_pool: dict[str, Any], mode: str, item: dict[str, Any]
) -> dict[str, bool]:
    completeness = {key: False for key in COMPLETENESS_KEYS}
    completeness.update(existing_pool.get("completeness", {}) or {})
    if mode in completeness:
        completeness[mode] = True
    if item.get("media") or int(item.get("media_count") or 0) > 0:
        completeness["media"] = True
    return completeness


def update_pool_meta(
    existing: dict[str, Any],
    item: dict[str, Any],
    *,
    mode: str,
    source: str,
    fetched_at: str,
    field_sources: dict[str, Any],
) -> dict[str, Any]:
    existing_pool = existing.get("_pool", {})
    if not isinstance(existing_pool, dict):
        existing_pool = {}
    sources = set(existing_pool.get("sources", []) or [])
    if source:
        sources.add(source)
    modes = set(existing_pool.get("modes", []) or [])
    if mode:
        modes.add(mode)
    return {
        "first_seen_at": existing_pool.get("first_seen_at") or fetched_at or now_iso(),
        "last_seen_at": fetched_at or now_iso(),
        "sources": sorted(sources),
        "modes": sorted(modes),
        "completeness": completeness_for(existing_pool, mode, item),
        "field_sources": field_sources,
    }


def upsert_tweet(
    item: dict[str, Any],
    runtime: Path,
    *,
    mode: str,
    source: str,
    fetched_at: str,
) -> dict[str, Any]:
    tweet_id = str(item.get("id") or "").strip()
    if not tweet_id:
        raise ValueError("tweet item is missing id")
    ensure_runtime(runtime)
    path = runtime / "tweets" / f"{tweet_id}.json"
    existing = read_json(path) if path.exists() else {}
    merged, field_sources = merge_tweet(
        existing,
        item,
        mode=mode,
        source=source,
        fetched_at=fetched_at,
    )
    merged["_pool"] = update_pool_meta(
        existing,
        item,
        mode=mode,
        source=source,
        fetched_at=fetched_at,
        field_sources=field_sources,
    )
    write_json(path, merged)
    upsert_author_from_tweet(merged, runtime, fetched_at=fetched_at)
    return merged


def author_avatar(item: dict[str, Any]) -> str:
    profile = item.get("author_profile")
    if isinstance(profile, dict):
        for key in ("avatar_url", "profile_image_url", "profile_image_url_https"):
            if profile.get(key):
                return str(profile[key])
    for key in ("avatar_url", "profile_image_url", "profile_image_url_https"):
        if item.get(key):
            return str(item[key])
    return ""


def upsert_author_from_tweet(
    item: dict[str, Any], runtime: Path, *, fetched_at: str
) -> None:
    username = str(item.get("screen_name") or "").strip()
    if not username:
        return
    path = runtime / "authors" / f"{username}.json"
    existing = read_json(path) if path.exists() else {}
    author = {
        "username": username,
        "display_name": item.get("author") or existing.get("display_name", ""),
        "avatar_url": author_avatar(item) or existing.get("avatar_url", ""),
        "first_seen_at": existing.get("first_seen_at") or fetched_at or now_iso(),
        "last_seen_at": fetched_at or now_iso(),
    }
    write_json(path, author)


def append_jsonl(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n")


def record_timeline_observation(
    payload: dict[str, Any], runtime: Path, tweet_ids: list[str]
) -> None:
    username = str((payload.get("input") or {}).get("user") or "").strip()
    mode = str(payload.get("mode") or "")
    if not username or mode not in {"timeline", "history"}:
        return
    fetched_at = str(payload.get("fetched_at") or now_iso())
    observation = {
        "fetched_at": fetched_at,
        "mode": mode,
        "source": payload.get("source", ""),
        "input": payload.get("input") or {},
        "tweet_ids": tweet_ids,
    }
    append_jsonl(runtime / "timelines" / f"{username}.jsonl", observation)
    update_fetch_state(username, runtime, observation)


def update_fetch_state(username: str, runtime: Path, observation: dict[str, Any]) -> None:
    path = runtime / "fetch_state" / f"{username}.json"
    existing = read_json(path) if path.exists() else {}
    tweet_ids = observation.get("tweet_ids", []) or []
    numeric_ids = [int(tweet_id) for tweet_id in tweet_ids if str(tweet_id).isdigit()]
    state = {
        "username": username,
        "last_observed_at": observation["fetched_at"],
        "last_mode": observation["mode"],
        "last_source": observation["source"],
        "last_count": len(tweet_ids),
        "newest_id": existing.get("newest_id", ""),
        "oldest_id": existing.get("oldest_id", ""),
    }
    if numeric_ids:
        newest = str(max(numeric_ids))
        oldest = str(min(numeric_ids))
        previous_newest = existing.get("newest_id")
        previous_oldest = existing.get("oldest_id")
        state["newest_id"] = (
            str(max(int(previous_newest), int(newest)))
            if str(previous_newest).isdigit()
            else newest
        )
        state["oldest_id"] = (
            str(min(int(previous_oldest), int(oldest)))
            if str(previous_oldest).isdigit()
            else oldest
        )
    write_json(path, state)


def ingest_payload(payload: Any, runtime: Path) -> dict[str, Any]:
    ensure_runtime(runtime)
    if isinstance(payload, dict):
        mode = str(payload.get("mode") or "items")
        source = str(payload.get("source") or "")
        fetched_at = str(payload.get("fetched_at") or now_iso())
        root_items = payload.get("items") or []
    else:
        mode = "items"
        source = ""
        fetched_at = now_iso()
        root_items = []

    ingested = []
    root_tweet_ids = []
    for item in iter_tweet_items(payload):
        tweet = upsert_tweet(
            item,
            runtime,
            mode=mode,
            source=source,
            fetched_at=fetched_at,
        )
        tweet_id = str(tweet["id"])
        ingested.append(tweet_id)
        if item in root_items:
            root_tweet_ids.append(tweet_id)

    if isinstance(payload, dict):
        record_timeline_observation(payload, runtime, root_tweet_ids)

    unique_ids = sorted(
        set(ingested),
        key=lambda value: int(value) if str(value).isdigit() else value,
    )
    return {
        "ok": True,
        "runtime": str(runtime),
        "ingested": len(unique_ids),
        "tweet_ids": unique_ids,
    }


def root_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        return [item for item in payload["items"] if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def item_created_at(item: dict[str, Any]) -> datetime | None:
    return parse_iso_datetime(str(item.get("created_at") or ""))


def tweet_ids_in_window(
    items: list[dict[str, Any]], window_start: datetime, window_end: datetime
) -> list[str]:
    tweet_ids: list[str] = []
    for item in items:
        created = item_created_at(item)
        tweet_id = str(item.get("id") or "")
        if not tweet_id or created is None:
            continue
        if window_start <= created < window_end:
            tweet_ids.append(tweet_id)
    return tweet_ids


def timeline_coverage(
    items: list[dict[str, Any]], window_start: datetime, limit: int
) -> dict[str, Any]:
    created_values = [created for item in items if (created := item_created_at(item))]
    newest = max(created_values) if created_values else None
    oldest = min(created_values) if created_values else None
    observed_count = len(items)
    hit_scan_limit = limit > 0 and observed_count >= limit
    covers_window_start = not hit_scan_limit or (
        oldest is not None and oldest <= window_start
    )
    return {
        "newest_created_at": format_iso(newest) if newest else "",
        "oldest_created_at": format_iso(oldest) if oldest else "",
        "covers_window_start": covers_window_start,
        "hit_scan_limit": hit_scan_limit,
        "unparseable_created_at": observed_count - len(created_values),
    }


def window_status(
    payload: Any,
    *,
    window_end: datetime,
    now: datetime,
    grace_minutes: int,
    coverage: dict[str, Any],
) -> str:
    if isinstance(payload, dict) and payload.get("error"):
        return "failed"
    if not coverage.get("covers_window_start"):
        return "incomplete"
    if now < window_end + timedelta(minutes=max(grace_minutes, 0)):
        return "provisional"
    return "finalized"


def build_window_snapshot(
    payload: Any,
    *,
    username: str,
    window_start: str,
    window_end: str,
    limit: int,
    grace_minutes: int,
    now: str,
) -> dict[str, Any]:
    start_dt = parse_iso_datetime(window_start)
    end_dt = parse_iso_datetime(window_end)
    now_dt = parse_iso_datetime(now)
    if start_dt is None or end_dt is None or now_dt is None:
        raise ValueError("window-start, window-end, and now must be ISO datetimes")
    if start_dt >= end_dt:
        raise ValueError("window-start must be earlier than window-end")

    items = root_items(payload)
    coverage = timeline_coverage(items, start_dt, limit)
    source = payload.get("source", "") if isinstance(payload, dict) else ""
    mode = payload.get("mode", "timeline") if isinstance(payload, dict) else "timeline"
    fetched_at = payload.get("fetched_at", now) if isinstance(payload, dict) else now
    tweet_ids = tweet_ids_in_window(items, start_dt, end_dt)
    return {
        "version": 1,
        "mode": "timeline_window",
        "provider": source,
        "source_mode": mode,
        "username": username,
        "window_start": format_iso(start_dt),
        "window_end": format_iso(end_dt),
        "fetched_at": str(fetched_at or now),
        "status": window_status(
            payload,
            window_end=end_dt,
            now=now_dt,
            grace_minutes=grace_minutes,
            coverage=coverage,
        ),
        "tweet_ids": tweet_ids,
        "observed_count": len(items),
        "coverage": coverage,
        "request": {
            "limit": limit,
            "grace_minutes": grace_minutes,
        },
        "error": payload.get("error") if isinstance(payload, dict) else None,
    }


def read_window_snapshot(
    runtime: Path, username: str, window_start: str, window_end: str
) -> dict[str, Any] | None:
    path = window_snapshot_path(runtime, username, window_start, window_end)
    if not path.exists():
        return None
    return read_json(path)


def write_window_snapshot(
    runtime: Path, snapshot: dict[str, Any]
) -> dict[str, Any]:
    ensure_runtime(runtime)
    path = window_snapshot_path(
        runtime,
        str(snapshot["username"]),
        str(snapshot["window_start"]),
        str(snapshot["window_end"]),
    )
    snapshot = dict(snapshot)
    snapshot["path"] = str(path)
    write_json(path, snapshot)
    return snapshot


def window_payload(
    runtime: Path,
    snapshot: dict[str, Any] | None,
    *,
    include_items: bool = False,
) -> dict[str, Any]:
    payload = {
        "ok": True,
        "runtime": str(runtime),
        "found": snapshot is not None,
        "snapshot": snapshot,
    }
    if include_items:
        tweet_ids = snapshot.get("tweet_ids", []) if snapshot else []
        payload["items"] = (
            export_tweets(runtime, tweet_ids=[str(item) for item in tweet_ids])
            if tweet_ids
            else []
        )
    return payload


def put_window(
    payload: Any,
    runtime: Path,
    *,
    username: str,
    window_start: str,
    window_end: str,
    limit: int,
    grace_minutes: int,
    now: str,
    include_items: bool = False,
) -> dict[str, Any]:
    ensure_runtime(runtime)
    ingest_payload(payload, runtime)
    snapshot = build_window_snapshot(
        payload,
        username=username,
        window_start=window_start,
        window_end=window_end,
        limit=limit,
        grace_minutes=grace_minutes,
        now=now,
    )
    snapshot = write_window_snapshot(runtime, snapshot)
    return window_payload(runtime, snapshot, include_items=include_items)


def set_consumer_status(
    consumer: str,
    tweet_id: str,
    status: str,
    runtime: Path,
    **metadata: Any,
) -> dict[str, Any]:
    if not consumer:
        raise ValueError("consumer is required")
    if not tweet_id:
        raise ValueError("tweet_id is required")
    ensure_runtime(runtime)
    path = runtime / "consumers" / f"{consumer}.json"
    state = read_json(path) if path.exists() else {"consumer": consumer, "items": {}}
    state["consumer"] = consumer
    state.setdefault("items", {})
    item_state = {
        "status": status,
        "updated_at": now_iso(),
    }
    item_state.update({key: value for key, value in metadata.items() if value})
    state["items"][str(tweet_id)] = item_state
    write_json(path, state)
    return {
        "ok": True,
        "consumer": consumer,
        "tweet_id": str(tweet_id),
        "status": status,
        "path": str(path),
    }


def parse_tweet_ids(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def read_tweet_ids_file(path: str) -> list[str]:
    raw = Path(path).read_text(encoding="utf-8")
    if not raw.strip():
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return [line.strip() for line in raw.splitlines() if line.strip()]
    if isinstance(payload, list):
        return [str(item).strip() for item in payload if str(item).strip()]
    raise ValueError("--tweet-ids-file must contain a JSON list or newline-separated ids")


def load_tweet(runtime: Path, tweet_id: str) -> dict[str, Any] | None:
    path = runtime / "tweets" / f"{tweet_id}.json"
    if not path.exists():
        return None
    return read_json(path)


def tweet_sort_key(item: dict[str, Any]) -> tuple[int, str]:
    tweet_id = str(item.get("id") or "")
    return (int(tweet_id), tweet_id) if tweet_id.isdigit() else (0, tweet_id)


def id_after(tweet_id: str, since_id: str) -> bool:
    if not since_id:
        return True
    if tweet_id.isdigit() and since_id.isdigit():
        return int(tweet_id) > int(since_id)
    return tweet_id > since_id


def id_before_or_equal(tweet_id: str, until_id: str) -> bool:
    if not until_id:
        return True
    if tweet_id.isdigit() and until_id.isdigit():
        return int(tweet_id) <= int(until_id)
    return tweet_id <= until_id


def export_tweets(
    runtime: Path,
    *,
    tweet_ids: list[str] | None = None,
    user: str = "",
    since_id: str = "",
    until_id: str = "",
    limit: int = 0,
) -> list[dict[str, Any]]:
    ensure_runtime(runtime)
    items: list[dict[str, Any]] = []
    if tweet_ids:
        for tweet_id in tweet_ids:
            item = load_tweet(runtime, tweet_id)
            if item is not None:
                items.append(item)
        return items

    user_lower = user.lower()
    for path in sorted((runtime / "tweets").glob("*.json")):
        item = read_json(path)
        tweet_id = str(item.get("id") or "")
        if user_lower and str(item.get("screen_name") or "").lower() != user_lower:
            continue
        if not id_after(tweet_id, since_id):
            continue
        if not id_before_or_equal(tweet_id, until_id):
            continue
        items.append(item)

    items.sort(key=tweet_sort_key)
    if limit > 0:
        items = items[-limit:]
    return items


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Maintain a normalized X/Twitter fetch cache")
    parser.add_argument("--runtime", default=None, help="Tweet pool runtime directory")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ensure = subparsers.add_parser("ensure", help="Create the tweet-pool runtime layout")
    ensure.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")

    ingest = subparsers.add_parser(
        "ingest", help="Ingest a twitter-fetch JSON envelope or JSONL"
    )
    ingest.add_argument("--input", required=True, help="Input JSON path, JSONL path, or '-'")
    ingest.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")

    consumer = subparsers.add_parser("consumer", help="Read or update consumer state")
    consumer_sub = consumer.add_subparsers(dest="consumer_command", required=True)
    set_cmd = consumer_sub.add_parser("set", help="Set a consumer-specific tweet status")
    set_cmd.add_argument("--consumer", required=True)
    set_cmd.add_argument("--tweet-id", required=True)
    set_cmd.add_argument("--status", required=True)
    set_cmd.add_argument("--reason", default="")
    set_cmd.add_argument("--output", default="")
    set_cmd.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")

    export = subparsers.add_parser("export", help="Export cached tweets as JSON or JSONL")
    export.add_argument("--tweet-ids", default="", help="Comma-separated tweet ids")
    export.add_argument("--tweet-ids-file", default="", help="JSON list or newline-separated ids")
    export.add_argument("--user", default="", help="Filter by screen_name when ids are not passed")
    export.add_argument("--since-id", default="", help="Only export ids greater than this id")
    export.add_argument("--until-id", default="", help="Only export ids less than or equal to this id")
    export.add_argument("--limit", type=int, default=0, help="Keep only the newest N matched tweets")
    export.add_argument("--format", choices=("json", "jsonl"), default="json")
    export.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")

    window = subparsers.add_parser("window", help="Read or write timeline window snapshots")
    window_sub = window.add_subparsers(dest="window_command", required=True)
    get_window = window_sub.add_parser("get", help="Read a cached timeline window snapshot")
    get_window.add_argument("--user", required=True)
    get_window.add_argument("--window-start", required=True)
    get_window.add_argument("--window-end", required=True)
    get_window.add_argument("--include-items", action="store_true")
    get_window.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")

    put_window_cmd = window_sub.add_parser(
        "put", help="Ingest a timeline payload and write its window snapshot"
    )
    put_window_cmd.add_argument("--user", required=True)
    put_window_cmd.add_argument("--window-start", required=True)
    put_window_cmd.add_argument("--window-end", required=True)
    put_window_cmd.add_argument("--input", required=True, help="Input JSON path or '-'")
    put_window_cmd.add_argument("--limit", type=int, required=True)
    put_window_cmd.add_argument("--grace-minutes", type=int, default=10)
    put_window_cmd.add_argument("--now", default="")
    put_window_cmd.add_argument("--include-items", action="store_true")
    put_window_cmd.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    return parser


def output(payload: dict[str, Any], pretty: bool) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2 if pretty else None))


def output_jsonl(items: list[dict[str, Any]]) -> None:
    for item in items:
        print(json.dumps(item, ensure_ascii=False, separators=(",", ":")))


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    runtime = Path(args.runtime).expanduser() if args.runtime else runtime_dir()

    try:
        if args.command == "ensure":
            ensure_runtime(runtime)
            payload = {"ok": True, "runtime": str(runtime), "dirs": list(CACHE_DIRS)}
        elif args.command == "ingest":
            payload = ingest_payload(read_input(args.input), runtime)
        elif args.command == "consumer" and args.consumer_command == "set":
            payload = set_consumer_status(
                args.consumer,
                args.tweet_id,
                args.status,
                runtime,
                reason=args.reason,
                output=args.output,
            )
        elif args.command == "export":
            tweet_ids = parse_tweet_ids(args.tweet_ids)
            if args.tweet_ids_file:
                tweet_ids.extend(read_tweet_ids_file(args.tweet_ids_file))
            items = export_tweets(
                runtime,
                tweet_ids=tweet_ids,
                user=args.user,
                since_id=args.since_id,
                until_id=args.until_id,
                limit=args.limit,
            )
            if args.format == "jsonl":
                output_jsonl(items)
                return 0
            payload = {
                "ok": True,
                "runtime": str(runtime),
                "count": len(items),
                "items": items,
            }
        elif args.command == "window" and args.window_command == "get":
            snapshot = read_window_snapshot(
                runtime,
                args.user,
                args.window_start,
                args.window_end,
            )
            payload = window_payload(runtime, snapshot, include_items=args.include_items)
        elif args.command == "window" and args.window_command == "put":
            payload = put_window(
                read_input(args.input),
                runtime,
                username=args.user,
                window_start=args.window_start,
                window_end=args.window_end,
                limit=args.limit,
                grace_minutes=args.grace_minutes,
                now=args.now or now_iso(),
                include_items=args.include_items,
            )
        else:
            parser.error("unknown command")
            return 2
    except Exception as exc:
        payload = {"ok": False, "error": str(exc), "runtime": str(runtime)}
        output(payload, args.pretty)
        return 1

    output(payload, args.pretty)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
