import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kol_index import load_docs, main


class KolIndexTests(unittest.TestCase):
    def test_loads_clean_corpus_before_raw(self):
        with tempfile.TemporaryDirectory() as td:
            vault = Path(td)
            wiki = vault / "h" / "wiki"
            raw = vault / "h" / "raw" / "tweets"
            wiki.mkdir(parents=True)
            raw.mkdir(parents=True)
            (wiki / ".clean_corpus.jsonl").write_text(
                json.dumps({
                    "id": "2",
                    "date": "2026-01-02",
                    "text": "$NVDA 因为需求强",
                    "quality": "high",
                    "routing": {"distill": True},
                    "reasons": ["has_ticker"],
                }, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            (raw / "1.md").write_text("---\nid: 1\n---\nraw", encoding="utf-8")
            docs, source = load_docs("h", vault)
            self.assertEqual(source, str(wiki / ".clean_corpus.jsonl"))
            self.assertEqual([doc["id"] for doc in docs], ["2"])
            self.assertEqual(docs[0]["quality"], "high")

    def test_loads_raw_when_clean_missing(self):
        with tempfile.TemporaryDirectory() as td:
            vault = Path(td)
            raw = vault / "h" / "raw" / "tweets"
            raw.mkdir(parents=True)
            (raw / "1.md").write_text(
                "---\nid: 1\ncreated_at: 2026-01-01\nis_reply: true\n---\n@a 这个用 forward PE 看",
                encoding="utf-8",
            )
            docs, source = load_docs("h", vault)
            self.assertEqual(source, str(raw))
            self.assertEqual(docs[0]["id"], "1")
            self.assertFalse(docs[0]["low_content"])

    def test_main_requires_clean_corpus_by_default(self):
        with tempfile.TemporaryDirectory() as td:
            vault = Path(td)
            raw = vault / "h" / "raw" / "tweets"
            raw.mkdir(parents=True)
            (raw / "1.md").write_text("---\nid: 1\n---\nraw", encoding="utf-8")

            with redirect_stdout(StringIO()):
                rc = main(["h", "--vault", str(vault), "--dry-run"])

            self.assertEqual(rc, 2)

    def test_legacy_raw_mode_allows_raw_fallback(self):
        with tempfile.TemporaryDirectory() as td:
            vault = Path(td)
            raw = vault / "h" / "raw" / "tweets"
            raw.mkdir(parents=True)
            (raw / "1.md").write_text("---\nid: 1\n---\nraw content with enough words", encoding="utf-8")

            with redirect_stdout(StringIO()):
                rc = main(["h", "--vault", str(vault), "--dry-run", "--legacy-raw"])

            self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
