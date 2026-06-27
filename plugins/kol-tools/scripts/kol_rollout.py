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


def action_for_route(route: str) -> str:
    if route == "existing_mature_wiki":
        return "delta"
    if route in {"partial_wiki_repair", "bootstrap_required"}:
        return "bootstrap-pack"
    return "blocked"


def build_plan(vault: Path, handles: list[str] | None = None) -> dict[str, Any]:
    selected = handles or iter_handles(vault)
    items = []
    for handle in selected:
        inventory = classify_handle(vault, handle)
        items.append(
            {
                "handle": handle,
                "action": action_for_route(inventory["route"]),
                "inventory": inventory,
            }
        )
    by_action: dict[str, int] = {}
    for item in items:
        by_action[item["action"]] = by_action.get(item["action"], 0) + 1
    return {"vault": str(vault), "items": items, "by_action": by_action}


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
    parser.add_argument("--handles", default="")
    parser.add_argument("--dry-run", action="store_true", help="only print the rollout plan; currently the default behavior")
    args = parser.parse_args(argv)

    handles = [h.strip() for h in args.handles.split(",") if h.strip()] or None
    plan = build_plan(args.vault, handles=handles)
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
