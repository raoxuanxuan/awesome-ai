#!/usr/bin/env python3
"""Check and initialize Obsidian Tools vault configuration."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any


DEFAULT_RUNTIME_DIR = Path("~/.obsidian-tools").expanduser()
ENV_RUNTIME_DIR = "OBSIDIAN_TOOLS_HOME"


def default_example_path() -> Path:
    return Path(__file__).resolve().parents[1] / "vaults.json.example"


def runtime_dir_from_env() -> Path:
    return Path(os.environ.get(ENV_RUNTIME_DIR, str(DEFAULT_RUNTIME_DIR))).expanduser()


def load_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except FileNotFoundError:
        return None, "missing"
    except json.JSONDecodeError as exc:
        return None, f"invalid_json: {exc}"


def is_placeholder_root(root: Any) -> bool:
    if not isinstance(root, str) or not root.strip():
        return True
    return "/Users/CHANGE_ME/" in root or root.startswith("/Users/CHANGE_ME")


def select_vault(config: dict[str, Any], prompt: str) -> tuple[dict[str, Any] | None, str]:
    vaults = config.get("vaults")
    if not isinstance(vaults, list) or not vaults:
        return None, "no_vaults"

    for vault in vaults:
        if not isinstance(vault, dict):
            continue
        triggers = vault.get("triggers", [])
        if not isinstance(triggers, list):
            continue
        for trigger in triggers:
            if isinstance(trigger, str) and trigger and trigger in prompt:
                return vault, "trigger"

    default_id = config.get("default")
    for vault in vaults:
        if isinstance(vault, dict) and vault.get("id") == default_id:
            return vault, "default"

    for vault in vaults:
        if isinstance(vault, dict):
            return vault, "first"

    return None, "no_valid_vault"


def find_common_vault_paths() -> list[str]:
    home = Path.home()
    candidates = [
        home / "vault",
        home / "vault" / "ai",
        home / "vault" / "invest",
        home / "Documents" / "Obsidian",
        home / "Obsidian",
    ]
    return [str(path) for path in candidates if path.is_dir()]


def ensure_config(config_path: Path, example_path: Path) -> bool:
    if config_path.exists():
        return False
    config_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(example_path, config_path)
    os.chmod(config_path, 0o600)
    return True


def check_config(config: dict[str, Any], selected: dict[str, Any] | None) -> tuple[bool, list[str]]:
    problems: list[str] = []
    if selected is None:
        problems.append("No usable vault entry found in vaults.json.")
        return False, problems

    vault_id = selected.get("id", "<missing id>")
    root = selected.get("root")
    if is_placeholder_root(root):
        problems.append(f"Vault '{vault_id}' has no real root path configured.")
        return False, problems

    root_path = Path(str(root)).expanduser()
    if not root_path.exists():
        problems.append(f"Vault '{vault_id}' root does not exist: {root_path}")
        return False, problems
    if not root_path.is_dir():
        problems.append(f"Vault '{vault_id}' root is not a directory: {root_path}")
        return False, problems
    return True, problems


def build_result(
    *,
    status: str,
    config_path: Path,
    created: bool,
    selected_vault: dict[str, Any] | None,
    selection_reason: str,
    problems: list[str],
) -> dict[str, Any]:
    selected_summary = None
    if selected_vault is not None:
        selected_summary = {
            "id": selected_vault.get("id"),
            "root": selected_vault.get("root"),
            "mode": selected_vault.get("mode", "karpathy"),
        }
    return {
        "ok": status == "ok",
        "status": status,
        "config_path": str(config_path),
        "created_config": created,
        "selected_vault": selected_summary,
        "selection_reason": selection_reason,
        "problems": problems,
        "suggested_existing_paths": find_common_vault_paths(),
        "next_action": (
            "Proceed with writing."
            if status == "ok"
            else "Edit vault roots in vaults.json, then retry. Do not write until this check passes."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", default="", help="Original user prompt used for trigger matching.")
    parser.add_argument("--config", type=Path, help="Path to vaults.json. Defaults to ~/.obsidian-tools/vaults.json.")
    parser.add_argument("--example", type=Path, default=default_example_path(), help="Path to vaults.json.example.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    args = parser.parse_args(argv)

    config_path = (args.config or runtime_dir_from_env() / "vaults.json").expanduser()
    example_path = args.example.expanduser()
    created = False

    if not example_path.exists():
        result = build_result(
            status="needs_config",
            config_path=config_path,
            created=False,
            selected_vault=None,
            selection_reason="missing_example",
            problems=[f"Example config not found: {example_path}"],
        )
        print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))
        return 2

    try:
        created = ensure_config(config_path, example_path)
    except OSError as exc:
        result = build_result(
            status="needs_config",
            config_path=config_path,
            created=False,
            selected_vault=None,
            selection_reason="create_failed",
            problems=[f"Could not create vault config: {exc}"],
        )
        print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))
        return 2

    config, error = load_json(config_path)
    if error is not None or config is None:
        result = build_result(
            status="needs_config",
            config_path=config_path,
            created=created,
            selected_vault=None,
            selection_reason="load_failed",
            problems=[f"Could not load vault config: {error}"],
        )
        print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))
        return 2

    selected, reason = select_vault(config, args.prompt)
    ok, problems = check_config(config, selected)
    result = build_result(
        status="ok" if ok else "needs_config",
        config_path=config_path,
        created=created,
        selected_vault=selected,
        selection_reason=reason,
        problems=problems,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
