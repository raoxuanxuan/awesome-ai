from __future__ import annotations

import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

from . import models


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
SYNDICATION_URL = (
    "https://syndication.twitter.com/srv/timeline-profile/screen-name/{username}"
)
GRAPHQL_BEARER = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs"
    "%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)
GRAPHQL_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Safari/605.1.15"
)
GRAPHQL_BUNDLE_HOME = "https://x.com/"
GRAPHQL_FALLBACK_HASHES = {
    "UserTweetsAndReplies": "D5eKzDa5ZoJuC1TCeAXbWA",
    "UserByScreenName": "IGgvgiOx4QZndDHuD3x9TQ",
    "SearchTimeline": "Bcw3RzK-PatNAmbnw54hFw",
}
TWITTER_SNOWFLAKE_EPOCH = 1288834974657
REPLIES_PROVIDER_ORDER = ("graphql", "browseros", "camofox_nitter", "direct_nitter")


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _extract_media(tweet_obj: dict[str, Any]) -> dict[str, Any] | None:
    media_data: dict[str, Any] = {}
    media = tweet_obj.get("media", {}) or {}
    all_media = media.get("all", []) or []
    photos = [item for item in all_media if item.get("type") == "photo"]
    if photos:
        media_data["images"] = []
        for photo in photos:
            image = {"url": photo.get("url", "")}
            if photo.get("width"):
                image["width"] = photo.get("width")
            if photo.get("height"):
                image["height"] = photo.get("height")
            media_data["images"].append(image)
    videos = media.get("videos", []) or []
    if videos:
        media_data["videos"] = []
        for video in videos:
            item: dict[str, Any] = {}
            for src_key, dst_key in (
                ("url", "url"),
                ("duration", "duration"),
                ("thumbnail_url", "thumbnail"),
            ):
                if video.get(src_key):
                    item[dst_key] = video[src_key]
            if video.get("variants"):
                item["variants"] = [
                    {
                        key: value
                        for key, value in variant.items()
                        if key in {"url", "bitrate", "content_type"} and value
                    }
                    for variant in video["variants"]
                ]
            if item:
                media_data["videos"].append(item)
    return media_data or None


def id_to_datetime(tweet_id: int) -> datetime:
    return datetime.fromtimestamp(
        ((tweet_id >> 22) + TWITTER_SNOWFLAKE_EPOCH) / 1000,
        tz=timezone.utc,
    )


def normalize_fxtwitter_tweet(
    raw: dict[str, Any], *, source_url: str, username: str, tweet_id: str
) -> dict[str, Any]:
    tweet = raw["tweet"]
    author = tweet.get("author", {}) or {}
    stats = models.empty_stats()
    stats.update(
        {
            "likes": _int(tweet.get("likes")),
            "retweets": _int(tweet.get("retweets")),
            "bookmarks": _int(tweet.get("bookmarks")),
            "views": _int(tweet.get("views")),
            "replies": _int(tweet.get("replies")),
            "quotes": _int(tweet.get("quotes")),
        }
    )

    article = None
    if tweet.get("article"):
        article_raw = tweet["article"]
        blocks = article_raw.get("content", {}).get("blocks", []) or []
        full_text = "\n\n".join(
            block.get("text", "") for block in blocks if block.get("text")
        )
        article = {
            "title": article_raw.get("title", ""),
            "preview_text": article_raw.get("preview_text", ""),
            "created_at": article_raw.get("created_at", ""),
            "full_text": full_text,
            "word_count": len(full_text.split()),
            "char_count": len(full_text),
        }
        images = []
        cover = article_raw.get("cover_media", {}) or {}
        cover_url = cover.get("media_info", {}).get("original_img_url")
        if cover_url:
            images.append({"type": "cover", "url": cover_url})
        for entity in article_raw.get("media_entities", []) or []:
            image_url = entity.get("media_info", {}).get("original_img_url")
            if image_url:
                images.append({"type": "image", "url": image_url})
        if images:
            article["images"] = images
            article["image_count"] = len(images)

    quote = None
    if tweet.get("quote"):
        q = tweet["quote"]
        q_author = q.get("author", {}) or {}
        quote = {
            "text": q.get("text", ""),
            "author": q_author.get("name", ""),
            "screen_name": q_author.get("screen_name", ""),
            "stats": {
                "likes": _int(q.get("likes")),
                "retweets": _int(q.get("retweets")),
                "bookmarks": _int(q.get("bookmarks")),
                "views": _int(q.get("views")),
                "replies": _int(q.get("replies")),
                "quotes": _int(q.get("quotes")),
            },
            "media": _extract_media(q),
        }

    media = _extract_media(tweet)
    return {
        "id": str(tweet.get("id") or tweet_id),
        "url": tweet.get("url") or source_url,
        "author": author.get("name", ""),
        "screen_name": author.get("screen_name") or username,
        "created_at": models.parse_twitter_date(tweet.get("created_at", "")),
        "lang": tweet.get("lang", ""),
        "text": tweet.get("text", ""),
        "full_text": tweet.get("text", ""),
        "is_article": bool(article),
        "article": article,
        "media": media,
        "media_count": len(media.get("images", [])) if media else 0,
        "stats": stats,
        "conversation_id": str(tweet.get("conversation_id") or tweet_id),
        "is_reply": bool(tweet.get("in_reply_to_status_id")),
        "in_reply_to": str(tweet.get("in_reply_to_status_id") or ""),
        "is_thread_part": False,
        "is_quote": bool(quote),
        "is_retweet": False,
        "quote": quote,
    }


def fetch_single_fxtwitter(url: str, timeout: int = 30) -> dict[str, Any]:
    username, tweet_id = models.parse_tweet_url(url)
    if not username:
        return models.standard_response(
            mode="single",
            source="fxtwitter",
            input_value={"url": url},
            error=models.standard_error(
                "missing_username",
                "FxTwitter requires a username in the status URL",
                provider="fxtwitter",
                retryable=False,
            ),
        )
    api_url = f"https://api.fxtwitter.com/{username}/status/{tweet_id}"
    for attempt in range(2):
        try:
            req = urllib.request.Request(api_url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = json.loads(resp.read().decode())
            if raw.get("code") != 200:
                return models.standard_response(
                    mode="single",
                    source="fxtwitter",
                    input_value={"url": url},
                    error=models.standard_error(
                        "provider_error",
                        f"FxTwitter returned code {raw.get('code')}: {raw.get('message', 'Unknown')}",
                        provider="fxtwitter",
                        retryable=True,
                    ),
                )
            item = normalize_fxtwitter_tweet(
                raw, source_url=url, username=username, tweet_id=tweet_id
            )
            return models.standard_response(
                mode="single",
                source="fxtwitter",
                input_value={"url": url},
                items=[item],
            )
        except urllib.error.URLError as exc:
            if attempt == 0:
                time.sleep(1)
                continue
            return models.standard_response(
                mode="single",
                source="fxtwitter",
                input_value={"url": url},
                error=models.standard_error(
                    "network_error", str(exc), provider="fxtwitter", retryable=True
                ),
            )
        except Exception as exc:
            return models.standard_response(
                mode="single",
                source="fxtwitter",
                input_value={"url": url},
                error=models.standard_error(
                    "unexpected_error", str(exc), provider="fxtwitter", retryable=False
                ),
            )


def _load_cookie_header(cookie_file: str | None) -> str | None:
    if not cookie_file:
        return None
    try:
        with open(cookie_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        auth_token = data.get("auth_token", "")
        ct0 = data.get("ct0", "")
        if not auth_token or not ct0 or auth_token == "从浏览器复制":
            return None
        return f"auth_token={auth_token}; ct0={ct0}"
    except Exception:
        return None


def _fetch_syndication_html(url: str, cookie_header: str | None) -> str:
    cmd = ["curl", "-s", "-f", "--max-time", "15", "-H", f"User-Agent: {USER_AGENT}"]
    if cookie_header:
        cmd.extend(["--cookie", cookie_header])
    cmd.append(url)
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    if proc.returncode == 0:
        return proc.stdout
    headers = {"User-Agent": USER_AGENT}
    if cookie_header:
        headers["Cookie"] = cookie_header
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8")


def _find_entries(obj: Any) -> list[Any] | None:
    if isinstance(obj, dict):
        if isinstance(obj.get("entries"), list):
            return obj["entries"]
        for value in obj.values():
            result = _find_entries(value)
            if result is not None:
                return result
    elif isinstance(obj, list):
        for item in obj:
            result = _find_entries(item)
            if result is not None:
                return result
    return None


def normalize_syndication_entry(entry: dict[str, Any]) -> dict[str, Any] | None:
    tweet = entry.get("content", {}).get("tweet", {})
    if not tweet:
        return None
    tweet_id = str(tweet.get("id_str") or "")
    if not tweet_id:
        return None
    full_text = tweet.get("full_text", tweet.get("text", ""))
    user = tweet.get("user", {}) or {}
    screen_name = user.get("screen_name", "")
    conversation_id = str(tweet.get("conversation_id_str") or "")
    entities = tweet.get("entities", {}) or {}
    extended = tweet.get("extended_entities", {}) or {}
    media_count = max(
        len(entities.get("media", []) or []),
        len(extended.get("media", []) or []),
    )
    return {
        "id": tweet_id,
        "url": f"https://x.com/{screen_name}/status/{tweet_id}",
        "author": user.get("name", ""),
        "screen_name": screen_name,
        "created_at": models.parse_twitter_date(tweet.get("created_at", "")),
        "lang": tweet.get("lang", "unknown"),
        "text": full_text[:280],
        "full_text": full_text,
        "is_article": False,
        "article": None,
        "media": None,
        "media_count": media_count,
        "stats": {
            **models.empty_stats(),
            "likes": _int(tweet.get("favorite_count")),
            "retweets": _int(tweet.get("retweet_count")),
        },
        "conversation_id": conversation_id,
        "is_reply": bool(tweet.get("in_reply_to_status_id_str")),
        "in_reply_to": str(tweet.get("in_reply_to_status_id_str") or ""),
        "is_thread_part": bool(conversation_id and conversation_id != tweet_id),
        "is_quote": bool(tweet.get("is_quote_status") or tweet.get("quoted_status")),
        "is_retweet": full_text.startswith("RT @") or "retweeted_status" in tweet,
        "quote": None,
    }


def normalize_graphql_tweet(
    tr: dict[str, Any], want_screen: str | None = None
) -> dict[str, Any] | None:
    if tr.get("__typename") == "TweetWithVisibilityResults":
        tr = tr.get("tweet", {})
    legacy = tr.get("legacy")
    if not legacy:
        return None
    user_res = tr.get("core", {}).get("user_results", {}).get("result", {})
    user_core = user_res.get("core", {}) or {}
    user_legacy = user_res.get("legacy", {}) or {}
    screen_name = user_core.get("screen_name") or user_legacy.get("screen_name", "")
    author = user_core.get("name") or user_legacy.get("name", "")
    if not screen_name:
        return None
    if want_screen and screen_name.lower() != want_screen.lower():
        return None
    tweet_id = str(legacy.get("id_str") or tr.get("rest_id") or "")
    if not tweet_id:
        return None
    note = tr.get("note_tweet", {}).get("note_tweet_results", {}).get("result", {})
    full_text = note.get("text") if note else legacy.get("full_text", "")
    reply_to = str(legacy.get("in_reply_to_status_id_str") or "")
    conversation_id = str(legacy.get("conversation_id_str") or "")
    entities = legacy.get("entities", {}) or {}
    extended = legacy.get("extended_entities", {}) or {}
    media_count = max(
        len(entities.get("media", []) or []),
        len(extended.get("media", []) or []),
    )
    stats = models.empty_stats()
    stats.update(
        {
            "likes": _int(legacy.get("favorite_count")),
            "retweets": _int(legacy.get("retweet_count")),
            "replies": _int(legacy.get("reply_count")),
            "quotes": _int(legacy.get("quote_count")),
            "views": _int(tr.get("views", {}).get("count")),
        }
    )
    return {
        "id": tweet_id,
        "url": f"https://x.com/{screen_name}/status/{tweet_id}",
        "author": author,
        "screen_name": screen_name,
        "created_at": models.parse_twitter_date(legacy.get("created_at", "")),
        "lang": legacy.get("lang", "unknown"),
        "text": full_text[:280],
        "full_text": full_text,
        "is_article": False,
        "article": None,
        "media": None,
        "media_count": media_count,
        "stats": stats,
        "conversation_id": conversation_id,
        "is_reply": bool(reply_to),
        "in_reply_to": reply_to,
        "is_thread_part": bool(conversation_id and conversation_id != tweet_id),
        "is_quote": bool(legacy.get("is_quote_status")),
        "is_retweet": bool(legacy.get("retweeted_status_result"))
        or full_text.startswith("RT @"),
        "quote": None,
    }


def extract_graphql_history_page(
    payload: dict[str, Any], want_screen: str
) -> tuple[list[dict[str, Any]], str | None]:
    user = payload["data"]["user"]["result"]
    timeline = user.get("timeline_v2") or user.get("timeline")
    instructions = timeline["timeline"]["instructions"]
    items: list[dict[str, Any]] = []
    bottom: str | None = None
    for inst in instructions:
        entries = inst.get("entries") or ([inst["entry"]] if inst.get("entry") else [])
        for entry in entries:
            entry_id = entry.get("entryId", "")
            content = entry.get("content", {}) or {}
            if entry_id.startswith("cursor-bottom-"):
                bottom = content.get("value")
                continue
            if entry_id.startswith("tweet-"):
                result = (
                    content.get("itemContent", {})
                    .get("tweet_results", {})
                    .get("result", {})
                )
                item = normalize_graphql_tweet(result, want_screen)
                if item:
                    items.append(item)
            elif (
                entry_id.startswith("profile-conversation-")
                or content.get("entryType") == "TimelineTimelineModule"
            ):
                for module_item in content.get("items", []) or []:
                    result = (
                        module_item.get("item", {})
                        .get("itemContent", {})
                        .get("tweet_results", {})
                        .get("result", {})
                    )
                    item = normalize_graphql_tweet(result, want_screen)
                    if item:
                        items.append(item)
    return items, bottom


def _iter_graphql_tweet_results(obj: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(obj, dict):
        tweet_results = obj.get("tweet_results")
        if isinstance(tweet_results, dict):
            result = tweet_results.get("result")
            if isinstance(result, dict):
                found.append(result)
        for value in obj.values():
            found.extend(_iter_graphql_tweet_results(value))
    elif isinstance(obj, list):
        for item in obj:
            found.extend(_iter_graphql_tweet_results(item))
    return found


def extract_graphql_search_replies_page(
    payload: dict[str, Any], conversation_id: str
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for result in _iter_graphql_tweet_results(payload):
        item = normalize_graphql_tweet(result)
        if not item:
            continue
        if item["id"] == conversation_id:
            continue
        if item.get("conversation_id") != conversation_id:
            continue
        if item["id"] in seen:
            continue
        seen.add(item["id"])
        items.append(item)
    items.sort(key=lambda item: int(item["id"]))
    return items


def fetch_timeline_syndication(
    username: str, *, limit: int = 20, cookie_file: str | None = None
) -> dict[str, Any]:
    url = SYNDICATION_URL.format(username=username)
    try:
        html = _fetch_syndication_html(url, _load_cookie_header(cookie_file))
        match = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            html,
            re.DOTALL,
        )
        if not match:
            raise RuntimeError("Could not find __NEXT_DATA__ in response")
        next_data = json.loads(match.group(1))
        entries = _find_entries(next_data)
        if entries is None:
            raise RuntimeError("Could not find timeline entries in response")
        items = [item for entry in entries if (item := normalize_syndication_entry(entry))]
        items.sort(key=lambda item: item["id"], reverse=True)
        return models.standard_response(
            mode="timeline",
            source="syndication",
            input_value={"user": username, "limit": limit},
            items=items[:limit],
        )
    except Exception as exc:
        return models.standard_response(
            mode="timeline",
            source="syndication",
            input_value={"user": username, "limit": limit},
            error=models.standard_error(
                "provider_error", str(exc), provider="syndication", retryable=True
            ),
        )


def fetch_thread_syndication(url: str, *, limit: int = 50) -> dict[str, Any]:
    username, tweet_id = models.parse_tweet_url(url)
    if not username:
        return models.standard_response(
            mode="thread",
            source="syndication",
            input_value={"url": url},
            error=models.standard_error(
                "missing_username",
                "Thread discovery requires a username in the status URL",
                provider="syndication",
            ),
        )
    timeline = fetch_timeline_syndication(username, limit=limit)
    if not timeline["ok"]:
        timeline["mode"] = "thread"
        timeline["input"] = {"url": url}
        return timeline
    items = [
        item
        for item in timeline["items"]
        if item.get("conversation_id") == tweet_id or item.get("id") == tweet_id
    ]
    items.sort(key=lambda item: int(item["id"]))
    return models.standard_response(
        mode="thread",
        source="syndication",
        input_value={"url": url},
        items=items,
    )


def _parse_nitter_stats(raw: str) -> tuple[str, int, int, int, int]:
    stat_match = re.search(
        r"^(.*?)\s{2,}(\d[\d,]*)\s{2,}(\d[\d,]*)\s{2,}(\d[\d,]*)$",
        raw.rstrip(),
    )
    if stat_match:
        text_part = stat_match.group(1).strip()
        nums = [int(stat_match.group(i).replace(",", "")) for i in (2, 3, 4)]
        return text_part, nums[0], nums[1], nums[2], 0

    stat_match2 = re.search(
        r"^(.*?)\s{2,}(\d[\d,]*)\s{2,}(\d[\d,]*)$",
        raw.rstrip(),
    )
    if stat_match2:
        text_part = stat_match2.group(1).strip()
        nums = [int(stat_match2.group(i).replace(",", "")) for i in (2, 3)]
        return text_part, nums[0], 0, nums[1], 0

    icon_match = re.search(
        r"^(.*?)\s*\ue803\s*(\d[\d,]*)\s*\ue80c\s*\ue801\s*(\d[\d,]*)\s*\ue800\s*(\d[\d,]*)",
        raw,
    )
    if icon_match:
        return (
            icon_match.group(1).strip(),
            int(icon_match.group(2).replace(",", "")),
            0,
            int(icon_match.group(3).replace(",", "")),
            int(icon_match.group(4).replace(",", "")),
        )

    cleaned = re.sub(r"\s*[\ue800-\ue8ff]\s*[\d,]+", "", raw).strip()
    return cleaned, 0, 0, 0, 0


def _is_nitter_timestamp(value: str) -> bool:
    return bool(
        re.match(r"^\d+[smhd]$", value)
        or re.match(r"^[A-Z][a-z]{2} \d+(?:, \d{4})?$", value)
    )


def _nitter_media_dict(media_urls: list[str]) -> dict[str, Any] | None:
    if not media_urls:
        return None
    return {"images": [{"url": media_url} for media_url in media_urls]}


def parse_nitter_replies_snapshot(
    snapshot: str,
    *,
    original_author: str,
    conversation_id: str,
) -> list[dict[str, Any]]:
    replies: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    lines = snapshot.split("\n")
    n = len(lines)
    i = 0

    while i < n:
        if lines[i].strip() != "- text: Replying to":
            i += 1
            continue

        reply_id = ""
        reply_screen = ""
        author_name = ""
        time_ago = ""
        text_parts: list[str] = []
        likes = retweets = replies_count = views = 0
        stats_set = False
        media_urls: list[str] = []
        links: list[str] = []

        for j in range(i - 1, max(-1, i - 16), -1):
            prev = lines[j].strip()
            if not reply_id:
                tid_m = re.match(r"^- /url:\s+/([A-Za-z0-9_]{1,15})/status/(\d+)#m$", prev)
                if tid_m:
                    reply_screen = tid_m.group(1)
                    reply_id = tid_m.group(2)
            if not reply_screen:
                handle_m = re.match(r'^- link "@(\w+)"\s*(\[e\d+\])?:?$', prev)
                if handle_m and handle_m.group(1).lower() != original_author.lower():
                    reply_screen = handle_m.group(1)
            if not author_name:
                name_m = re.match(r'^- link "([^@#][^"]*?)"\s*(\[e\d+\])?:?$', prev)
                if name_m:
                    name = name_m.group(1).strip()
                    if (
                        name
                        and not _is_nitter_timestamp(name)
                        and name.lower() not in {"nitter", "logo", "more replies"}
                    ):
                        author_name = name
            if not time_ago:
                time_m = re.match(r'^- link "([^"]+)"\s*(\[e\d+\])?:?$', prev)
                if time_m and _is_nitter_timestamp(time_m.group(1).strip()):
                    time_ago = time_m.group(1).strip()
            if reply_id and reply_screen and author_name and time_ago:
                break

        for j in range(i + 1, min(n, i + 24)):
            fwd = lines[j].strip()
            if j > i + 1 and fwd == "- text: Replying to":
                break
            if re.match(r'^- link "@\w+"\s*(\[e\d+\])?:?$', fwd):
                continue
            if fwd.startswith("- text:"):
                raw = fwd[len("- text:"):].strip()
                if not raw:
                    continue
                text_part, rc, rt, lk, vw = _parse_nitter_stats(raw)
                if (lk or rc or rt or vw) and not stats_set:
                    replies_count = rc
                    retweets = rt
                    likes = lk
                    views = vw
                    stats_set = True
                if text_part and text_part.lower() != "replying to":
                    text_parts.append(text_part)
                continue
            media_m = re.match(r"^- /url:\s+/pic/orig/(.+)$", fwd)
            if media_m:
                decoded = urllib.parse.unquote(media_m.group(1))
                if decoded.startswith("media/"):
                    media_url = f"https://pbs.twimg.com/media/{decoded[6:]}"
                    if media_url not in media_urls:
                        media_urls.append(media_url)
                continue
            link_m = re.match(r"^- /url:\s+(.+)$", fwd)
            if link_m:
                decoded_url = urllib.parse.unquote(link_m.group(1).strip())
                if decoded_url.startswith("http") and decoded_url not in links:
                    links.append(decoded_url)
                continue
            named_link_m = re.match(r'^- link "([^"]+)"\s*(\[e\d+\])?:?$', fwd)
            if named_link_m:
                link_text = named_link_m.group(1).strip()
                if link_text.startswith("http") and link_text not in links:
                    links.append(link_text)

        full_text = " ".join(text_parts).strip()
        if reply_id and reply_screen and full_text:
            media = _nitter_media_dict(media_urls)
            key = (reply_screen.lower(), full_text[:120])
            if key not in seen:
                seen.add(key)
                item = {
                    "id": reply_id,
                    "url": f"https://x.com/{reply_screen}/status/{reply_id}",
                    "author": author_name or reply_screen,
                    "screen_name": reply_screen,
                    "created_at": time_ago,
                    "lang": "unknown",
                    "text": full_text[:280],
                    "full_text": full_text,
                    "is_article": False,
                    "article": None,
                    "media": media,
                    "media_count": len(media_urls),
                    "stats": {
                        **models.empty_stats(),
                        "likes": likes,
                        "retweets": retweets,
                        "replies": replies_count,
                        "views": views,
                    },
                    "conversation_id": conversation_id,
                    "is_reply": True,
                    "in_reply_to": conversation_id,
                    "is_thread_part": True,
                    "is_quote": False,
                    "is_retweet": False,
                    "quote": None,
                }
                if links:
                    item["links"] = links
                replies.append(item)

        i += 1

    replies.sort(key=lambda item: int(item["id"]))
    return replies


def _check_camofox(port: int) -> bool:
    try:
        req = urllib.request.Request(f"http://localhost:{port}/tabs", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            resp.read()
        return True
    except Exception:
        return False


def _fetch_camofox_snapshot(
    url: str,
    session_key: str,
    port: int,
    *,
    wait: float = 8,
) -> str | None:
    tab_id = None
    try:
        payload = json.dumps(
            {
                "userId": "twitter-fetch",
                "sessionKey": session_key,
                "url": url,
            }
        ).encode()
        req = urllib.request.Request(
            f"http://localhost:{port}/tabs",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        tab_id = data.get("tabId")
        if not tab_id:
            return None
        time.sleep(wait)
        snapshot_url = f"http://localhost:{port}/tabs/{tab_id}/snapshot?userId=twitter-fetch"
        with urllib.request.urlopen(snapshot_url, timeout=15) as resp:
            snapshot_data = json.loads(resp.read().decode())
        return snapshot_data.get("snapshot", "")
    finally:
        if tab_id:
            try:
                close_req = urllib.request.Request(
                    f"http://localhost:{port}/tabs/{tab_id}",
                    method="DELETE",
                )
                urllib.request.urlopen(close_req, timeout=5)
            except Exception:
                pass


GRAPHQL_UTAR_FEATURES = {
    "rweb_video_screen_enabled": False,
    "rweb_cashtags_enabled": True,
    "profile_label_improvements_pcf_label_in_post_enabled": True,
    "responsive_web_profile_redirect_enabled": True,
    "rweb_tipjar_consumption_enabled": True,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "premium_content_api_read_enabled": False,
    "communities_web_enable_tweet_community_results_fetch": True,
    "c9s_tweet_anatomy_moderator_badge_enabled": True,
    "responsive_web_grok_analyze_button_fetch_trends_enabled": False,
    "responsive_web_grok_analyze_post_followups_enabled": True,
    "rweb_cashtags_composer_attachment_enabled": True,
    "responsive_web_jetfuel_frame": False,
    "responsive_web_grok_share_attachment_enabled": True,
    "responsive_web_grok_annotations_enabled": True,
    "articles_preview_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "rweb_conversational_replies_downvote_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "content_disclosure_indicator_enabled": True,
    "content_disclosure_ai_generated_indicator_enabled": True,
    "responsive_web_grok_show_grok_translated_post": False,
    "responsive_web_grok_analysis_button_from_backend": True,
    "post_ctas_fetch_enabled": True,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": True,
    "responsive_web_grok_image_annotation_enabled": True,
    "responsive_web_grok_imagine_annotation_enabled": True,
    "responsive_web_grok_community_note_auto_translation_is_enabled": True,
    "responsive_web_enhance_cards_enabled": False,
}
GRAPHQL_UTAR_FIELD_TOGGLES = {
    "withPayments": False,
    "withAuxiliaryUserLabels": True,
    "withArticleRichContentState": True,
    "withArticlePlainText": False,
    "withArticleSummaryText": False,
    "withArticleVoiceOver": False,
    "withGrokAnalyze": False,
    "withDisallowedReplyControls": False,
}
GRAPHQL_USER_FEATURES = {
    "hidden_profile_likes_enabled": True,
    "hidden_profile_subscriptions_enabled": True,
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "subscriptions_verification_info_is_identity_verified_enabled": True,
    "subscriptions_verification_info_verified_since_enabled": True,
    "highlights_tweets_tab_ui_enabled": True,
    "responsive_web_twitter_article_notes_tab_enabled": True,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "responsive_web_graphql_timeline_navigation_enabled": True,
}


def _load_graphql_cookies(cookie_file: str) -> dict[str, str]:
    with open(cookie_file, "r", encoding="utf-8") as f:
        cookies = json.load(f)
    auth_token = cookies.get("auth_token", "")
    ct0 = cookies.get("ct0", "")
    if not auth_token or not ct0 or auth_token == "从浏览器复制":
        raise RuntimeError(f"missing auth_token/ct0 in cookies file: {cookie_file}")
    return {"auth_token": auth_token, "ct0": ct0}


def _scrape_graphql_hashes(client: Any) -> dict[str, str]:
    hashes = dict(GRAPHQL_FALLBACK_HASHES)
    try:
        html = client.get(GRAPHQL_BUNDLE_HOME, timeout=20).text
        matches = re.findall(
            r"https://abs\.twimg\.com/responsive-web/client-web/main\.[a-f0-9]+\.js",
            html,
        )
        if not matches:
            return hashes
        js = client.get(matches[0], timeout=20).text
        for op in ("UserTweetsAndReplies", "UserByScreenName"):
            match = re.search(
                r'queryId:"([a-zA-Z0-9_-]{15,})",operationName:"' + op + '"',
                js,
            )
            if match:
                hashes[op] = match.group(1)
    except Exception:
        return hashes
    return hashes


def _build_graphql_transaction(client: Any) -> Any:
    from x_client_transaction import ClientTransaction
    from x_client_transaction.utils import get_ondemand_file_url, handle_x_migration

    home = handle_x_migration(client)
    ondemand_url = get_ondemand_file_url(home)
    ondemand = client.get(ondemand_url, timeout=20).text
    return ClientTransaction(home, ondemand)


def _graphql_headers(cookies: dict[str, str]) -> dict[str, str]:
    return {
        "authorization": f"Bearer {GRAPHQL_BEARER}",
        "cookie": f"auth_token={cookies['auth_token']}; ct0={cookies['ct0']}",
        "x-csrf-token": cookies["ct0"],
        "x-twitter-active-user": "yes",
        "x-twitter-auth-type": "OAuth2Session",
        "x-twitter-client-language": "en",
        "referer": "https://x.com/",
        "user-agent": GRAPHQL_UA,
    }


def _graphql_get(
    client: Any,
    transaction: Any,
    hashes: dict[str, str],
    cookies: dict[str, str],
    op: str,
    variables: dict[str, Any],
    features: dict[str, Any],
    field_toggles: dict[str, Any] | None = None,
) -> dict[str, Any]:
    headers = _graphql_headers(cookies)
    for attempt in range(4):
        query_id = hashes[op]
        path = f"/i/api/graphql/{query_id}/{op}"
        if transaction is not None:
            headers["x-client-transaction-id"] = transaction.generate_transaction_id(
                method="GET", path=path
            )
        params = {
            "variables": json.dumps(variables, separators=(",", ":")),
            "features": json.dumps(features, separators=(",", ":")),
        }
        if field_toggles is not None:
            params["fieldToggles"] = json.dumps(field_toggles, separators=(",", ":"))
        try:
            response = client.get(
                f"https://x.com{path}",
                params=params,
                headers=headers,
                timeout=30,
            )
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2**attempt)
            continue
        if response.status_code == 429:
            reset = int(response.headers.get("x-rate-limit-reset", "0") or 0)
            time.sleep(max(60, reset - int(time.time())))
            continue
        if response.status_code == 404 and attempt == 0:
            hashes.update(_scrape_graphql_hashes(client))
            continue
        response.raise_for_status()
        return response.json()
    raise RuntimeError(f"{op} failed after retries")


def _resolve_graphql_user_id(
    client: Any,
    transaction: Any,
    hashes: dict[str, str],
    cookies: dict[str, str],
    screen_name: str,
) -> str:
    data = _graphql_get(
        client,
        transaction,
        hashes,
        cookies,
        "UserByScreenName",
        {"screen_name": screen_name, "withSafetyModeUserFields": True},
        GRAPHQL_USER_FEATURES,
    )
    user = data.get("data", {}).get("user", {}).get("result", {})
    if not user or "rest_id" not in user:
        raise RuntimeError(f"resolve @{screen_name} failed: {str(data)[:300]}")
    return str(user["rest_id"])


def _history_meta(
    *,
    user_id: str | None = None,
    page_count: int = 0,
    next_cursor: str | None = None,
    newest_id: str | None = None,
    oldest_id: str | None = None,
    reached_cutoff: bool = False,
    reached_since_id: bool = False,
    exhausted: bool = False,
) -> dict[str, Any]:
    return {
        "user_id": user_id,
        "page_count": page_count,
        "next_cursor": next_cursor,
        "newest_id": newest_id,
        "oldest_id": oldest_id,
        "reached_cutoff": reached_cutoff,
        "reached_since_id": reached_since_id,
        "exhausted": exhausted,
    }


def fetch_history_graphql(
    username: str,
    *,
    cookie_file: str,
    months: int = 6,
    page_size: int = 40,
    sleep_s: float = 1.5,
    cursor: str | None = None,
    since_id: str | None = None,
    max_pages: int = 0,
) -> dict[str, Any]:
    input_value = {
        "user": username,
        "months": months,
        "page_size": page_size,
        "cursor": cursor,
        "since_id": since_id,
        "max_pages": max_pages,
    }
    try:
        import httpx

        cookies = _load_graphql_cookies(cookie_file)
        cookie_header = f"auth_token={cookies['auth_token']}; ct0={cookies['ct0']}"
        client = httpx.Client(
            headers={"User-Agent": GRAPHQL_UA, "Cookie": cookie_header},
            follow_redirects=True,
            timeout=30,
        )
        try:
            hashes = _scrape_graphql_hashes(client)
            try:
                transaction = _build_graphql_transaction(client)
            except Exception:
                transaction = None
            user_id = _resolve_graphql_user_id(
                client, transaction, hashes, cookies, username
            )
            cutoff = datetime.now(timezone.utc) - timedelta(days=months * 31)
            watermark = int(since_id) if since_id else None
            items: list[dict[str, Any]] = []
            page = 0
            prev_cursor = None
            next_cursor = cursor
            reached_cutoff = False
            reached_since_id = False
            exhausted = False

            while True:
                page += 1
                variables = {
                    "userId": user_id,
                    "count": page_size,
                    "includePromotedContent": True,
                    "withCommunity": True,
                    "withVoice": True,
                    "withV2Timeline": True,
                }
                if next_cursor:
                    variables["cursor"] = next_cursor
                payload = _graphql_get(
                    client,
                    transaction,
                    hashes,
                    cookies,
                    "UserTweetsAndReplies",
                    variables,
                    GRAPHQL_UTAR_FEATURES,
                    GRAPHQL_UTAR_FIELD_TOGGLES,
                )
                page_items, bottom = extract_graphql_history_page(payload, username)
                page_old = 0
                for item in page_items:
                    tweet_id = int(item["id"])
                    if watermark is not None and tweet_id <= watermark:
                        reached_since_id = True
                        continue
                    if id_to_datetime(tweet_id) < cutoff:
                        page_old += 1
                        continue
                    items.append(item)

                if page_items and page_old == len(page_items):
                    reached_cutoff = True
                    break
                if reached_since_id:
                    break
                if not bottom or bottom == prev_cursor:
                    exhausted = True
                    break
                if max_pages and page >= max_pages:
                    next_cursor = bottom
                    break
                if not page_items:
                    exhausted = True
                    next_cursor = bottom
                    break
                prev_cursor = next_cursor
                next_cursor = bottom
                time.sleep(sleep_s)

            ids = [int(item["id"]) for item in items]
            return models.standard_response(
                mode="history",
                source="graphql",
                input_value=input_value,
                items=items,
                meta=_history_meta(
                    user_id=user_id,
                    page_count=page,
                    next_cursor=next_cursor,
                    newest_id=str(max(ids)) if ids else since_id,
                    oldest_id=str(min(ids)) if ids else None,
                    reached_cutoff=reached_cutoff,
                    reached_since_id=reached_since_id,
                    exhausted=exhausted,
                ),
            )
        finally:
            client.close()
    except Exception as exc:
        return models.standard_response(
            mode="history",
            source="graphql",
            input_value=input_value,
            error=models.standard_error(
                "provider_error", str(exc), provider="graphql", retryable=True
            ),
            meta=_history_meta(),
        )


def _cookie_error_response(mode: str, source: str, input_value: dict[str, Any], exc: Exception) -> dict[str, Any]:
    text = str(exc)
    code = "missing_cookies" if isinstance(exc, FileNotFoundError) else "invalid_cookies"
    return models.standard_response(
        mode=mode,
        source=source,
        input_value=input_value,
        error=models.standard_error(code, text, provider="runtime", retryable=False),
    )


def fetch_replies_graphql(
    url: str,
    *,
    cookie_file: str,
    product: str = "Latest",
    count: int = 40,
    search_payload_fetcher: Any | None = None,
) -> dict[str, Any]:
    try:
        _, tweet_id = models.parse_tweet_url(url)
    except ValueError as exc:
        return models.standard_response(
            mode="replies",
            source="graphql",
            input_value={"url": url},
            error=models.standard_error("bad_url", str(exc), provider="graphql"),
        )
    input_value = {
        "url": url,
        "conversation_id": tweet_id,
        "product": product,
        "count": count,
        "cookie_file": cookie_file,
    }
    try:
        if search_payload_fetcher is None:
            import httpx

            cookies = _load_graphql_cookies(cookie_file)
            cookie_header = f"auth_token={cookies['auth_token']}; ct0={cookies['ct0']}"
            client = httpx.Client(
                headers={"User-Agent": GRAPHQL_UA, "Cookie": cookie_header},
                follow_redirects=True,
                timeout=30,
            )
            try:
                hashes = _scrape_graphql_hashes(client)
                try:
                    transaction = _build_graphql_transaction(client)
                except Exception:
                    transaction = None
                payload = _graphql_get(
                    client,
                    transaction,
                    hashes,
                    cookies,
                    "SearchTimeline",
                    {
                        "rawQuery": f"conversation_id:{tweet_id}",
                        "count": count,
                        "querySource": "typed_query",
                        "product": product,
                    },
                    GRAPHQL_UTAR_FEATURES,
                )
            finally:
                client.close()
        else:
            payload = search_payload_fetcher(tweet_id, product, count)
        items = extract_graphql_search_replies_page(payload, tweet_id)
        return models.standard_response(
            mode="replies",
            source="graphql",
            input_value=input_value,
            items=items,
            meta={"reply_count": len(items), "query": f"conversation_id:{tweet_id}"},
        )
    except (FileNotFoundError, RuntimeError) as exc:
        return _cookie_error_response("replies", "graphql", input_value, exc)
    except Exception as exc:
        return models.standard_response(
            mode="replies",
            source="graphql",
            input_value=input_value,
            error=models.standard_error(
                "provider_error", str(exc), provider="graphql", retryable=True
            ),
        )


def _mcp_call(endpoint: str, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = json.dumps(
        {"jsonrpc": "2.0", "id": int(time.time() * 1000), "method": method, "params": params or {}}
    ).encode()
    req = urllib.request.Request(
        endpoint,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    if data.get("error"):
        raise RuntimeError(data["error"])
    return data.get("result", {})


def _parse_browseros_replies_snapshot(snapshot: str, conversation_id: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    lines = snapshot.splitlines()
    for idx, line in enumerate(lines):
        match = re.search(
            r"(?:https://x\.com|https://twitter\.com|)/(?:i/web/status/)?([A-Za-z0-9_]{1,15})?/status/(\d+)",
            line,
        )
        if not match:
            continue
        tweet_id = match.group(2)
        if tweet_id == conversation_id or tweet_id in seen:
            continue
        seen.add(tweet_id)
        screen_name = match.group(1) or "unknown"
        text_parts = []
        for nearby in lines[idx : min(len(lines), idx + 12)]:
            stripped = nearby.strip()
            text_match = re.search(r'(?:text|link|heading) "([^"]+)"', stripped)
            if text_match:
                text = text_match.group(1).strip()
            elif stripped.startswith("- text:"):
                text = stripped.split("- text:", 1)[1].strip()
            else:
                continue
            if text and not text.startswith(("http://", "https://", "@")):
                text_parts.append(text)
        full_text = " ".join(text_parts).strip()
        items.append(
            {
                "id": tweet_id,
                "url": f"https://x.com/{screen_name}/status/{tweet_id}",
                "author": screen_name,
                "screen_name": screen_name,
                "created_at": "",
                "lang": "unknown",
                "text": full_text[:280],
                "full_text": full_text,
                "is_article": False,
                "article": None,
                "media": None,
                "media_count": 0,
                "stats": models.empty_stats(),
                "conversation_id": conversation_id,
                "is_reply": True,
                "in_reply_to": conversation_id,
                "is_thread_part": True,
                "is_quote": False,
                "is_retweet": False,
                "quote": None,
            }
        )
    items.sort(key=lambda item: int(item["id"]))
    return items


def fetch_replies_browseros(
    url: str,
    *,
    endpoint: str = "http://127.0.0.1:9000/mcp",
    max_scrolls: int = 2,
    snapshot_fetcher: Any | None = None,
) -> dict[str, Any]:
    try:
        _, tweet_id = models.parse_tweet_url(url)
    except ValueError as exc:
        return models.standard_response(
            mode="replies",
            source="browseros",
            input_value={"url": url},
            error=models.standard_error("bad_url", str(exc), provider="browseros"),
        )
    search_url = (
        "https://x.com/search?q="
        + urllib.parse.quote(f"conversation_id:{tweet_id}")
        + "&src=typed_query&f=live"
    )
    input_value = {
        "url": url,
        "conversation_id": tweet_id,
        "browseros_endpoint": endpoint,
        "search_url": search_url,
        "max_scrolls": max_scrolls,
    }
    try:
        if snapshot_fetcher is None:
            tab = _mcp_call(endpoint, "tools/call", {"name": "tabs", "arguments": {"action": "new", "url": search_url, "hidden": True}})
            page = tab.get("content", [{}])[0].get("text") if isinstance(tab.get("content"), list) else None
            page_id_match = re.search(r"\bpage(?:Id)?[=: ]+(\d+)", str(tab))
            page_id = int(page_id_match.group(1)) if page_id_match else None
            if page_id is None:
                structured = tab.get("structuredContent") or tab
                page_id = structured.get("page") or structured.get("pageId") or structured.get("id")
            if page_id is None:
                raise RuntimeError(f"BrowserOS tabs tool did not return a page id: {str(tab)[:300]}")
            _mcp_call(endpoint, "tools/call", {"name": "wait", "arguments": {"page": int(page_id), "for": "time", "value": 3000}})
            for _ in range(max_scrolls):
                _mcp_call(endpoint, "tools/call", {"name": "act", "arguments": {"page": int(page_id), "kind": "scroll", "direction": "down", "amount": 4}})
                _mcp_call(endpoint, "tools/call", {"name": "wait", "arguments": {"page": int(page_id), "for": "time", "value": 1000}})
            snap = _mcp_call(endpoint, "tools/call", {"name": "snapshot", "arguments": {"page": int(page_id)}})
            snapshot = json.dumps(snap, ensure_ascii=False)
        else:
            snapshot = snapshot_fetcher(search_url, max_scrolls)
        items = _parse_browseros_replies_snapshot(snapshot, tweet_id)
        return models.standard_response(
            mode="replies",
            source="browseros",
            input_value=input_value,
            items=items,
            meta={"reply_count": len(items)},
        )
    except Exception as exc:
        return models.standard_response(
            mode="replies",
            source="browseros",
            input_value=input_value,
            error=models.standard_error(
                "provider_error", str(exc), provider="browseros", retryable=True
            ),
        )


def fetch_replies_nitter(
    url: str,
    *,
    port: int = 9377,
    nitter: str = "nitter.net",
    snapshot_fetcher: Any | None = None,
) -> dict[str, Any]:
    try:
        username, tweet_id = models.parse_tweet_url(url)
    except ValueError as exc:
        return models.standard_response(
            mode="replies",
            source="nitter",
            input_value={"url": url},
            error=models.standard_error("bad_url", str(exc), provider="nitter"),
        )
    input_value = {
        "url": url,
        "nitter": nitter,
        "port": port,
        "conversation_id": tweet_id,
    }
    nitter_url = f"https://{nitter}/{username}/status/{tweet_id}"
    try:
        if snapshot_fetcher is None:
            if not _check_camofox(port):
                return models.standard_response(
                    mode="replies",
                    source="nitter",
                    input_value=input_value,
                    error=models.standard_error(
                        "missing_camofox",
                        f"Camofox is not reachable on localhost:{port}",
                        provider="camofox",
                        retryable=False,
                    ),
                )
            snapshot_fetcher = _fetch_camofox_snapshot
        snapshot = snapshot_fetcher(nitter_url, f"replies-{tweet_id}", port)
        if not snapshot:
            return models.standard_response(
                mode="replies",
                source="nitter",
                input_value=input_value,
                error=models.standard_error(
                    "snapshot_failed",
                    "Could not fetch a Nitter page snapshot through Camofox",
                    provider="camofox",
                    retryable=True,
                ),
            )
        items = parse_nitter_replies_snapshot(
            snapshot,
            original_author=username,
            conversation_id=tweet_id,
        )
        return models.standard_response(
            mode="replies",
            source="nitter",
            input_value=input_value,
            items=items,
            meta={"reply_count": len(items), "provider_url": nitter_url},
        )
    except Exception as exc:
        return models.standard_response(
            mode="replies",
            source="nitter",
            input_value=input_value,
            error=models.standard_error(
                "provider_error", str(exc), provider="nitter", retryable=True
            ),
        )


def fetch_replies_direct_nitter(
    url: str,
    *,
    nitter: str = "nitter.net",
    timeout: int = 15,
    html_fetcher: Any | None = None,
) -> dict[str, Any]:
    try:
        username, tweet_id = models.parse_tweet_url(url)
    except ValueError as exc:
        return models.standard_response(
            mode="replies",
            source="direct_nitter",
            input_value={"url": url},
            error=models.standard_error("bad_url", str(exc), provider="direct_nitter"),
        )
    nitter_url = f"https://{nitter}/{username}/status/{tweet_id}"
    input_value = {"url": url, "nitter": nitter, "conversation_id": tweet_id}
    try:
        if html_fetcher is None:
            req = urllib.request.Request(nitter_url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                html = resp.read().decode("utf-8", "replace")
        else:
            html = html_fetcher(nitter_url)
        if not html:
            return models.standard_response(
                mode="replies",
                source="direct_nitter",
                input_value=input_value,
                error=models.standard_error(
                    "empty_response",
                    "Nitter returned an empty response",
                    provider="direct_nitter",
                    retryable=True,
                ),
            )
        blocks = re.findall(
            r'<div class="timeline-item[^"]*".*?(?=<div class="timeline-item|\Z)',
            html,
            re.DOTALL,
        )
        items: list[dict[str, Any]] = []
        seen: set[str] = set()
        for block in blocks:
            if "replying-to" not in block and "Replying to" not in block:
                continue
            id_match = re.search(r'href="/([A-Za-z0-9_]{1,15})/status/(\d+)', block)
            text_match = re.search(r'<div class="tweet-content[^"]*"[^>]*>(.*?)</div>', block, re.DOTALL)
            if not id_match or not text_match:
                continue
            reply_screen, reply_id = id_match.group(1), id_match.group(2)
            if reply_id == tweet_id or reply_id in seen:
                continue
            seen.add(reply_id)
            text = re.sub(r"<[^>]+>", " ", text_match.group(1))
            text = urllib.parse.unquote(text)
            text = re.sub(r"\s+", " ", text).strip()
            items.append(
                {
                    "id": reply_id,
                    "url": f"https://x.com/{reply_screen}/status/{reply_id}",
                    "author": reply_screen,
                    "screen_name": reply_screen,
                    "created_at": "",
                    "lang": "unknown",
                    "text": text[:280],
                    "full_text": text,
                    "is_article": False,
                    "article": None,
                    "media": None,
                    "media_count": 0,
                    "stats": models.empty_stats(),
                    "conversation_id": tweet_id,
                    "is_reply": True,
                    "in_reply_to": tweet_id,
                    "is_thread_part": True,
                    "is_quote": False,
                    "is_retweet": False,
                    "quote": None,
                }
            )
        items.sort(key=lambda item: int(item["id"]))
        return models.standard_response(
            mode="replies",
            source="direct_nitter",
            input_value=input_value,
            items=items,
            meta={"reply_count": len(items), "provider_url": nitter_url},
        )
    except Exception as exc:
        return models.standard_response(
            mode="replies",
            source="direct_nitter",
            input_value=input_value,
            error=models.standard_error(
                "provider_error", str(exc), provider="direct_nitter", retryable=True
            ),
        )


def _with_chain_meta(
    payload: dict[str, Any],
    chain: list[str],
    errors: list[dict[str, Any]],
) -> dict[str, Any]:
    meta = dict(payload.get("meta") or {})
    meta["provider_chain"] = chain
    if errors:
        meta["provider_errors"] = errors
    payload["meta"] = meta
    return payload


def fetch_replies(
    url: str,
    *,
    provider: str = "auto",
    cookie_file: str | None = None,
    port: int = 9377,
    nitter: str = "nitter.net",
    browseros_endpoint: str = "http://127.0.0.1:9000/mcp",
    provider_funcs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    def default_funcs() -> dict[str, Any]:
        return {
            "graphql": lambda: fetch_replies_graphql(
                url, cookie_file=cookie_file or "", product="Latest"
            ),
            "browseros": lambda: fetch_replies_browseros(
                url, endpoint=browseros_endpoint
            ),
            "camofox_nitter": lambda: fetch_replies_nitter(
                url, port=port, nitter=nitter
            ),
            "direct_nitter": lambda: fetch_replies_direct_nitter(url, nitter=nitter),
        }

    funcs = {**default_funcs(), **(provider_funcs or {})}
    if provider != "auto":
        if provider not in funcs:
            return models.standard_response(
                mode="replies",
                source=provider,
                input_value={"url": url, "provider": provider},
                error=models.standard_error(
                    "unknown_provider",
                    f"Unknown replies provider: {provider}",
                    provider="runtime",
                    retryable=False,
                ),
            )
        return _with_chain_meta(funcs[provider](), [provider], [])

    chain: list[str] = []
    errors: list[dict[str, Any]] = []
    for name in REPLIES_PROVIDER_ORDER:
        if name not in funcs:
            continue
        chain.append(name)
        payload = funcs[name]()
        if payload.get("ok"):
            return _with_chain_meta(payload, chain, errors)
        if payload.get("error"):
            errors.append({"provider": name, **payload["error"]})
    return models.standard_response(
        mode="replies",
        source="auto",
        input_value={"url": url, "provider": "auto"},
        error=models.standard_error(
            "all_providers_failed",
            "All replies providers failed",
            provider="auto",
            retryable=True,
        ),
        meta={"provider_chain": chain, "provider_errors": errors},
    )
