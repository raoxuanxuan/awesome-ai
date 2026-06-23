from __future__ import annotations

from typing import Any


def single_to_legacy(payload: dict[str, Any], source_url: str) -> dict[str, Any]:
    if not payload.get("items"):
        out = {"url": source_url}
        if payload.get("error"):
            out["error"] = payload["error"]["message"]
        return out
    item = payload["items"][0]
    stats = item.get("stats", {}) or {}
    tweet = {
        "text": item.get("full_text") or item.get("text", ""),
        "author": item.get("author", ""),
        "screen_name": item.get("screen_name", ""),
        "likes": stats.get("likes", 0),
        "retweets": stats.get("retweets", 0),
        "bookmarks": stats.get("bookmarks", 0),
        "views": stats.get("views", 0),
        "replies_count": stats.get("replies", 0),
        "created_at": item.get("created_at", ""),
        "is_note_tweet": False,
        "is_article": bool(item.get("is_article")),
        "lang": item.get("lang", ""),
    }
    if item.get("media"):
        tweet["media"] = item["media"]
    if item.get("quote"):
        quote = item["quote"]
        q_stats = quote.get("stats", {}) or {}
        tweet["quote"] = {
            "text": quote.get("text", ""),
            "author": quote.get("author", ""),
            "screen_name": quote.get("screen_name", ""),
            "likes": q_stats.get("likes", 0),
            "retweets": q_stats.get("retweets", 0),
            "views": q_stats.get("views", 0),
        }
        if quote.get("media"):
            tweet["quote"]["media"] = quote["media"]
    if item.get("article"):
        tweet["article"] = item["article"]
    return {
        "url": source_url,
        "username": item.get("screen_name", ""),
        "tweet_id": item.get("id", ""),
        "tweet": tweet,
    }


def timeline_to_legacy(payload: dict[str, Any], username: str) -> dict[str, Any]:
    if payload.get("error"):
        return {
            "username": username,
            "tweets": [],
            "tweet_count": 0,
            "fetched_at": payload.get("fetched_at", ""),
            "error": payload["error"]["message"],
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
