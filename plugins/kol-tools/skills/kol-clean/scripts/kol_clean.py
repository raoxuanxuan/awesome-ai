#!/usr/bin/env python3
"""Clean and score KOL raw tweet Markdown into a routed JSONL corpus."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

DEFAULT_VAULT = Path(os.environ.get("KOL_TOOLS_VAULT", "/Users/saberrao/vault/kol"))

FM_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)
TICKER_RE = re.compile(r"(?<!\w)\$[A-Za-z]{1,8}\b")
NUMBER_RE = re.compile(r"(\d+(?:\.\d+)?\s*%|\b\d{2,}\b)")
URL_RE = re.compile(r"https?://\S+")
MENTION_RE = re.compile(r"@\w+")
URL_ONLY_RE = re.compile(r"^\s*(https?://\S+\s*)+$")
MENTION_ONLY_RE = re.compile(r"^\s*(@\w+[\s,，]*)+$")

METHOD_KEYWORDS = (
    "FPE", "FORWARD", "PE", "P/E", "PEG", "capex", "CAPEX", "ARR", "ROI",
    "估值", "降息", "加息", "仓位", "加仓", "减仓", "看多", "看空",
    "左侧", "右侧", "证伪", "现金流", "财报", "guidance", "BETA",
)
POSITION_KEYWORDS = (
    "买", "卖", "持有", "不碰", "减仓", "加仓", "做多", "做空",
    "看多", "看空", "止盈", "止损", "仓位",
)
REASONING_KEYWORDS = (
    "因为", "所以", "但是", "如果", "只要", "除非", "证伪", "反而",
    "意味着", "核心", "逻辑", "前提", "ROI", "现金流", "需求", "供给",
)
TIMELINE_KEYWORDS = (
    "之前", "现在", "后来", "转向", "反转", "修正", "承认错", "卖飞",
    "复盘", "从", "到", "不再", "第一次",
)


def parse_scalar(raw: str) -> Any:
    value = raw.strip().strip('"').strip("'")
    low = value.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if low in {"null", "none", ""}:
        return None
    try:
        return int(value)
    except ValueError:
        return value


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    match = FM_RE.match(text)
    if not match:
        return {}, text.strip()
    block, body = match.groups()
    data: dict[str, Any] = {}
    for line in block.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        data[key.strip()] = parse_scalar(value)
    return data, body.strip()


def substantive_text(text: str) -> str:
    text = URL_RE.sub("", text)
    text = re.sub(r"^(RT @\w+:?\s*)", "", text.strip())
    text = re.sub(r"^(@\w+[\s,，]*)+", "", text.strip())
    return text.strip()


def source_type(meta: dict[str, Any], is_reply: bool, is_quote: bool) -> str:
    explicit = str(meta.get("source_type") or meta.get("source") or "").strip()
    if explicit == "subscriber":
        return "x_subscriber"
    if explicit in {"x_public", "x_reply", "x_quote", "x_subscriber", "manual_article"}:
        return explicit
    if is_reply:
        return "x_reply"
    if is_quote:
        return "x_quote"
    return "x_public"


def classify_text(text: str, is_reply: bool = False, is_quote: bool = False,
                  is_retweet: bool = False, source: str = "x_public") -> dict[str, Any]:
    raw = text or ""
    stripped = raw.strip()
    sub = substantive_text(stripped)
    reasons: list[str] = []

    has_ticker = bool(TICKER_RE.search(stripped))
    has_number = bool(NUMBER_RE.search(stripped))
    has_method = any(k.lower() in stripped.lower() for k in METHOD_KEYWORDS)
    has_position = any(k in stripped for k in POSITION_KEYWORDS)
    has_reasoning = any(k.lower() in stripped.lower() for k in REASONING_KEYWORDS)
    has_timeline = any(k in stripped for k in TIMELINE_KEYWORDS)

    if has_ticker:
        reasons.append("has_ticker")
    if has_number:
        reasons.append("has_number")
    if has_method:
        reasons.append("has_method_keyword")
    if has_position:
        reasons.append("has_position")
    if has_reasoning:
        reasons.append("has_reasoning")
    if has_timeline:
        reasons.append("has_timeline_signal")
    if is_reply:
        reasons.append("is_reply")
    if is_quote:
        reasons.append("is_quote")
    if source == "x_subscriber":
        reasons.append("subscriber_private")

    signal_score = sum([has_ticker, has_number, has_method, has_position, has_reasoning, has_timeline])
    length_score = min(len(sub) / 180.0, 1.0)
    content_density = min(1.0, round(length_score * 0.45 + min(signal_score / 4.0, 1.0) * 0.55, 2))

    if not stripped or URL_ONLY_RE.match(stripped) or MENTION_ONLY_RE.match(stripped):
        quality = "noise"
        if not stripped:
            reasons.append("empty")
        elif URL_ONLY_RE.match(stripped):
            reasons.append("url_only")
        else:
            reasons.append("mention_only")
    elif is_retweet:
        quality = "low" if signal_score else "noise"
        reasons.append("is_retweet")
    elif is_reply and len(sub) < 20 and signal_score == 0:
        quality = "noise"
        reasons.append("short_social_reply")
    elif is_reply and len(sub) >= 20:
        quality = "medium"
        reasons.append("substantive_reply_length")
    elif signal_score >= 3 or (has_ticker and has_reasoning) or (has_method and has_reasoning):
        quality = "high"
    elif signal_score >= 1 or len(sub) >= 80:
        quality = "medium"
    else:
        quality = "low"

    routing = {
        "distill": quality in {"high", "medium"},
        "voice": bool(stripped) and quality != "noise" or bool(stripped and is_reply),
        "timeline": quality in {"high", "medium"} and has_timeline,
        "position": quality in {"high", "medium"} and (has_ticker or has_position),
    }

    return {
        "quality": quality,
        "content_density": content_density,
        "routing": routing,
        "reasons": sorted(set(reasons)),
    }


def raw_item(path: Path) -> dict[str, Any] | None:
    meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
    tweet_id = str(meta.get("id") or path.stem).strip()
    if not tweet_id:
        return None
    is_reply = bool(meta.get("is_reply"))
    is_quote = bool(meta.get("is_quote"))
    is_retweet = bool(meta.get("is_retweet"))
    st = source_type(meta, is_reply, is_quote)
    classified = classify_text(body, is_reply=is_reply, is_quote=is_quote,
                               is_retweet=is_retweet, source=st)
    visibility = "subscriber_private" if st == "x_subscriber" else "private"
    return {
        "id": tweet_id,
        "date": meta.get("created_at") or meta.get("date") or "",
        "url": meta.get("url") or "",
        "text": body,
        "lang": meta.get("lang", "unknown") or "unknown",
        "is_reply": is_reply,
        "is_quote": is_quote,
        "is_retweet": is_retweet,
        "is_thread_part": bool(meta.get("is_thread_part", False)),
        "conversation_id": str(meta.get("conversation_id") or ""),
        "reply_to": meta.get("in_reply_to") or meta.get("reply_to") or None,
        "favorite_count": int(meta.get("favorite_count", 0) or 0),
        "retweet_count": int(meta.get("retweet_count", 0) or 0),
        "reply_count": int(meta.get("reply_count", 0) or 0),
        "view_count": int(meta.get("view_count", 0) or 0),
        "media_count": int(meta.get("media_count", 0) or 0),
        "length": int(meta.get("full_text_length", len(body)) or len(body)),
        "quality": classified["quality"],
        "content_density": classified["content_density"],
        "routing": classified["routing"],
        "reasons": classified["reasons"],
        "source_type": st,
        "visibility": visibility,
    }


def clean_handle(handle: str, vault: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    raw_dir = vault / handle / "raw" / "tweets"
    if not raw_dir.is_dir():
        raise FileNotFoundError(f"raw tweets dir not found: {raw_dir}")
    items = [item for path in sorted(raw_dir.glob("*.md")) if (item := raw_item(path))]
    quality = Counter(item["quality"] for item in items)
    source_counts = Counter(item["source_type"] for item in items)
    stats = {
        "handle": handle,
        "total": len(items),
        "quality": dict(sorted(quality.items())),
        "source_type": dict(sorted(source_counts.items())),
        "replies": sum(1 for item in items if item["is_reply"]),
        "substantive_replies": sum(
            1 for item in items
            if item["is_reply"] and item["quality"] in {"high", "medium"}
        ),
        "distill": sum(1 for item in items if item["routing"]["distill"]),
        "voice": sum(1 for item in items if item["routing"]["voice"]),
        "position": sum(1 for item in items if item["routing"]["position"]),
        "timeline": sum(1 for item in items if item["routing"]["timeline"]),
        "output": str(vault / handle / "wiki" / ".clean_corpus.jsonl"),
    }
    return items, stats


def write_jsonl(items: list[dict[str, Any]], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for item in items:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Clean and score KOL raw tweets.")
    parser.add_argument("handle", nargs="?")
    parser.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    parser.add_argument("--input", type=Path, help="classify one raw tweet Markdown file")
    parser.add_argument("--json", action="store_true", help="accepted for explicit JSON output")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="print stats without writing")
    mode.add_argument("--write", action="store_true", help="write wiki/.clean_corpus.jsonl")
    args = parser.parse_args(argv)

    if args.input:
        try:
            item = raw_item(args.input)
            if item is None:
                raise ValueError(f"no tweet id found in {args.input}")
        except Exception as exc:  # noqa: BLE001
            print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False))
            return 2
        print(json.dumps(item, ensure_ascii=False, indent=2))
        return 0

    if not args.handle:
        parser.error("handle is required unless --input is provided")

    try:
        items, stats = clean_handle(args.handle, args.vault)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"handle": args.handle, "status": "error", "error": str(exc)}, ensure_ascii=False))
        return 2

    if args.write:
        write_jsonl(items, Path(stats["output"]))
        stats["status"] = "written"
    else:
        stats["status"] = "dry_run"
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
