import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kol_debate import main


class KolDebateTests(unittest.TestCase):
    def build_vault(self, root: Path) -> Path:
        vault = root / "vault"
        cross = vault / "_cross"
        cross.mkdir(parents=True)
        cross.joinpath("_registry.md").write_text(
            """# KOL 注册表

## @TJ_Research

- handle: `TJ_Research`
- aliases: [投资TALK君]
- path: `vault/kol/TJ_Research/`

## @LinQingV

- handle: `LinQingV`
- aliases: [林]
- path: `vault/kol/LinQingV/`
""",
            encoding="utf-8",
        )
        for handle, stance in (
            ("TJ_Research", "forward PE 和 AI capex"),
            ("LinQingV", "产业链和量化交易结构"),
        ):
            wiki = vault / handle / "wiki"
            (wiki / "methods").mkdir(parents=True)
            (wiki / "positions").mkdir()
            (wiki / "sources").mkdir()
            (wiki / "soul.md").write_text(f"# {handle}\n{stance}\n", encoding="utf-8")
            (wiki / "methods" / "ai.md").write_text(f"# AI method\n{stance}\n", encoding="utf-8")
            (wiki / "sources" / "AI算力.md").write_text(f"# AI算力\n{stance}\n", encoding="utf-8")
            (wiki / "timeline.md").write_text("# Timeline\nAI 观点演变\n", encoding="utf-8")
        return vault

    def test_prompt_pack_writes_debate_workspace(self):
        with tempfile.TemporaryDirectory() as td:
            vault = self.build_vault(Path(td))
            out = StringIO()
            with redirect_stdout(out):
                rc = main([
                    "--vault",
                    str(vault),
                    "--kols",
                    "投资TALK君,林",
                    "--question",
                    "AI capex 是泡沫吗？",
                    "--rounds",
                    "2",
                    "--mode",
                    "prompt-pack",
                    "--pack-id",
                    "debate-pack",
                ])

            self.assertEqual(rc, 0)
            result = json.loads(out.getvalue())
            self.assertEqual(result["status"], "prompt_pack_ready")
            workspace = Path(result["workspace"])
            self.assertTrue((workspace / "question.md").exists())
            self.assertTrue((workspace / "manifest.json").exists())
            self.assertTrue((workspace / "contexts" / "TJ_Research.md").exists())
            self.assertTrue((workspace / "contexts" / "LinQingV.md").exists())
            self.assertTrue((workspace / "prompts" / "r1-TJ_Research.md").exists())
            self.assertTrue((workspace / "prompts" / "r1-LinQingV.md").exists())
            self.assertTrue((workspace / "prompts" / "r2-TJ_Research.md").exists())
            self.assertTrue((workspace / "prompts" / "synthesize.md").exists())
            manifest = json.loads((workspace / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["handles"], ["TJ_Research", "LinQingV"])
            self.assertEqual(manifest["rounds"], 2)
            self.assertFalse(manifest["executes_model"])
            prompt = (workspace / "prompts" / "r1-TJ_Research.md").read_text(encoding="utf-8")
            self.assertIn("你不是 TJ_Research 本人", prompt)
            self.assertIn("第 1 轮", prompt)

    def test_prompt_pack_requires_two_kols(self):
        with tempfile.TemporaryDirectory() as td:
            vault = self.build_vault(Path(td))
            out = StringIO()
            with redirect_stdout(out):
                rc = main([
                    "--vault",
                    str(vault),
                    "--kols",
                    "TJ_Research",
                    "--question",
                    "AI capex 是泡沫吗？",
                    "--mode",
                    "prompt-pack",
                ])

            self.assertEqual(rc, 2)
            result = json.loads(out.getvalue())
            self.assertEqual(result["status"], "error")
            self.assertIn("至少 2 个", result["error"])

    def test_run_mode_executes_prompts_with_runner_command(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            vault = self.build_vault(root)
            runner = root / "fake_runner.py"
            runner.write_text(
                """import json
import sys

prompt = sys.stdin.read()
if "Debate Synthesizer Prompt" in prompt:
    print(json.dumps({
        "question": "AI capex 是泡沫吗？",
        "participants": ["TJ_Research", "LinQingV"],
        "rounds_held": 2,
        "立场摘要": [],
        "共识点": ["都需要证据边界"],
        "分歧点": [],
        "支持比例": {"人头": {}, "信心度加权": {}},
        "辩论质量": "充分",
        "盲点提示": "样本为测试桩",
        "推荐行动": "继续观察"
    }, ensure_ascii=False))
else:
    print("明确立场：中立\\n\\n```meta\\nconfidence: 中\\nin_comfort_zone: yes\\nprimary_sources: []\\nwikilinks_used: []\\ncaveats: 测试桩\\n```")
""",
                encoding="utf-8",
            )

            out = StringIO()
            with redirect_stdout(out):
                rc = main([
                    "--vault",
                    str(vault),
                    "--kols",
                    "TJ_Research,LinQingV",
                    "--question",
                    "AI capex 是泡沫吗？",
                    "--rounds",
                    "2",
                    "--mode",
                    "run",
                    "--pack-id",
                    "debate-run",
                    "--runner-command",
                    f"{sys.executable} {runner}",
                ])

            self.assertEqual(rc, 0)
            result = json.loads(out.getvalue())
            self.assertEqual(result["status"], "run_complete")
            workspace = Path(result["workspace"])
            self.assertTrue((workspace / "turns" / "r1-TJ_Research.md").exists())
            self.assertTrue((workspace / "turns" / "r1-LinQingV.md").exists())
            self.assertTrue((workspace / "turns" / "r2-TJ_Research.md").exists())
            self.assertTrue((workspace / "turns" / "r2-LinQingV.md").exists())
            self.assertTrue((workspace / "verdict.json").exists())
            verdict = json.loads((workspace / "verdict.json").read_text(encoding="utf-8"))
            self.assertEqual(verdict["辩论质量"], "充分")
            manifest = json.loads((workspace / "manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(manifest["executes_model"])
            self.assertEqual(manifest["run_status"], "complete")
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
                    "--vault",
                    str(vault),
                    "--kols",
                    "TJ_Research,LinQingV",
                    "--question",
                    "AI capex 是泡沫吗？",
                    "--rounds",
                    "2",
                    "--mode",
                    "prompt-pack",
                    "--pack-id",
                    "debate-run",
                ])
            self.assertEqual(rc, 0)

            out = StringIO()
            with redirect_stdout(out):
                rc = main([
                    "--vault",
                    str(vault),
                    "--kols",
                    "TJ_Research,LinQingV",
                    "--question",
                    "不同问题",
                    "--rounds",
                    "2",
                    "--mode",
                    "run",
                    "--pack-id",
                    "debate-run",
                    "--runner-command",
                    f"{sys.executable} {runner}",
                ])

            self.assertEqual(rc, 2)
            result = json.loads(out.getvalue())
            self.assertEqual(result["status"], "error")
            self.assertIn("different question", result["error"])


if __name__ == "__main__":
    unittest.main()
