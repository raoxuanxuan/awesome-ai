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
        (wiki / ".ingest_meta.json").write_text(
            json.dumps(
                {
                    "ingest_watermark_id": "200",
                    "last_ingest": "2026-06-19",
                    "tweet_count_indexed": 1,
                    "history": [
                        {
                            "date": "2026-06-19",
                            "event": "bootstrap",
                            "added": 0,
                            "watermark": "200",
                        }
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

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
            self.assertTrue((workspace / "schema_manifest.json").exists())
            self.assertTrue((workspace / "schemas" / "source.schema.md").exists())
            self.assertTrue((workspace / "schemas" / "method.schema.md").exists())
            self.assertTrue((workspace / "schemas" / "position.schema.md").exists())
            self.assertTrue((workspace / "schemas" / "timeline.schema.md").exists())
            self.assertTrue((workspace / "schemas" / "soul.schema.md").exists())
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
            self.assertIn("schema_manifest", manifest)
            self.assertEqual(manifest["schema_manifest"]["schema_version"], "1")
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

    def test_bootstrap_pack_uses_selected_high_medium_items_without_delta_file(self):
        with tempfile.TemporaryDirectory() as td:
            vault = Path(td) / "vault"
            wiki = vault / "h" / "wiki"
            wiki.mkdir(parents=True)
            write_jsonl(
                wiki / ".clean_corpus.jsonl",
                [
                    {
                        "id": "1",
                        "date": "2026-01-01",
                        "text": "$NVDA 因为需求强",
                        "quality": "high",
                        "routing": {"distill": True},
                    },
                    {
                        "id": "2",
                        "date": "2026-01-02",
                        "text": "普通闲聊",
                        "quality": "low",
                        "routing": {"distill": False},
                    },
                    {
                        "id": "3",
                        "date": "2026-01-03",
                        "text": "现金流和估值是关键",
                        "quality": "medium",
                        "routing": {"distill": True},
                    },
                ],
            )

            out = StringIO()
            with redirect_stdout(out):
                rc = main([
                    "h",
                    "--vault",
                    str(vault),
                    "--mode",
                    "bootstrap-pack",
                    "--pack-id",
                    "bootstrap-test",
                    "--bootstrap-limit",
                    "10",
                ])

            self.assertEqual(rc, 0)
            result = json.loads(out.getvalue())
            self.assertEqual(result["status"], "bootstrap_pack_ready")
            self.assertEqual(result["risk_level"], "high")
            self.assertEqual(result["review_status"], "user_review_required")
            workspace = Path(result["workspace"])
            rows = [
                json.loads(line)
                for line in (workspace / "delta_items.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual([row["id"] for row in rows], ["1", "3"])
            self.assertTrue((workspace / "prompts" / "00-bootstrap-wiki.md").exists())

    def test_apply_validate_commit_low_risk_pack(self):
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

            out = StringIO()
            with redirect_stdout(out):
                rc = main([
                    "h",
                    "--vault",
                    str(vault),
                    "--mode",
                    "apply",
                    "--pack-id",
                    "low-risk-pack",
                ])
            self.assertEqual(rc, 0)
            apply_result = json.loads(out.getvalue())
            self.assertEqual(apply_result["status"], "applied")
            workspace = Path(apply_result["workspace"])
            self.assertTrue((workspace / "apply_result.json").exists())

            source_text = (vault / "h" / "wiki" / "sources" / "杂感与社区互动.md").read_text(encoding="utf-8")
            self.assertIn("201", source_text)
            self.assertIn("大统华", source_text)
            log_text = (vault / "h" / "wiki" / "_log.md").read_text(encoding="utf-8")
            self.assertIn("low-risk-pack", log_text)

            out = StringIO()
            with redirect_stdout(out):
                rc = main([
                    "h",
                    "--vault",
                    str(vault),
                    "--mode",
                    "validate",
                    "--pack-id",
                    "low-risk-pack",
                ])
            self.assertEqual(rc, 0)
            validate_result = json.loads(out.getvalue())
            self.assertEqual(validate_result["status"], "validated")
            self.assertTrue(validate_result["safe_to_commit_watermark"])

            out = StringIO()
            with redirect_stdout(out):
                rc = main([
                    "h",
                    "--vault",
                    str(vault),
                    "--mode",
                    "commit",
                    "--pack-id",
                    "low-risk-pack",
                ])
            self.assertEqual(rc, 0)
            commit_result = json.loads(out.getvalue())
            self.assertEqual(commit_result["status"], "committed")
            meta = json.loads((vault / "h" / "wiki" / ".ingest_meta.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["ingest_watermark_id"], "201")

    def test_validate_reports_schema_issues_for_changed_files(self):
        with tempfile.TemporaryDirectory() as td:
            vault = self.build_low_risk_vault(Path(td))
            out = StringIO()
            with redirect_stdout(out):
                self.assertEqual(main(["h", "--vault", str(vault), "--mode", "prompt-pack", "--pack-id", "schema-pack"]), 0)
            with redirect_stdout(StringIO()):
                self.assertEqual(main(["h", "--vault", str(vault), "--mode", "apply", "--pack-id", "schema-pack"]), 0)
            bad_source = vault / "h" / "wiki" / "sources" / "杂感与社区互动.md"
            bad_source.write_text("# broken\n201\n", encoding="utf-8")

            out = StringIO()
            with redirect_stdout(out):
                rc = main(["h", "--vault", str(vault), "--mode", "validate", "--pack-id", "schema-pack"])

            result = json.loads(out.getvalue())
            self.assertEqual(rc, 2)
            self.assertEqual(result["status"], "validation_failed")
            self.assertTrue(any("schema issue" in issue for issue in result["blockers"]))

    def test_validate_refuses_incomplete_pack_without_risk_or_schema_manifest(self):
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
                    "incomplete-pack",
                ])
            self.assertEqual(rc, 0)

            out = StringIO()
            with redirect_stdout(out):
                rc = main([
                    "h",
                    "--vault",
                    str(vault),
                    "--mode",
                    "apply",
                    "--pack-id",
                    "incomplete-pack",
                ])
            self.assertEqual(rc, 0)

            workspace = vault / "h" / "wiki" / ".distill_prompt_packs" / "incomplete-pack"
            (workspace / "risk_assessment.json").unlink(missing_ok=True)
            (workspace / "schema_manifest.json").unlink(missing_ok=True)

            out = StringIO()
            with redirect_stdout(out):
                rc = main([
                    "h",
                    "--vault",
                    str(vault),
                    "--mode",
                    "validate",
                    "--pack-id",
                    "incomplete-pack",
                ])

            self.assertEqual(rc, 2)
            result = json.loads(out.getvalue())
            self.assertEqual(result["status"], "validation_failed")
            self.assertIn("missing risk_assessment.json", result["blockers"])
            self.assertIn("missing schema_manifest.json", result["blockers"])

    def test_apply_refuses_high_risk_pack_without_force(self):
        with tempfile.TemporaryDirectory() as td:
            vault = self.build_vault(Path(td))

            out = StringIO()
            with redirect_stdout(out):
                rc = main([
                    "h",
                    "--vault",
                    str(vault),
                    "--mode",
                    "prompt-pack",
                    "--pack-id",
                    "high-risk-pack",
                ])
            self.assertEqual(rc, 0)

            out = StringIO()
            with redirect_stdout(out):
                rc = main([
                    "h",
                    "--vault",
                    str(vault),
                    "--mode",
                    "apply",
                    "--pack-id",
                    "high-risk-pack",
                ])
            self.assertEqual(rc, 2)
            result = json.loads(out.getvalue())
            self.assertEqual(result["status"], "apply_refused")
            self.assertIn("user_review_required", result["reason"])

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
