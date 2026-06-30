#!/usr/bin/env python3
"""Run the stateful Twitter monitor core."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fetch_timeline import fetch_history_window, fetch_timeline_window, ingest_tweet_pool
from twitter_fetch_runner import run_twitter_fetch


DEFAULT_RUNTIME = Path("/Users/saberrao/ai-workspace/.twitter-monitor")
SEEN_STATUSES = {"saved", "skipped", "fetched"}
SHORT_TEXT_LIMIT = 40
SHORT_TEXT_ALLOWLIST_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bbuy\s+this\s+dip\b",
        r"\bbuy\s+the\s+dip\b",
        r"\bsell\s+the\s+rip\b",
        r"\bhawk(?:ish)?\b",
        r"\bdovish\b",
        r"\bbull(?:ish)?\b",
        r"\bbear(?:ish)?\b",
        r"加息",
        r"降息",
        r"鹰",
        r"鸽",
        r"估值",
        r"财报",
        r"仓位",
        r"风险偏好",
        r"目标价",
        r"买入",
        r"卖出",
        r"抄底",
        r"做空",
    )
]
INVEST_RELEVANCE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\$[A-Za-z]{1,6}(?:\b|[._-])",
        r"\b[A-Z]{2,6}\s+(?:stock|shares|earnings|revenue|eps|guidance|capex)\b",
        r"\b(?:stock|stocks|shares|equity|equities|earnings|revenue|profit|margin|cash flow|fcf|eps|pe|p/e|valuation|guidance|capex|market cap|buyback|dividend|portfolio|position|long|short|bullish|bearish)\b",
        r"美股|A股|港股|股票|个股|股价|股市|大盘|纳指|标普|道指|期权|仓位|持仓|建仓|减仓|加仓|清仓|做多|做空",
        r"财报|营收|收入|利润|毛利|净利|现金流|自由现金流|EPS|PE|PS|PB|估值|市值|目标价|回购|分红|指引",
        r"订单|出货|产能|良率|供应链|产业链|半导体|芯片|HBM|DRAM|晶圆|光模块|CPO|GPU|ASIC",
        r"降息|加息|利率|美债|收益率|通胀数据|CPI|PCE|非农|流动性|衰退|信用利差",
        r"SEC|IPO|并购|收购|拆分|增发|稀释|可转债|债务|融资",
    )
]
DEFAULT_INTERVAL_MINUTES = 60
DEFAULT_MAX_SCAN_PER_USER = 50
DEFAULT_WINDOW_GRACE_MINUTES = 10
DEFAULT_NOTIFICATION_APPEND = Path.home() / ".codex/skills/notification-center/append.py"
DEFAULT_KOL_VAULT = Path.home() / "vault/kol"
SUMMARY_LIMIT = 600
SUMMARY_TIMEOUT_SECONDS = 20
AUTHOR_TAG_LIMIT = 3
AUTHOR_TAG_CHAR_LIMIT = 24


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


def kol_vault_dir(
    config: dict[str, Any] | None = None,
    env: dict[str, str] | None = None,
) -> Path:
    env = os.environ if env is None else env
    override = env.get("TWITTER_MONITOR_KOL_VAULT") or env.get("KOL_TWIN_VAULT")
    if override:
        return Path(override).expanduser()
    settings = (config or {}).get("settings") if isinstance(config, dict) else {}
    if isinstance(settings, dict):
        configured = settings.get("kol_vault") or settings.get("kol_twin_vault")
        if configured:
            return Path(str(configured)).expanduser()
    return DEFAULT_KOL_VAULT


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
    current_user: dict[str, Any] | None = None
    current_topic: dict[str, Any] | None = None
    current_sink: dict[str, Any] | None = None
    in_topic_users = False
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if not line.startswith(" "):
            section = line.rstrip(":")
            current_user = None
            current_topic = None
            current_sink = None
            in_topic_users = False
            continue
        stripped = line.strip()
        if section == "users" and stripped.startswith("- username:"):
            current_user = {"username": parse_scalar(stripped.split(":", 1)[1])}
            config["users"].append(current_user)
            continue
        if section == "users" and current_user is not None and ":" in stripped:
            key, value = stripped.split(":", 1)
            current_user[key.strip()] = parse_scalar(value)
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
            continue
        if section == "sinks":
            if line.startswith("  ") and not line.startswith("    ") and stripped.endswith(":"):
                sink_name = stripped[:-1].strip()
                current_sink = config["sinks"].setdefault(sink_name, {})
                continue
            if current_sink is not None and ":" in stripped:
                key, value = stripped.split(":", 1)
                current_sink[key.strip()] = parse_scalar(value)
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


def user_config_by_user(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}
    for item in config.get("users") or []:
        if isinstance(item, dict) and item.get("username"):
            username = str(item["username"]).lstrip("@")
            mapping.setdefault(username.lower(), item)
    return mapping


def user_config(username: str, config: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(config, dict):
        return {}
    return user_config_by_user(config).get(username.lstrip("@").lower(), {})


def user_fetch_mode(username: str, config: dict[str, Any]) -> str:
    mode = str(user_config(username, config).get("fetch_mode") or "timeline").strip().lower()
    if mode in {"timeline", "history"}:
        return mode
    raise ValueError(f"unsupported fetch_mode for {username}: {mode}")


def user_labels(username: str, config: dict[str, Any] | None) -> list[str]:
    options = user_config(username, config)
    raw_labels = options.get("labels") or []
    labels: list[str] = []
    if isinstance(raw_labels, list):
        labels.extend(str(label).strip() for label in raw_labels)
    elif isinstance(raw_labels, str):
        labels.extend(part.strip() for part in raw_labels.split(","))
    if options.get("paid") or options.get("subscriber_only"):
        labels.append("付费")
    seen: set[str] = set()
    unique: list[str] = []
    for label in labels:
        if not label or label in seen:
            continue
        seen.add(label)
        unique.append(label)
    return unique


def normalize_tag(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("label") or value.get("name") or value.get("id") or ""
    tag = re.sub(r"\s+", " ", str(value or "")).strip()
    if not tag:
        return ""
    return tag[:AUTHOR_TAG_CHAR_LIMIT].rstrip()


def normalize_tag_list(raw_tags: Any) -> list[str]:
    if isinstance(raw_tags, str):
        values: list[Any] = re.split(r"[,，/|;；]", raw_tags)
    elif isinstance(raw_tags, list):
        values = raw_tags
    else:
        values = []
    seen: set[str] = set()
    tags: list[str] = []
    for raw in values:
        tag = normalize_tag(raw)
        key = tag.lower()
        if not tag or key in seen:
            continue
        seen.add(key)
        tags.append(tag)
        if len(tags) >= AUTHOR_TAG_LIMIT:
            break
    return tags


def resolve_kol_path(raw_path: str, kol_root: Path) -> Path:
    raw = raw_path.strip().strip("`").strip()
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path
    parts = path.parts
    if len(parts) >= 2 and parts[0] == "vault" and parts[1] == "kol":
        return kol_root.joinpath(*parts[2:])
    return kol_root / path


def kol_registry_paths(kol_root: Path) -> dict[str, Path]:
    registry = kol_root / "_cross" / "_registry.md"
    if not registry.exists():
        return {}
    mapping: dict[str, Path] = {}
    current_handle = ""
    for raw_line in registry.read_text(encoding="utf-8").splitlines():
        header = re.match(r"^##\s+@?([A-Za-z0-9_]+)", raw_line.strip())
        if header:
            current_handle = header.group(1)
            mapping.setdefault(current_handle.lower(), kol_root / current_handle)
            continue
        if not current_handle:
            continue
        path_match = re.match(r"^-\s+path:\s+(.+)$", raw_line.strip())
        if path_match:
            mapping[current_handle.lower()] = resolve_kol_path(path_match.group(1), kol_root)
    return mapping


def profile_path_for_user(username: str, config: dict[str, Any] | None = None) -> Path | None:
    kol_root = kol_vault_dir(config)
    key = username.lstrip("@").lower()
    kol_path = kol_registry_paths(kol_root).get(key, kol_root / username.lstrip("@"))
    candidates = [
        kol_path / "wiki" / "profile.json",
        kol_path / "profile.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def author_tags_from_profile(username: str, config: dict[str, Any] | None = None) -> list[str]:
    profile_path = profile_path_for_user(username, config)
    if profile_path is None:
        return []
    try:
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(profile, dict):
        return []
    for key in ("display_tags", "author_tags", "tags", "chips"):
        tags = normalize_tag_list(profile.get(key))
        if tags:
            return tags
    return []


def topic_by_user(config: dict[str, Any]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for topic in config.get("topics") or []:
        if not isinstance(topic, dict):
            continue
        topic_name = str(topic.get("name") or "").strip()
        if not topic_name:
            continue
        for username in topic.get("users") or []:
            key = str(username).lstrip("@").lower()
            mapping.setdefault(key, topic_name)
    return mapping


def topics_by_user(config: dict[str, Any]) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    for topic in config.get("topics") or []:
        if not isinstance(topic, dict):
            continue
        topic_name = str(topic.get("name") or "").strip()
        if not topic_name:
            continue
        for username in topic.get("users") or []:
            key = str(username).lstrip("@").lower()
            topics = mapping.setdefault(key, [])
            if topic_name not in topics:
                topics.append(topic_name)
    return mapping


def topics_for_user(username: str, config: dict[str, Any] | None) -> list[str]:
    if not isinstance(config, dict):
        return []
    return topics_by_user(config).get(username.lstrip("@").lower(), [])


def topic_for_user(username: str, config: dict[str, Any] | None) -> str:
    if not isinstance(config, dict):
        return ""
    topics = topics_for_user(username, config)
    return topics[0] if topics else ""


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


def looks_like_short_market_opinion(text: str) -> bool:
    normalized = text.strip()
    return any(pattern.search(normalized) for pattern in SHORT_TEXT_ALLOWLIST_PATTERNS)


def relevance_text(item: dict[str, Any]) -> str:
    parts = [str(item.get("full_text") or item.get("text") or "").strip()]
    quote = item.get("quote")
    if isinstance(quote, dict):
        parts.append(str(quote.get("full_text") or quote.get("text") or "").strip())
    article = item.get("article")
    if isinstance(article, dict):
        parts.append(
            str(
                article.get("title")
                or article.get("headline")
                or article.get("body")
                or article.get("text")
                or ""
            ).strip()
        )
    return "\n".join(part for part in parts if part)


def is_topic_relevant(item: dict[str, Any], topic: str) -> bool:
    if topic.strip().lower() != "invest":
        return True
    text = relevance_text(item)
    return any(pattern.search(text) for pattern in INVEST_RELEVANCE_PATTERNS)


def topic_relevance_enabled(settings: dict[str, Any]) -> bool:
    return setting_bool(settings, "topic_relevance_filter", True)


def skip_reason(item: dict[str, Any], settings: dict[str, Any], topic: str = "") -> str | None:
    if not settings.get("include_retweets", False) and item.get("is_retweet"):
        return "retweet"
    if not settings.get("include_replies", False) and item.get("is_reply") and not item.get("is_quote"):
        return "reply"
    if topic and topic_relevance_enabled(settings) and not is_topic_relevant(item, topic):
        return "topic_irrelevant"
    text = (item.get("full_text") or item.get("text") or "").strip()
    media_count = int(item.get("media_count") or 0)
    if (
        len(text) < SHORT_TEXT_LIMIT
        and not item.get("is_quote")
        and media_count == 0
        and not item.get("media")
        and not has_url(text)
        and not looks_like_short_market_opinion(text)
    ):
        return "short_no_url"
    return None


def notification_enabled(config: dict[str, Any]) -> bool:
    notification = ((config.get("sinks") or {}).get("notification") or {})
    return bool(isinstance(notification, dict) and notification.get("enabled"))


def notification_settings(config: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(config, dict):
        return {}
    notification = ((config.get("sinks") or {}).get("notification") or {})
    return notification if isinstance(notification, dict) else {}


def setting_int(settings: dict[str, Any], key: str, default: int, *, minimum: int = 1) -> int:
    try:
        raw = settings.get(key)
        value = int(default if raw is None or raw == "" else raw)
    except (TypeError, ValueError):
        value = default
    return max(value, minimum)


def setting_bool(settings: dict[str, Any], key: str, default: bool = False) -> bool:
    raw = settings.get(key)
    if raw is None or raw == "":
        return default
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return bool(raw)
    value = str(raw).strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return default


def clean_summary(text: str, limit: int = SUMMARY_LIMIT) -> str:
    compact = re.sub(r"\s+", " ", text or "").strip()
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 3)].rstrip() + "..."


def clean_llm_summary(text: str, limit: int = SUMMARY_LIMIT) -> str:
    compact = re.sub(r"[ \t\r\f\v]+", " ", text or "").strip()
    compact = re.sub(r" *\n *", "\n", compact)
    compact = re.sub(r"\n{3,}", "\n\n", compact)
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 3)].rstrip() + "..."


def detect_original_language(text: str) -> str:
    cjk = re.findall(r"[\u3400-\u9fff]", text or "")
    letters = re.findall(r"[A-Za-z]", text or "")
    if len(cjk) >= 4 and len(cjk) >= len(letters) * 0.1:
        return "zh"
    compact = re.sub(r"\s+", "", text or "")
    if len(letters) >= 8 and len(letters) >= max(1, len(compact)) * 0.45:
        return "en"
    return ""


def extract_text(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    return str(value.get("full_text") or value.get("text") or "").strip()


def first_full_item(item: dict[str, Any], full_payload: dict[str, Any]) -> dict[str, Any]:
    items = full_payload.get("items") if isinstance(full_payload, dict) else None
    if isinstance(items, list) and items and isinstance(items[0], dict):
        return items[0]
    return item


def notification_text(item: dict[str, Any], full_payload: dict[str, Any]) -> str:
    full_item = first_full_item(item, full_payload)
    parts = [extract_text(full_item) or extract_text(item)]
    quote = full_item.get("quote") or item.get("quote")
    if isinstance(quote, dict):
        quote_text = extract_text(quote)
        if quote_text:
            quote_author = str(quote.get("author") or "").strip()
            quote_screen_name = str(quote.get("screen_name") or "").strip()
            quote_label = "引用推文"
            if quote_author and quote_screen_name:
                quote_label = f"{quote_label} {quote_author} (@{quote_screen_name})"
            elif quote_author:
                quote_label = f"{quote_label} {quote_author}"
            elif quote_screen_name:
                quote_label = f"{quote_label} @{quote_screen_name}"
            parts.append(f"{quote_label}: {quote_text}")
    article = full_item.get("article") or item.get("article")
    if isinstance(article, dict):
        article_text = str(
            article.get("title")
            or article.get("headline")
            or article.get("body")
            or article.get("text")
            or ""
        ).strip()
        if article_text:
            parts.append(article_text)
    thread = full_item.get("thread")
    if isinstance(thread, dict):
        for thread_item in thread.get("items") or []:
            thread_text = extract_text(thread_item)
            if thread_text and thread_text not in parts:
                parts.append(thread_text)
    return "\n\n".join(part for part in parts if part)


def tweet_content_types(item: dict[str, Any], full_payload: dict[str, Any]) -> list[str]:
    full_item = first_full_item(item, full_payload)
    types = []
    thread = full_item.get("thread")
    if item.get("is_thread_part") or (isinstance(thread, dict) and bool(thread.get("items"))):
        types.append("thread")
    if item.get("is_quote") or full_item.get("is_quote") or item.get("quote") or full_item.get("quote"):
        types.append("quote")
    if item.get("is_article") or full_item.get("is_article") or item.get("article") or full_item.get("article"):
        types.append("article")
    return types or ["tweet"]


def parse_summary_output(raw: str) -> str:
    text = raw.strip()
    if not text:
        return ""
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError:
        return text
    if isinstance(loaded, dict):
        return str(loaded.get("summary") or loaded.get("text") or "").strip()
    return text


def run_summary_command(
    command: str,
    payload: dict[str, Any],
    *,
    timeout_seconds: int = SUMMARY_TIMEOUT_SECONDS,
) -> str:
    if not command.strip():
        return ""
    proc = subprocess.run(
        shlex.split(command),
        input=json.dumps(payload, ensure_ascii=False) + "\n",
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "summary command failed")
    return parse_summary_output(proc.stdout)


def build_notification_summary(
    username: str,
    item: dict[str, Any],
    full_payload: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    settings = notification_settings(config)
    global_settings = (config or {}).get("settings") if isinstance(config, dict) else {}
    if not isinstance(global_settings, dict):
        global_settings = {}
    direct_chars = setting_int(settings, "direct_chars", SUMMARY_LIMIT)
    summary_chars = setting_int(settings, "summary_chars", SUMMARY_LIMIT)
    text = notification_text(item, full_payload)
    compact = clean_summary(text, limit=max(len(text), 1))
    labels = user_labels(username, config)
    original_language = detect_original_language(compact)
    translate_non_chinese = setting_bool(global_settings, "translate_non_chinese", False)
    should_translate = translate_non_chinese and original_language == "en"
    display_labels = list(labels)
    if should_translate:
        display_labels.append("原文英文")
    label_prefix = " ".join(f"[{label}]" for label in display_labels)
    paid_content = "付费" in labels
    if len(compact) <= direct_chars and not paid_content and not should_translate:
        summary = f"{label_prefix} {compact}".strip()
        return clean_summary(summary, limit=max(direct_chars, len(label_prefix) + 1)), {
            "summary_source": "direct"
        }

    command = str(settings.get("summary_command") or "").strip()
    if command:
        try:
            content_types = tweet_content_types(item, full_payload)
            summary = run_summary_command(
                command,
                {
                    "username": username,
                    "tweet_id": str(item.get("id") or first_full_item(item, full_payload).get("id") or ""),
                    "url": str(item.get("url") or first_full_item(item, full_payload).get("url") or ""),
                    "types": content_types,
                    "original_language": original_language,
                    "max_chars": summary_chars,
                    "text": text,
                    "item": first_full_item(item, full_payload),
                },
                timeout_seconds=setting_int(
                    settings,
                    "summary_timeout_seconds",
                    SUMMARY_TIMEOUT_SECONDS,
                ),
            )
            summary = clean_llm_summary(summary, limit=summary_chars)
            if summary:
                summary = f"{label_prefix} {summary}".strip()
                meta = {"summary_source": "llm"}
                if should_translate:
                    meta["original_language"] = original_language
                return summary, meta
        except Exception as exc:
            if paid_content:
                meta = {
                    "summary_source": "fallback",
                    "summary_error": str(exc),
                }
                if should_translate:
                    meta["original_language"] = original_language
                return f"{label_prefix} 摘要生成失败，请点击链接查看原文。".strip(), meta
            summary = f"{label_prefix} {clean_summary(text, limit=summary_chars)}".strip()
            meta = {
                "summary_source": "fallback",
                "summary_error": str(exc),
            }
            if should_translate:
                meta["original_language"] = original_language
            return clean_summary(summary, limit=max(summary_chars, len(label_prefix) + 1)), meta

    if paid_content:
        meta = {
            "summary_source": "fallback"
        }
        if should_translate:
            meta["original_language"] = original_language
        return f"{label_prefix} 摘要生成失败，请点击链接查看原文。".strip(), meta

    summary = f"{label_prefix} {clean_summary(text, limit=summary_chars)}".strip()
    meta = {
        "summary_source": "fallback"
    }
    if should_translate:
        meta["original_language"] = original_language
    return clean_summary(summary, limit=max(summary_chars, len(label_prefix) + 1)), meta


def build_notification_event(
    username: str,
    item: dict[str, Any],
    full_payload: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    full_item = first_full_item(item, full_payload)
    tweet_id = str(item.get("id") or full_item.get("id") or "")
    url = str(item.get("url") or full_item.get("url") or "")
    author = str(
        full_item.get("author")
        or item.get("author")
        or full_item.get("screen_name")
        or item.get("screen_name")
        or username
    ).strip()
    content_types = tweet_content_types(item, full_payload)
    summary, summary_meta = build_notification_summary(username, item, full_payload, config)
    topics = topics_for_user(username, config)
    topic = topics[0] if topics else ""
    labels = user_labels(username, config)
    author_tags = author_tags_from_profile(username, config)
    meta = {
        "tweet_id": tweet_id,
        "username": username,
        "types": content_types,
        "display": {"hide_source_prefix": True, "hide_level": True, "hide_footer": True},
        **summary_meta,
    }
    if labels:
        meta["labels"] = labels
    if author_tags:
        meta["author_tags"] = author_tags
    if topic:
        meta["topic"] = topic
    if len(topics) > 1:
        meta["topics"] = topics
    return {
        "source": "twitter-monitor",
        "level": "alert",
        "title": author,
        "summary": summary,
        "dedupe_key": f"tweet:{tweet_id}",
        "links": [{"label": url, "url": url}] if url else [],
        "meta": meta,
        "targets": ["feishu"],
    }


def notification_append_path(env: dict[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    override = env.get("NOTIFICATION_CENTER_APPEND")
    if override:
        return Path(override).expanduser()
    return DEFAULT_NOTIFICATION_APPEND


def append_notification_event(event: dict[str, Any]) -> dict[str, Any]:
    append_path = notification_append_path()
    if not append_path.exists():
        raise FileNotFoundError(f"notification append script missing: {append_path}")
    proc = subprocess.run(
        [sys.executable, str(append_path), "--stdin"],
        input=json.dumps(event, ensure_ascii=False) + "\n",
        capture_output=True,
        text=True,
        timeout=10,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "notification append failed")
    return json.loads(proc.stdout)


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


def full_payload_from_history_item(username: str, item: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "mode": "history",
        "source": "tweet-pool",
        "fetched_at": now_iso(),
        "input": {
            "user": username,
            "url": str(item.get("url") or ""),
        },
        "items": [item],
        "error": None,
    }


def run_user(username: str, config: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    settings = config.get("settings") or {}
    limit = scan_limit(settings)
    fetch_mode = user_fetch_mode(username, config)
    topic = topic_for_user(username, config)
    history_max_pages = setting_int(settings, "history_max_pages", 3)
    expand_thread = bool(settings.get("expand_thread", True))
    mark_skipped = bool(settings.get("mark_skipped_as_seen", True))
    notify = notification_enabled(config)
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
        "notified": 0,
        "notification_failed": 0,
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
        "fetch_mode": fetch_mode,
    }
    if fetch_mode == "history":
        timeline = fetch_history_window(
            username,
            format_iso(window_start),
            format_iso(window_end),
            limit,
            grace_minutes,
            history_max_pages=history_max_pages,
        )
        report["history_max_pages"] = history_max_pages
    else:
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
        reason = skip_reason(item, settings, topic=topic)
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
            full_payload = (
                full_payload_from_history_item(username, item)
                if fetch_mode == "history"
                else fetch_single(item, expand_thread)
            )
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
        outputs = {"tweet_pool": True}
        if notify:
            try:
                append_notification_event(build_notification_event(username, item, full_payload, config))
                report["notified"] += 1
                outputs["notification"] = True
            except Exception as exc:
                report["notification_failed"] += 1
                outputs["notification"] = False
                outputs["notification_error"] = str(exc)
        report["fetched"] += 1
        mark_item(
            user_entry,
            tweet_id,
            "fetched",
            source_url=str(item.get("url") or ""),
            created_at=str(item.get("created_at") or ""),
            outputs=outputs,
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
