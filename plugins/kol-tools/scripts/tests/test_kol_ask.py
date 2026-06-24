import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kol_ask import main


class KolAskTests(unittest.TestCase):
    def build_vault(self, root: Path) -> Path:
        vault = root / "vault"
        cross = vault / "_cross"
        cross.mkdir(parents=True)
        cross.joinpath("_registry.md").write_text(
            """# KOL 注册表

## @TJ_Research

- handle: `TJ_Research`
- aliases: [投资TALK君, 逃课君]
- path: `vault/kol/TJ_Research/`
- domain: [投资, 美股, 宏观]
- entry: `[[../TJ_Research/wiki/soul.md]]`
""",
            encoding="utf-8",
        )
        wiki = vault / "TJ_Research" / "wiki"
        (wiki / "methods").mkdir(parents=True)
        (wiki / "positions").mkdir()
        (wiki / "sources").mkdir()
        (wiki / "soul.md").write_text("# Soul\n擅长 AI 算力和美股估值。\n", encoding="utf-8")
        (wiki / "methods" / "forward-pe-anchor.md").write_text(
            "# Forward PE Anchor\n用 forward P/E 看估值。\n",
            encoding="utf-8",
        )
        (wiki / "positions" / "NVDA.md").write_text(
            "# NVDA\n核心是 AI capex 和现金流。\n",
            encoding="utf-8",
        )
        (wiki / "sources" / "AI算力与芯片.md").write_text(
            "# AI算力与芯片\n关注算力需求和大科技 capex。\n",
            encoding="utf-8",
        )
        (wiki / "timeline.md").write_text("# Timeline\nAI capex 尚未证伪。\n", encoding="utf-8")
        return vault

    def test_context_pack_resolves_alias_and_selects_relevant_files(self):
        with tempfile.TemporaryDirectory() as td:
            vault = self.build_vault(Path(td))
            out = StringIO()
            with redirect_stdout(out):
                rc = main([
                    "投资TALK君",
                    "--vault",
                    str(vault),
                    "--question",
                    "怎么看 NVDA 和 AI 算力？",
                    "--mode",
                    "context-pack",
                    "--pack-id",
                    "ask-pack",
                ])

            self.assertEqual(rc, 0)
            result = json.loads(out.getvalue())
            self.assertEqual(result["status"], "context_pack_ready")
            workspace = Path(result["workspace"])
            manifest = json.loads((workspace / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["handle"], "TJ_Research")
            selected = "\n".join(item["path"] for item in manifest["selected_files"])
            self.assertIn("soul.md", selected)
            self.assertIn("positions/NVDA.md", selected)
            self.assertIn("sources/AI算力与芯片.md", selected)
            self.assertTrue((workspace / "context.md").exists())
            prompt = (workspace / "prompt.md").read_text(encoding="utf-8")
            self.assertIn("你不是 TJ_Research 本人", prompt)
            self.assertIn("confidence:", prompt)

    def test_context_pack_rejects_unknown_kol(self):
        with tempfile.TemporaryDirectory() as td:
            vault = self.build_vault(Path(td))
            out = StringIO()
            with redirect_stdout(out):
                rc = main([
                    "unknown",
                    "--vault",
                    str(vault),
                    "--question",
                    "怎么看 NVDA？",
                    "--mode",
                    "context-pack",
                ])

            self.assertEqual(rc, 2)
            result = json.loads(out.getvalue())
            self.assertEqual(result["status"], "error")
            self.assertIn("未注册", result["error"])

    def test_run_mode_executes_prompt_with_runner_command(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            vault = self.build_vault(root)
            runner = root / "fake_runner.py"
            runner.write_text(
                """import sys

prompt = sys.stdin.read()
assert "KOL Ask Prompt" in prompt
print("基于档案，我会保持中立。\\n\\n```meta\\nconfidence: 中\\nin_comfort_zone: yes\\nprimary_sources: []\\nwikilinks_used: []\\ncaveats: 测试桩\\n```")
""",
                encoding="utf-8",
            )

            out = StringIO()
            with redirect_stdout(out):
                rc = main([
                    "投资TALK君",
                    "--vault",
                    str(vault),
                    "--question",
                    "怎么看 NVDA 和 AI 算力？",
                    "--mode",
                    "run",
                    "--pack-id",
                    "ask-run",
                    "--runner-command",
                    f"{sys.executable} {runner}",
                ])

            self.assertEqual(rc, 0)
            result = json.loads(out.getvalue())
            self.assertEqual(result["status"], "run_complete")
            workspace = Path(result["workspace"])
            answer = workspace / "answer.md"
            self.assertTrue(answer.exists())
            self.assertIn("confidence", answer.read_text(encoding="utf-8"))
            manifest = json.loads((workspace / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["run_status"], "complete")
            self.assertTrue(manifest["executes_model"])
            self.assertNotIn("argv", manifest["runner"])
            self.assertEqual(manifest["runner"]["executable"], sys.executable)

    def test_run_mode_refuses_pack_id_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            vault = self.build_vault(root)
            runner = root / "fake_runner.py"
            runner.write_text("print('ok')\n", encoding="utf-8")

            out = StringIO()
            with redirect_stdout(out):
                rc = main([
                    "TJ_Research",
                    "--vault",
                    str(vault),
                    "--question",
                    "怎么看 NVDA？",
                    "--mode",
                    "context-pack",
                    "--pack-id",
                    "ask-run",
                ])
            self.assertEqual(rc, 0)

            out = StringIO()
            with redirect_stdout(out):
                rc = main([
                    "TJ_Research",
                    "--vault",
                    str(vault),
                    "--question",
                    "不同问题",
                    "--mode",
                    "run",
                    "--pack-id",
                    "ask-run",
                    "--runner-command",
                    f"{sys.executable} {runner}",
                ])

            self.assertEqual(rc, 2)
            result = json.loads(out.getvalue())
            self.assertEqual(result["status"], "error")
            self.assertIn("different question", result["error"])


if __name__ == "__main__":
    unittest.main()
