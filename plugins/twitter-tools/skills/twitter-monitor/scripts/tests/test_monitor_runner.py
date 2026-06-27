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

    def test_topic_for_user_uses_first_topic_membership(self):
        config = {
            "topics": [
                {"name": "AI", "users": ["@karpathy"]},
                {"name": "invest", "users": ["Money_or_Life_X"]},
            ]
        }

        self.assertEqual(monitor.topic_for_user("karpathy", config), "AI")
        self.assertEqual(monitor.topic_for_user("@Money_or_Life_X", config), "invest")
        self.assertEqual(monitor.topic_for_user("unknown", config), "")

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
            opinion = tweet("104", text="所以美联储到底鹰不鹰？ Buy this dip")
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
                            return_value=window_payload(useful, reply, short, opinion),
                        ) as fetch_window:
                            report = monitor.run_monitor(runtime)

            self.assertEqual(report["users"]["karpathy"]["timeline_count"], 4)
            self.assertEqual(report["users"]["karpathy"]["fetched"], 2)
            self.assertEqual(report["users"]["karpathy"]["skipped"], 2)
            self.assertEqual(
                calls,
                [
                    ["single", "--url", useful["url"], "--include-thread"],
                    ["single", "--url", opinion["url"], "--include-thread"],
                ],
            )
            fetch_window.assert_called_once()
            self.assertEqual(ingest_pool.call_count, 2)

            state = json.loads((runtime / ".state.json").read_text())
            items = state["users"]["karpathy"]["items"]
            self.assertEqual(items["101"]["status"], "fetched")
            self.assertEqual(items["102"]["status"], "skipped")
            self.assertEqual(items["102"]["reason"], "reply")
            self.assertEqual(items["103"]["status"], "skipped")
            self.assertEqual(items["103"]["reason"], "short_no_url")
            self.assertEqual(items["104"]["status"], "fetched")
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
                "display": {"hide_source_prefix": True, "hide_level": True, "hide_footer": True},
                "summary_source": "direct",
            },
        )

    def test_short_chinese_notification_summary_uses_cleaned_text_without_llm(self):
        item = tweet("302", text="短内容\n带换行。")
        config = {"sinks": {"notification": {"direct_chars": 80, "summary_chars": 40}}}

        with mock.patch.object(monitor, "run_summary_command") as summarize:
            event = monitor.build_notification_event("karpathy", item, timeline_payload(item), config)

        summarize.assert_not_called()
        self.assertEqual(event["summary"], "短内容 带换行。")
        self.assertEqual(event["meta"]["summary_source"], "direct")

    def test_short_english_notification_summary_uses_llm_and_marks_original_language(self):
        item = tweet("306", text="Short English note about agent workflows.")
        config = {
            "settings": {"translate_non_chinese": True},
            "sinks": {
                "notification": {
                    "direct_chars": 80,
                    "summary_chars": 80,
                    "summary_command": "/mock/summarizer",
                }
            },
        }

        with mock.patch.object(monitor, "run_summary_command", return_value="关于智能体工作流的短观点。") as summarize:
            event = monitor.build_notification_event("karpathy", item, timeline_payload(item), config)

        summarize.assert_called_once()
        self.assertEqual(event["summary"], "[原文英文] 关于智能体工作流的短观点。")
        self.assertEqual(event["meta"]["summary_source"], "llm")
        self.assertEqual(event["meta"]["original_language"], "en")

    def test_quote_notification_summary_includes_quoted_tweet_text(self):
        item = tweet(
            "307",
            text="Holy…..",
            is_quote=True,
            quote={
                "text": "18% sounds like a lot already but RAM upgrade cost went up 100%.",
                "author": "David",
                "screen_name": "dayonefoundry",
            },
        )
        config = {
            "settings": {"translate_non_chinese": True},
            "sinks": {
                "notification": {
                    "direct_chars": 300,
                    "summary_chars": 120,
                    "summary_command": "/mock/summarizer",
                }
            },
        }

        llm_summary = "Holy…..\n\n引用: David 指出，RAM 升级费从 +$800 到 +$1600，涨幅达 100%。"
        with mock.patch.object(monitor, "run_summary_command", return_value=llm_summary) as summarize:
            event = monitor.build_notification_event("Damnang2", item, timeline_payload(item), config)

        payload = summarize.call_args.args[1]
        self.assertIn("Holy", payload["text"])
        self.assertIn("引用推文 David (@dayonefoundry)", payload["text"])
        self.assertIn("RAM upgrade cost went up 100%", payload["text"])
        self.assertEqual(
            event["summary"],
            "[原文英文] Holy…..\n\n引用: David 指出，RAM 升级费从 +$800 到 +$1600，涨幅达 100%。",
        )
        self.assertEqual(event["meta"]["summary_source"], "llm")
        self.assertEqual(event["meta"]["original_language"], "en")

    def test_notification_event_includes_topic_when_configured(self):
        item = tweet("305")
        config = {"topics": [{"name": "AI", "users": ["karpathy"]}]}

        event = monitor.build_notification_event("karpathy", item, timeline_payload(item), config)

        self.assertEqual(event["meta"]["topic"], "AI")
        self.assertEqual(event["targets"], ["feishu"])

    def test_notification_event_includes_author_tags_from_kol_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            kol_root = Path(tmp) / "kol"
            profile_dir = kol_root / "aleabitoreddit" / "wiki"
            profile_dir.mkdir(parents=True)
            (kol_root / "_cross").mkdir()
            (kol_root / "_cross" / "_registry.md").write_text(
                """
## @aleabitoreddit

- handle: `aleabitoreddit`
- path: `vault/kol/aleabitoreddit/`
""",
                encoding="utf-8",
            )
            (profile_dir / "profile.json").write_text(
                json.dumps(
                    {
                        "display_tags": [
                            "CPO",
                            "小盘chokepoint",
                            "散户优先",
                            "多余标签",
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            item = tweet("308", author="Serenity", screen_name="aleabitoreddit")
            config = {"settings": {"kol_vault": str(kol_root)}}

            event = monitor.build_notification_event("aleabitoreddit", item, timeline_payload(item), config)

        self.assertEqual(event["meta"]["author_tags"], ["CPO", "小盘chokepoint", "散户优先"])

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
    summary_command: "/mock/summarizer"
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

    def test_history_mode_uses_history_item_and_adds_paid_notification_label(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / ".twitter-monitor"
            runtime.mkdir()
            (runtime / "config.yaml").write_text(
                """
users:
  - username: "tig88411109"
    fetch_mode: "history"
    paid: true

topics:
  - name: "invest"
    users:
      - "tig88411109"

settings:
  interval_minutes: 60
  window_grace_minutes: 0
  max_scan_per_user: 20
  history_max_pages: 2

sinks:
  notification:
    enabled: true
    summary_command: "/mock/summarizer"
""",
                encoding="utf-8",
            )
            paid_tweet = tweet(
                "501",
                text="Subscriber-only long view on MU valuation before earnings.",
                author="Tigris 会讲课教授是好老师",
                screen_name="tig88411109",
            )

            with mock.patch.object(monitor, "now_iso", return_value="2026-06-23T10:00:00Z"):
                with mock.patch.object(
                    monitor,
                    "fetch_history_window",
                    return_value=window_payload(paid_tweet),
                ) as fetch_history:
                    with mock.patch.object(monitor, "fetch_single") as fetch_single:
                        with mock.patch.object(
                            monitor,
                            "run_summary_command",
                            return_value="MU 财报前估值观点摘要。",
                        ) as summarize:
                            with mock.patch.object(monitor, "ingest_tweet_pool"):
                                with mock.patch.object(monitor, "append_notification_event") as append:
                                    report = monitor.run_monitor(runtime)

            fetch_history.assert_called_once_with(
                "tig88411109",
                "2026-06-23T09:00:00Z",
                "2026-06-23T10:00:00Z",
                20,
                0,
                history_max_pages=2,
            )
            fetch_single.assert_not_called()
            event = append.call_args.args[0]
            self.assertEqual(event["title"], "Tigris 会讲课教授是好老师")
            summarize.assert_called_once()
            self.assertEqual(event["summary"], "[付费] MU 财报前估值观点摘要。")
            self.assertEqual(event["meta"]["labels"], ["付费"])
            self.assertEqual(event["meta"]["topic"], "invest")
            self.assertEqual(event["meta"]["summary_source"], "llm")
            user_report = report["users"]["tig88411109"]
            self.assertEqual(user_report["fetch_mode"], "history")
            self.assertEqual(user_report["history_max_pages"], 2)
            self.assertEqual(user_report["notified"], 1)

    def test_paid_notification_does_not_fallback_to_original_text(self):
        item = tweet("502", text="Subscriber-only short original text.")
        config = {
            "users": [{"username": "tig88411109", "paid": True}],
            "sinks": {"notification": {"direct_chars": 300, "summary_chars": 300}},
        }

        event = monitor.build_notification_event("tig88411109", item, timeline_payload(item), config)

        self.assertEqual(event["summary"], "[付费] 摘要生成失败，请点击链接查看原文。")
        self.assertNotIn("Subscriber-only short original text", event["summary"])
        self.assertEqual(event["meta"]["summary_source"], "fallback")

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
