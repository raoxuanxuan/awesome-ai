import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kol_refresh import default_twitter_fetch_bin, item_to_markdown, load_state, main, state_path


class KolRefreshTests(unittest.TestCase):
    def test_item_to_markdown_preserves_reply_metadata(self):
        item = {
            "id": "2",
            "url": "https://x.com/h/status/2",
            "screen_name": "h",
            "created_at": "2026-01-02T00:00:00Z",
            "lang": "zh",
            "full_text": "@a forward PE 看",
            "is_reply": True,
            "in_reply_to": "1",
            "conversation_id": "1",
            "stats": {"likes": 3, "retweets": 1, "replies": 2, "views": 10},
        }
        md = item_to_markdown(item, "h")
        self.assertIn('id: "2"', md)
        self.assertIn("is_reply: true", md)
        self.assertIn('in_reply_to: "1"', md)
        self.assertIn('source_type: "x_reply"', md)
        self.assertTrue(md.endswith("@a forward PE 看\n"))

    def test_input_jsonl_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            vault = Path(td) / "vault"
            fixture = Path(td) / "history.jsonl"
            fixture.write_text(
                json.dumps({"id": "1", "screen_name": "h", "text": "hello"}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            with redirect_stdout(StringIO()):
                rc = main(["--vault", str(vault), "--handle", "h", "--input-jsonl", str(fixture), "--dry-run"])
            self.assertEqual(rc, 0)
            self.assertFalse((vault / "h" / "raw" / "tweets" / "1.md").exists())
            self.assertFalse(state_path(vault, "h").exists())

    def test_input_jsonl_write_creates_raw_and_state(self):
        with tempfile.TemporaryDirectory() as td:
            vault = Path(td) / "vault"
            fixture = Path(td) / "history.jsonl"
            fixture.write_text(
                json.dumps({
                    "id": "2",
                    "screen_name": "h",
                    "created_at": "2026-01-02T00:00:00Z",
                    "text": "$NVDA 因为需求强",
                }, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            with redirect_stdout(StringIO()):
                rc = main(["--vault", str(vault), "--handle", "h", "--input-jsonl", str(fixture)])
            self.assertEqual(rc, 0)
            self.assertTrue((vault / "h" / "raw" / "tweets" / "2.md").exists())
            state = load_state(vault, "h")
            self.assertEqual(state["newest_id"], "2")
            self.assertEqual(state["total_fetched"], 1)

    def test_default_twitter_fetch_bin_resolves_in_repo(self):
        binary = default_twitter_fetch_bin()
        self.assertIsNotNone(binary)
        self.assertTrue(str(binary).endswith("twitter-fetch"))


if __name__ == "__main__":
    unittest.main()
