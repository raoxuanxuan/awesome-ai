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
}
TWITTER_SNOWFLAKE_EPOCH = 1288834974657


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


def normalize_graphql_tweet(tr: dict[str, Any], want_screen: str) -> dict[str, Any] | None:
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
    if not screen_name or screen_name.lower() != want_screen.lower():
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


def fetch_replies_nitter(url: str, *, port: int = 9377, nitter: str = "nitter.net") -> dict[str, Any]:
    try:
        username, tweet_id = models.parse_tweet_url(url)
    except ValueError as exc:
        return models.standard_response(
            mode="replies",
            source="nitter",
            input_value={"url": url},
            error=models.standard_error("bad_url", str(exc), provider="nitter"),
        )
    # Keep first version intentionally conservative: existing x-tweet-fetcher still
    # owns rich Nitter parsing, while twitter-fetch exposes a structured failure.
    return models.standard_response(
        mode="replies",
        source="nitter",
        input_value={"url": url, "nitter": nitter, "port": port},
        error=models.standard_error(
            "not_implemented",
            f"Replies provider is reserved for Camofox/Nitter migration ({username}/{tweet_id})",
            provider="nitter",
            retryable=False,
        ),
    )
