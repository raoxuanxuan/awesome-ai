#!/usr/bin/env python3
"""Validate durable KOL wiki pages against lightweight schema rules."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from kol_common import DEFAULT_VAULT, wiki_dir


REQUIRED_SECTIONS = {
    "source": ["## Evidence"],
    "method": [
        "## Core Rule",
        "## Applies When",
        "## Does Not Apply When",
        "## Signals",
        "## Failure Conditions",
        "## Related Sources",
        "## Related Positions",
        "## Evidence",
    ],
    "position": [
        "## Current Stance",
        "## Stance Strength",
        "## Reasons",
        "## Evolution",
        "## Relevant Methods",
        "## Risks / Disconfirming Evidence",
        "## Evidence",
    ],
    "timeline": ["### Evidence Chain"],
    "soul": ["## Evidence Anchors"],
}

TWEET_ID_RE = re.compile(r"(?<!\d)\d{8,}(?!\d)")


def infer_kind(path: Path) -> str:
    parts = set(path.parts)
    if "sources" in parts:
        return "source"
    if "methods" in parts:
        return "method"
    if "positions" in parts:
        return "position"
    if path.name == "timeline.md":
        return "timeline"
    if path.name == "soul.md":
        return "soul"
    return "generic"


def validate_file(path: Path, kind: str | None = None) -> dict[str, Any]:
    kind = kind or infer_kind(path)
    issues: list[str] = []
    if not path.exists():
        return {"path": str(path), "kind": kind, "ok": False, "issues": ["file does not exist"]}

    text = path.read_text(encoding="utf-8")
    for section in REQUIRED_SECTIONS.get(kind, []):
        if section not in text:
            issues.append(f"missing section: {section}")
    if kind in REQUIRED_SECTIONS and not TWEET_ID_RE.search(text):
        issues.append("missing tweet id evidence")
    return {"path": str(path), "kind": kind, "ok": not issues, "issues": issues}


def durable_files(vault: Path, handle: str) -> list[Path]:
    wdir = wiki_dir(vault, handle)
    files = []
    for name in ["soul.md", "timeline.md"]:
        path = wdir / name
        if path.exists():
            files.append(path)
    for subdir in ["sources", "methods", "positions"]:
        root = wdir / subdir
        if root.exists():
            files.extend(path for path in sorted(root.glob("*.md")) if ".bak-" not in path.name)
    return files


def validate_handle(vault: Path, handle: str) -> dict[str, Any]:
    wdir = wiki_dir(vault, handle)
    files = []
    for name in ["soul.md", "timeline.md"]:
        path = wdir / name
        if path.exists():
            files.append(validate_file(path))
        else:
            files.append(validate_file(path, name.removesuffix(".md")))
    files.extend(validate_file(path) for path in durable_files(vault, handle) if path.name not in {"soul.md", "timeline.md"})
    return {
        "handle": handle,
        "ok": bool(files) and all(item["ok"] for item in files),
        "files": files,
        "issue_count": sum(len(item["issues"]) for item in files),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate KOL wiki Markdown schema.")
    parser.add_argument("handle")
    parser.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    args = parser.parse_args(argv)

    result = validate_handle(args.vault, args.handle)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
