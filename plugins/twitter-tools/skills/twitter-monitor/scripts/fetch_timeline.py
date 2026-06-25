#!/usr/bin/env python3
"""Monitor timeline wrapper around twitter-fetch with tweet-pool side caching."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from twitter_fetch_runner import run_twitter_fetch


TWEET_POOL_ENV_BIN = "TWEET_POOL_BIN"
TWEET_POOL_RELATIVE_PATH = Path("skills/tweet-pool/bin/tweet-pool")


def is_executable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def iter_tweet_pool_runners(home: Path) -> Iterable[Path]:
    roots = [
        home / ".codex/plugins/cache",
        home / ".claude/plugins/cache",
        home / ".agents/plugins/cache",
    ]
    for root in roots:
        if not root.exists():
            continue
        matches = [
            path for path in root.glob(f"**/{TWEET_POOL_RELATIVE_PATH}") if is_executable(path)
        ]
        matches.sort(key=lambda p: (p.stat().st_mtime, str(p)), reverse=True)
        yield from matches


def iter_source_tweet_pool_runners(home: Path) -> Iterable[Path]:
    candidates = [
        home / "ai-workspace/awesome-ai/plugins/twitter-tools/skills/tweet-pool/bin/tweet-pool",
        home / ".codex/skills/tweet-pool/bin/tweet-pool",
        home / ".claude/skills/tweet-pool/bin/tweet-pool",
        home / ".agents/skills/tweet-pool/bin/tweet-pool",
    ]
    for candidate in candidates:
        if is_executable(candidate):
            yield candidate


def resolve_tweet_pool_bin() -> Path:
    override = os.environ.get(TWEET_POOL_ENV_BIN)
    if override:
        override_path = Path(override).expanduser()
        if is_executable(override_path):
            return override_path
        raise RuntimeError(f"{TWEET_POOL_ENV_BIN} is set but not executable: {override_path}")

    from_path = shutil.which("tweet-pool")
    if from_path:
        return Path(from_path)

    home = Path.home()
    for runner in iter_tweet_pool_runners(home):
        return runner

    for runner in iter_source_tweet_pool_runners(home):
        return runner

    raise RuntimeError(
        "tweet-pool runner not found. Install twitter-tools, "
        f"or set {TWEET_POOL_ENV_BIN}=/absolute/path/to/bin/tweet-pool."
    )


def ingest_tweet_pool(payload: dict[str, Any]) -> dict[str, Any]:
    runner = resolve_tweet_pool_bin()
    return run_tweet_pool(["ingest", "--input", "-"], payload, runner=runner)


def run_tweet_pool(
    args: list[str],
    payload: dict[str, Any] | None = None,
    *,
    runner: Path | None = None,
) -> dict[str, Any]:
    runner = runner or resolve_tweet_pool_bin()
    completed = subprocess.run(
        [str(runner), *args],
        input=json.dumps(payload, ensure_ascii=False) if payload is not None else None,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "tweet-pool failed "
            f"(exit {completed.returncode}): {completed.stderr.strip() or completed.stdout.strip()}"
        )
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"tweet-pool returned non-JSON output: {exc}") from exc


def maybe_ingest_tweet_pool(payload: dict[str, Any]) -> None:
    if os.environ.get("TWITTER_MONITOR_TWEET_POOL", "1") in {"0", "false", "False"}:
        return
    if payload.get("error") or not payload.get("items"):
        return
    try:
        ingest_tweet_pool(payload)
    except RuntimeError as exc:
        print(f"Warning: tweet-pool ingest failed: {exc}", file=sys.stderr)


def window_summary(payload: dict[str, Any], *, cache_hit: bool) -> dict[str, Any]:
    snapshot = payload.get("snapshot") or {}
    tweet_ids = snapshot.get("tweet_ids") or []
    observed_count = int(snapshot.get("observed_count") or 0)
    return {
        "ok": True,
        "items": payload.get("items") or [],
        "snapshot": snapshot,
        "cache_hit": cache_hit,
        "timeline_count": observed_count,
        "within_window": len(tweet_ids),
        "outside_window": max(observed_count - len(tweet_ids), 0),
    }


def fetch_window(
    username: str,
    window_start: str,
    window_end: str,
    limit: int,
    grace_minutes: int,
    *,
    fetch_mode: str = "timeline",
    history_max_pages: int = 3,
) -> dict[str, Any]:
    cache_payload = run_tweet_pool(
        [
            "window",
            "get",
            "--user",
            username,
            "--window-start",
            window_start,
            "--window-end",
            window_end,
            "--include-items",
        ]
    )
    snapshot = cache_payload.get("snapshot") or {}
    snapshot_source_mode = str(snapshot.get("source_mode") or "timeline")
    if (
        cache_payload.get("found")
        and snapshot.get("status") == "finalized"
        and snapshot_source_mode == fetch_mode
    ):
        return window_summary(cache_payload, cache_hit=True)

    if fetch_mode == "history":
        payload = run_twitter_fetch(
            [
                "history",
                "--user",
                username,
                "--page-size",
                str(limit),
                "--max-pages",
                str(max(history_max_pages, 1)),
            ]
        )
        coverage_limit = limit * max(history_max_pages, 1)
    elif fetch_mode == "timeline":
        payload = run_twitter_fetch(["timeline", "--user", username, "--limit", str(limit)])
        coverage_limit = limit
    else:
        raise ValueError(f"unsupported fetch_mode: {fetch_mode}")

    window_payload = run_tweet_pool(
        [
            "window",
            "put",
            "--user",
            username,
            "--window-start",
            window_start,
            "--window-end",
            window_end,
            "--input",
            "-",
            "--limit",
            str(coverage_limit),
            "--grace-minutes",
            str(grace_minutes),
            "--now",
            now_iso(),
            "--include-items",
        ],
        payload,
    )
    return window_summary(window_payload, cache_hit=False)


def fetch_timeline_window(
    username: str,
    window_start: str,
    window_end: str,
    limit: int,
    grace_minutes: int,
) -> dict[str, Any]:
    return fetch_window(
        username,
        window_start,
        window_end,
        limit,
        grace_minutes,
        fetch_mode="timeline",
    )


def fetch_history_window(
    username: str,
    window_start: str,
    window_end: str,
    limit: int,
    grace_minutes: int,
    *,
    history_max_pages: int = 3,
) -> dict[str, Any]:
    return fetch_window(
        username,
        window_start,
        window_end,
        limit,
        grace_minutes,
        fetch_mode="history",
        history_max_pages=history_max_pages,
    )


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def standard_error_payload(args: argparse.Namespace, exc: RuntimeError) -> dict[str, Any]:
    return {
        "ok": False,
        "mode": "timeline",
        "source": "twitter-monitor",
        "fetched_at": now_iso(),
        "input": {
            "user": args.user,
            "limit": args.limit,
            "cookie_file": args.cookie_file,
        },
        "items": [],
        "error": {
            "code": "timeline_fetch_failed",
            "message": str(exc),
            "provider": "twitter-monitor",
            "retryable": True,
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch Twitter user timeline via twitter-fetch")
    parser.add_argument("--user", required=True, help="Twitter username (without @)")
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Deprecated no-op; output is always the standard JSON envelope",
    )
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--pretty", action="store_true")
    parser.add_argument("--cookie-file", default=None)
    parser.add_argument("--mock", action="store_true", help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    standard_args = ["timeline", "--user", args.user, "--limit", str(args.limit)]
    if args.cookie_file:
        standard_args.extend(["--cookie-file", args.cookie_file])
    if args.mock:
        standard_args.append("--mock")
    try:
        payload = run_twitter_fetch(standard_args)
    except RuntimeError as exc:
        payload = standard_error_payload(args, exc)
    else:
        maybe_ingest_tweet_pool(payload)

    print(json.dumps(payload, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
