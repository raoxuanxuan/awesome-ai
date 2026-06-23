import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kol_clean import classify_text, raw_item


class KolCleanTests(unittest.TestCase):
    def test_reply_with_finance_signal_is_not_noise(self):
        item = classify_text("@abc 这个用 forward PE 看，不看 TTM。", is_reply=True)
        self.assertIn(item["quality"], {"high", "medium"})
        self.assertTrue(item["routing"]["distill"])
        self.assertIn("has_method_keyword", item["reasons"])

    def test_short_social_reply_is_noise_for_distill_but_voice_candidate(self):
        item = classify_text("@abc 哈哈哈", is_reply=True)
        self.assertEqual(item["quality"], "noise")
        self.assertFalse(item["routing"]["distill"])
        self.assertTrue(item["routing"]["voice"])

    def test_reply_with_substantive_length_is_kept(self):
        item = classify_text("@abc 我觉得这里关键不是价格，是订单和现金流兑现的节奏。", is_reply=True)
        self.assertEqual(item["quality"], "medium")
        self.assertTrue(item["routing"]["distill"])
        self.assertIn("substantive_reply_length", item["reasons"])

    def test_ticker_reasoning_is_high_quality(self):
        item = classify_text("$NVDA PEG 1 倍不贵，因为未来三年 EPS 增速还在。")
        self.assertEqual(item["quality"], "high")
        self.assertTrue(item["routing"]["position"])
        self.assertIn("has_ticker", item["reasons"])
        self.assertIn("has_reasoning", item["reasons"])

    def test_raw_item_preserves_metadata_for_index(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "1.md"
            path.write_text(
                "---\n"
                "id: 1\n"
                "lang: zh\n"
                "favorite_count: 7\n"
                "retweet_count: 2\n"
                "reply_count: 3\n"
                "view_count: 100\n"
                "media_count: 1\n"
                "is_thread_part: true\n"
                "---\n"
                "$NVDA 因为需求强\n",
                encoding="utf-8",
            )
            item = raw_item(path)
            self.assertEqual(item["lang"], "zh")
            self.assertEqual(item["favorite_count"], 7)
            self.assertEqual(item["retweet_count"], 2)
            self.assertEqual(item["reply_count"], 3)
            self.assertEqual(item["view_count"], 100)
            self.assertEqual(item["media_count"], 1)
            self.assertTrue(item["is_thread_part"])


if __name__ == "__main__":
    unittest.main()
