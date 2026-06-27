#!/usr/bin/env python3
"""Dispatch pending notification center events to Feishu."""

from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import hmac
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, time as dtime, timedelta, timezone
from pathlib import Path
from typing import Any


CST = timezone(timedelta(hours=8))
DEFAULT_RUNTIME = Path.home() / "vault" / ".notification-center"
SKILL_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = Path.home() / ".notification-center" / "feishu.json"
LEGACY_CONFIG = Path.home() / ".codex" / "skills" / "notification-center" / "feishu.json"
DELIVERED_DIR_NAME = ".delivered"
DIGEST_DIR_NAME = ".digest"
LOG_NAME = ".dispatch.log"
LOCK_NAME = ".dispatch.lock"
QUIET_START = dtime(23, 0)
QUIET_END = dtime(8, 0)
DIGEST_HOUR = 8
DIGEST_WINDOW = (0, 30)
LEVEL_COLOR = {"critical": "red", "alert": "yellow", "info": "blue"}


def runtime_dir(env: dict[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    override = env.get("NOTIFICATION_CENTER_RUNTIME")
    if override:
        return Path(override).expanduser()
    return DEFAULT_RUNTIME


def config_path(env: dict[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    override = env.get("NOTIFICATION_CENTER_FEISHU_CONFIG")
    if override:
        return Path(override).expanduser()
    if DEFAULT_CONFIG.exists():
        return DEFAULT_CONFIG
    if LEGACY_CONFIG.exists():
        return LEGACY_CONFIG
    bundled = SKILL_DIR / "feishu.json"
    if bundled.exists():
        return bundled
    return DEFAULT_CONFIG


def now_cst() -> datetime:
    return datetime.now(CST)


def log(runtime: Path, message: str) -> None:
    runtime.mkdir(parents=True, exist_ok=True)
    with (runtime / LOG_NAME).open("a", encoding="utf-8") as fh:
        fh.write(f"{now_cst().isoformat(timespec='seconds')} {message}\n")


def normalize_bot(name: str, data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError(f"Feishu bot config must be an object: {name}")
    if not data.get("webhook") or not data.get("secret"):
        raise ValueError(f"Feishu bot config must contain webhook and secret: {name}")
    return {
        "name": name,
        "webhook": str(data["webhook"]),
        "secret": str(data["secret"]),
        "topics": [str(topic) for topic in data.get("topics") or []],
    }


def normalize_config(data: dict[str, Any]) -> dict[str, Any]:
    if data.get("webhook") and data.get("secret"):
        bot = normalize_bot("default", data)
        return {"default": "default", "bots": {"default": bot}, "topics": {}}

    bots: dict[str, dict[str, Any]] = {}
    topic_routes: dict[str, list[str]] = {}
    default_ref = data.get("default")

    def add_topic_route(topic: str, bot_name: str) -> None:
        topic = str(topic)
        bot_name = str(bot_name)
        routes = topic_routes.setdefault(topic, [])
        if bot_name not in routes:
            routes.append(bot_name)

    if isinstance(default_ref, dict):
        bots["default"] = normalize_bot("default", default_ref)
        default_name = "default"
    elif isinstance(default_ref, str) and default_ref:
        default_name = default_ref
    else:
        default_name = ""

    raw_bots = data.get("bots") or {}
    if isinstance(raw_bots, dict):
        for name, bot_data in raw_bots.items():
            bot = normalize_bot(str(name), bot_data)
            bots[bot["name"]] = bot
            for topic in bot["topics"]:
                add_topic_route(topic, bot["name"])
    elif isinstance(raw_bots, list):
        for index, bot_data in enumerate(raw_bots):
            name = str(bot_data.get("name") or f"bot{index + 1}") if isinstance(bot_data, dict) else f"bot{index + 1}"
            bot = normalize_bot(name, bot_data)
            bots[bot["name"]] = bot
            for topic in bot["topics"]:
                add_topic_route(topic, bot["name"])
    else:
        raise ValueError("Feishu config bots must be an object or array")

    raw_topics = data.get("topics") or {}
    if isinstance(raw_topics, dict):
        for topic, bot_names in raw_topics.items():
            values = bot_names if isinstance(bot_names, list) else [bot_names]
            topic_routes[str(topic)] = []
            for bot_name in values:
                add_topic_route(str(topic), str(bot_name))

    if not default_name:
        default_name = "default" if "default" in bots else next(iter(bots), "")
    if not default_name or default_name not in bots:
        raise ValueError("Feishu config must contain a default bot or at least one bot")
    for topic, bot_names in topic_routes.items():
        for bot_name in bot_names:
            if bot_name not in bots:
                raise ValueError(f"Feishu topic {topic!r} references unknown bot {bot_name!r}")
    return {"default": default_name, "bots": bots, "topics": topic_routes}


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Feishu config missing: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Feishu config must be an object: {path}")
    return normalize_config(data)


def sign(timestamp: int, secret: str) -> str:
    string_to_sign = f"{timestamp}\n{secret}"
    digest = hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def post_feishu(webhook: str, secret: str, payload: dict[str, Any], timeout: int = 10) -> dict[str, Any]:
    timestamp = int(time.time())
    body = {"timestamp": str(timestamp), "sign": sign(timestamp, secret), **payload}
    req = urllib.request.Request(
        webhook,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw)


def today_path(runtime: Path, now: datetime) -> Path:
    return runtime / f"{now.strftime('%Y-%m-%d')}.jsonl"


def load_entries(runtime: Path, now: datetime) -> list[dict[str, Any]]:
    path = today_path(runtime, now)
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(entry, dict):
                entries.append(entry)
    return entries


def is_quiet(now: datetime) -> bool:
    current = now.time().replace(tzinfo=None)
    return current >= QUIET_START or current < QUIET_END


def delivered_dir(runtime: Path) -> Path:
    return runtime / DELIVERED_DIR_NAME


def delivered_entry_id(entry_id: str, target: str = "feishu") -> str:
    if target == "feishu":
        return entry_id
    safe_target = re_safe_target(target)
    return f"{entry_id}__{safe_target}"


def re_safe_target(target: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "-" for ch in target)
    return safe[:80] or "target"


def is_delivered(runtime: Path, entry_id: str, target: str = "feishu") -> bool:
    return (delivered_dir(runtime) / delivered_entry_id(entry_id, target)).exists()


def mark_delivered(runtime: Path, entry_id: str, target: str = "feishu") -> None:
    delivered_dir(runtime).mkdir(parents=True, exist_ok=True)
    (delivered_dir(runtime) / delivered_entry_id(entry_id, target)).touch()


def digest_marker(runtime: Path, day: str) -> Path:
    return runtime / DIGEST_DIR_NAME / day


def mark_digest(runtime: Path, day: str) -> None:
    marker = digest_marker(runtime, day)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch()


def ensure_config(cfg: dict[str, Any]) -> dict[str, Any]:
    if "bots" in cfg and "default" in cfg and "topics" in cfg:
        return cfg
    return normalize_config(cfg)


def entry_topic(entry: dict[str, Any]) -> str:
    meta = entry.get("meta") if isinstance(entry.get("meta"), dict) else {}
    return str(meta.get("topic") or "").strip()


def feishu_routes(entry: dict[str, Any], cfg: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    cfg = ensure_config(cfg)
    targets = [str(target) for target in (entry.get("targets") or ["feishu"])]
    routes: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()
    for target in targets:
        if target != "feishu" and not target.startswith("feishu:"):
            continue
        topic = target.split(":", 1)[1] if ":" in target else entry_topic(entry)
        bot_names = cfg["topics"].get(topic, []) if topic else []
        if not bot_names and topic in cfg["bots"]:
            bot_names = [topic]
        if not bot_names:
            bot_names = [cfg["default"]]
        for bot_name in bot_names:
            route_key = "feishu" if bot_name == cfg["default"] and not topic else f"feishu:{bot_name}"
            if route_key in seen:
                continue
            seen.add(route_key)
            routes.append((route_key, cfg["bots"][bot_name]))
    return routes


def pending_feishu_routes(entry: dict[str, Any], runtime: Path, cfg: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    entry_id = str(entry.get("id") or "")
    return [(target, bot) for target, bot in feishu_routes(entry, cfg) if not is_delivered(runtime, entry_id, target)]


def should_push(entry: dict[str, Any], runtime: Path, quiet: bool, cfg: dict[str, Any]) -> bool:
    cfg = ensure_config(cfg)
    if not pending_feishu_routes(entry, runtime, cfg):
        return False
    level = entry.get("level")
    if level == "info":
        return False
    if quiet and level != "critical":
        return False
    return True


def pending_entries(entries: list[dict[str, Any]], runtime: Path, now: datetime, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    quiet = is_quiet(now)
    return [entry for entry in entries if should_push(entry, runtime, quiet, cfg)]


def link_lines(entry: dict[str, Any]) -> list[str]:
    lines = []
    for link in entry.get("links") or []:
        if not isinstance(link, dict):
            continue
        label = str(link.get("label") or "link")
        url = str(link.get("url") or "")
        if url:
            lines.append(f"[{label}]({url})")
    for path in entry.get("paths") or []:
        value = str(path)
        if value.startswith(("http://", "https://")):
            lines.append(f"[link]({value})")
        else:
            lines.append(f"`{value}`")
    return lines


def author_tag_text(meta: dict[str, Any], limit: int = 3) -> str:
    raw_tags = meta.get("author_tags") or []
    if isinstance(raw_tags, str):
        values = re.split(r"[,，/|;；]", raw_tags)
    elif isinstance(raw_tags, list):
        values = raw_tags
    else:
        values = []
    tags: list[str] = []
    seen: set[str] = set()
    for value in values:
        tag = re.sub(r"\s+", " ", str(value or "")).strip()
        key = tag.lower()
        if not tag or key in seen:
            continue
        seen.add(key)
        tags.append(tag)
        if len(tags) >= limit:
            break
    return " · ".join(tags)


def build_card(entry: dict[str, Any]) -> dict[str, Any]:
    level = str(entry.get("level") or "info")
    source = str(entry.get("source") or "notification")
    title = str(entry.get("title") or "(untitled)")
    meta = entry.get("meta") if isinstance(entry.get("meta"), dict) else {}
    display = meta.get("display") if isinstance(meta.get("display"), dict) else {}
    tags = author_tag_text(meta)
    display_title = f"{title}  {tags}" if tags else title
    title_content = display_title if display.get("hide_source_prefix") else f"[{source}] {display_title}"
    body_lines = []
    summary = str(entry.get("summary") or "").strip()
    if summary:
        body_lines.append(summary)
    links = link_lines(entry)
    if links:
        if body_lines:
            body_lines.append("")
        body_lines.extend(links[:5])
    if not display.get("hide_footer"):
        footer = str(entry.get("ts") or "")[11:16]
        if not display.get("hide_level"):
            footer = f"{footer} · {level}"
        body_lines.append("")
        body_lines.append(f"<font color=grey>{footer}</font>")
    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": title_content[:150]},
                "template": LEVEL_COLOR.get(level, "blue"),
            },
            "elements": [{"tag": "markdown", "content": "\n".join(body_lines)}],
        },
    }


def digest_due(runtime: Path, now: datetime) -> bool:
    if now.hour != DIGEST_HOUR:
        return False
    if not (DIGEST_WINDOW[0] <= now.minute < DIGEST_WINDOW[1]):
        return False
    return not digest_marker(runtime, now.strftime("%Y-%m-%d")).exists()


def build_digest_card(entries: list[dict[str, Any]], runtime: Path, now: datetime, cfg: dict[str, Any]) -> dict[str, Any]:
    undelivered = [entry for entry in entries if pending_feishu_routes(entry, runtime, cfg)]
    by_level: dict[str, list[dict[str, Any]]] = {"critical": [], "alert": [], "info": []}
    for entry in undelivered:
        by_level.setdefault(str(entry.get("level") or "info"), []).append(entry)
    lines = [f"Daily notification digest {now.strftime('%Y-%m-%d')}", ""]
    for level in ("critical", "alert", "info"):
        bucket = by_level.get(level) or []
        if not bucket:
            continue
        lines.append(f"**{level} ({len(bucket)})**")
        for entry in bucket[:10]:
            lines.append(f"- [{entry.get('source')}] {entry.get('title')}")
        if len(bucket) > 10:
            lines.append(f"- ... {len(bucket) - 10} more")
        lines.append("")
    if len(lines) == 2:
        lines.append("No pending notifications.")
    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": "Notification Center Digest"},
                "template": "blue",
            },
            "elements": [{"tag": "markdown", "content": "\n".join(lines)}],
        },
    }


def dispatch(runtime: Path, cfg: dict[str, Any], dry_run: bool = False, now: datetime | None = None) -> dict[str, Any]:
    now = now or now_cst()
    if dry_run:
        return _dispatch_unlocked(runtime, cfg, dry_run=True, now=now)

    runtime.mkdir(parents=True, exist_ok=True)
    lock_path = runtime / LOCK_NAME
    with lock_path.open("a+", encoding="utf-8") as lock_fh:
        try:
            fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            entries = load_entries(runtime, now)
            result = {
                "ok": True,
                "runtime": str(runtime),
                "total_today": len(entries),
                "pending": 0,
                "pushed": 0,
                "failed": 0,
                "digest": False,
                "quiet": is_quiet(now),
                "locked": True,
            }
            log(runtime, "LOCKED dispatch already running")
            log(runtime, "RUN " + json.dumps(result, ensure_ascii=False, sort_keys=True))
            return result
        try:
            return _dispatch_unlocked(runtime, cfg, dry_run=False, now=now)
        finally:
            fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)


def _dispatch_unlocked(runtime: Path, cfg: dict[str, Any], dry_run: bool = False, now: datetime | None = None) -> dict[str, Any]:
    now = now or now_cst()
    cfg = ensure_config(cfg)
    entries = load_entries(runtime, now)
    to_push = pending_entries(entries, runtime, now, cfg)
    pushed = 0
    failed = 0
    dry: list[str] = []
    send_index = 0

    for entry in to_push:
        entry_id = str(entry.get("id") or "")
        for target, bot in pending_feishu_routes(entry, runtime, cfg):
            if send_index > 0 and not dry_run:
                time.sleep(3.5)
            send_index += 1
            if dry_run:
                dry.append(f"{target} {entry.get('level')} {entry.get('source')} {entry.get('title')}")
                continue
            try:
                response = post_feishu(bot["webhook"], bot["secret"], build_card(entry))
            except Exception as exc:
                failed += 1
                log(runtime, f"SEND ERROR {entry_id} {target} {exc}")
                continue
            if response.get("code") == 0:
                mark_delivered(runtime, entry_id, target)
                pushed += 1
                log(runtime, f"SEND OK {entry_id} {target} {entry.get('level')} {entry.get('source')}")
            else:
                failed += 1
                log(runtime, f"SEND FAIL {entry_id} {target} resp={response}")
                if response.get("code") == 11232:
                    break

    digest_sent = False
    if digest_due(runtime, now):
        if dry_run:
            dry.append("digest")
        else:
            try:
                bot = cfg["bots"][cfg["default"]]
                response = post_feishu(bot["webhook"], bot["secret"], build_digest_card(entries, runtime, now, cfg))
            except Exception as exc:
                failed += 1
                log(runtime, f"DIGEST ERROR {exc}")
            else:
                if response.get("code") == 0:
                    mark_digest(runtime, now.strftime("%Y-%m-%d"))
                    digest_sent = True
                    log(runtime, f"DIGEST OK {now.strftime('%Y-%m-%d')}")
                else:
                    failed += 1
                    log(runtime, f"DIGEST FAIL resp={response}")

    result = {
        "ok": failed == 0,
        "runtime": str(runtime),
        "total_today": len(entries),
        "pending": len(to_push),
        "pushed": pushed,
        "failed": failed,
        "digest": digest_sent,
        "quiet": is_quiet(now),
    }
    if dry_run:
        result["dry_run"] = dry
    log(runtime, "RUN " + json.dumps(result, ensure_ascii=False, sort_keys=True))
    return result


def send_test(cfg: dict[str, Any], dry_run: bool = False) -> dict[str, Any]:
    cfg = ensure_config(cfg)
    entry = {
        "id": f"test-{int(time.time())}",
        "ts": now_cst().isoformat(timespec="seconds"),
        "source": "notification-center",
        "level": "alert",
        "title": "Feishu webhook self-test",
        "summary": "Notification center can sign and send Feishu interactive cards.",
        "links": [],
        "paths": [],
    }
    if dry_run:
        return build_card(entry)
    bot = cfg["bots"][cfg["default"]]
    return post_feishu(bot["webhook"], bot["secret"], build_card(entry))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Dispatch notification center events")
    parser.add_argument("--runtime", help="Notification center runtime directory")
    parser.add_argument("--config", help="Feishu config path")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--test", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    runtime = Path(args.runtime).expanduser() if args.runtime else runtime_dir()
    cfg_path = Path(args.config).expanduser() if args.config else config_path()
    cfg = load_config(cfg_path)
    if args.test:
        result = send_test(cfg, dry_run=args.dry_run)
    else:
        result = dispatch(runtime, cfg, dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.dry_run else None))
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
