#!/usr/bin/env python3
"""Read-only KOL registry health checker."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

DEFAULT_VAULT = Path(os.environ.get("KOL_TOOLS_VAULT", "/Users/saberrao/vault/kol"))


def parse_scalar(raw: str) -> Any:
    value = raw.strip().strip("`").strip('"').strip("'")
    if value.lower() in {"null", "none", "待填", ""}:
        return None
    try:
        return int(value)
    except ValueError:
        return value


def parse_meta(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data: dict[str, Any] = {}
    current_key: str | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith(" ") and ":" in line:
            key, _, value = line.partition(":")
            current_key = key.strip()
            if value.strip():
                data[current_key] = parse_scalar(value.split("#", 1)[0])
            else:
                data[current_key] = []
        elif current_key and line.strip().startswith("-"):
            data.setdefault(current_key, [])
            if isinstance(data[current_key], list):
                data[current_key].append(line.strip()[1:].strip())
    return data


def registry_sections(registry_text: str) -> dict[str, dict[str, Any]]:
    sections: dict[str, dict[str, Any]] = {}
    current: str | None = None
    for line in registry_text.splitlines():
        match = re.match(r"^##\s+@?([A-Za-z0-9_]+)", line)
        if match:
            current = match.group(1)
            sections[current] = {"handle": current, "raw": []}
            continue
        if current is None:
            continue
        sections[current]["raw"].append(line)
        bullet = re.match(r"^-\s+([^:]+):\s*(.+)$", line)
        if bullet:
            key = bullet.group(1).strip().replace(" ", "_")
            value = bullet.group(2).strip()
            sections[current][key] = value
    return sections


def first_int(text: Any) -> int | None:
    if text is None:
        return None
    match = re.search(r"\d+", str(text))
    if not match:
        return None
    return int(match.group(0))


def health_for_handle(vault: Path, handle: str, reg: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    meta = parse_meta(vault / handle / ".meta.yaml")
    wiki = vault / handle / "wiki"
    soul = wiki / "soul.md"
    stats = wiki / ".ingest_stats.json"

    reg_last_ingest = reg.get("last_ingest")
    meta_last_ingest = meta.get("last_ingest")
    reg_soul = first_int(reg.get("soul_version"))
    meta_soul = first_int(meta.get("soul_version"))
    reg_raw_count = first_int(reg.get("tweet_count_raw"))
    meta_raw_count = first_int(meta.get("tweet_count_raw"))

    if not meta:
        issues.append({
            "handle": handle,
            "severity": "warning",
            "issue": "missing_meta_yaml",
        })
    if reg_last_ingest and not meta_last_ingest:
        issues.append({
            "handle": handle,
            "severity": "warning",
            "issue": "meta_skeleton_but_registry_ingested",
            "registry_last_ingest": reg_last_ingest,
            "meta_last_ingest": meta_last_ingest,
        })
    if reg_soul and (not meta_soul or meta_soul < reg_soul):
        issues.append({
            "handle": handle,
            "severity": "warning",
            "issue": "meta_soul_version_behind_registry",
            "registry_soul_version": reg_soul,
            "meta_soul_version": meta_soul,
        })
    if reg_raw_count and (not meta_raw_count):
        issues.append({
            "handle": handle,
            "severity": "warning",
            "issue": "meta_raw_count_missing",
            "registry_tweet_count_raw": reg_raw_count,
            "meta_tweet_count_raw": meta_raw_count,
        })
    if reg_last_ingest and not soul.exists():
        issues.append({
            "handle": handle,
            "severity": "error",
            "issue": "registry_ingested_but_soul_missing",
            "soul": str(soul),
        })
    if reg_last_ingest and not stats.exists():
        issues.append({
            "handle": handle,
            "severity": "warning",
            "issue": "registry_ingested_but_stats_missing",
            "stats": str(stats),
        })
    return issues


def build_report(vault: Path, handle_filter: str | None = None) -> dict[str, Any]:
    registry_path = vault / "_cross" / "_registry.md"
    if not registry_path.exists():
        raise FileNotFoundError(f"registry not found: {registry_path}")
    sections = registry_sections(registry_path.read_text(encoding="utf-8"))
    issues: list[dict[str, Any]] = []
    for handle, reg in sections.items():
        if handle_filter and handle != handle_filter:
            continue
        issues.extend(health_for_handle(vault, handle, reg))
    return {
        "vault": str(vault),
        "handles": 1 if handle_filter and handle_filter in sections else len(sections),
        "handle": handle_filter,
        "issue_count": len(issues),
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check KOL registry/meta consistency.")
    parser.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    parser.add_argument("--handle")
    parser.add_argument("--json", action="store_true", help="accepted for explicit JSON output")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    try:
        report = build_report(args.vault, args.handle)
        if args.write:
            out = args.vault / "_cross" / "registry_health.json"
            out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            report["status"] = "written"
            report["output"] = str(out)
        else:
            report["status"] = "dry_run"
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False))
        return 2

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
