import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kol_pool_backfill import main, raw_markdown_to_item


RAW = """---
id: "123"
url: https://x.com/h/status/123
author: Display Name
screen_name: h
lang: zh
created_at: 2026-01-02T00:00:00Z
is_retweet: false
is_quote: true
quoted_tweet_id: "99"
is_reply: true
in_reply_to: "122"
is_thread_part: false
conversation_id: "122"
favorite_count: 5
retweet_count: 1
reply_count: 2
quote_count: 3
view_count: 100
media_count: 1
full_text_length: 12
source_type: "x_reply"
---
@a 这是一条历史推文
"""


class KolPoolBackfillTests(unittest.TestCase):
    def build_vault(self, root: Path) -> Path:
        vault = root / "vault"
        raw = vault / "h" / "raw" / "tweets"
        raw.mkdir(parents=True)
        (raw / "123.md").write_text(RAW, encoding="utf-8")
        return vault

    def test_raw_markdown_to_item_preserves_frontmatter_and_body(self):
        item = raw_markdown_to_item(Path("123.md"), RAW, "fallback")

        self.assertEqual(item["id"], "123")
        self.assertEqual(item["screen_name"], "h")
        self.assertEqual(item["author"], "Display Name")
        self.assertEqual(item["full_text"], "@a 这是一条历史推文")
        self.assertTrue(item["is_reply"])
        self.assertEqual(item["in_reply_to"], "122")
        self.assertTrue(item["is_quote"])
        self.assertEqual(item["quoted_tweet_id"], "99")
        self.assertIsNone(item["quote"])
        self.assertEqual(item["stats"]["likes"], 5)
        self.assertEqual(item["stats"]["quotes"], 3)
        self.assertEqual(item["source_type"], "x_reply")

    def test_dry_run_does_not_write_tweet_pool_or_kol_state(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            vault = self.build_vault(root)
            runtime = root / ".tweet-pool"

            out = StringIO()
            with redirect_stdout(out):
                rc = main([
                    "--vault",
                    str(vault),
                    "--handle",
                    "h",
                    "--tweet-pool-runtime",
                    str(runtime),
                    "--dry-run",
                ])

            self.assertEqual(rc, 0)
            result = json.loads(out.getvalue())
            self.assertEqual(result["status"], "dry_run")
            self.assertEqual(result["found"], 1)
            self.assertFalse((runtime / "tweets" / "123.json").exists())
            self.assertFalse((vault / "h" / "raw" / ".backfill_state.json").exists())

    def test_write_backfills_tweet_pool_and_consumer_status_only(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            vault = self.build_vault(root)
            runtime = root / ".tweet-pool"

            out = StringIO()
            with redirect_stdout(out):
                rc = main([
                    "--vault",
                    str(vault),
                    "--handle",
                    "h",
                    "--tweet-pool-runtime",
                    str(runtime),
                ])

            self.assertEqual(rc, 0)
            result = json.loads(out.getvalue())
            self.assertEqual(result["status"], "backfilled")
            self.assertEqual(result["tweet_pool"]["ingested"], 1)
            tweet = json.loads((runtime / "tweets" / "123.json").read_text(encoding="utf-8"))
            self.assertEqual(tweet["full_text"], "@a 这是一条历史推文")
            self.assertEqual(tweet["_pool"]["sources"], ["kol-raw-archive"])
            self.assertEqual(tweet["_pool"]["modes"], ["history"])
            consumer = json.loads((runtime / "consumers" / "kol-tools.json").read_text(encoding="utf-8"))
            self.assertEqual(consumer["items"]["123"]["status"], "raw_backfilled")
            self.assertTrue(consumer["items"]["123"]["output"].endswith("123.md"))
            self.assertFalse((vault / "h" / "raw" / ".backfill_state.json").exists())


if __name__ == "__main__":
    unittest.main()
