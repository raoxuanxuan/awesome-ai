import unittest
import sys

from pathlib import Path
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from registry_health import health_for_handle, registry_sections

class RegistryHealthTests(unittest.TestCase):
    def test_registry_sections_parse_handle_and_fields(self):
        sections = registry_sections("""# Registry

## @LinQingV

- handle: `LinQingV`
- last_ingest: 2026-05-15
- soul_version: 1
- tweet_count_raw: 698
""")
        self.assertIn("LinQingV", sections)
        self.assertEqual(sections["LinQingV"]["last_ingest"], "2026-05-15")

    def test_detects_meta_skeleton_but_registry_ingested(self):
        with tempfile.TemporaryDirectory() as td:
            vault = Path(td)
            (vault / "LinQingV").mkdir()
            (vault / "LinQingV" / ".meta.yaml").write_text(
                "handle: LinQingV\nlast_ingest: null\nsoul_version: 0\ntweet_count_raw: null\n",
                encoding="utf-8",
            )
            issues = health_for_handle(vault, "LinQingV", {
                "last_ingest": "2026-05-15",
                "soul_version": "1",
                "tweet_count_raw": "698",
            })
            names = {issue["issue"] for issue in issues}
            self.assertIn("meta_skeleton_but_registry_ingested", names)
            self.assertIn("meta_soul_version_behind_registry", names)
            self.assertIn("meta_raw_count_missing", names)


if __name__ == "__main__":
    unittest.main()
