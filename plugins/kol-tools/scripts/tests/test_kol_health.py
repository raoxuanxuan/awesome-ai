import tempfile
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kol_health import build_report


class KolHealthEntrypointTests(unittest.TestCase):
    def test_handle_filter_limits_report(self):
        with tempfile.TemporaryDirectory() as td:
            vault = Path(td)
            cross = vault / "_cross"
            cross.mkdir(parents=True)
            (cross / "_registry.md").write_text(
                "## @A\n\n- last_ingest: 2026-01-01\n- soul_version: 1\n\n"
                "## @B\n\n- last_ingest: 2026-01-01\n- soul_version: 1\n",
                encoding="utf-8",
            )
            for handle in ("A", "B"):
                (vault / handle / "wiki").mkdir(parents=True)
                (vault / handle / ".meta.yaml").write_text(
                    f"handle: {handle}\nlast_ingest: null\nsoul_version: 0\n",
                    encoding="utf-8",
                )
            report = build_report(vault, "A")
            self.assertEqual(report["handles"], 1)
            self.assertEqual({issue["handle"] for issue in report["issues"]}, {"A"})


if __name__ == "__main__":
    unittest.main()
