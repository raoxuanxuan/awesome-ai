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


def window_payload(*items, **overrides):
    payload = {
        "ok": True,
        "items": list(items),
        "snapshot": {
            "status": "finalized",
            "tweet_ids": [str(item.get("id")) for item in items],
            "observed_count": len(items),
            "window_start": "2026-06-23T09:00:00Z",
            "window_end": "2026-06-23T10:00:00Z",
        },
        "cache_hit": False,
        "timeline_count": len(items),
        "within_window": len(items),
        "outside_window": 0,
    }
    payload.update(overrides)
    return payload


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
  window_grace_minutes: 0
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
                if args[0] == "single":
                    return full
                raise AssertionError(args)

            with mock.patch.object(monitor, "now_iso", return_value="2026-06-23T10:00:00Z"):
                with mock.patch.object(monitor, "run_twitter_fetch", side_effect=fake_fetch):
                    with mock.patch.object(monitor, "ingest_tweet_pool") as ingest_pool:
                        with mock.patch.object(
                            monitor,
                            "fetch_timeline_window",
                            return_value=window_payload(useful, reply, short),
                        ) as fetch_window:
                            report = monitor.run_monitor(runtime)

            self.assertEqual(report["users"]["karpathy"]["timeline_count"], 3)
            self.assertEqual(report["users"]["karpathy"]["fetched"], 1)
            self.assertEqual(report["users"]["karpathy"]["skipped"], 2)
            self.assertEqual(
                calls,
                [
                    ["single", "--url", useful["url"], "--include-thread"],
                ],
            )
            fetch_window.assert_called_once()
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
                    "fetch_timeline_window",
                    return_value=window_payload(tweet("101"), tweet("102")),
                ) as fetch_window:
                    with mock.patch.object(monitor, "run_twitter_fetch") as fetch:
                        report = monitor.run_monitor(runtime)

            fetch_window.assert_called_once()
            self.assertEqual(fetch.call_count, 0)
            self.assertEqual(report["users"]["karpathy"]["already_seen"], 2)

    def test_run_uses_closed_window_snapshot_boundaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / ".twitter-monitor"
            runtime.mkdir()
            (runtime / "config.yaml").write_text(
                """
users:
  - username: "karpathy"

settings:
  interval_minutes: 60
  window_grace_minutes: 0
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
                if args[0] == "single":
                    return full
                raise AssertionError(args)

            with mock.patch.object(monitor, "now_iso", return_value="2026-06-24T10:00:00Z"):
                with mock.patch.object(monitor, "run_twitter_fetch", side_effect=fake_fetch):
                    with mock.patch.object(monitor, "ingest_tweet_pool"):
                        with mock.patch.object(
                            monitor,
                            "fetch_timeline_window",
                            return_value=window_payload(
                                inside,
                                snapshot={
                                    "status": "finalized",
                                    "tweet_ids": ["201"],
                                    "observed_count": 2,
                                    "window_start": "2026-06-24T09:00:00Z",
                                    "window_end": "2026-06-24T10:00:00Z",
                                },
                                timeline_count=2,
                                within_window=1,
                                outside_window=1,
                                cache_hit=True,
                            ),
                        ) as fetch_window:
                            report = monitor.run_monitor(runtime)

            user_report = report["users"]["karpathy"]
            self.assertEqual(user_report["timeline_count"], 2)
            self.assertEqual(user_report["outside_window"], 1)
            self.assertEqual(user_report["window_end"], "2026-06-24T10:00:00Z")
            self.assertEqual(user_report["window_status"], "finalized")
            self.assertIs(user_report["cache_hit"], True)
            self.assertEqual(user_report["fetched"], 1)
            self.assertEqual(
                calls,
                [
                    ["single", "--url", inside["url"], "--include-thread"],
                ],
            )
            fetch_window.assert_called_once_with(
                "karpathy",
                "2026-06-24T09:00:00Z",
                "2026-06-24T10:00:00Z",
                50,
                0,
            )

            state = json.loads((runtime / ".state.json").read_text())
            user_state = state["users"]["karpathy"]
            self.assertEqual(user_state["window_start"], "2026-06-24T09:00:00Z")
            self.assertEqual(user_state["window_end"], "2026-06-24T10:00:00Z")
            self.assertEqual(user_state["last_success_at"], "2026-06-24T10:00:00Z")
            self.assertEqual(user_state["items"]["201"]["status"], "fetched")
            self.assertEqual(user_state["items"]["201"]["created_at"], "2026-06-24T09:30:00Z")
            self.assertNotIn("202", user_state["items"])

    def test_build_notification_event_uses_minimal_card_fields(self):
        item = tweet(
            "301",
            text="A technical observation about model training and product systems.",
            author="Andrej Karpathy",
            screen_name="karpathy",
            is_quote=True,
            quote={"id": "99", "screen_name": "openai"},
            is_article=True,
            article={"title": "Longform note"},
        )
        full_payload = {
            **timeline_payload(item),
            "mode": "single",
            "items": [
                {
                    **item,
                    "thread": {"ok": True, "items": [tweet("302")]},
                }
            ],
        }

        event = monitor.build_notification_event("karpathy", item, full_payload)

        self.assertEqual(event["source"], "twitter-monitor")
        self.assertEqual(event["level"], "alert")
        self.assertEqual(event["title"], "Andrej Karpathy")
        self.assertEqual(event["dedupe_key"], "tweet:301")
        self.assertEqual(event["links"], [{"label": item["url"], "url": item["url"]}])
        self.assertNotIn("Type:", event["summary"])
        self.assertIn("A technical observation", event["summary"])
        self.assertLessEqual(len(event["summary"]), 300)
        self.assertEqual(
            event["meta"],
            {
                "tweet_id": "301",
                "username": "karpathy",
                "types": ["thread", "quote", "article"],
                "display": {"hide_source_prefix": True, "hide_level": True},
                "summary_source": "direct",
            },
        )

    def test_short_notification_summary_uses_cleaned_text_without_llm(self):
        item = tweet("302", text="Short text\nwith spacing.")
        config = {"sinks": {"notification": {"direct_chars": 80, "summary_chars": 40}}}

        with mock.patch.object(monitor, "run_summary_command") as summarize:
            event = monitor.build_notification_event("karpathy", item, timeline_payload(item), config)

        summarize.assert_not_called()
        self.assertEqual(event["summary"], "Short text with spacing.")
        self.assertEqual(event["meta"]["summary_source"], "direct")

    def test_long_notification_summary_uses_llm_command(self):
        item = tweet("303", text="Long observation. " * 30)
        config = {
            "sinks": {
                "notification": {
                    "direct_chars": 80,
                    "summary_chars": 120,
                    "summary_command": "/mock/summarizer",
                }
            }
        }

        with mock.patch.object(monitor, "run_summary_command", return_value="LLM summary.") as summarize:
            event = monitor.build_notification_event("karpathy", item, timeline_payload(item), config)

        summarize.assert_called_once()
        self.assertEqual(event["summary"], "LLM summary.")
        self.assertEqual(event["meta"]["summary_source"], "llm")

    def test_long_notification_summary_falls_back_when_llm_fails(self):
        item = tweet("304", text="Long observation. " * 30)
        config = {
            "sinks": {
                "notification": {
                    "direct_chars": 80,
                    "summary_chars": 60,
                    "summary_command": "/mock/summarizer",
                }
            }
        }

        with mock.patch.object(monitor, "run_summary_command", side_effect=RuntimeError("boom")):
            event = monitor.build_notification_event("karpathy", item, timeline_payload(item), config)

        self.assertLessEqual(len(event["summary"]), 60)
        self.assertTrue(event["summary"].endswith("..."))
        self.assertEqual(event["meta"]["summary_source"], "fallback")
        self.assertEqual(event["meta"]["summary_error"], "boom")

    def test_run_appends_notification_after_successful_fetch_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / ".twitter-monitor"
            runtime.mkdir()
            (runtime / "config.yaml").write_text(
                """
users:
  - username: "karpathy"

settings:
  interval_minutes: 60
  window_grace_minutes: 0
  max_scan_per_user: 20
  expand_thread: true

sinks:
  notification:
    enabled: true
""",
                encoding="utf-8",
            )
            useful = tweet("401", author="Andrej Karpathy", screen_name="karpathy")
            full = {
                **timeline_payload(useful),
                "mode": "single",
                "input": {"url": useful["url"], "context": "thread"},
            }

            def fake_fetch(args):
                if args[0] == "single":
                    return full
                raise AssertionError(args)

            with mock.patch.object(monitor, "now_iso", return_value="2026-06-23T10:00:00Z"):
                with mock.patch.object(monitor, "run_twitter_fetch", side_effect=fake_fetch):
                    with mock.patch.object(monitor, "ingest_tweet_pool"):
                        with mock.patch.object(
                            monitor,
                            "fetch_timeline_window",
                            return_value=window_payload(useful),
                        ):
                            with mock.patch.object(monitor, "append_notification_event") as append:
                                report = monitor.run_monitor(runtime)

            append.assert_called_once()
            event = append.call_args.args[0]
            self.assertEqual(event["title"], "Andrej Karpathy")
            self.assertEqual(event["links"], [{"label": useful["url"], "url": useful["url"]}])
            self.assertEqual(report["users"]["karpathy"]["notified"], 1)

    def test_run_passes_config_to_notification_builder(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / ".twitter-monitor"
            runtime.mkdir()
            (runtime / "config.yaml").write_text(
                """
users:
  - username: "karpathy"

settings:
  interval_minutes: 60
  window_grace_minutes: 0
  max_scan_per_user: 20

sinks:
  notification:
    enabled: true
    direct_chars: 80
    summary_command: "/mock/summarizer"
""",
                encoding="utf-8",
            )
            useful = tweet("402")
            full = {**timeline_payload(useful), "mode": "single"}

            def fake_fetch(args):
                if args[0] == "single":
                    return full
                raise AssertionError(args)

            with mock.patch.object(monitor, "now_iso", return_value="2026-06-23T10:00:00Z"):
                with mock.patch.object(monitor, "run_twitter_fetch", side_effect=fake_fetch):
                    with mock.patch.object(monitor, "ingest_tweet_pool"):
                        with mock.patch.object(
                            monitor,
                            "fetch_timeline_window",
                            return_value=window_payload(useful),
                        ):
                            with mock.patch.object(
                                monitor,
                                "build_notification_event",
                                return_value={"source": "twitter-monitor", "title": "x"},
                            ) as builder:
                                with mock.patch.object(monitor, "append_notification_event"):
                                    monitor.run_monitor(runtime)

            self.assertEqual(builder.call_args.args[3]["sinks"]["notification"]["direct_chars"], 80)


if __name__ == "__main__":
    unittest.main()
