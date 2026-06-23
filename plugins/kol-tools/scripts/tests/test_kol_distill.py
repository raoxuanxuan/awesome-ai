import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kol_distill import main, suggest_topics


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


class KolDistillTests(unittest.TestCase):
    def test_topic_suggestions_avoid_ascii_substring_false_positive(self):
        self.assertNotIn(
            "AI算力与Capex",
            suggest_topics("@terryaidev 大统华在多伦多已经排不上号了"),
        )

    def test_topic_suggestions_cover_market_earnings_expectations(self):
        self.assertIn("市场盈利预期", suggest_topics("标普EPS增速从14%上修到23.3%"))

    def build_vault(self, root: Path) -> Path:
        vault = root / "vault"
        wiki = vault / "h" / "wiki"
        wiki.mkdir(parents=True)
        (wiki / "soul.md").write_text("# Existing soul\n", encoding="utf-8")
        (wiki / "timeline.md").write_text("# Existing timeline\n", encoding="utf-8")
        (wiki / "sources").mkdir()
        (wiki / "methods").mkdir()
        (wiki / "positions").mkdir()
        (vault / "_cross").mkdir(parents=True)
        (vault / "_cross" / "topic_registry.md").write_text(
            "# Topic Registry\n\n- **AI算力与Capex**\n- **美联储与利率**\n",
            encoding="utf-8",
        )

        clean = wiki / ".clean_corpus.jsonl"
        write_jsonl(
            clean,
            [
                {
                    "id": "101",
                    "date": "2026-06-20",
                    "lang": "zh",
                    "text": "Token价格下跌不是算力需求通缩，AI capex还没证伪",
                    "url": "https://x.com/h/status/101",
                    "is_reply": False,
                    "quality": "high",
                    "routing": {"distill": True},
                    "favorite_count": 10,
                    "view_count": 1000,
                },
                {
                    "id": "102",
                    "date": "2026-06-21",
                    "lang": "zh",
                    "text": "@a 根据债市定价调整判断是成熟投资者该做的",
                    "url": "https://x.com/h/status/102",
                    "is_reply": True,
                    "quality": "medium",
                    "routing": {"distill": True},
                    "favorite_count": 3,
                    "view_count": 300,
                },
                {
                    "id": "99",
                    "date": "2026-06-18",
                    "lang": "zh",
                    "text": "old item",
                    "url": "https://x.com/h/status/99",
                    "is_reply": False,
                    "quality": "high",
                    "routing": {"distill": True},
                },
                {
                    "id": "103",
                    "date": "2026-06-21",
                    "lang": "zh",
                    "text": "inside watermark range but excluded by kol-delta",
                    "url": "https://x.com/h/status/103",
                    "is_reply": False,
                    "quality": "noise",
                    "routing": {"distill": False},
                },
            ],
        )
        delta = {
            "handle": "h",
            "status": "ready",
            "delta": 2,
            "replies": 1,
            "watermark_old": "100",
            "watermark_proposed": "104",
            "date_range": ["2026-06-20", "2026-06-21"],
            "source": str(clean),
            "delta_tsv": str(wiki / ".ingest_delta.tsv"),
        }
        (wiki / ".ingest_delta.json").write_text(
            json.dumps(delta, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (wiki / ".ingest_delta.tsv").write_text(
            "101\t2026-06-20\tzh\tT\tToken价格下跌不是算力需求通缩\n"
            "102\t2026-06-21\tzh\tR\t根据债市定价调整判断\n",
            encoding="utf-8",
        )
        return vault

    def build_low_risk_vault(self, root: Path) -> Path:
        vault = root / "vault"
        wiki = vault / "h" / "wiki"
        (wiki / "sources").mkdir(parents=True)
        (wiki / "methods").mkdir()
        (wiki / "positions").mkdir()
        (wiki / "sources" / "杂感与社区互动.md").write_text("# community\n", encoding="utf-8")
        (wiki / "soul.md").write_text("# soul\n", encoding="utf-8")
        (wiki / "timeline.md").write_text("# timeline\n", encoding="utf-8")
        (wiki / "_index.md").write_text("# index\n", encoding="utf-8")
        (wiki / "_log.md").write_text("# log\n", encoding="utf-8")

        clean = wiki / ".clean_corpus.jsonl"
        write_jsonl(
            clean,
            [
                {
                    "id": "201",
                    "date": "2026-06-20",
                    "lang": "zh",
                    "text": "@a 大统华在多伦多已经排不上号了，大把中超比他们质量高",
                    "url": "https://x.com/h/status/201",
                    "is_reply": True,
                    "quality": "medium",
                    "routing": {"distill": True},
                }
            ],
        )
        (wiki / ".ingest_delta.json").write_text(
            json.dumps(
                {
                    "handle": "h",
                    "status": "ready",
                    "delta": 1,
                    "replies": 1,
                    "watermark_old": "200",
                    "watermark_proposed": "201",
                    "date_range": ["2026-06-20", "2026-06-20"],
                    "source": str(clean),
                    "delta_tsv": str(wiki / ".ingest_delta.tsv"),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (wiki / ".ingest_delta.tsv").write_text(
            "201\t2026-06-20\tzh\tR\t大统华在多伦多已经排不上号了\n",
            encoding="utf-8",
        )
        return vault

    def test_prompt_pack_generates_review_workspace_without_mutating_wiki(self):
        with tempfile.TemporaryDirectory() as td:
            vault = self.build_vault(Path(td))
            soul = vault / "h" / "wiki" / "soul.md"
            before = soul.read_text(encoding="utf-8")

            out = StringIO()
            with redirect_stdout(out):
                rc = main([
                    "h",
                    "--vault",
                    str(vault),
                    "--mode",
                    "prompt-pack",
                    "--pack-id",
                    "test-pack",
                ])

            self.assertEqual(rc, 0)
            result = json.loads(out.getvalue())
            self.assertEqual(result["status"], "prompt_pack_ready")
            workspace = Path(result["workspace"])
            self.assertTrue((workspace / "manifest.json").exists())
            self.assertTrue((workspace / "delta_items.jsonl").exists())
            self.assertTrue((workspace / "delta_brief.md").exists())
            self.assertTrue((workspace / "backup_plan.json").exists())
            self.assertTrue((workspace / "prompts" / "01-sources.md").exists())
            self.assertTrue((workspace / "prompts" / "02-methods-positions.md").exists())
            self.assertTrue((workspace / "prompts" / "03-timeline-soul.md").exists())

            manifest = json.loads((workspace / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["handle"], "h")
            self.assertEqual(manifest["watermark_proposed"], "104")
            self.assertEqual(manifest["delta_count"], 2)
            self.assertEqual(manifest["reply_count"], 1)
            self.assertEqual(manifest["risk_level"], "high")
            self.assertEqual(manifest["review_status"], "user_review_required")
            self.assertTrue(manifest["needs_user"])
            self.assertIn("sources", manifest["target_groups"])
            self.assertTrue((workspace / "risk_assessment.json").exists())
            delta_ids = [
                json.loads(line)["id"]
                for line in (workspace / "delta_items.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(delta_ids, ["101", "102"])

            brief = (workspace / "delta_brief.md").read_text(encoding="utf-8")
            self.assertIn("Token价格", brief)
            self.assertIn("美联储与利率", brief)
            self.assertIn("review_status: user_review_required", brief)
            self.assertEqual(soul.read_text(encoding="utf-8"), before)

    def test_low_risk_source_only_delta_is_auto_eligible(self):
        with tempfile.TemporaryDirectory() as td:
            vault = self.build_low_risk_vault(Path(td))

            out = StringIO()
            with redirect_stdout(out):
                rc = main([
                    "h",
                    "--vault",
                    str(vault),
                    "--mode",
                    "prompt-pack",
                    "--pack-id",
                    "low-risk-pack",
                ])

            self.assertEqual(rc, 0)
            result = json.loads(out.getvalue())
            self.assertEqual(result["risk_level"], "low")
            self.assertEqual(result["review_status"], "auto_eligible")
            self.assertFalse(result["needs_user"])
            self.assertTrue(result["safe_to_auto_apply"])
            manifest = json.loads((Path(result["workspace"]) / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["risk_assessment"]["scopes"], ["index_log", "sources"])

    def test_private_or_subscriber_evidence_blocks_distill(self):
        with tempfile.TemporaryDirectory() as td:
            vault = self.build_low_risk_vault(Path(td))
            clean = vault / "h" / "wiki" / ".clean_corpus.jsonl"
            payload = json.loads(clean.read_text(encoding="utf-8").splitlines()[0])
            payload["is_subscriber"] = True
            write_jsonl(clean, [payload])

            out = StringIO()
            with redirect_stdout(out):
                rc = main([
                    "h",
                    "--vault",
                    str(vault),
                    "--mode",
                    "prompt-pack",
                    "--pack-id",
                    "blocked-pack",
                ])

            self.assertEqual(rc, 0)
            result = json.loads(out.getvalue())
            self.assertEqual(result["risk_level"], "blocked")
            self.assertEqual(result["review_status"], "blocked")
            risk = json.loads((Path(result["workspace"]) / "risk_assessment.json").read_text(encoding="utf-8"))
            self.assertTrue(risk["blockers"])

    def test_prompt_pack_refuses_when_delta_not_ready(self):
        with tempfile.TemporaryDirectory() as td:
            vault = self.build_vault(Path(td))
            delta_path = vault / "h" / "wiki" / ".ingest_delta.json"
            payload = json.loads(delta_path.read_text(encoding="utf-8"))
            payload["status"] = "none"
            delta_path.write_text(json.dumps(payload), encoding="utf-8")

            out = StringIO()
            with redirect_stdout(out):
                rc = main(["h", "--vault", str(vault), "--mode", "prompt-pack"])

            self.assertEqual(rc, 2)
            result = json.loads(out.getvalue())
            self.assertEqual(result["status"], "error")
            self.assertIn("ready", result["error"])


if __name__ == "__main__":
    unittest.main()
