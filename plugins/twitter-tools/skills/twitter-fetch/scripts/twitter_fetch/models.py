from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_tweet_url(url: str) -> tuple[str, str]:
    """Return (username, tweet_id) from common X/Twitter status URLs."""
    patterns = [
        r"(?:x\.com|twitter\.com)/([A-Za-z0-9_]{1,15})/status/(\d+)",
        r"(?:x\.com|twitter\.com)/i/web/status/(\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if not match:
            continue
        if len(match.groups()) == 2:
            username, tweet_id = match.group(1), match.group(2)
        else:
            username, tweet_id = "", match.group(1)
        if username and not re.match(r"^[A-Za-z0-9_]{1,15}$", username):
            raise ValueError(f"Invalid username format: {username}")
        if not tweet_id.isdigit():
            raise ValueError(f"Invalid tweet ID format: {tweet_id}")
        return username, tweet_id
    raise ValueError(f"Cannot parse tweet URL: {url}")


def parse_twitter_date(value: str) -> str:
    if not value:
        return ""
    try:
        return datetime.strptime(value, "%a %b %d %H:%M:%S %z %Y").strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    except Exception:
        return value


def empty_stats() -> dict[str, int]:
    return {
        "likes": 0,
        "retweets": 0,
        "bookmarks": 0,
        "views": 0,
        "replies": 0,
        "quotes": 0,
    }


def standard_response(
    *,
    mode: str,
    source: str,
    input_value: dict[str, Any],
    items: list[dict[str, Any]] | None = None,
    error: dict[str, Any] | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "ok": error is None,
        "mode": mode,
        "source": source,
        "fetched_at": now_iso(),
        "input": input_value,
        "items": items or [],
        "error": error,
    }
    if meta is not None:
        payload["meta"] = meta
    return payload


def standard_error(
    code: str,
    message: str,
    *,
    provider: str,
    retryable: bool = False,
) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "provider": provider,
        "retryable": retryable,
    }


def mock_tweet(url: str) -> dict[str, Any]:
    username, tweet_id = parse_tweet_url(url)
    username = username or "unknown"
    return {
        "id": tweet_id,
        "url": url,
        "author": username,
        "screen_name": username,
        "created_at": "2026-01-01T00:00:00Z",
        "lang": "en",
        "text": f"mock tweet {tweet_id}",
        "full_text": f"mock tweet {tweet_id}",
        "is_article": False,
        "article": None,
        "media": None,
        "media_count": 0,
        "stats": empty_stats(),
        "conversation_id": tweet_id,
        "is_reply": False,
        "in_reply_to": "",
        "is_thread_part": False,
        "is_quote": False,
        "is_retweet": False,
        "quote": None,
    }


def mock_timeline(username: str) -> list[dict[str, Any]]:
    return [
        {
            **mock_tweet(f"https://x.com/{username}/status/100"),
            "author": username,
            "screen_name": username,
            "text": "mock timeline tweet",
            "full_text": "mock timeline tweet",
            "conversation_id": "100",
        }
    ]
