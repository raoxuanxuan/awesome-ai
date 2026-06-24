#!/usr/bin/env python3
"""Build deterministic KOL ingest index from clean corpus or raw Markdown."""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_VAULT = Path(os.environ.get("KOL_TOOLS_VAULT", "/Users/saberrao/vault/kol"))

FM_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)
URL_ONLY_RE = re.compile(r"^https?://\S+\s*$")
MENTION_ONLY_RE = re.compile(r"^(@\w+\s*)+$")
SIGNAL_RE = re.compile(
    r"(\$[A-Za-z]{1,8}\b|\d+\s*%|看多|看空|加仓|减仓|做空|做多|"
    r"PEG|FPE|FORWARD|capex|ARR|估值|降息|加息|仓位)",
    re.IGNORECASE,
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


def substantive(body: str) -> str:
    s = re.sub(r"https?://\S+", "", body)
    s = re.sub(r"^(RT @\w+:?\s*)", "", s.strip())
    s = re.sub(r"^(@\w+[\s,，]*)+", "", s.strip())
    return s.strip()


def is_low_content(body: str, is_reply: bool = False) -> bool:
    s = body.strip()
    if len(s) < 10:
        return True
    if URL_ONLY_RE.match(s) or MENTION_ONLY_RE.match(s):
        return True
    no_url = re.sub(r"https?://\S+", "", s).strip()
    if len(no_url) < 5:
        return True
    if is_reply:
        sub = substantive(s)
        if len(sub) < 20 and not SIGNAL_RE.search(sub):
            return True
    return False


def doc_from_raw(path: Path) -> dict[str, Any] | None:
    meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
    tweet_id = meta.get("id") or path.stem
    if not tweet_id:
        return None
    return {
        "id": str(tweet_id),
        "date": meta.get("created_at", "") or meta.get("date", ""),
        "lang": meta.get("lang", "unknown") or "unknown",
        "is_retweet": bool(meta.get("is_retweet", False)),
        "is_quote": bool(meta.get("is_quote", False)),
        "is_thread_part": bool(meta.get("is_thread_part", False)),
        "conversation_id": str(meta.get("conversation_id", "") or ""),
        "is_reply": bool(meta.get("is_reply", False)),
        "reply_to": meta.get("in_reply_to") or meta.get("reply_to") or None,
        "favorite_count": int(meta.get("favorite_count", 0) or 0),
        "retweet_count": int(meta.get("retweet_count", 0) or 0),
        "reply_count": int(meta.get("reply_count", 0) or 0),
        "view_count": int(meta.get("view_count", 0) or 0),
        "media_count": int(meta.get("media_count", 0) or 0),
        "length": int(meta.get("full_text_length", len(body)) or len(body)),
        "low_content": is_low_content(body, bool(meta.get("is_reply", False))),
        "text": body,
        "url": meta.get("url", "") or "",
    }


def doc_from_clean(item: dict[str, Any]) -> dict[str, Any]:
    text = item.get("text") or ""
    routing = item.get("routing") or {}
    doc = {
        "id": str(item["id"]),
        "date": item.get("date", ""),
        "lang": item.get("lang", "unknown") or "unknown",
        "is_retweet": bool(item.get("is_retweet", False)),
        "is_quote": bool(item.get("is_quote", False)),
        "is_thread_part": bool(item.get("is_thread_part", False)),
        "conversation_id": str(item.get("conversation_id", "") or ""),
        "is_reply": bool(item.get("is_reply", False)),
        "reply_to": item.get("reply_to"),
        "favorite_count": int(item.get("favorite_count", 0) or 0),
        "retweet_count": int(item.get("retweet_count", 0) or 0),
        "reply_count": int(item.get("reply_count", 0) or 0),
        "view_count": int(item.get("view_count", 0) or 0),
        "media_count": int(item.get("media_count", 0) or 0),
        "length": len(text),
        "low_content": item.get("quality") == "noise" or not bool(routing.get("distill", False)),
        "text": text,
        "url": item.get("url", ""),
        "quality": item.get("quality"),
        "content_density": item.get("content_density"),
        "routing": routing,
        "reasons": item.get("reasons", []),
        "source_type": item.get("source_type", "unknown"),
        "visibility": item.get("visibility", "private"),
    }
    return doc


def load_docs(handle: str, vault: Path, *, allow_raw: bool = True) -> tuple[list[dict[str, Any]], str]:
    wiki_dir = vault / handle / "wiki"
    clean_path = wiki_dir / ".clean_corpus.jsonl"
    if clean_path.exists():
        docs = []
        with clean_path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.rstrip("\n")
                if line.strip():
                    docs.append(doc_from_clean(json.loads(line)))
        return docs, str(clean_path)

    if not allow_raw:
        raise FileNotFoundError(f"clean corpus required for {handle}: {clean_path}")

    raw_dir = vault / handle / "raw" / "tweets"
    if not raw_dir.is_dir():
        raise FileNotFoundError(f"no clean corpus or raw tweets dir for {handle}")
    docs = [doc for path in sorted(raw_dir.glob("*.md")) if (doc := doc_from_raw(path))]
    return docs, str(raw_dir)


def build_stats(handle: str, docs: list[dict[str, Any]], source: str) -> dict[str, Any]:
    stats: dict[str, Any] = {
        "handle": handle,
        "total": len(docs),
        "source": source,
        "by_lang": Counter(),
        "by_year_month": Counter(),
        "retweet": 0,
        "thread_part": 0,
        "low_content": 0,
        "with_media": 0,
        "engagement_total": {"fav": 0, "rt": 0, "reply": 0, "view": 0},
        "reply": 0,
        "reply_low_filtered": 0,
    }
    quality = Counter()
    for doc in docs:
        stats["by_lang"][doc.get("lang", "unknown")] += 1
        date = doc.get("date") or ""
        if date:
            stats["by_year_month"][date[:7]] += 1
        if doc.get("is_retweet"):
            stats["retweet"] += 1
        if doc.get("is_thread_part"):
            stats["thread_part"] += 1
        if doc.get("is_reply"):
            stats["reply"] += 1
            if doc.get("low_content"):
                stats["reply_low_filtered"] += 1
        if doc.get("low_content"):
            stats["low_content"] += 1
        if doc.get("media_count"):
            stats["with_media"] += 1
        if doc.get("quality"):
            quality[doc["quality"]] += 1
        stats["engagement_total"]["fav"] += int(doc.get("favorite_count", 0) or 0)
        stats["engagement_total"]["rt"] += int(doc.get("retweet_count", 0) or 0)
        stats["engagement_total"]["reply"] += int(doc.get("reply_count", 0) or 0)
        stats["engagement_total"]["view"] += int(doc.get("view_count", 0) or 0)

    stats["by_lang"] = dict(stats["by_lang"].most_common())
    stats["by_year_month"] = dict(sorted(stats["by_year_month"].items()))
    if quality:
        stats["quality"] = dict(sorted(quality.items()))
    stats["built_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return stats


def write_outputs(vault: Path, handle: str, docs: list[dict[str, Any]], stats: dict[str, Any]) -> None:
    wiki_dir = vault / handle / "wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    docs.sort(key=lambda d: int(d["id"]), reverse=True)
    index_path = wiki_dir / ".ingest_index.jsonl"
    stats_path = wiki_dir / ".ingest_stats.json"
    with index_path.open("w", encoding="utf-8") as fh:
        for doc in docs:
            fh.write(json.dumps(doc, ensure_ascii=False) + "\n")
    stats["ingest_index_path"] = str(index_path)
    stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build KOL ingest index.")
    parser.add_argument("handle")
    parser.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--legacy-raw",
        action="store_true",
        help="allow fallback indexing directly from raw/tweets/*.md when clean corpus is missing",
    )
    args = parser.parse_args(argv)

    try:
        docs, source = load_docs(args.handle, args.vault, allow_raw=args.legacy_raw)
        docs.sort(key=lambda d: int(d["id"]), reverse=True)
        stats = build_stats(args.handle, docs, source)
        stats["status"] = "dry_run" if args.dry_run else "written"
        if not args.dry_run:
            write_outputs(args.vault, args.handle, docs, stats)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"handle": args.handle, "status": "error", "error": str(exc)}, ensure_ascii=False))
        return 2

    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
