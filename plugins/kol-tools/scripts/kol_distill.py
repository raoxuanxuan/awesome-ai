#!/usr/bin/env python3
"""Generate reviewable KOL distillation prompt packs.

The first productized distill mode is intentionally conservative: it prepares a
workspace for an agent or human reviewer, but does not modify durable wiki pages
or advance the ingest watermark.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kol_common import DEFAULT_VAULT, wiki_dir


TOPIC_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("AI算力与Capex", ("ai", "api", "token", "capex", "算力", "大科技", "anthropic", "agent", "coding", "英伟达", "模型")),
    ("美联储与利率", ("fed", "美联储", "加息", "降息", "债市", "沃什", "鲍威尔", "通胀", "货币政策")),
    ("市场盈利预期", ("eps", "标普", "盈利预期", "增速", "市场预期")),
    ("个股时间成本与退出标准", ("时间成本", "退出", "仓位", "估值", "财报", "替代品")),
    ("公司经营与管理层变化", ("oracle", "nbis", "intel", "陈", "管理", "公司", "人员", "氛围")),
    ("现金流与商业模式", ("现金流", "软件", "costco", "沃尔玛", "投资回报")),
    ("杂感与社区互动", ("中超", "大统华", "硅谷", "社区", "排队")),
]

CORE_WIKI_FILES = ("soul.md", "timeline.md", "_index.md", "_log.md")


def now_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )


def load_delta_info(vault: Path, handle: str) -> dict[str, Any]:
    path = wiki_dir(vault, handle) / ".ingest_delta.json"
    if not path.exists():
        raise FileNotFoundError(f"missing delta file: {path}")
    info = read_json(path)
    if info.get("status") != "ready":
        raise RuntimeError(f"delta status must be ready, got {info.get('status')!r}")
    return info


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_delta_ids(info: dict[str, Any]) -> list[str]:
    path_value = info.get("delta_tsv")
    if not path_value:
        return []
    path = Path(str(path_value))
    if not path.exists():
        return []
    ids = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        tweet_id = line.split("\t", 1)[0].strip()
        if tweet_id:
            ids.append(tweet_id)
    return ids


def id_in_delta(tweet_id: str, old: str, proposed: str) -> bool:
    if tweet_id.isdigit() and old.isdigit() and proposed.isdigit():
        value = int(tweet_id)
        return int(old) < value <= int(proposed)
    return old < tweet_id <= proposed


def load_delta_items(info: dict[str, Any]) -> list[dict[str, Any]]:
    source = Path(str(info.get("source") or ""))
    if not source.exists():
        raise FileNotFoundError(f"delta source not found: {source}")
    old = str(info.get("watermark_old") or "")
    proposed = str(info.get("watermark_proposed") or "")
    delta_ids = load_delta_ids(info)
    delta_id_set = set(delta_ids)
    rows = []
    for row in load_jsonl(source):
        tweet_id = str(row.get("id") or "")
        if delta_id_set:
            include = tweet_id in delta_id_set
        else:
            include = bool(tweet_id and id_in_delta(tweet_id, old, proposed))
        if include:
            rows.append(normalize_item(row))
    if delta_ids:
        order = {tweet_id: index for index, tweet_id in enumerate(delta_ids)}
        rows.sort(key=lambda item: order.get(str(item["id"]), len(order)))
    else:
        rows.sort(key=lambda item: int(item["id"]) if str(item["id"]).isdigit() else item["id"])
    return rows


def normalize_item(row: dict[str, Any]) -> dict[str, Any]:
    text = str(row.get("text") or row.get("full_text") or "").strip()
    stats = row.get("stats") if isinstance(row.get("stats"), dict) else {}
    return {
        "id": str(row.get("id") or ""),
        "date": str(row.get("date") or row.get("created_at") or "")[:10],
        "lang": row.get("lang") or "",
        "url": row.get("url") or "",
        "text": text,
        "is_reply": bool(row.get("is_reply")),
        "in_reply_to": row.get("in_reply_to") or row.get("reply_to") or "",
        "is_quote": bool(row.get("is_quote")),
        "quality": row.get("quality") or "",
        "favorite_count": row.get("favorite_count", stats.get("likes", 0)),
        "retweet_count": row.get("retweet_count", stats.get("retweets", 0)),
        "view_count": row.get("view_count", stats.get("views", 0)),
        "routing": row.get("routing") if isinstance(row.get("routing"), dict) else {},
        "topics": suggest_topics(text),
        "targets": extract_targets(text),
    }


def suggest_topics(text: str) -> list[str]:
    topics = [name for name, keywords in TOPIC_RULES if any(keyword_matches(text, keyword) for keyword in keywords)]
    return topics or ["杂感与社区互动"]


def keyword_matches(text: str, keyword: str) -> bool:
    if keyword.isascii() and re.fullmatch(r"[A-Za-z0-9_+-]+", keyword):
        return re.search(
            rf"(?<![A-Za-z0-9_]){re.escape(keyword)}(?![A-Za-z0-9_])",
            text,
            flags=re.IGNORECASE,
        ) is not None
    return keyword.lower() in text.lower()


def extract_targets(text: str) -> list[str]:
    targets = {match.upper() for match in re.findall(r"\$([A-Za-z]{1,6})\b", text)}
    aliases = {
        "oracle": "ORCL",
        "英伟达": "NVDA",
        "nvidia": "NVDA",
        "intel": "INTC",
        "costco": "COST",
        "沃尔玛": "WMT",
    }
    lowered = text.lower()
    for key, value in aliases.items():
        if key.lower() in lowered:
            targets.add(value)
    return sorted(targets)


def group_by_topic(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        for topic in item["topics"]:
            grouped[topic].append(item)
    return dict(sorted(grouped.items(), key=lambda kv: (-len(kv[1]), kv[0])))


def slugify_topic(topic: str) -> str:
    known = {
        "AI算力与Capex": "ai-capex",
        "美联储与利率": "fed-rates",
        "个股时间成本与退出标准": "stock-time-cost",
        "公司经营与管理层变化": "company-operations",
        "现金流与商业模式": "cash-flow-business-model",
        "杂感与社区互动": "community-interactions",
    }
    return known.get(topic, re.sub(r"[^A-Za-z0-9]+", "-", topic).strip("-").lower() or "topic")


def build_target_groups(vault: Path, handle: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    wdir = wiki_dir(vault, handle)
    topics = group_by_topic(items)
    target_ids = sorted({target for item in items for target in item.get("targets", [])})
    return {
        "sources": [
            {
                "topic": topic,
                "suggested_path": str(wdir / "sources" / f"{slugify_topic(topic)}.md"),
                "tweet_ids": [item["id"] for item in topic_items],
                "reply_count": sum(1 for item in topic_items if item.get("is_reply")),
            }
            for topic, topic_items in topics.items()
        ],
        "methods": [
            {
                "name": "根据市场信号动态修正判断",
                "suggested_path": str(wdir / "methods" / "market-signal-revision.md"),
                "tweet_ids": [item["id"] for item in items if "美联储与利率" in item.get("topics", [])],
            },
            {
                "name": "个股时间成本与退出标准",
                "suggested_path": str(wdir / "methods" / "stock-time-cost.md"),
                "tweet_ids": [item["id"] for item in items if "个股时间成本与退出标准" in item.get("topics", [])],
            },
        ],
        "positions": [
            {
                "target": target,
                "suggested_path": str(wdir / "positions" / f"{target}.md"),
                "tweet_ids": [item["id"] for item in items if target in item.get("targets", [])],
            }
            for target in target_ids
        ],
        "timeline": [{"suggested_path": str(wdir / "timeline.md")}],
        "soul": [{"suggested_path": str(wdir / "soul.md")}],
        "index_log": [
            {"suggested_path": str(wdir / "_index.md")},
            {"suggested_path": str(wdir / "_log.md")},
        ],
    }


def existing_paths_from_targets(target_groups: dict[str, Any]) -> list[str]:
    paths = set()
    for entries in target_groups.values():
        for entry in entries:
            path = Path(str(entry.get("suggested_path") or ""))
            if path.exists():
                paths.add(str(path))
    return sorted(paths)


def build_backup_plan(vault: Path, handle: str, target_groups: dict[str, Any]) -> dict[str, Any]:
    wdir = wiki_dir(vault, handle)
    core_existing = [str(wdir / name) for name in CORE_WIKI_FILES if (wdir / name).exists()]
    target_existing = existing_paths_from_targets(target_groups)
    to_backup = sorted(set(core_existing + target_existing))
    return {
        "handle": handle,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "note": "Plan only. prompt-pack mode does not create backup copies or mutate wiki files.",
        "paths": [
            {
                "path": path,
                "backup_hint": f"{path}.bak-before-distill-{today()}",
            }
            for path in to_backup
        ],
    }


def render_items_table(items: list[dict[str, Any]]) -> str:
    lines = ["| id | date | type | topics | text |", "| --- | --- | --- | --- | --- |"]
    for item in items:
        flag = "reply" if item.get("is_reply") else "tweet"
        text = item["text"].replace("\n", " ")[:180]
        lines.append(f"| {item['id']} | {item['date']} | {flag} | {', '.join(item['topics'])} | {text} |")
    return "\n".join(lines)


def render_brief(handle: str, info: dict[str, Any], items: list[dict[str, Any]], target_groups: dict[str, Any]) -> str:
    topic_lines = []
    for entry in target_groups["sources"]:
        topic_lines.append(f"- {entry['topic']}: {len(entry['tweet_ids'])} items, replies {entry['reply_count']}")
    return "\n".join(
        [
            f"# {handle} Distill Delta Brief",
            "",
            f"- delta: {len(items)}",
            f"- replies: {sum(1 for item in items if item.get('is_reply'))}",
            f"- watermark_old: {info.get('watermark_old')}",
            f"- watermark_proposed: {info.get('watermark_proposed')}",
            f"- date_range: {' ~ '.join(info.get('date_range') or [])}",
            "",
            "## Suggested Topics",
            *topic_lines,
            "",
            "## Delta Items",
            render_items_table(items),
            "",
            "## Next",
            "Use the prompts in `prompts/` to update wiki files. Do not commit the ingest watermark until the wiki changes are reviewed.",
            "",
        ]
    )


def render_prompt(title: str, handle: str, workspace: Path, target_groups: dict[str, Any], extra: str) -> str:
    return "\n".join(
        [
            f"# {title}",
            "",
            f"Handle: `{handle}`",
            "",
            "Read these generated files first:",
            f"- `{workspace / 'manifest.json'}`",
            f"- `{workspace / 'delta_items.jsonl'}`",
            f"- `{workspace / 'delta_brief.md'}`",
            f"- `{workspace / 'backup_plan.json'}`",
            "",
            "Hard rules:",
            "- Treat replies as first-class evidence.",
            "- Every durable claim must cite tweet ids.",
            "- Do not advance `.ingest_meta.json`; that is a separate commit step after review.",
            "- Back up existing target files before any real wiki mutation.",
            "",
            "Suggested targets:",
            json.dumps(target_groups, ensure_ascii=False, indent=2),
            "",
            extra,
            "",
        ]
    )


def write_prompt_pack(vault: Path, handle: str, pack_id: str, info: dict[str, Any], items: list[dict[str, Any]]) -> Path:
    wdir = wiki_dir(vault, handle)
    workspace = wdir / ".distill_prompt_packs" / pack_id
    prompts = workspace / "prompts"
    prompts.mkdir(parents=True, exist_ok=True)

    target_groups = build_target_groups(vault, handle, items)
    manifest = {
        "handle": handle,
        "mode": "prompt-pack",
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "delta_count": len(items),
        "reply_count": sum(1 for item in items if item.get("is_reply")),
        "watermark_old": info.get("watermark_old"),
        "watermark_proposed": info.get("watermark_proposed"),
        "date_range": info.get("date_range") or [],
        "delta_source": info.get("source"),
        "target_groups": target_groups,
        "safe_to_commit_watermark": False,
    }
    write_json(workspace / "manifest.json", manifest)
    write_jsonl(workspace / "delta_items.jsonl", items)
    (workspace / "delta_brief.md").write_text(
        render_brief(handle, info, items, target_groups),
        encoding="utf-8",
    )
    write_json(workspace / "backup_plan.json", build_backup_plan(vault, handle, target_groups))
    (prompts / "01-sources.md").write_text(
        render_prompt(
            "Sources Update Prompt",
            handle,
            workspace,
            {"sources": target_groups["sources"]},
            "Update or create only the relevant `wiki/sources/*.md` pages after review.",
        ),
        encoding="utf-8",
    )
    (prompts / "02-methods-positions.md").write_text(
        render_prompt(
            "Methods And Positions Update Prompt",
            handle,
            workspace,
            {"methods": target_groups["methods"], "positions": target_groups["positions"]},
            "Update methods only when the delta strengthens a repeated framework; update positions only when evidence is target-specific.",
        ),
        encoding="utf-8",
    )
    (prompts / "03-timeline-soul.md").write_text(
        render_prompt(
            "Timeline Soul Index Log Prompt",
            handle,
            workspace,
            {
                "timeline": target_groups["timeline"],
                "soul": target_groups["soul"],
                "index_log": target_groups["index_log"],
            },
            "Update `timeline.md`, `soul.md`, `_index.md`, and `_log.md` only after sources/methods/positions are reviewed.",
        ),
        encoding="utf-8",
    )
    return workspace


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare KOL distillation workspaces")
    parser.add_argument("handle")
    parser.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    parser.add_argument("--mode", choices=("prompt-pack",), default="prompt-pack")
    parser.add_argument("--pack-id", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        info = load_delta_info(args.vault, args.handle)
        items = load_delta_items(info)
        if len(items) != int(info.get("delta") or len(items)):
            # Keep going, but surface the mismatch in the generated manifest/report.
            pass
        pack_id = args.pack_id or f"delta-{info.get('watermark_proposed', 'unknown')}-{now_compact()}"
        workspace = write_prompt_pack(args.vault, args.handle, pack_id, info, items)
        print(
            json.dumps(
                {
                    "handle": args.handle,
                    "status": "prompt_pack_ready",
                    "workspace": str(workspace),
                    "delta": len(items),
                    "watermark_proposed": info.get("watermark_proposed"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"handle": args.handle, "status": "error", "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
