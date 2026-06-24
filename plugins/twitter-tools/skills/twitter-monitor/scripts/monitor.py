#!/usr/bin/env python3
"""Run the stateful Twitter monitor core."""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fetch_timeline import fetch_timeline_window, ingest_tweet_pool
from twitter_fetch_runner import run_twitter_fetch


DEFAULT_RUNTIME = Path("/Users/saberrao/ai-workspace/content-creation/.twitter-monitor")
SEEN_STATUSES = {"saved", "skipped", "fetched"}
SHORT_TEXT_LIMIT = 40
DEFAULT_INTERVAL_MINUTES = 60
DEFAULT_MAX_SCAN_PER_USER = 50
DEFAULT_WINDOW_GRACE_MINUTES = 10


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


def current_time() -> datetime:
    parsed = parse_iso_datetime(now_iso())
    if parsed is None:
        return datetime.now(timezone.utc)
    return parsed


def runtime_dir(env: dict[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    override = env.get("TWITTER_MONITOR_RUNTIME")
    if override:
        return Path(override).expanduser()
    return DEFAULT_RUNTIME


def parse_scalar(value: str) -> Any:
    value = value.strip()
    if value.startswith(("'", '"')) and value.endswith(("'", '"')):
        return value[1:-1]
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    try:
        return int(value)
    except ValueError:
        return value


def load_config(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore
    except Exception:
        return parse_config_subset(text)
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError(f"config must be an object: {path}")
    return data


def parse_config_subset(text: str) -> dict[str, Any]:
    config: dict[str, Any] = {"users": [], "settings": {}, "topics": [], "sinks": {}}
    section = ""
    current_topic: dict[str, Any] | None = None
    in_topic_users = False
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if not line.startswith(" "):
            section = line.rstrip(":")
            current_topic = None
            in_topic_users = False
            continue
        stripped = line.strip()
        if section == "users" and stripped.startswith("- username:"):
            config["users"].append({"username": parse_scalar(stripped.split(":", 1)[1])})
            continue
        if section == "topics":
            if stripped.startswith("- name:"):
                current_topic = {"name": parse_scalar(stripped.split(":", 1)[1]), "users": []}
                config["topics"].append(current_topic)
                in_topic_users = False
                continue
            if stripped == "users:":
                in_topic_users = True
                continue
            if in_topic_users and stripped.startswith("- ") and current_topic is not None:
                current_topic["users"].append(parse_scalar(stripped[2:]))
                continue
        if section == "settings" and ":" in stripped:
            key, value = stripped.split(":", 1)
            config["settings"][key.strip()] = parse_scalar(value)
    return config


def configured_users(config: dict[str, Any]) -> list[str]:
    users = []
    for item in config.get("users") or []:
        if isinstance(item, dict) and item.get("username"):
            users.append(str(item["username"]).lstrip("@"))
    for topic in config.get("topics") or []:
        if not isinstance(topic, dict):
            continue
        for username in topic.get("users") or []:
            users.append(str(username).lstrip("@"))
    seen = set()
    unique = []
    for user in users:
        key = user.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(user)
    return unique


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 3, "users": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"state must be an object: {path}")
    data["version"] = 3
    data.setdefault("users", {})
    return data


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def user_state(state: dict[str, Any], username: str) -> dict[str, Any]:
    users = state.setdefault("users", {})
    entry = users.setdefault(username, {})
    entry.setdefault("items", {})
    return entry


def item_status(user_entry: dict[str, Any], tweet_id: str) -> str:
    item = user_entry.get("items", {}).get(tweet_id, {})
    return str(item.get("status", ""))


def setting_minutes(
    settings: dict[str, Any], key: str, default: int, *, minimum: int = 1
) -> int:
    try:
        raw = settings.get(key)
        value = int(default if raw is None or raw == "" else raw)
    except (TypeError, ValueError):
        value = default
    return max(value, minimum)


def scan_limit(settings: dict[str, Any]) -> int:
    try:
        raw = settings.get("max_scan_per_user")
        value = int(DEFAULT_MAX_SCAN_PER_USER if raw is None or raw == "" else raw)
    except (TypeError, ValueError):
        value = DEFAULT_MAX_SCAN_PER_USER
    return max(value, 1)


def floor_to_interval(dt: datetime, interval_minutes: int) -> datetime:
    interval_seconds = interval_minutes * 60
    timestamp = int(dt.timestamp())
    floored = timestamp - (timestamp % interval_seconds)
    return datetime.fromtimestamp(floored, timezone.utc)


def compute_closed_window(settings: dict[str, Any], now: datetime) -> tuple[datetime, datetime, int]:
    interval = setting_minutes(settings, "interval_minutes", DEFAULT_INTERVAL_MINUTES)
    grace = setting_minutes(
        settings,
        "window_grace_minutes",
        DEFAULT_WINDOW_GRACE_MINUTES,
        minimum=0,
    )
    boundary = floor_to_interval(now, interval)
    if now < boundary + timedelta(minutes=grace):
        boundary = boundary - timedelta(minutes=interval)
    return boundary - timedelta(minutes=interval), boundary, grace


def has_url(text: str) -> bool:
    return bool(re.search(r"https?://|t\.co/", text))


def skip_reason(item: dict[str, Any], settings: dict[str, Any]) -> str | None:
    if not settings.get("include_retweets", False) and item.get("is_retweet"):
        return "retweet"
    if not settings.get("include_replies", False) and item.get("is_reply") and not item.get("is_quote"):
        return "reply"
    text = (item.get("full_text") or item.get("text") or "").strip()
    media_count = int(item.get("media_count") or 0)
    if (
        len(text) < SHORT_TEXT_LIMIT
        and not item.get("is_quote")
        and media_count == 0
        and not item.get("media")
        and not has_url(text)
    ):
        return "short_no_url"
    return None


def mark_item(
    user_entry: dict[str, Any],
    tweet_id: str,
    status: str,
    *,
    source_url: str = "",
    created_at: str = "",
    reason: str = "",
    error: str = "",
    outputs: dict[str, Any] | None = None,
) -> None:
    item = {
        "status": status,
        "source_url": source_url,
        "updated_at": now_iso(),
    }
    if created_at:
        item["created_at"] = created_at
    if reason:
        item["reason"] = reason
    if error:
        item["error"] = error
    if outputs:
        item["outputs"] = outputs
    user_entry.setdefault("items", {})[tweet_id] = item


def fetch_single(item: dict[str, Any], expand_thread: bool) -> dict[str, Any]:
    args = ["single", "--url", item["url"]]
    if expand_thread:
        args.append("--include-thread")
    return run_twitter_fetch(args)


def run_user(username: str, config: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    settings = config.get("settings") or {}
    limit = scan_limit(settings)
    expand_thread = bool(settings.get("expand_thread", True))
    mark_skipped = bool(settings.get("mark_skipped_as_seen", True))
    user_entry = user_state(state, username)
    now = current_time()
    window_start, window_end, grace_minutes = compute_closed_window(settings, now)
    report = {
        "timeline_count": 0,
        "within_window": 0,
        "outside_window": 0,
        "already_seen": 0,
        "skipped": 0,
        "fetched": 0,
        "failed": 0,
        "interval_minutes": setting_minutes(
            settings,
            "interval_minutes",
            DEFAULT_INTERVAL_MINUTES,
        ),
        "window_start": format_iso(window_start),
        "window_end": format_iso(window_end),
        "window_grace_minutes": grace_minutes,
        "window_status": "",
        "cache_hit": False,
        "scan_limit": limit,
    }
    timeline = fetch_timeline_window(
        username,
        format_iso(window_start),
        format_iso(window_end),
        limit,
        grace_minutes,
    )
    items = timeline.get("items") or []
    snapshot = timeline.get("snapshot") or {}
    report["timeline_count"] = int(timeline.get("timeline_count") or len(items))
    report["within_window"] = int(timeline.get("within_window") or len(items))
    report["outside_window"] = int(timeline.get("outside_window") or 0)
    report["window_status"] = str(snapshot.get("status") or "")
    report["cache_hit"] = bool(timeline.get("cache_hit"))
    user_entry["last_checked"] = format_iso(now)
    user_entry["window_start"] = format_iso(window_start)
    user_entry["window_end"] = format_iso(window_end)

    for item in items:
        tweet_id = str(item.get("id") or "")
        if not tweet_id:
            continue
        if item_status(user_entry, tweet_id) in SEEN_STATUSES:
            report["already_seen"] += 1
            continue
        reason = skip_reason(item, settings)
        if reason:
            report["skipped"] += 1
            if mark_skipped:
                mark_item(
                    user_entry,
                    tweet_id,
                    "skipped",
                    source_url=str(item.get("url") or ""),
                    created_at=str(item.get("created_at") or ""),
                    reason=reason,
                )
            continue
        try:
            full_payload = fetch_single(item, expand_thread)
            ingest_tweet_pool(full_payload)
        except Exception as exc:
            report["failed"] += 1
            mark_item(
                user_entry,
                tweet_id,
                "failed",
                source_url=str(item.get("url") or ""),
                created_at=str(item.get("created_at") or ""),
                error=str(exc),
            )
            continue
        report["fetched"] += 1
        mark_item(
            user_entry,
            tweet_id,
            "fetched",
            source_url=str(item.get("url") or ""),
            created_at=str(item.get("created_at") or ""),
            outputs={"tweet_pool": True},
        )
    user_entry["last_success_at"] = format_iso(now)
    return report


def run_monitor(runtime: Path | None = None) -> dict[str, Any]:
    runtime = runtime or runtime_dir()
    config_path = runtime / "config.yaml"
    state_path = runtime / ".state.json"
    config = load_config(config_path)
    state = load_state(state_path)
    state["last_run"] = now_iso()
    report = {"ok": True, "runtime": str(runtime), "users": {}}

    for username in configured_users(config):
        try:
            report["users"][username] = run_user(username, config, state)
        except Exception as exc:
            report["ok"] = False
            report["users"][username] = {"error": str(exc)}

    save_state(state_path, state)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the configured Twitter monitor")
    parser.add_argument("--runtime", default=None, help="Twitter monitor runtime directory")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON report")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run", help="Fetch configured timelines and update monitor state")
    run.add_argument("--pretty", action="store_true", help="Pretty-print JSON report")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    runtime = Path(args.runtime).expanduser() if args.runtime else runtime_dir()
    report = run_monitor(runtime)
    print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
