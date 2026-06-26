import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest import mock


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]


def load_module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


append = load_module("append")
dispatch = load_module("dispatch")
watcher = load_module("watcher")


class NotificationCenterTests(unittest.TestCase):
    def test_append_uses_dedupe_key_and_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / ".notification-center"
            now = datetime(2026, 6, 24, 9, 0, tzinfo=timezone(timedelta(hours=8)))
            entry = append.build_entry(
                {
                    "source": "twitter-monitor",
                    "level": "alert",
                    "title": "New tweet",
                    "summary": "Useful content",
                    "dedupe_key": "tweet:123",
                    "links": ["https://x.com/u/status/123", "tweet=https://x.com/u/status/123"],
                    "meta": {"tweet_id": "123"},
                },
                now=now,
            )

            self.assertTrue(append.append_entry(runtime, entry))
            self.assertFalse(append.append_entry(runtime, entry))

            rows = [
                json.loads(line)
                for line in (runtime / "2026-06-24.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["dedupe_key"], "tweet:123")
            self.assertEqual(
                rows[0]["links"],
                [
                    {"label": "https://x.com/u/status/123", "url": "https://x.com/u/status/123"},
                    {"label": "tweet", "url": "https://x.com/u/status/123"},
                ],
            )
            self.assertEqual(rows[0]["targets"], ["feishu"])

    def test_dispatch_pushes_alert_outside_quiet_and_marks_delivered(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / ".notification-center"
            now = datetime(2026, 6, 24, 10, 0, tzinfo=timezone(timedelta(hours=8)))
            entry = append.build_entry(
                {"source": "test", "level": "alert", "title": "A", "dedupe_key": "a"},
                now=now,
            )
            append.append_entry(runtime, entry)

            with mock.patch.object(dispatch, "post_feishu", return_value={"code": 0}) as post:
                result = dispatch.dispatch(runtime, {"webhook": "w", "secret": "s"}, now=now)

            self.assertTrue(result["ok"])
            self.assertEqual(result["pushed"], 1)
            self.assertEqual(post.call_count, 1)
            self.assertTrue((runtime / ".delivered" / entry["id"]).exists())

    def test_dispatch_skips_when_another_dispatcher_holds_the_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / ".notification-center"
            now = datetime(2026, 6, 24, 10, 0, tzinfo=timezone(timedelta(hours=8)))
            entry = append.build_entry(
                {"source": "test", "level": "alert", "title": "A", "dedupe_key": "a"},
                now=now,
            )
            append.append_entry(runtime, entry)

            with (
                mock.patch.object(dispatch.fcntl, "flock", side_effect=BlockingIOError),
                mock.patch.object(dispatch, "post_feishu", return_value={"code": 0}) as post,
            ):
                result = dispatch.dispatch(runtime, {"webhook": "w", "secret": "s"}, now=now)

            self.assertTrue(result["ok"])
            self.assertTrue(result["locked"])
            self.assertEqual(result["pending"], 0)
            self.assertEqual(result["pushed"], 0)
            self.assertEqual(post.call_count, 0)

    def test_dispatch_routes_topics_to_configured_feishu_bots(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / ".notification-center"
            now = datetime(2026, 6, 24, 10, 0, tzinfo=timezone(timedelta(hours=8)))
            ai = append.build_entry(
                {
                    "source": "twitter-monitor",
                    "level": "alert",
                    "title": "AI",
                    "dedupe_key": "tweet:ai",
                    "meta": {"topic": "AI"},
                },
                now=now,
            )
            claude = append.build_entry(
                {
                    "source": "twitter-monitor",
                    "level": "alert",
                    "title": "Claude",
                    "dedupe_key": "tweet:claude",
                    "meta": {"topic": "ClaudeCode"},
                },
                now=now,
            )
            invest = append.build_entry(
                {
                    "source": "twitter-monitor",
                    "level": "alert",
                    "title": "Invest",
                    "dedupe_key": "tweet:invest",
                    "meta": {"topic": "invest"},
                },
                now=now,
            )
            append.append_entry(runtime, ai)
            append.append_entry(runtime, claude)
            append.append_entry(runtime, invest)
            cfg = dispatch.normalize_config(
                {
                    "default": "general",
                    "bots": {
                        "general": {"webhook": "w-general", "secret": "s-general"},
                        "tech": {"webhook": "w-tech", "secret": "s-tech", "topics": ["AI", "ClaudeCode"]},
                        "invest": {"webhook": "w-invest", "secret": "s-invest", "topics": ["invest"]},
                    },
                }
            )

            with mock.patch.object(dispatch, "post_feishu", return_value={"code": 0}) as post:
                result = dispatch.dispatch(runtime, cfg, now=now)

            self.assertTrue(result["ok"])
            self.assertEqual(result["pushed"], 3)
            self.assertEqual([call.args[0] for call in post.call_args_list], ["w-tech", "w-tech", "w-invest"])
            self.assertTrue((runtime / ".delivered" / dispatch.delivered_entry_id(ai["id"], "feishu:tech")).exists())
            self.assertTrue((runtime / ".delivered" / dispatch.delivered_entry_id(invest["id"], "feishu:invest")).exists())

    def test_dispatch_can_route_one_topic_to_multiple_feishu_bots(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / ".notification-center"
            now = datetime(2026, 6, 24, 10, 0, tzinfo=timezone(timedelta(hours=8)))
            entry = append.build_entry(
                {
                    "source": "twitter-monitor",
                    "level": "alert",
                    "title": "AI",
                    "dedupe_key": "tweet:ai",
                    "meta": {"topic": "AI"},
                },
                now=now,
            )
            append.append_entry(runtime, entry)
            cfg = dispatch.normalize_config(
                {
                    "default": "general",
                    "bots": {
                        "general": {"webhook": "w-general", "secret": "s-general"},
                        "ai": {"webhook": "w-ai", "secret": "s-ai", "topics": ["AI"]},
                        "archive": {"webhook": "w-archive", "secret": "s-archive", "topics": ["AI"]},
                    },
                }
            )

            with mock.patch.object(dispatch, "post_feishu", return_value={"code": 0}) as post:
                result = dispatch.dispatch(runtime, cfg, now=now)

            self.assertTrue(result["ok"])
            self.assertEqual(result["pushed"], 2)
            self.assertEqual([call.args[0] for call in post.call_args_list], ["w-ai", "w-archive"])
            self.assertTrue((runtime / ".delivered" / dispatch.delivered_entry_id(entry["id"], "feishu:ai")).exists())
            self.assertTrue((runtime / ".delivered" / dispatch.delivered_entry_id(entry["id"], "feishu:archive")).exists())

    def test_dispatch_topics_map_can_route_one_topic_to_multiple_named_bots(self):
        cfg = dispatch.normalize_config(
            {
                "default": "general",
                "bots": {
                    "general": {"webhook": "w-general", "secret": "s-general"},
                    "ai": {"webhook": "w-ai", "secret": "s-ai"},
                    "archive": {"webhook": "w-archive", "secret": "s-archive"},
                },
                "topics": {"AI": ["ai", "archive"]},
            }
        )

        routes = dispatch.feishu_routes({"targets": ["feishu"], "meta": {"topic": "AI"}}, cfg)

        self.assertEqual([target for target, _bot in routes], ["feishu:ai", "feishu:archive"])

    def test_dispatch_falls_back_to_default_bot_for_unmatched_topic(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / ".notification-center"
            now = datetime(2026, 6, 24, 10, 0, tzinfo=timezone(timedelta(hours=8)))
            entry = append.build_entry(
                {
                    "source": "twitter-monitor",
                    "level": "alert",
                    "title": "General",
                    "dedupe_key": "tweet:general",
                    "meta": {"topic": "unmatched"},
                },
                now=now,
            )
            append.append_entry(runtime, entry)
            cfg = dispatch.normalize_config(
                {
                    "default": {"webhook": "w-default", "secret": "s-default"},
                    "bots": {
                        "tech": {"webhook": "w-tech", "secret": "s-tech", "topics": ["AI"]},
                    },
                }
            )

            with mock.patch.object(dispatch, "post_feishu", return_value={"code": 0}) as post:
                result = dispatch.dispatch(runtime, cfg, now=now)

            self.assertTrue(result["ok"])
            self.assertEqual(result["pushed"], 1)
            self.assertEqual(post.call_args.args[0], "w-default")
            self.assertTrue((runtime / ".delivered" / dispatch.delivered_entry_id(entry["id"], "feishu:default")).exists())

    def test_dispatch_defers_alert_during_quiet_but_sends_critical(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / ".notification-center"
            now = datetime(2026, 6, 24, 23, 30, tzinfo=timezone(timedelta(hours=8)))
            alert = append.build_entry(
                {"source": "test", "level": "alert", "title": "A", "dedupe_key": "a"},
                now=now,
            )
            critical = append.build_entry(
                {"source": "test", "level": "critical", "title": "C", "dedupe_key": "c"},
                now=now,
            )
            append.append_entry(runtime, alert)
            append.append_entry(runtime, critical)

            with mock.patch.object(dispatch, "post_feishu", return_value={"code": 0}) as post:
                result = dispatch.dispatch(runtime, {"webhook": "w", "secret": "s"}, now=now)

            self.assertTrue(result["quiet"])
            self.assertEqual(result["pending"], 1)
            self.assertEqual(result["pushed"], 1)
            self.assertEqual(post.call_count, 1)
            self.assertFalse((runtime / ".delivered" / alert["id"]).exists())
            self.assertTrue((runtime / ".delivered" / critical["id"]).exists())

    def test_build_card_can_hide_source_prefix_from_title(self):
        entry = append.build_entry(
            {
                "source": "twitter-monitor",
                "level": "alert",
                "title": "Andrej Karpathy",
                "summary": "Useful content",
                "dedupe_key": "tweet:123",
                "meta": {"display": {"hide_source_prefix": True}},
            },
            now=datetime(2026, 6, 24, 10, 0, tzinfo=timezone(timedelta(hours=8))),
        )

        card = dispatch.build_card(entry)

        self.assertEqual(card["card"]["header"]["title"]["content"], "Andrej Karpathy")

    def test_build_card_shows_source_prefix_by_default(self):
        entry = append.build_entry(
            {
                "source": "twitter-monitor",
                "level": "alert",
                "title": "Andrej Karpathy",
                "summary": "Useful content",
                "dedupe_key": "tweet:123",
            },
            now=datetime(2026, 6, 24, 10, 0, tzinfo=timezone(timedelta(hours=8))),
        )

        card = dispatch.build_card(entry)

        self.assertEqual(
            card["card"]["header"]["title"]["content"],
            "[twitter-monitor] Andrej Karpathy",
        )

    def test_build_card_can_hide_visible_level(self):
        entry = append.build_entry(
            {
                "source": "twitter-monitor",
                "level": "alert",
                "title": "Andrej Karpathy",
                "summary": "Useful content",
                "dedupe_key": "tweet:123",
                "meta": {"display": {"hide_level": True}},
            },
            now=datetime(2026, 6, 24, 10, 0, tzinfo=timezone(timedelta(hours=8))),
        )

        card = dispatch.build_card(entry)
        body = card["card"]["elements"][0]["content"]

        self.assertIn("<font color=grey>10:00</font>", body)
        self.assertNotIn("alert", body)

    def test_build_card_can_hide_footer(self):
        entry = append.build_entry(
            {
                "source": "twitter-monitor",
                "level": "alert",
                "title": "Damnang2",
                "summary": "Useful content",
                "dedupe_key": "tweet:123",
                "meta": {"display": {"hide_footer": True}},
            },
            now=datetime(2026, 6, 24, 10, 0, tzinfo=timezone(timedelta(hours=8))),
        )

        card = dispatch.build_card(entry)
        body = card["card"]["elements"][0]["content"]

        self.assertEqual(body, "Useful content")
        self.assertNotIn("10:00", body)
        self.assertNotIn("alert", body)

    def test_watcher_per_file_appends_to_notification_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = root / ".notification-center"
            source_dir = root / "source"
            source_dir.mkdir()
            article = source_dir / "note.md"
            article.write_text("---\ntitle: Test Note\nsource: https://example.com\n---\n\n## 摘要\n\nhello world\n", encoding="utf-8")
            config = root / "watch.json"
            config.write_text(
                json.dumps(
                    {
                        "watchers": [
                            {
                                "source": "notes",
                                "glob": str(source_dir / "*.md"),
                                "level": "alert",
                                "mode": "per-file",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            result = watcher.run_watchers(runtime, config)

            self.assertTrue(result["ok"])
            self.assertEqual(result["appended"], 1)
            queue_files = list(runtime.glob("20*.jsonl"))
            self.assertEqual(len(queue_files), 1)
            row = json.loads(queue_files[0].read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(row["source"], "notes")
            self.assertEqual(row["links"], [{"label": "source", "url": "https://example.com"}])
            self.assertTrue((runtime / ".watermarks.json").exists())


if __name__ == "__main__":
    unittest.main()
