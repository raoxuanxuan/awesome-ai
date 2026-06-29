#!/usr/bin/env python3
"""Inspect KOL wiki rollout readiness."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from kol_common import DEFAULT_VAULT, wiki_dir


CORE_FILES = ("_index.md", "soul.md", "timeline.md")
CONTENT_DIRS = ("sources", "methods", "positions")

READINESS_BY_LEGACY_ROUTE = {
    "existing_mature_wiki": "mature_wiki",
    "partial_wiki_repair": "partial_wiki",
    "bootstrap_required": "no_wiki_yet",
    "not_ready": "clean_index_not_ready",
}

NEXT_ACTION_BY_READINESS = {
    "mature_wiki": "process_delta",
    "partial_wiki": "create_repair_pack",
    "no_wiki_yet": "create_bootstrap_pack",
    "clean_index_not_ready": "run_clean_index_first",
}


def count_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def markdown_count(path: Path) -> int:
    if not path.exists():
        return 0
    return len([p for p in path.glob("*.md") if p.is_file() and ".bak-" not in p.name])


def index_source_is_clean_corpus(stats_payload: dict[str, Any], clean_path: Path) -> bool:
    source = str(stats_payload.get("source") or "")
    if not source:
        return False
    source_path = Path(source)
    try:
        return source_path.resolve() == clean_path.resolve()
    except FileNotFoundError:
        return source_path.name == clean_path.name and source.endswith("/wiki/.clean_corpus.jsonl")


def classify_handle(vault: Path, handle: str) -> dict[str, Any]:
    wdir = wiki_dir(vault, handle)
    clean = wdir / ".clean_corpus.jsonl"
    index = wdir / ".ingest_index.jsonl"
    stats = wdir / ".ingest_stats.json"
    meta = wdir / ".ingest_meta.json"
    issues: list[str] = []

    clean_count = count_jsonl(clean)
    index_count = count_jsonl(index)
    stats_payload = read_json(stats)
    index_source = str(stats_payload.get("source") or "")
    source_is_clean = index_source_is_clean_corpus(stats_payload, clean)

    if not clean.exists():
        issues.append("missing .clean_corpus.jsonl")
    if not index.exists():
        issues.append("missing .ingest_index.jsonl")
    if not stats.exists():
        issues.append("missing .ingest_stats.json")
    elif not source_is_clean:
        issues.append("index source is not clean corpus")
    if clean.exists() and clean_count == 0:
        issues.append("empty .clean_corpus.jsonl")
    if index.exists() and index_count == 0:
        issues.append("empty .ingest_index.jsonl")

    core_present = {name: (wdir / name).exists() for name in CORE_FILES}
    for name, exists in core_present.items():
        if not exists:
            issues.append(f"missing {name}")

    content_counts = {name: markdown_count(wdir / name) for name in CONTENT_DIRS}
    if sum(content_counts.values()) == 0:
        issues.append("missing durable content pages")

    if clean_count == 0 or index_count == 0 or not stats.exists():
        legacy_route = "not_ready"
    elif all(core_present.values()) and sum(content_counts.values()) > 0 and source_is_clean:
        legacy_route = "existing_mature_wiki"
    elif any(core_present.values()) or sum(content_counts.values()) > 0:
        legacy_route = "partial_wiki_repair"
    else:
        legacy_route = "bootstrap_required"

    readiness = READINESS_BY_LEGACY_ROUTE[legacy_route]

    return {
        "kol": handle,
        "readiness": readiness,
        "next_action": NEXT_ACTION_BY_READINESS[readiness],
        "issues": issues,
        "clean_count": clean_count,
        "index_count": index_count,
        "index_source": index_source,
        "index_source_is_clean": source_is_clean,
        "core_present": core_present,
        "content_counts": content_counts,
        "has_ingest_meta": meta.exists(),
    }


def iter_handles(vault: Path) -> list[str]:
    if not vault.exists():
        return []
    return sorted(
        p.name
        for p in vault.iterdir()
        if p.is_dir()
        and not p.name.startswith(".")
        and p.name != "_cross"
        and (p / "wiki").is_dir()
    )


def inventory_vault(vault: Path) -> dict[str, Any]:
    kols = [classify_handle(vault, handle) for handle in iter_handles(vault)]
    by_readiness: dict[str, int] = {}
    by_next_action: dict[str, int] = {}
    for item in kols:
        by_readiness[item["readiness"]] = by_readiness.get(item["readiness"], 0) + 1
        by_next_action[item["next_action"]] = by_next_action.get(item["next_action"], 0) + 1
    return {
        "vault": str(vault),
        "kols": kols,
        "by_readiness": by_readiness,
        "by_next_action": by_next_action,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect KOL wiki rollout readiness.")
    parser.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    parser.add_argument("--kol")
    parser.add_argument("--handle", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    kol = args.kol or args.handle
    result = classify_handle(args.vault, kol) if kol else inventory_vault(args.vault)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
