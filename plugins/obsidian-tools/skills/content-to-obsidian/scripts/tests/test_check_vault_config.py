#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "check_vault_config.py"
EXAMPLE = Path(__file__).resolve().parents[2] / "vaults.json.example"


def run_check(*args: str) -> tuple[int, dict]:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--example", str(EXAMPLE), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    return proc.returncode, json.loads(proc.stdout)


class CheckVaultConfigTest(unittest.TestCase):
    def test_missing_config_is_created_then_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "runtime" / "vaults.json"
            code, data = run_check("--config", str(config), "--prompt", "保存这篇文章")

            self.assertEqual(code, 2)
            self.assertTrue(config.exists())
            self.assertTrue(data["created_config"])
            self.assertEqual(data["status"], "needs_config")
            self.assertIn("Vault 'main' has no real root path configured.", data["problems"])

    def test_prompt_trigger_selects_matching_vault(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "work-vault"
            vault.mkdir()
            config = Path(tmp) / "vaults.json"
            config.write_text(
                json.dumps(
                    {
                        "default": "main",
                        "vaults": [
                            {
                                "id": "main",
                                "triggers": ["保存这篇文章"],
                                "root": "/Users/CHANGE_ME/vault",
                                "mode": "karpathy",
                            },
                            {
                                "id": "work",
                                "triggers": ["保存到 工作"],
                                "root": str(vault),
                                "mode": "karpathy",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            code, data = run_check("--config", str(config), "--prompt", "保存到 工作: https://example.com")

            self.assertEqual(code, 0)
            self.assertTrue(data["ok"])
            self.assertEqual(data["selection_reason"], "trigger")
            self.assertEqual(data["selected_vault"]["id"], "work")

    def test_default_vault_is_used_when_no_trigger_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / "main-vault"
            vault.mkdir()
            config = Path(tmp) / "vaults.json"
            config.write_text(
                json.dumps(
                    {
                        "default": "main",
                        "vaults": [
                            {
                                "id": "main",
                                "triggers": ["保存这篇文章"],
                                "root": str(vault),
                                "mode": "karpathy",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            code, data = run_check("--config", str(config), "--prompt", "保存: https://example.com")

            self.assertEqual(code, 0)
            self.assertEqual(data["selection_reason"], "default")
            self.assertEqual(data["selected_vault"]["id"], "main")

    def test_nonexistent_real_path_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "vaults.json"
            missing = Path(tmp) / "missing-vault"
            config.write_text(
                json.dumps(
                    {
                        "default": "main",
                        "vaults": [
                            {
                                "id": "main",
                                "triggers": ["保存这篇文章"],
                                "root": str(missing),
                                "mode": "karpathy",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            code, data = run_check("--config", str(config), "--prompt", "保存这篇文章")

            self.assertEqual(code, 2)
            self.assertIn("root does not exist", data["problems"][0])


if __name__ == "__main__":
    unittest.main()
