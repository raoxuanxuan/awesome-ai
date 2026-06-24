import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import monitor  # noqa: E402


def timeline_payload(*items):
    return {
        "ok": True,
        "mode": "timeline",
        "source": "mock",
        "fetched_at": "2026-06-23T10:00:00Z",
        "input": {"user": "karpathy", "limit": 20},
        "items": list(items),
        "error": None,
    }


def tweet(tweet_id, text="useful long tweet about AI systems and monitor architecture", **overrides):
    item = {
        "id": str(tweet_id),
        "url": f"https://x.com/karpathy/status/{tweet_id}",
        "author": "Andrej Karpathy",
        "screen_name": "karpathy",
        "created_at": "2026-06-23T09:59:00Z",
        "lang": "en",
        "text": text,
        "full_text": text,
        "media": None,
        "media_count": 0,
        "stats": {"likes": 1, "retweets": 0},
        "conversation_id": str(tweet_id),
        "is_reply": False,
        "in_reply_to": "",
        "is_thread_part": False,
        "is_quote": False,
        "is_retweet": False,
        "quote": None,
    }
    item.update(overrides)
    return item


class MonitorRunnerTests(unittest.TestCase):
    def test_configured_users_includes_topic_users_and_dedupes(self):
        config = {
            "users": [{"username": "@karpathy"}],
            "topics": [
                {"name": "AI", "users": ["karpathy", "@omarsar0"]},
                {"name": "invest", "users": ["Money_or_Life_X"]},
            ],
        }

        self.assertEqual(
            monitor.configured_users(config),
            ["karpathy", "omarsar0", "Money_or_Life_X"],
        )

    def test_run_fetches_timeline_filters_items_fetches_single_and_updates_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / ".twitter-monitor"
            runtime.mkdir()
            (runtime / "config.yaml").write_text(
                """
users:
  - username: "karpathy"

settings:
  interval_minutes: 60
  lookback_minutes: 70
  first_run_lookback_minutes: 60
  max_scan_per_user: 20
  include_replies: false
  include_retweets: false
  expand_thread: true
  mark_skipped_as_seen: true
""",
                encoding="utf-8",
            )
            useful = tweet("101")
            reply = tweet("102", text="@user thanks", is_reply=True, in_reply_to="1")
            short = tweet("103", text="ok")
            full = {
                **timeline_payload(useful),
                "mode": "single",
                "input": {"url": useful["url"], "context": "thread"},
            }

            calls = []

            def fake_fetch(args):
                calls.append(args)
                if args[0] == "timeline":
                    return timeline_payload(useful, reply, short)
                if args[0] == "single":
                    return full
                raise AssertionError(args)

            with mock.patch.object(monitor, "now_iso", return_value="2026-06-23T10:00:00Z"):
                with mock.patch.object(monitor, "run_twitter_fetch", side_effect=fake_fetch):
                    with mock.patch.object(monitor, "ingest_tweet_pool") as ingest_pool:
                        with mock.patch.object(monitor, "maybe_ingest_tweet_pool") as ingest_timeline:
                            report = monitor.run_monitor(runtime)

            self.assertEqual(report["users"]["karpathy"]["timeline_count"], 3)
            self.assertEqual(report["users"]["karpathy"]["fetched"], 1)
            self.assertEqual(report["users"]["karpathy"]["skipped"], 2)
            self.assertEqual(
                calls,
                [
                    ["timeline", "--user", "karpathy", "--limit", "20"],
                    ["single", "--url", useful["url"], "--include-thread"],
                ],
            )
            self.assertEqual(ingest_timeline.call_count, 1)
            self.assertEqual(ingest_pool.call_count, 1)

            state = json.loads((runtime / ".state.json").read_text())
            items = state["users"]["karpathy"]["items"]
            self.assertEqual(items["101"]["status"], "fetched")
            self.assertEqual(items["102"]["status"], "skipped")
            self.assertEqual(items["102"]["reason"], "reply")
            self.assertEqual(items["103"]["status"], "skipped")
            self.assertEqual(items["103"]["reason"], "short_no_url")
            self.assertEqual(state["version"], 3)
            self.assertIn("last_success_at", state["users"]["karpathy"])
            self.assertIn("window_start", state["users"]["karpathy"])

    def test_run_does_not_refetch_items_already_saved_or_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / ".twitter-monitor"
            runtime.mkdir()
            (runtime / "config.yaml").write_text(
                'users:\n  - username: "karpathy"\nsettings:\n  max_scan_per_user: 20\n',
                encoding="utf-8",
            )
            (runtime / ".state.json").write_text(
                json.dumps(
                    {
                        "version": 3,
                        "users": {
                            "karpathy": {
                                "items": {
                                    "101": {"status": "saved"},
                                    "102": {"status": "skipped"},
                                }
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            with mock.patch.object(monitor, "now_iso", return_value="2026-06-23T10:00:00Z"):
                with mock.patch.object(
                    monitor,
                    "run_twitter_fetch",
                    return_value=timeline_payload(tweet("101"), tweet("102")),
                ) as fetch:
                    with mock.patch.object(monitor, "maybe_ingest_tweet_pool"):
                        report = monitor.run_monitor(runtime)

            self.assertEqual(fetch.call_count, 1)
            self.assertEqual(report["users"]["karpathy"]["already_seen"], 2)

    def test_run_filters_items_outside_lookback_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / ".twitter-monitor"
            runtime.mkdir()
            (runtime / "config.yaml").write_text(
                """
users:
  - username: "karpathy"

settings:
  interval_minutes: 60
  lookback_minutes: 70
  first_run_lookback_minutes: 60
  max_scan_per_user: 50
  include_replies: false
  include_retweets: false
  expand_thread: true
  mark_skipped_as_seen: true
""",
                encoding="utf-8",
            )
            inside = tweet("201", created_at="2026-06-24T09:30:00Z")
            outside = tweet("202", created_at="2026-06-24T08:59:59Z")
            full = {
                **timeline_payload(inside),
                "mode": "single",
                "input": {"url": inside["url"], "context": "thread"},
            }
            calls = []

            def fake_fetch(args):
                calls.append(args)
                if args[0] == "timeline":
                    return timeline_payload(inside, outside)
                if args[0] == "single":
                    return full
                raise AssertionError(args)

            with mock.patch.object(monitor, "now_iso", return_value="2026-06-24T10:00:00Z"):
                with mock.patch.object(monitor, "run_twitter_fetch", side_effect=fake_fetch):
                    with mock.patch.object(monitor, "ingest_tweet_pool"):
                        with mock.patch.object(monitor, "maybe_ingest_tweet_pool"):
                            report = monitor.run_monitor(runtime)

            user_report = report["users"]["karpathy"]
            self.assertEqual(user_report["timeline_count"], 2)
            self.assertEqual(user_report["outside_window"], 1)
            self.assertEqual(user_report["fetched"], 1)
            self.assertEqual(
                calls,
                [
                    ["timeline", "--user", "karpathy", "--limit", "50"],
                    ["single", "--url", inside["url"], "--include-thread"],
                ],
            )

            state = json.loads((runtime / ".state.json").read_text())
            user_state = state["users"]["karpathy"]
            self.assertEqual(user_state["window_start"], "2026-06-24T09:00:00Z")
            self.assertEqual(user_state["last_success_at"], "2026-06-24T10:00:00Z")
            self.assertEqual(user_state["items"]["201"]["status"], "fetched")
            self.assertEqual(user_state["items"]["201"]["created_at"], "2026-06-24T09:30:00Z")
            self.assertNotIn("202", user_state["items"])


if __name__ == "__main__":
    unittest.main()
