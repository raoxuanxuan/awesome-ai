import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fetch_timeline  # noqa: E402


def sample_timeline_payload() -> dict:
    return {
        "ok": True,
        "mode": "timeline",
        "source": "mock",
        "fetched_at": "2026-06-23T10:00:00Z",
        "input": {"user": "karpathy", "limit": 1},
        "items": [
            {
                "id": "100",
                "url": "https://x.com/karpathy/status/100",
                "text": "hello pool",
                "full_text": "hello pool",
                "author": "Andrej Karpathy",
                "screen_name": "karpathy",
                "created_at": "2026-06-23T09:59:00Z",
                "lang": "en",
                "stats": {"likes": 1, "retweets": 0},
                "conversation_id": "100",
                "is_reply": False,
                "is_quote": False,
                "is_retweet": False,
                "media_count": 0,
            }
        ],
        "error": None,
    }


class FetchTimelinePoolTests(unittest.TestCase):
    def test_successful_timeline_is_ingested_into_tweet_pool_before_standard_output(self):
        out = StringIO()
        payload = sample_timeline_payload()
        with mock.patch.object(fetch_timeline, "run_twitter_fetch", return_value=payload):
            with mock.patch.object(fetch_timeline, "ingest_tweet_pool") as ingest:
                with redirect_stdout(out):
                    rc = fetch_timeline.main(["--user", "karpathy", "--json"])

        self.assertEqual(rc, 0)
        ingest.assert_called_once_with(payload)
        standard = json.loads(out.getvalue())
        self.assertIs(standard["ok"], True)
        self.assertEqual(standard["mode"], "timeline")
        self.assertEqual(standard["items"][0]["id"], "100")
        self.assertNotIn("tweet_count", standard)
        self.assertNotIn("tweets", standard)

    def test_tweet_pool_failure_does_not_break_timeline_output(self):
        out = StringIO()
        err = StringIO()
        payload = sample_timeline_payload()
        with mock.patch.object(fetch_timeline, "run_twitter_fetch", return_value=payload):
            with mock.patch.object(
                fetch_timeline,
                "ingest_tweet_pool",
                side_effect=RuntimeError("pool unavailable"),
            ):
                with redirect_stdout(out), redirect_stderr(err):
                    rc = fetch_timeline.main(["--user", "karpathy", "--json"])

        self.assertEqual(rc, 0)
        standard = json.loads(out.getvalue())
        self.assertIs(standard["ok"], True)
        self.assertEqual(standard["items"][0]["id"], "100")
        self.assertIn("tweet-pool ingest failed", err.getvalue())

    def test_twitter_fetch_failure_outputs_standard_error_envelope(self):
        out = StringIO()
        with mock.patch.object(
            fetch_timeline,
            "run_twitter_fetch",
            side_effect=RuntimeError("runner missing"),
        ):
            with redirect_stdout(out):
                rc = fetch_timeline.main(["--user", "karpathy", "--json"])

        self.assertEqual(rc, 1)
        payload = json.loads(out.getvalue())
        self.assertIs(payload["ok"], False)
        self.assertEqual(payload["mode"], "timeline")
        self.assertEqual(payload["input"]["user"], "karpathy")
        self.assertEqual(payload["error"]["code"], "timeline_fetch_failed")
        self.assertIn("runner missing", payload["error"]["message"])

    def test_fetch_timeline_window_reuses_finalized_window_cache(self):
        cached = {
            "ok": True,
            "found": True,
            "snapshot": {
                "status": "finalized",
                "tweet_ids": ["100"],
                "observed_count": 3,
            },
            "items": sample_timeline_payload()["items"],
        }

        with mock.patch.object(fetch_timeline, "run_tweet_pool", return_value=cached) as pool:
            with mock.patch.object(fetch_timeline, "run_twitter_fetch") as twitter:
                result = fetch_timeline.fetch_timeline_window(
                    "karpathy",
                    "2026-06-23T09:00:00Z",
                    "2026-06-23T10:00:00Z",
                    50,
                    10,
                )

        self.assertIs(result["cache_hit"], True)
        self.assertEqual(result["timeline_count"], 3)
        self.assertEqual(result["within_window"], 1)
        self.assertEqual(result["outside_window"], 2)
        self.assertEqual(result["items"][0]["id"], "100")
        self.assertEqual(pool.call_count, 1)
        twitter.assert_not_called()

    def test_fetch_timeline_window_miss_fetches_x_and_writes_snapshot(self):
        missing = {"ok": True, "found": False, "snapshot": None, "items": []}
        written = {
            "ok": True,
            "found": True,
            "snapshot": {
                "status": "finalized",
                "tweet_ids": ["100"],
                "observed_count": 1,
            },
            "items": sample_timeline_payload()["items"],
        }

        with mock.patch.object(fetch_timeline, "run_tweet_pool", side_effect=[missing, written]) as pool:
            with mock.patch.object(
                fetch_timeline,
                "run_twitter_fetch",
                return_value=sample_timeline_payload(),
            ) as twitter:
                with mock.patch.object(fetch_timeline, "now_iso", return_value="2026-06-23T10:11:00Z"):
                    result = fetch_timeline.fetch_timeline_window(
                        "karpathy",
                        "2026-06-23T09:00:00Z",
                        "2026-06-23T10:00:00Z",
                        50,
                        10,
                    )

        self.assertIs(result["cache_hit"], False)
        self.assertEqual(result["items"][0]["id"], "100")
        twitter.assert_called_once_with(["timeline", "--user", "karpathy", "--limit", "50"])
        self.assertEqual(pool.call_count, 2)
        self.assertEqual(pool.call_args_list[1].args[1]["items"][0]["id"], "100")


if __name__ == "__main__":
    unittest.main()
