import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT.parent
RUNNER = SKILL_ROOT / "bin/tweet-pool"

import sys

sys.path.insert(0, str(ROOT))

import tweet_pool  # noqa: E402


def sample_payload(tweet_id: str = "123") -> dict:
    return {
        "ok": True,
        "mode": "timeline",
        "source": "mock",
        "fetched_at": "2026-06-23T10:00:00Z",
        "input": {"user": "karpathy", "limit": 20},
        "items": [
            {
                "id": tweet_id,
                "url": f"https://x.com/karpathy/status/{tweet_id}",
                "author": "Andrej Karpathy",
                "screen_name": "karpathy",
                "created_at": "2026-06-23T09:59:00Z",
                "lang": "en",
                "text": "poolable tweet",
                "full_text": "poolable tweet",
                "media": None,
                "media_count": 0,
                "stats": {
                    "likes": 1,
                    "retweets": 0,
                    "bookmarks": 0,
                    "views": 10,
                    "replies": 0,
                    "quotes": 0,
                },
                "conversation_id": tweet_id,
                "is_reply": False,
                "in_reply_to": "",
                "is_thread_part": False,
                "is_quote": False,
                "is_retweet": False,
                "quote": None,
                "author_profile": {
                    "avatar_url": "https://pbs.twimg.com/profile_images/karpathy.jpg"
                },
            }
        ],
        "error": None,
    }


class TweetPoolTests(unittest.TestCase):
    def test_runtime_defaults_to_authoritative_content_creation_path(self):
        self.assertEqual(
            tweet_pool.runtime_dir({}),
            Path("/Users/saberrao/ai-workspace/content-creation/.tweet-pool"),
        )

    def test_ensure_runtime_creates_cache_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = tweet_pool.ensure_runtime(Path(tmp) / ".tweet-pool")

            for child in (
                "tweets",
                "authors",
                "media",
                "timelines",
                "windows",
                "fetch_state",
                "consumers",
            ):
                self.assertTrue((runtime / child).is_dir(), child)

    def test_ingest_envelope_writes_tweet_author_and_timeline_observation(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / ".tweet-pool"
            result = tweet_pool.ingest_payload(sample_payload(), runtime)

            self.assertEqual(result["ingested"], 1)
            tweet = json.loads((runtime / "tweets/123.json").read_text())
            self.assertEqual(tweet["id"], "123")
            self.assertEqual(tweet["screen_name"], "karpathy")
            self.assertEqual(tweet["_pool"]["sources"], ["mock"])
            self.assertIs(tweet["_pool"]["completeness"]["timeline"], True)

            author = json.loads((runtime / "authors/karpathy.json").read_text())
            self.assertEqual(author["username"], "karpathy")
            self.assertEqual(author["display_name"], "Andrej Karpathy")
            self.assertEqual(
                author["avatar_url"], "https://pbs.twimg.com/profile_images/karpathy.jpg"
            )

            observations = [
                json.loads(line)
                for line in (runtime / "timelines/karpathy.jsonl").read_text().splitlines()
            ]
            self.assertEqual(observations[0]["tweet_ids"], ["123"])
            self.assertEqual(observations[0]["mode"], "timeline")

    def test_ingest_preserves_existing_completeness_when_same_tweet_is_seen_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / ".tweet-pool"
            tweet_pool.ingest_payload(sample_payload("123"), runtime)

            payload = sample_payload("123")
            payload["mode"] = "single"
            payload["source"] = "fxtwitter"
            payload["items"][0]["full_text"] = "more complete text"
            tweet_pool.ingest_payload(payload, runtime)

            tweet = json.loads((runtime / "tweets/123.json").read_text())
            self.assertEqual(tweet["full_text"], "more complete text")
            self.assertIs(tweet["_pool"]["completeness"]["timeline"], True)
            self.assertIs(tweet["_pool"]["completeness"]["single"], True)
            self.assertEqual(tweet["_pool"]["sources"], ["fxtwitter", "mock"])

    def test_ingest_records_field_provenance_for_updated_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / ".tweet-pool"
            tweet_pool.ingest_payload(sample_payload("123"), runtime)

            payload = sample_payload("123")
            payload["mode"] = "single"
            payload["source"] = "fxtwitter"
            payload["fetched_at"] = "2026-06-23T11:00:00Z"
            payload["items"][0]["full_text"] = "single mode canonical text"
            tweet_pool.ingest_payload(payload, runtime)

            tweet = json.loads((runtime / "tweets/123.json").read_text())
            provenance = tweet["_pool"]["field_sources"]
            self.assertEqual(provenance["full_text"]["source"], "fxtwitter")
            self.assertEqual(provenance["full_text"]["mode"], "single")
            self.assertEqual(provenance["full_text"]["updated_at"], "2026-06-23T11:00:00Z")
            self.assertEqual(provenance["screen_name"]["source"], "mock")

    def test_short_text_does_not_replace_longer_canonical_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / ".tweet-pool"
            payload = sample_payload("123")
            payload["mode"] = "single"
            payload["source"] = "fxtwitter"
            payload["items"][0]["full_text"] = "this is a much more complete canonical tweet text"
            tweet_pool.ingest_payload(payload, runtime)

            shorter = sample_payload("123")
            shorter["mode"] = "timeline"
            shorter["source"] = "syndication"
            shorter["items"][0]["full_text"] = "short text"
            shorter["items"][0]["text"] = "short text"
            tweet_pool.ingest_payload(shorter, runtime)

            tweet = json.loads((runtime / "tweets/123.json").read_text())
            self.assertEqual(tweet["full_text"], "this is a much more complete canonical tweet text")
            self.assertEqual(tweet["_pool"]["field_sources"]["full_text"]["source"], "fxtwitter")

    def test_empty_media_payload_does_not_clear_existing_media(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / ".tweet-pool"
            payload = sample_payload("123")
            payload["items"][0]["media"] = [{"type": "photo", "url": "https://x.com/a.jpg"}]
            payload["items"][0]["media_count"] = 1
            tweet_pool.ingest_payload(payload, runtime)

            empty_media = sample_payload("123")
            empty_media["source"] = "syndication"
            empty_media["items"][0]["media"] = []
            empty_media["items"][0]["media_count"] = 0
            tweet_pool.ingest_payload(empty_media, runtime)

            tweet = json.loads((runtime / "tweets/123.json").read_text())
            self.assertEqual(tweet["media"], [{"type": "photo", "url": "https://x.com/a.jpg"}])
            self.assertEqual(tweet["media_count"], 1)

    def test_empty_quote_payload_does_not_clear_existing_quote(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / ".tweet-pool"
            payload = sample_payload("123")
            payload["items"][0]["is_quote"] = True
            payload["items"][0]["quote"] = {
                "id": "99",
                "screen_name": "other",
                "full_text": "quoted context",
            }
            tweet_pool.ingest_payload(payload, runtime)

            empty_quote = sample_payload("123")
            empty_quote["source"] = "syndication"
            empty_quote["items"][0]["is_quote"] = False
            empty_quote["items"][0]["quote"] = None
            tweet_pool.ingest_payload(empty_quote, runtime)

            tweet = json.loads((runtime / "tweets/123.json").read_text())
            self.assertIs(tweet["is_quote"], True)
            self.assertEqual(tweet["quote"]["id"], "99")

    def test_consumer_status_is_separate_from_tweet_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / ".tweet-pool"
            tweet_pool.ingest_payload(sample_payload(), runtime)

            tweet_pool.set_consumer_status(
                "twitter-monitor",
                "123",
                "skipped",
                runtime,
                reason="short_reply",
            )
            tweet_pool.set_consumer_status(
                "kol-twin",
                "123",
                "raw_written",
                runtime,
                output="/Users/saberrao/vault/kol/karpathy/raw/tweets/123.md",
            )

            monitor = json.loads((runtime / "consumers/twitter-monitor.json").read_text())
            kol = json.loads((runtime / "consumers/kol-twin.json").read_text())
            tweet = json.loads((runtime / "tweets/123.json").read_text())

            self.assertEqual(monitor["items"]["123"]["status"], "skipped")
            self.assertEqual(kol["items"]["123"]["status"], "raw_written")
            self.assertNotIn("status", tweet)

    def test_cli_ingest_outputs_machine_readable_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / ".tweet-pool"
            payload = Path(tmp) / "payload.json"
            payload.write_text(json.dumps(sample_payload()), encoding="utf-8")

            out = StringIO()
            with redirect_stdout(out):
                rc = tweet_pool.main(
                    [
                        "--runtime",
                        str(runtime),
                        "ingest",
                        "--input",
                        str(payload),
                    ]
                )

            self.assertEqual(rc, 0)
            summary = json.loads(out.getvalue())
            self.assertEqual(summary["ingested"], 1)
            self.assertTrue((runtime / "tweets/123.json").exists())

    def test_cli_ingest_accepts_twitter_fetch_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / ".tweet-pool"
            jsonl = Path(tmp) / "history.jsonl"
            first = sample_payload("123")["items"][0]
            second = sample_payload("124")["items"][0]
            jsonl.write_text(
                json.dumps(first) + "\n" + json.dumps(second) + "\n",
                encoding="utf-8",
            )

            out = StringIO()
            with redirect_stdout(out):
                rc = tweet_pool.main(
                    [
                        "--runtime",
                        str(runtime),
                        "ingest",
                        "--input",
                        str(jsonl),
                    ]
                )

            self.assertEqual(rc, 0)
            summary = json.loads(out.getvalue())
            self.assertEqual(summary["tweet_ids"], ["123", "124"])
            self.assertTrue((runtime / "tweets/124.json").exists())

    def test_export_by_tweet_ids_returns_cached_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / ".tweet-pool"
            tweet_pool.ingest_payload(sample_payload("123"), runtime)
            tweet_pool.ingest_payload(sample_payload("124"), runtime)

            items = tweet_pool.export_tweets(runtime, tweet_ids=["124", "missing", "123"])

            self.assertEqual([item["id"] for item in items], ["124", "123"])

    def test_cli_export_filters_by_user_and_since_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / ".tweet-pool"
            tweet_pool.ingest_payload(sample_payload("123"), runtime)
            tweet_pool.ingest_payload(sample_payload("124"), runtime)

            out = StringIO()
            with redirect_stdout(out):
                rc = tweet_pool.main(
                    [
                        "--runtime",
                        str(runtime),
                        "export",
                        "--user",
                        "karpathy",
                        "--since-id",
                        "123",
                    ]
                )

            self.assertEqual(rc, 0)
            summary = json.loads(out.getvalue())
            self.assertEqual(summary["count"], 1)
            self.assertEqual(summary["items"][0]["id"], "124")

    def test_cli_export_outputs_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / ".tweet-pool"
            tweet_pool.ingest_payload(sample_payload("123"), runtime)

            out = StringIO()
            with redirect_stdout(out):
                rc = tweet_pool.main(
                    [
                        "--runtime",
                        str(runtime),
                        "export",
                        "--tweet-ids",
                        "123",
                        "--format",
                        "jsonl",
                    ]
                )

            self.assertEqual(rc, 0)
            self.assertEqual(json.loads(out.getvalue())["id"], "123")

    def test_window_put_finalizes_empty_closed_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / ".tweet-pool"
            payload = sample_payload("123")
            payload["items"] = []
            payload_path = Path(tmp) / "payload.json"
            payload_path.write_text(json.dumps(payload), encoding="utf-8")

            out = StringIO()
            with redirect_stdout(out):
                rc = tweet_pool.main(
                    [
                        "--runtime",
                        str(runtime),
                        "window",
                        "put",
                        "--user",
                        "karpathy",
                        "--window-start",
                        "2026-06-23T09:00:00Z",
                        "--window-end",
                        "2026-06-23T10:00:00Z",
                        "--input",
                        str(payload_path),
                        "--limit",
                        "50",
                        "--grace-minutes",
                        "10",
                        "--now",
                        "2026-06-23T10:11:00Z",
                        "--include-items",
                    ]
                )

            self.assertEqual(rc, 0, out.getvalue())
            summary = json.loads(out.getvalue())
            snapshot = summary["snapshot"]
            self.assertEqual(snapshot["status"], "finalized")
            self.assertEqual(snapshot["tweet_ids"], [])
            self.assertEqual(snapshot["observed_count"], 0)
            self.assertEqual(summary["items"], [])

    def test_window_put_marks_incomplete_when_scan_limit_does_not_cover_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / ".tweet-pool"
            first = sample_payload("123")["items"][0]
            first["created_at"] = "2026-06-23T09:50:00Z"
            second = sample_payload("124")["items"][0]
            second["created_at"] = "2026-06-23T09:40:00Z"
            payload = sample_payload("123")
            payload["items"] = [first, second]
            payload_path = Path(tmp) / "payload.json"
            payload_path.write_text(json.dumps(payload), encoding="utf-8")

            out = StringIO()
            with redirect_stdout(out):
                rc = tweet_pool.main(
                    [
                        "--runtime",
                        str(runtime),
                        "window",
                        "put",
                        "--user",
                        "karpathy",
                        "--window-start",
                        "2026-06-23T09:00:00Z",
                        "--window-end",
                        "2026-06-23T10:00:00Z",
                        "--input",
                        str(payload_path),
                        "--limit",
                        "2",
                        "--grace-minutes",
                        "10",
                        "--now",
                        "2026-06-23T10:11:00Z",
                    ]
                )

            self.assertEqual(rc, 0, out.getvalue())
            snapshot = json.loads(out.getvalue())["snapshot"]
            self.assertEqual(snapshot["status"], "incomplete")
            self.assertEqual(snapshot["tweet_ids"], ["123", "124"])
            self.assertIs(snapshot["coverage"]["hit_scan_limit"], True)
            self.assertIs(snapshot["coverage"]["covers_window_start"], False)

    def test_window_get_returns_cached_items_for_finalized_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / ".tweet-pool"
            payload = sample_payload("123")
            outside = sample_payload("124")["items"][0]
            outside["created_at"] = "2026-06-23T08:59:59Z"
            payload["items"].append(outside)
            payload_path = Path(tmp) / "payload.json"
            payload_path.write_text(json.dumps(payload), encoding="utf-8")
            with redirect_stdout(StringIO()):
                tweet_pool.main(
                    [
                        "--runtime",
                        str(runtime),
                        "window",
                        "put",
                        "--user",
                        "karpathy",
                        "--window-start",
                        "2026-06-23T09:00:00Z",
                        "--window-end",
                        "2026-06-23T10:00:00Z",
                        "--input",
                        str(payload_path),
                        "--limit",
                        "50",
                        "--grace-minutes",
                        "10",
                        "--now",
                        "2026-06-23T10:11:00Z",
                    ]
                )

            out = StringIO()
            with redirect_stdout(out):
                rc = tweet_pool.main(
                    [
                        "--runtime",
                        str(runtime),
                        "window",
                        "get",
                        "--user",
                        "karpathy",
                        "--window-start",
                        "2026-06-23T09:00:00Z",
                        "--window-end",
                        "2026-06-23T10:00:00Z",
                        "--include-items",
                    ]
                )

            self.assertEqual(rc, 0, out.getvalue())
            summary = json.loads(out.getvalue())
            self.assertIs(summary["found"], True)
            self.assertEqual(summary["snapshot"]["status"], "finalized")
            self.assertEqual([item["id"] for item in summary["items"]], ["123"])

    def test_window_get_keeps_empty_finalized_snapshot_empty_with_cached_pool_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / ".tweet-pool"
            tweet_pool.ingest_payload(sample_payload("999"), runtime)

            payload = sample_payload("123")
            payload["items"] = []
            payload_path = Path(tmp) / "payload.json"
            payload_path.write_text(json.dumps(payload), encoding="utf-8")
            with redirect_stdout(StringIO()):
                tweet_pool.main(
                    [
                        "--runtime",
                        str(runtime),
                        "window",
                        "put",
                        "--user",
                        "karpathy",
                        "--window-start",
                        "2026-06-23T09:00:00Z",
                        "--window-end",
                        "2026-06-23T10:00:00Z",
                        "--input",
                        str(payload_path),
                        "--limit",
                        "50",
                        "--grace-minutes",
                        "10",
                        "--now",
                        "2026-06-23T10:11:00Z",
                    ]
                )

            out = StringIO()
            with redirect_stdout(out):
                rc = tweet_pool.main(
                    [
                        "--runtime",
                        str(runtime),
                        "window",
                        "get",
                        "--user",
                        "karpathy",
                        "--window-start",
                        "2026-06-23T09:00:00Z",
                        "--window-end",
                        "2026-06-23T10:00:00Z",
                        "--include-items",
                    ]
                )

            self.assertEqual(rc, 0, out.getvalue())
            summary = json.loads(out.getvalue())
            self.assertIs(summary["found"], True)
            self.assertEqual(summary["snapshot"]["status"], "finalized")
            self.assertEqual(summary["snapshot"]["tweet_ids"], [])
            self.assertEqual(summary["items"], [])

    def test_runner_invokes_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / ".tweet-pool"
            proc = subprocess.run(
                ["/bin/bash", str(RUNNER), "--runtime", str(runtime), "ensure"],
                capture_output=True,
                text=True,
                env={**os.environ},
            )

            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["runtime"], str(runtime))
            self.assertTrue((runtime / "tweets").is_dir())

    def test_cli_accepts_pretty_after_subcommand(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / ".tweet-pool"
            out = StringIO()
            with redirect_stdout(out):
                rc = tweet_pool.main(["--runtime", str(runtime), "ensure", "--pretty"])

            self.assertEqual(rc, 0)
            self.assertIn("\n  ", out.getvalue())
            self.assertTrue((runtime / "tweets").is_dir())


if __name__ == "__main__":
    unittest.main()
