import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kol_delta import commit, compute, meta_path


def write_index(vault: Path, handle: str, items: list[dict]) -> None:
    wiki = vault / handle / "wiki"
    wiki.mkdir(parents=True)
    with (wiki / ".clean_corpus.jsonl").open("w", encoding="utf-8") as fh:
        for item in items:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")


class KolDeltaTests(unittest.TestCase):
    def test_bootstrap_sets_watermark_without_delta(self):
        with tempfile.TemporaryDirectory() as td:
            vault = Path(td)
            write_index(vault, "h", [
                {"id": "1", "text": "old", "routing": {"distill": True}},
                {"id": "2", "text": "new", "routing": {"distill": True}},
            ])
            result = compute(vault, "h", 120)
            self.assertEqual(result["status"], "bootstrap")
            self.assertEqual(result["watermark"], "2")
            self.assertTrue(meta_path(vault, "h").exists())

    def test_ready_writes_delta_files(self):
        with tempfile.TemporaryDirectory() as td:
            vault = Path(td)
            write_index(vault, "h", [
                {"id": "1", "text": "old", "routing": {"distill": True}},
                {"id": "2", "text": "new", "is_reply": True, "routing": {"distill": True}},
            ])
            meta_path(vault, "h").write_text(json.dumps({"ingest_watermark_id": "1"}), encoding="utf-8")
            result = compute(vault, "h", 120)
            self.assertEqual(result["status"], "ready")
            self.assertEqual(result["delta"], 1)
            self.assertTrue((vault / "h" / "wiki" / ".ingest_delta.tsv").exists())

    def test_over_cap_does_not_write_delta_files(self):
        with tempfile.TemporaryDirectory() as td:
            vault = Path(td)
            write_index(vault, "h", [
                {"id": "1", "text": "old", "routing": {"distill": True}},
                {"id": "2", "text": "new", "routing": {"distill": True}},
                {"id": "3", "text": "new", "routing": {"distill": True}},
            ])
            meta_path(vault, "h").write_text(json.dumps({"ingest_watermark_id": "1"}), encoding="utf-8")
            result = compute(vault, "h", 1)
            self.assertEqual(result["status"], "over_cap")
            self.assertFalse((vault / "h" / "wiki" / ".ingest_delta.tsv").exists())

    def test_commit_advances_watermark(self):
        with tempfile.TemporaryDirectory() as td:
            vault = Path(td)
            (vault / "h" / "wiki").mkdir(parents=True)
            meta_path(vault, "h").write_text(json.dumps({"ingest_watermark_id": "1"}), encoding="utf-8")
            result = commit(vault, "h", "2", 1)
            self.assertEqual(result["status"], "committed")
            data = json.loads(meta_path(vault, "h").read_text(encoding="utf-8"))
            self.assertEqual(data["ingest_watermark_id"], "2")

    def test_commit_noop_for_old_watermark(self):
        with tempfile.TemporaryDirectory() as td:
            vault = Path(td)
            (vault / "h" / "wiki").mkdir(parents=True)
            meta_path(vault, "h").write_text(json.dumps({"ingest_watermark_id": "2"}), encoding="utf-8")
            result = commit(vault, "h", "1", 1)
            self.assertEqual(result["status"], "commit_noop")


if __name__ == "__main__":
    unittest.main()
