import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kol_schema_validate import validate_file, validate_handle


class KolSchemaValidateTests(unittest.TestCase):
    def test_source_page_requires_evidence_section_and_tweet_id(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "sources" / "AI.md"
            path.parent.mkdir()
            path.write_text("# AI\n\n## Scope\ntext\n", encoding="utf-8")

            result = validate_file(path, "source")

            self.assertFalse(result["ok"])
            self.assertIn("missing section: ## Evidence", result["issues"])
            self.assertIn("missing tweet id evidence", result["issues"])

    def test_method_page_with_required_sections_and_tweet_id_passes(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "methods" / "m.md"
            path.parent.mkdir()
            path.write_text(
                "# M\n\n"
                "## Core Rule\nrule\n"
                "## Applies When\ncase\n"
                "## Does Not Apply When\ncase\n"
                "## Signals\nsignal\n"
                "## Failure Conditions\nfail\n"
                "## Related Sources\nsource\n"
                "## Related Positions\npos\n"
                "## Evidence\n- 2067851206475608569\n",
                encoding="utf-8",
            )

            result = validate_file(path, "method")

            self.assertTrue(result["ok"])

    def test_validate_handle_checks_core_and_subdirectories(self):
        with tempfile.TemporaryDirectory() as td:
            vault = Path(td)
            wiki = vault / "h" / "wiki"
            (wiki / "sources").mkdir(parents=True)
            (wiki / "sources" / "topic.md").write_text("# Topic\n\n## Evidence\n- 12345678\n", encoding="utf-8")
            (wiki / "soul.md").write_text("# Soul\n\n## Evidence Anchors\n- 12345678\n", encoding="utf-8")

            result = validate_handle(vault, "h")

            self.assertFalse(result["ok"])
            self.assertGreaterEqual(len(result["files"]), 2)


if __name__ == "__main__":
    unittest.main()
