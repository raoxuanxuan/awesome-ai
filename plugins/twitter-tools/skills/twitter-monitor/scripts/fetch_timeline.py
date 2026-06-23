#!/usr/bin/env python3
"""Compatibility wrapper for twitter-fetch timeline."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from twitter_fetch_runner import run_twitter_fetch


def timeline_to_legacy(payload: dict[str, Any], username: str) -> dict[str, Any]:
    if payload.get("error"):
        error = payload["error"]
        return {
            "username": username,
            "tweets": [],
            "tweet_count": 0,
            "fetched_at": payload.get("fetched_at", ""),
            "error": error.get("message", str(error)) if isinstance(error, dict) else str(error),
        }

    tweets = []
    for item in payload.get("items", []):
        stats = item.get("stats", {}) or {}
        text = item.get("text") or item.get("full_text", "")
        tweets.append(
            {
                "id": item.get("id", ""),
                "url": item.get("url", ""),
                "text": text[:280],
                "full_text_length": len(item.get("full_text") or text),
                "author": item.get("author", ""),
                "screen_name": item.get("screen_name", ""),
                "lang": item.get("lang", "unknown"),
                "is_retweet": bool(item.get("is_retweet")),
                "retweeted_user": None,
                "is_quote": bool(item.get("is_quote")),
                "is_thread_part": bool(item.get("is_thread_part")),
                "conversation_id": item.get("conversation_id", ""),
                "media_count": item.get("media_count", 0),
                "created_at": item.get("created_at", ""),
                "created_date": (item.get("created_at", "") or "")[:10],
                "favorite_count": stats.get("likes", 0),
                "retweet_count": stats.get("retweets", 0),
            }
        )
    return {
        "username": username,
        "tweets": tweets,
        "tweet_count": len(tweets),
        "fetched_at": payload.get("fetched_at", ""),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch Twitter user timeline via twitter-fetch")
    parser.add_argument("--user", required=True, help="Twitter username (without @)")
    parser.add_argument("--json", action="store_true", dest="json_output")
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
        legacy_payload = {
            "username": args.user,
            "tweets": [],
            "tweet_count": 0,
            "fetched_at": "",
            "error": str(exc),
        }
    else:
        legacy_payload = timeline_to_legacy(payload, args.user)

    if args.json_output or args.pretty:
        print(json.dumps(legacy_payload, ensure_ascii=False, indent=2 if args.pretty else None))
    else:
        if legacy_payload.get("error"):
            print(f"Error: {legacy_payload['error']}", file=sys.stderr)
            return 1
        print(f"=== @{legacy_payload['username']} - {legacy_payload['tweet_count']} tweets ===\n")
        for tweet in legacy_payload["tweets"]:
            prefix = "[RT] " if tweet["is_retweet"] else "[QT] " if tweet["is_quote"] else ""
            lang_tag = f"[{tweet['lang']}]" if tweet["lang"] != "unknown" else ""
            media_tag = f" [{tweet['media_count']} media]" if tweet["media_count"] else ""
            text_preview = tweet["text"][:120].replace("\n", " ")
            if len(tweet["text"]) > 120:
                text_preview += "..."
            print(f"  {tweet['id']} {lang_tag} {tweet['created_date']}")
            print(f"    {prefix}{text_preview}{media_tag}")
            print()
    return 0 if "error" not in legacy_payload else 1


if __name__ == "__main__":
    raise SystemExit(main())
