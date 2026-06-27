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
import shutil
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kol_common import DEFAULT_VAULT, wiki_dir
from kol_delta import commit as commit_delta


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
SCHEMA_VERSION = "1"
SCHEMA_FILES = (
    "source.schema.md",
    "method.schema.md",
    "position.schema.md",
    "timeline.schema.md",
    "soul.schema.md",
)

SOURCE_TARGETS: dict[str, str] = {
    "AI算力与Capex": "AI算力与芯片.md",
    "美联储与利率": "美联储政策.md",
    "市场盈利预期": "财报季解读.md",
    "个股时间成本与退出标准": "方法论与复盘.md",
    "公司经营与管理层变化": "财报季解读.md",
    "现金流与商业模式": "消费与零售.md",
    "杂感与社区互动": "杂感与社区互动.md",
}

METHOD_TARGETS: dict[str, list[tuple[str, str]]] = {
    "AI算力与Capex": [
        ("ai-capex-roi", "AI capex / token price / ROI framework"),
        ("ai-fundamental-validation", "AI landing evidence and fundamental validation"),
    ],
    "美联储与利率": [
        ("rate-cut-roadmap", "Fed path and market pricing framework"),
        ("data-source-discipline", "market price as a data source"),
        ("self-correction", "stance revision when data changes"),
    ],
    "个股时间成本与退出标准": [
        ("horizon-discipline", "stock holding horizon and exit discipline"),
    ],
    "市场盈利预期": [
        ("narrative-cycle", "earnings setup versus market storylines"),
    ],
    "公司经营与管理层变化": [
        ("narrative-cycle", "turnaround or management-change narrative"),
    ],
    "现金流与商业模式": [
        ("narrative-cycle", "cash-flow and business-model story rotation"),
    ],
}

POLICIES: dict[str, dict[str, Any]] = {
    "balanced": {
        "auto_delta_max": 10,
        "agent_delta_max": 50,
        "auto_allowed_scopes": {"sources", "index_log"},
    },
    "conservative": {
        "auto_delta_max": 0,
        "agent_delta_max": 10,
        "auto_allowed_scopes": set(),
    },
}


def now_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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


def plugin_root() -> Path:
    return Path(__file__).resolve().parents[1]


def schema_source_dir() -> Path:
    return plugin_root() / "schemas"


def copy_schema_bundle(workspace: Path) -> dict[str, Any]:
    source_dir = schema_source_dir()
    target_dir = workspace / "schemas"
    target_dir.mkdir(parents=True, exist_ok=True)
    schemas = []
    missing = []
    for filename in SCHEMA_FILES:
        source = source_dir / filename
        target = target_dir / filename
        if not source.exists():
            missing.append(filename)
            continue
        shutil.copy2(source, target)
        schemas.append({
            "name": filename.removesuffix(".schema.md"),
            "filename": filename,
            "path": str(target),
        })
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "source": str(source_dir),
        "schemas": schemas,
        "missing": missing,
    }
    write_json(workspace / "schema_manifest.json", manifest)
    return manifest


def workspace_path(vault: Path, handle: str, pack_id: str) -> Path:
    if not pack_id:
        raise ValueError("--pack-id is required for apply/validate/commit")
    return wiki_dir(vault, handle) / ".distill_prompt_packs" / pack_id


def load_workspace(vault: Path, handle: str, pack_id: str) -> tuple[Path, dict[str, Any], list[dict[str, Any]]]:
    workspace = workspace_path(vault, handle, pack_id)
    manifest_path = workspace / "manifest.json"
    items_path = workspace / "delta_items.jsonl"
    if not manifest_path.exists():
        raise FileNotFoundError(f"missing manifest: {manifest_path}")
    if not items_path.exists():
        raise FileNotFoundError(f"missing delta items: {items_path}")
    return workspace, read_json(manifest_path), load_jsonl(items_path)


def update_manifest(workspace: Path, updates: dict[str, Any]) -> dict[str, Any]:
    manifest_path = workspace / "manifest.json"
    manifest = read_json(manifest_path)
    manifest.update(updates)
    write_json(manifest_path, manifest)
    return manifest


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
        "visibility": row.get("visibility") or row.get("audience") or "",
        "is_subscriber": bool(row.get("is_subscriber") or row.get("subscriber_only")),
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


def source_path_for_topic(wdir: Path, topic: str) -> Path:
    filename = SOURCE_TARGETS.get(topic)
    if filename:
        return wdir / "sources" / filename
    return wdir / "sources" / f"{slugify_topic(topic)}.md"


def method_entries_for_topic(wdir: Path, topic: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entries = []
    for stem, reason in METHOD_TARGETS.get(topic, []):
        path = wdir / "methods" / f"{stem}.md"
        entries.append(
            {
                "name": stem,
                "suggested_path": str(path),
                "exists": path.exists(),
                "reason": reason,
                "tweet_ids": [item["id"] for item in items if topic in item.get("topics", [])],
            }
        )
    return entries


def needs_timeline_update(items: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    reasons = []
    keywords = ("转", "修正", "最新", "最早", "大概率", "已定价", "100%", "90%", "不再", "证伪")
    for item in items:
        text = item.get("text", "")
        topics = set(item.get("topics", []))
        if "美联储与利率" in topics and any(keyword in text for keyword in keywords):
            reasons.append(f"{item['id']}: Fed path or rate stance may have changed")
        if "AI算力与Capex" in topics and "证伪" in text:
            reasons.append(f"{item['id']}: AI capex stance may need timeline context")
    return bool(reasons), reasons


def needs_soul_update(items: list[dict[str, Any]], delta_count: int) -> tuple[bool, list[str]]:
    reasons = []
    core_topics = {"AI算力与Capex", "美联储与利率"}
    high_core = [
        item
        for item in items
        if item.get("quality") == "high" and core_topics.intersection(set(item.get("topics", [])))
    ]
    if len(high_core) >= 2:
        reasons.append("multiple high-quality core-topic items may affect soul summaries")
    if delta_count >= 20:
        reasons.append("large enough delta to refresh top-level summaries")
    return bool(reasons), reasons


def build_target_groups(vault: Path, handle: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    wdir = wiki_dir(vault, handle)
    topics = group_by_topic(items)
    target_ids = sorted({target for item in items for target in item.get("targets", [])})
    method_entries_by_path: dict[str, dict[str, Any]] = {}
    for topic in topics:
        for entry in method_entries_for_topic(wdir, topic, items):
            existing = method_entries_by_path.get(entry["suggested_path"])
            if existing:
                existing["tweet_ids"] = sorted(set(existing["tweet_ids"] + entry["tweet_ids"]))
                existing["reason"] = f"{existing['reason']}; {entry['reason']}"
            else:
                method_entries_by_path[entry["suggested_path"]] = entry

    timeline_needed, timeline_reasons = needs_timeline_update(items)
    soul_needed, soul_reasons = needs_soul_update(items, len(items))
    return {
        "sources": [
            {
                "topic": topic,
                "suggested_path": str(source_path_for_topic(wdir, topic)),
                "exists": source_path_for_topic(wdir, topic).exists(),
                "tweet_ids": [item["id"] for item in topic_items],
                "reply_count": sum(1 for item in topic_items if item.get("is_reply")),
            }
            for topic, topic_items in topics.items()
        ],
        "methods": sorted(method_entries_by_path.values(), key=lambda entry: entry["suggested_path"]),
        "positions": [
            {
                "target": target,
                "suggested_path": str(wdir / "positions" / f"{target}.md"),
                "exists": (wdir / "positions" / f"{target}.md").exists(),
                "tweet_ids": [item["id"] for item in items if target in item.get("targets", [])],
            }
            for target in target_ids
        ],
        "timeline": [
            {
                "suggested_path": str(wdir / "timeline.md"),
                "exists": (wdir / "timeline.md").exists(),
                "required": timeline_needed,
                "reasons": timeline_reasons,
            }
        ],
        "soul": [
            {
                "suggested_path": str(wdir / "soul.md"),
                "exists": (wdir / "soul.md").exists(),
                "required": soul_needed,
                "reasons": soul_reasons,
            }
        ],
        "index_log": [
            {"suggested_path": str(wdir / "_index.md"), "exists": (wdir / "_index.md").exists()},
            {"suggested_path": str(wdir / "_log.md"), "exists": (wdir / "_log.md").exists()},
        ],
    }


def touched_scopes(target_groups: dict[str, Any]) -> set[str]:
    scopes = {"sources", "index_log"}
    if target_groups.get("methods"):
        scopes.add("methods")
    if target_groups.get("positions"):
        scopes.add("positions")
    if any(entry.get("required") for entry in target_groups.get("timeline", [])):
        scopes.add("timeline")
    if any(entry.get("required") for entry in target_groups.get("soul", [])):
        scopes.add("soul")
    return scopes


def build_risk_assessment(
    info: dict[str, Any],
    items: list[dict[str, Any]],
    target_groups: dict[str, Any],
    policy_name: str,
) -> dict[str, Any]:
    policy = POLICIES[policy_name]
    delta_count = len(items)
    reasons: list[str] = []
    blockers: list[str] = []
    scopes = touched_scopes(target_groups)

    expected_delta = int(info.get("delta") or delta_count)
    if expected_delta != delta_count:
        blockers.append(f"delta_count_mismatch expected={expected_delta} actual={delta_count}")
    for item in items:
        if not item.get("id") or not item.get("text"):
            blockers.append(f"missing required evidence fields for item {item.get('id') or '<unknown>'}")
        if item.get("visibility") in {"subscriber", "private"} or item.get("is_subscriber"):
            blockers.append(f"private/subscriber evidence requires manual handling: {item.get('id')}")

    new_methods = [entry for entry in target_groups.get("methods", []) if not entry.get("exists")]
    new_positions = [entry for entry in target_groups.get("positions", []) if not entry.get("exists")]
    if new_methods:
        reasons.append("new method target(s): " + ", ".join(entry["name"] for entry in new_methods))
    if new_positions:
        reasons.append("new position target(s): " + ", ".join(entry["target"] for entry in new_positions))
    if "timeline" in scopes:
        reasons.append("timeline current-stance candidate detected")
    if "soul" in scopes:
        reasons.append("soul/core-summary candidate detected")
    if delta_count > policy["agent_delta_max"]:
        reasons.append(f"delta_count {delta_count} exceeds agent review max {policy['agent_delta_max']}")
    elif delta_count > policy["auto_delta_max"]:
        reasons.append(f"delta_count {delta_count} exceeds auto max {policy['auto_delta_max']}")
    if not scopes.issubset(policy["auto_allowed_scopes"]):
        reasons.append("touches non-auto scopes: " + ", ".join(sorted(scopes - policy["auto_allowed_scopes"])))

    if blockers:
        risk_level = "blocked"
        review_status = "blocked"
        needs_user = True
    elif (
        delta_count > policy["agent_delta_max"]
        or new_methods
        or new_positions
        or "timeline" in scopes
        or "soul" in scopes
    ):
        risk_level = "high"
        review_status = "user_review_required"
        needs_user = True
    elif delta_count > policy["auto_delta_max"] or not scopes.issubset(policy["auto_allowed_scopes"]):
        risk_level = "medium"
        review_status = "agent_review_required"
        needs_user = False
    else:
        risk_level = "low"
        review_status = "auto_eligible"
        needs_user = False

    return {
        "policy": policy_name,
        "risk_level": risk_level,
        "review_status": review_status,
        "needs_user": needs_user,
        "scopes": sorted(scopes),
        "delta_count": delta_count,
        "reply_count": sum(1 for item in items if item.get("is_reply")),
        "blockers": blockers,
        "reasons": reasons,
        "safe_to_auto_apply": review_status == "auto_eligible",
        "safe_to_commit_watermark": False,
        "next_step": next_step_for_status(review_status),
    }


def next_step_for_status(review_status: str) -> str:
    if review_status == "auto_eligible":
        return "auto apply may proceed after deterministic validators pass"
    if review_status == "agent_review_required":
        return "run agent review and validators; user review is optional unless validators fail"
    if review_status == "user_review_required":
        return "review report and proposed wiki changes before applying or committing watermark"
    return "fix blockers before applying or committing watermark"


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


def render_brief(
    handle: str,
    info: dict[str, Any],
    items: list[dict[str, Any]],
    target_groups: dict[str, Any],
    risk: dict[str, Any],
) -> str:
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
            f"- risk_level: {risk['risk_level']}",
            f"- review_status: {risk['review_status']}",
            f"- needs_user: {str(risk['needs_user']).lower()}",
            "",
            "## Suggested Topics",
            *topic_lines,
            "",
            "## Risk Assessment",
            f"- policy: {risk['policy']}",
            f"- scopes: {', '.join(risk['scopes'])}",
            f"- next_step: {risk['next_step']}",
            "- reasons:",
            *(f"  - {reason}" for reason in (risk["reasons"] or ["none"])),
            "- blockers:",
            *(f"  - {blocker}" for blocker in (risk["blockers"] or ["none"])),
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
            f"- `{workspace / 'schema_manifest.json'}`",
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


def write_prompt_pack(
    vault: Path,
    handle: str,
    pack_id: str,
    info: dict[str, Any],
    items: list[dict[str, Any]],
    policy: str,
) -> Path:
    wdir = wiki_dir(vault, handle)
    workspace = wdir / ".distill_prompt_packs" / pack_id
    prompts = workspace / "prompts"
    prompts.mkdir(parents=True, exist_ok=True)

    schema_manifest = copy_schema_bundle(workspace)
    target_groups = build_target_groups(vault, handle, items)
    risk = build_risk_assessment(info, items, target_groups, policy)
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
        "schema_manifest": schema_manifest,
        "risk_assessment": risk,
        "risk_level": risk["risk_level"],
        "review_status": risk["review_status"],
        "needs_user": risk["needs_user"],
        "safe_to_auto_apply": risk["safe_to_auto_apply"],
        "safe_to_commit_watermark": risk["safe_to_commit_watermark"],
    }
    write_json(workspace / "manifest.json", manifest)
    write_json(workspace / "risk_assessment.json", risk)
    write_jsonl(workspace / "delta_items.jsonl", items)
    (workspace / "delta_brief.md").write_text(
        render_brief(handle, info, items, target_groups, risk),
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


def backup_file(path: Path, pack_id: str) -> str:
    backup = Path(f"{path}.bak-before-distill-{pack_id}-{now_compact()}")
    shutil.copy2(path, backup)
    return str(backup)


def render_source_append(pack_id: str, topic: str, items: list[dict[str, Any]]) -> str:
    lines = [
        "",
        f"## Distill Update: {pack_id}",
        "",
        f"Topic: {topic}",
        "",
        "## Evidence",
        "",
    ]
    for item in items:
        kind = "reply" if item.get("is_reply") else "tweet"
        text = str(item.get("text") or "").replace("\n", " ").strip()
        if len(text) > 220:
            text = text[:217] + "..."
        url = item.get("url") or f"https://x.com/i/status/{item['id']}"
        lines.append(f"- [{kind} {item['id']}]({url}) ({item.get('date', '')}) — {text}")
    lines.append("")
    return "\n".join(lines)


def apply_workspace(vault: Path, handle: str, pack_id: str, *, force: bool = False) -> tuple[int, dict[str, Any]]:
    workspace, manifest, items = load_workspace(vault, handle, pack_id)
    review_status = manifest.get("review_status")
    if review_status != "auto_eligible" and not force:
        return 2, {
            "handle": handle,
            "status": "apply_refused",
            "workspace": str(workspace),
            "reason": f"review_status={review_status}; use --force only after review",
        }
    if review_status == "blocked":
        return 2, {
            "handle": handle,
            "status": "apply_refused",
            "workspace": str(workspace),
            "reason": "blocked distill pack cannot be applied",
        }

    item_by_id = {str(item["id"]): item for item in items}
    changed_files: list[str] = []
    backups: list[str] = []
    for source in manifest.get("target_groups", {}).get("sources", []):
        path = Path(str(source.get("suggested_path") or ""))
        if not path.exists():
            if not force:
                return 2, {
                    "handle": handle,
                    "status": "apply_refused",
                    "workspace": str(workspace),
                    "reason": f"source target does not exist: {path}",
                }
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"# {source.get('topic') or path.stem}\n", encoding="utf-8")
        current = path.read_text(encoding="utf-8")
        marker = f"## Distill Update: {pack_id}"
        if marker in current:
            continue
        source_items = [item_by_id[tweet_id] for tweet_id in source.get("tweet_ids", []) if tweet_id in item_by_id]
        backups.append(backup_file(path, pack_id))
        path.write_text(
            current.rstrip() + "\n" + render_source_append(pack_id, str(source.get("topic") or ""), source_items),
            encoding="utf-8",
        )
        changed_files.append(str(path))

    log_path = wiki_dir(vault, handle) / "_log.md"
    if log_path.exists():
        current = log_path.read_text(encoding="utf-8")
    else:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        current = "# ingest log\n"
    marker = f"## Distill Apply: {pack_id}"
    if marker not in current:
        if log_path.exists():
            backups.append(backup_file(log_path, pack_id))
        log_lines = [
            "",
            marker,
            "",
            f"- applied_at: {now_iso()}",
            f"- review_status: {review_status}",
            f"- delta_count: {manifest.get('delta_count')}",
            f"- watermark_proposed: {manifest.get('watermark_proposed')}",
            f"- changed_files: {len(changed_files)}",
            "",
        ]
        log_path.write_text(current.rstrip() + "\n" + "\n".join(log_lines), encoding="utf-8")
        changed_files.append(str(log_path))

    result = {
        "handle": handle,
        "status": "applied",
        "workspace": str(workspace),
        "pack_id": pack_id,
        "changed_files": changed_files,
        "backups": backups,
        "applied_at": now_iso(),
    }
    write_json(workspace / "apply_result.json", result)
    update_manifest(workspace, {"apply_status": "applied", "applied_at": result["applied_at"]})
    return 0, result


def durable_markdown_files(wdir: Path) -> list[Path]:
    candidates = [wdir / "soul.md", wdir / "timeline.md", wdir / "_index.md", wdir / "_log.md"]
    for subdir in ("sources", "methods", "positions"):
        root = wdir / subdir
        if root.exists():
            candidates.extend(sorted(root.glob("*.md")))
    return [path for path in candidates if path.exists() and ".bak-" not in path.name]


def validate_workspace(vault: Path, handle: str, pack_id: str) -> tuple[int, dict[str, Any]]:
    workspace, manifest, items = load_workspace(vault, handle, pack_id)
    wdir = wiki_dir(vault, handle)
    markdown = durable_markdown_files(wdir)
    corpus = "\n".join(path.read_text(encoding="utf-8") for path in markdown)
    missing_ids = [str(item["id"]) for item in items if str(item["id"]) not in corpus]
    blockers = []
    risk_path = workspace / "risk_assessment.json"
    schema_manifest_path = workspace / "schema_manifest.json"
    if risk_path.exists():
        risk = read_json(risk_path)
    else:
        blockers.append("missing risk_assessment.json")
        risk = manifest.get("risk_assessment", {}) if isinstance(manifest.get("risk_assessment"), dict) else {}
    if schema_manifest_path.exists():
        schema_manifest = read_json(schema_manifest_path)
        for entry in schema_manifest.get("schemas", []):
            schema_path = Path(str(entry.get("path") or ""))
            if not schema_path.exists():
                blockers.append(f"missing schema file: {entry.get('filename')}")
        for filename in schema_manifest.get("missing", []):
            blockers.append(f"schema bundle missing source file: {filename}")
    else:
        blockers.append("missing schema_manifest.json")
    blockers.extend(list(risk.get("blockers", [])))
    safe = not missing_ids and not blockers
    result = {
        "handle": handle,
        "status": "validated" if safe else "validation_failed",
        "workspace": str(workspace),
        "pack_id": pack_id,
        "checked_files": [str(path) for path in markdown],
        "missing_ids": missing_ids,
        "blockers": blockers,
        "safe_to_commit_watermark": safe,
        "validated_at": now_iso(),
    }
    write_json(workspace / "validation_result.json", result)
    update_manifest(
        workspace,
        {
            "validation_status": result["status"],
            "validated_at": result["validated_at"],
            "safe_to_commit_watermark": safe,
        },
    )
    return (0 if safe else 2), result


def commit_workspace(vault: Path, handle: str, pack_id: str) -> tuple[int, dict[str, Any]]:
    workspace, manifest, _items = load_workspace(vault, handle, pack_id)
    validation_path = workspace / "validation_result.json"
    if not validation_path.exists():
        return 2, {
            "handle": handle,
            "status": "commit_refused",
            "workspace": str(workspace),
            "reason": "missing validation_result.json; run --mode validate first",
        }
    validation = read_json(validation_path)
    if not validation.get("safe_to_commit_watermark"):
        return 2, {
            "handle": handle,
            "status": "commit_refused",
            "workspace": str(workspace),
            "reason": "validation did not mark safe_to_commit_watermark",
        }
    result = commit_delta(
        vault,
        handle,
        str(manifest.get("watermark_proposed") or ""),
        int(manifest.get("delta_count") or 0),
    )
    result["workspace"] = str(workspace)
    result["pack_id"] = pack_id
    write_json(workspace / "commit_result.json", result)
    update_manifest(workspace, {"commit_status": result.get("status"), "committed_at": now_iso()})
    return (0 if result.get("status") in {"committed", "commit_noop"} else 2), result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare KOL distillation workspaces")
    parser.add_argument("handle")
    parser.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    parser.add_argument("--mode", choices=("prompt-pack", "apply", "validate", "commit"), default="prompt-pack")
    parser.add_argument("--pack-id", default="")
    parser.add_argument("--policy", choices=tuple(POLICIES), default="balanced")
    parser.add_argument("--force", action="store_true", help="allow apply for reviewed non-auto packs; blocked packs still refuse")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.mode == "apply":
            rc, result = apply_workspace(args.vault, args.handle, args.pack_id, force=args.force)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return rc
        if args.mode == "validate":
            rc, result = validate_workspace(args.vault, args.handle, args.pack_id)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return rc
        if args.mode == "commit":
            rc, result = commit_workspace(args.vault, args.handle, args.pack_id)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return rc

        info = load_delta_info(args.vault, args.handle)
        items = load_delta_items(info)
        if len(items) != int(info.get("delta") or len(items)):
            # Keep going, but surface the mismatch in the generated manifest/report.
            pass
        pack_id = args.pack_id or f"delta-{info.get('watermark_proposed', 'unknown')}-{now_compact()}"
        workspace = write_prompt_pack(args.vault, args.handle, pack_id, info, items, args.policy)
        manifest = read_json(workspace / "manifest.json")
        print(
            json.dumps(
                {
                    "handle": args.handle,
                    "status": "prompt_pack_ready",
                    "workspace": str(workspace),
                    "delta": len(items),
                    "watermark_proposed": info.get("watermark_proposed"),
                    "risk_level": manifest["risk_level"],
                    "review_status": manifest["review_status"],
                    "needs_user": manifest["needs_user"],
                    "safe_to_auto_apply": manifest["safe_to_auto_apply"],
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
