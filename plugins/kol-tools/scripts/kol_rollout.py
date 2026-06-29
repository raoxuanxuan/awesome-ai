#!/usr/bin/env python3
"""Plan KOL Twin wiki rollout actions."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from kol_common import DEFAULT_VAULT
from kol_wiki_inventory import classify_handle, iter_handles


def build_plan(vault: Path, handles: list[str] | None = None) -> dict[str, Any]:
    selected = handles or iter_handles(vault)
    items = []
    for handle in selected:
        inventory = classify_handle(vault, handle)
        items.append(
            {
                "kol": inventory["kol"],
                "next_action": inventory["next_action"],
                "inventory": inventory,
            }
        )
    by_next_action: dict[str, int] = {}
    for item in items:
        by_next_action[item["next_action"]] = by_next_action.get(item["next_action"], 0) + 1
    return {"vault": str(vault), "items": items, "by_next_action": by_next_action}


def run_command(command: list[str], cwd: Path) -> dict[str, Any]:
    proc = subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)
    payload: dict[str, Any]
    if proc.stdout.strip().startswith("{"):
        payload = json.loads(proc.stdout)
    else:
        payload = {"stdout": proc.stdout.strip()}
    payload["returncode"] = proc.returncode
    if proc.stderr.strip():
        payload["stderr"] = proc.stderr.strip()
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plan KOL Twin wiki rollout.")
    parser.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    parser.add_argument("--kols", default="")
    parser.add_argument("--handles", default="", help=argparse.SUPPRESS)
    parser.add_argument("--dry-run", action="store_true", help="only print the rollout plan; currently the default behavior")
    args = parser.parse_args(argv)

    selected = args.kols or args.handles
    handles = [h.strip() for h in selected.split(",") if h.strip()] or None
    plan = build_plan(args.vault, handles=handles)
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
