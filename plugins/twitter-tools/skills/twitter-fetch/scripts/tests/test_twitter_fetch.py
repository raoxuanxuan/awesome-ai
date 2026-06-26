import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT.parent
RUNNER = SKILL_ROOT / "bin/twitter-fetch"
BOOTSTRAP = SKILL_ROOT / "scripts/bootstrap.sh"

sys.path.insert(0, str(ROOT))

from twitter_fetch import cli, models, providers  # noqa: E402
import save_cookies  # noqa: E402


class TwitterFetchTests(unittest.TestCase):
    def test_parse_tweet_url_accepts_x_and_twitter_domains(self):
        parsed = models.parse_tweet_url("https://x.com/sama/status/1234567890")
        self.assertEqual(parsed, ("sama", "1234567890"))

        parsed = models.parse_tweet_url("https://twitter.com/i/web/status/42")
        self.assertEqual(parsed, ("", "42"))

    def test_parse_tweet_url_rejects_non_twitter_urls(self):
        with self.assertRaisesRegex(ValueError, "Cannot parse tweet URL"):
            models.parse_tweet_url("https://example.com/sama/status/123")

    def test_fxtwitter_response_is_normalized(self):
        raw = {
            "code": 200,
            "tweet": {
                "id": "123",
                "url": "https://x.com/sama/status/123",
                "text": "hello world",
                "author": {"name": "Sam", "screen_name": "sama"},
                "created_at": "Mon Jan 01 12:00:00 +0000 2026",
                "likes": 10,
                "retweets": 2,
                "bookmarks": 3,
                "views": 100,
                "replies": 4,
                "lang": "en",
                "quote": {
                    "text": "quoted",
                    "author": {"name": "Q", "screen_name": "quote"},
                    "likes": 1,
                    "retweets": 0,
                    "views": 9,
                },
                "article": {
                    "title": "Long note",
                    "preview_text": "preview",
                    "created_at": "2026-01-01",
                    "content": {
                        "blocks": [
                            {"text": "first paragraph"},
                            {"text": "second paragraph"},
                        ]
                    },
                },
                "media": {
                    "all": [
                        {
                            "type": "photo",
                            "url": "https://pbs.twimg.com/a.jpg",
                            "width": 1200,
                            "height": 800,
                        }
                    ]
                },
            },
        }

        item = providers.normalize_fxtwitter_tweet(
            raw,
            source_url="https://x.com/sama/status/123",
            username="sama",
            tweet_id="123",
        )

        self.assertEqual(item["id"], "123")
        self.assertEqual(item["screen_name"], "sama")
        self.assertEqual(item["full_text"], "hello world")
        self.assertIs(item["is_article"], True)
        self.assertEqual(
            item["article"]["full_text"], "first paragraph\n\nsecond paragraph"
        )
        self.assertEqual(item["media"]["images"][0]["url"], "https://pbs.twimg.com/a.jpg")
        self.assertEqual(
            item["stats"],
            {
                "likes": 10,
                "retweets": 2,
                "bookmarks": 3,
                "views": 100,
                "replies": 4,
                "quotes": 0,
            },
        )
        self.assertEqual(item["quote"]["screen_name"], "quote")

    def test_syndication_entry_is_normalized(self):
        entry = {
            "content": {
                "tweet": {
                    "id_str": "456",
                    "full_text": "thread part",
                    "lang": "en",
                    "conversation_id_str": "123",
                    "favorite_count": 7,
                    "retweet_count": 1,
                    "created_at": "Mon Jan 01 12:00:00 +0000 2026",
                    "user": {"name": "Sam", "screen_name": "sama"},
                    "entities": {"media": [{"id": 1}]},
                }
            }
        }

        item = providers.normalize_syndication_entry(entry)

        self.assertEqual(item["id"], "456")
        self.assertEqual(item["url"], "https://x.com/sama/status/456")
        self.assertEqual(item["conversation_id"], "123")
        self.assertIs(item["is_thread_part"], True)
        self.assertEqual(item["media_count"], 1)
        self.assertEqual(item["stats"]["likes"], 7)

    def test_graphql_tweet_is_normalized_to_standard_item(self):
        raw = {
            "rest_id": "789",
            "legacy": {
                "id_str": "789",
                "full_text": "deep history tweet",
                "lang": "en",
                "created_at": "Mon Jan 01 12:00:00 +0000 2026",
                "conversation_id_str": "700",
                "in_reply_to_status_id_str": "701",
                "favorite_count": 11,
                "retweet_count": 3,
                "reply_count": 2,
                "quote_count": 1,
                "is_quote_status": True,
                "entities": {"media": [{"id": 1}]},
            },
            "views": {"count": "1234"},
            "core": {
                "user_results": {
                    "result": {
                        "core": {"name": "Sam", "screen_name": "sama"},
                    }
                }
            },
        }

        item = providers.normalize_graphql_tweet(raw, "sama")

        self.assertEqual(item["id"], "789")
        self.assertEqual(item["url"], "https://x.com/sama/status/789")
        self.assertEqual(item["full_text"], "deep history tweet")
        self.assertIs(item["is_reply"], True)
        self.assertEqual(item["in_reply_to"], "701")
        self.assertIs(item["is_thread_part"], True)
        self.assertIs(item["is_quote"], True)
        self.assertEqual(item["stats"]["likes"], 11)
        self.assertEqual(item["stats"]["views"], 1234)
        self.assertEqual(item["media_count"], 1)

    def test_graphql_history_payload_extracts_tweets_and_bottom_cursor(self):
        payload = {
            "data": {
                "user": {
                    "result": {
                        "timeline_v2": {
                            "timeline": {
                                "instructions": [
                                    {
                                        "entries": [
                                            {
                                                "entryId": "tweet-789",
                                                "content": {
                                                    "itemContent": {
                                                        "tweet_results": {
                                                            "result": {
                                                                "rest_id": "789",
                                                                "legacy": {
                                                                    "id_str": "789",
                                                                    "full_text": "tweet",
                                                                    "created_at": "Mon Jan 01 12:00:00 +0000 2026",
                                                                    "conversation_id_str": "789",
                                                                },
                                                                "core": {
                                                                    "user_results": {
                                                                        "result": {
                                                                            "core": {
                                                                                "name": "Sam",
                                                                                "screen_name": "sama",
                                                                            }
                                                                        }
                                                                    }
                                                                },
                                                            }
                                                        }
                                                    }
                                                },
                                            },
                                            {
                                                "entryId": "cursor-bottom-1",
                                                "content": {"value": "CURSOR"},
                                            },
                                        ]
                                    }
                                ]
                            }
                        }
                    }
                }
            }
        }

        items, cursor = providers.extract_graphql_history_page(payload, "sama")

        self.assertEqual(cursor, "CURSOR")
        self.assertEqual([item["id"] for item in items], ["789"])
        self.assertEqual(items[0]["stats"]["likes"], 0)

    def test_graphql_get_can_omit_transaction_header(self):
        class FakeResponse:
            status_code = 200
            headers = {}

            def raise_for_status(self):
                return None

            def json(self):
                return {"ok": True}

        class FakeClient:
            def __init__(self):
                self.headers_seen = None

            def get(self, url, params=None, headers=None, timeout=None):
                self.headers_seen = headers
                return FakeResponse()

        client = FakeClient()
        payload = providers._graphql_get(
            client,
            None,
            {"UserByScreenName": "HASH"},
            {"auth_token": "a", "ct0": "b"},
            "UserByScreenName",
            {"screen_name": "sama"},
            {},
        )

        self.assertEqual(payload, {"ok": True})
        self.assertNotIn("x-client-transaction-id", client.headers_seen)

    def test_nitter_replies_snapshot_is_normalized_to_standard_items(self):
        snapshot = """
- link [e1]:
  - /url: /alice/status/123#m
- link "Alice":
- link "@alice":
- link "2h":
- text: Replying to
- link "@sama":
- text: thoughtful reply  1  2  3
- link [e2]:
  - /url: /pic/orig/media%2Fabc.jpg
- link "https://example.com":
  - /url: https://example.com
"""

        items = providers.parse_nitter_replies_snapshot(
            snapshot,
            original_author="sama",
            conversation_id="100",
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], "123")
        self.assertEqual(items[0]["url"], "https://x.com/alice/status/123")
        self.assertEqual(items[0]["author"], "Alice")
        self.assertEqual(items[0]["screen_name"], "alice")
        self.assertEqual(items[0]["full_text"], "thoughtful reply")
        self.assertEqual(items[0]["conversation_id"], "100")
        self.assertIs(items[0]["is_reply"], True)
        self.assertEqual(items[0]["in_reply_to"], "100")
        self.assertEqual(items[0]["stats"]["likes"], 3)
        self.assertEqual(items[0]["stats"]["retweets"], 2)
        self.assertEqual(items[0]["stats"]["replies"], 1)
        self.assertEqual(
            items[0]["media"]["images"][0]["url"],
            "https://pbs.twimg.com/media/abc.jpg",
        )
        self.assertEqual(items[0]["links"], ["https://example.com"])

    def test_fetch_replies_nitter_returns_standard_envelope_from_snapshot(self):
        snapshot = """
- link [e1]:
  - /url: /alice/status/123#m
- link "Alice":
- link "@alice":
- link "2h":
- text: Replying to
- link "@sama":
- text: useful reply
"""

        payload = providers.fetch_replies_nitter(
            "https://x.com/sama/status/100",
            snapshot_fetcher=lambda _url, _session_key, _port: snapshot,
        )

        self.assertIs(payload["ok"], True)
        self.assertEqual(payload["mode"], "replies")
        self.assertEqual(payload["source"], "nitter")
        self.assertEqual(payload["input"]["url"], "https://x.com/sama/status/100")
        self.assertEqual(payload["input"]["conversation_id"], "100")
        self.assertEqual([item["id"] for item in payload["items"]], ["123"])
        self.assertIsNone(payload["error"])

    def test_graphql_search_payload_extracts_conversation_replies_from_any_author(self):
        payload = {
            "data": {
                "search_by_raw_query": {
                    "search_timeline": {
                        "timeline": {
                            "instructions": [
                                {
                                    "entries": [
                                        {
                                            "entryId": "tweet-100",
                                            "content": {
                                                "itemContent": {
                                                    "tweet_results": {
                                                        "result": {
                                                            "rest_id": "100",
                                                            "legacy": {
                                                                "id_str": "100",
                                                                "full_text": "root",
                                                                "conversation_id_str": "100",
                                                                "created_at": "Mon Jan 01 12:00:00 +0000 2026",
                                                            },
                                                            "core": {
                                                                "user_results": {
                                                                    "result": {
                                                                        "core": {
                                                                            "name": "Sam",
                                                                            "screen_name": "sama",
                                                                        }
                                                                    }
                                                                }
                                                            },
                                                        }
                                                    }
                                                }
                                            },
                                        },
                                        {
                                            "entryId": "tweet-123",
                                            "content": {
                                                "itemContent": {
                                                    "tweet_results": {
                                                        "result": {
                                                            "rest_id": "123",
                                                            "legacy": {
                                                                "id_str": "123",
                                                                "full_text": "reply",
                                                                "conversation_id_str": "100",
                                                                "in_reply_to_status_id_str": "100",
                                                                "created_at": "Mon Jan 01 12:01:00 +0000 2026",
                                                            },
                                                            "core": {
                                                                "user_results": {
                                                                    "result": {
                                                                        "core": {
                                                                            "name": "Alice",
                                                                            "screen_name": "alice",
                                                                        }
                                                                    }
                                                                }
                                                            },
                                                        }
                                                    }
                                                }
                                            },
                                        },
                                    ]
                                }
                            ]
                        }
                    }
                }
            }
        }

        items = providers.extract_graphql_search_replies_page(payload, "100")

        self.assertEqual([item["id"] for item in items], ["123"])
        self.assertEqual(items[0]["screen_name"], "alice")
        self.assertEqual(items[0]["conversation_id"], "100")
        self.assertEqual(items[0]["in_reply_to"], "100")

    def test_auto_replies_uses_graphql_first(self):
        payload = providers.fetch_replies(
            "https://x.com/sama/status/100",
            provider="auto",
            provider_funcs={
                "graphql": lambda: models.standard_response(
                    mode="replies",
                    source="graphql",
                    input_value={"url": "https://x.com/sama/status/100"},
                    items=[models.mock_tweet("https://x.com/alice/status/123")],
                ),
                "browseros": lambda: self.fail("browseros should not be called"),
                "camofox_nitter": lambda: self.fail("camofox should not be called"),
                "direct_nitter": lambda: self.fail("direct nitter should not be called"),
            },
        )

        self.assertIs(payload["ok"], True)
        self.assertEqual(payload["source"], "graphql")
        self.assertEqual(payload["meta"]["provider_chain"], ["graphql"])

    def test_auto_replies_falls_back_after_graphql_error(self):
        payload = providers.fetch_replies(
            "https://x.com/sama/status/100",
            provider="auto",
            provider_funcs={
                "graphql": lambda: models.standard_response(
                    mode="replies",
                    source="graphql",
                    input_value={"url": "https://x.com/sama/status/100"},
                    error=models.standard_error(
                        "missing_cookies",
                        "cookies required",
                        provider="runtime",
                    ),
                ),
                "browseros": lambda: models.standard_response(
                    mode="replies",
                    source="browseros",
                    input_value={"url": "https://x.com/sama/status/100"},
                    items=[models.mock_tweet("https://x.com/alice/status/123")],
                ),
            },
        )

        self.assertIs(payload["ok"], True)
        self.assertEqual(payload["source"], "browseros")
        self.assertEqual(payload["meta"]["provider_chain"], ["graphql", "browseros"])
        self.assertEqual(payload["meta"]["provider_errors"][0]["code"], "missing_cookies")

    def test_cli_replies_accepts_provider_and_cookie_file(self):
        with mock.patch("twitter_fetch.cli.providers.fetch_replies") as fetch:
            fetch.return_value = models.standard_response(
                mode="replies",
                source="graphql",
                input_value={"url": "https://x.com/sama/status/100"},
            )
            out = StringIO()
            with redirect_stdout(out):
                rc = cli.main(
                    [
                        "replies",
                        "--url",
                        "https://x.com/sama/status/100",
                        "--provider",
                        "graphql",
                        "--cookie-file",
                        "/tmp/cookies.json",
                    ]
                )

        self.assertEqual(rc, 0)
        fetch.assert_called_once()
        self.assertEqual(fetch.call_args.kwargs["provider"], "graphql")
        self.assertEqual(fetch.call_args.kwargs["cookie_file"], "/tmp/cookies.json")

    def test_cli_mock_single_outputs_standard_json(self):
        out = StringIO()
        with redirect_stdout(out):
            rc = cli.main(["single", "--url", "https://x.com/sama/status/123", "--mock"])
        self.assertEqual(rc, 0)
        payload = json.loads(out.getvalue())
        self.assertIs(payload["ok"], True)
        self.assertEqual(payload["mode"], "single")
        self.assertEqual(payload["source"], "mock")
        self.assertEqual(payload["items"][0]["id"], "123")
        self.assertNotIn("thread", payload["items"][0])

    def test_cli_mock_single_can_include_thread_context(self):
        out = StringIO()
        with redirect_stdout(out):
            rc = cli.main(
                [
                    "single",
                    "--url",
                    "https://x.com/sama/status/123",
                    "--include-thread",
                    "--mock",
                ]
            )
        self.assertEqual(rc, 0)
        payload = json.loads(out.getvalue())
        item = payload["items"][0]
        self.assertEqual(payload["mode"], "single")
        self.assertIn("thread", item)
        self.assertEqual(item["thread"]["source"], "mock")
        self.assertEqual([t["id"] for t in item["thread"]["items"]], ["123", "124"])

    def test_cli_mock_single_context_full_includes_thread_context(self):
        out = StringIO()
        with redirect_stdout(out):
            rc = cli.main(
                [
                    "single",
                    "--url",
                    "https://x.com/sama/status/123",
                    "--context",
                    "full",
                    "--mock",
                ]
            )
        self.assertEqual(rc, 0)
        payload = json.loads(out.getvalue())
        self.assertIn("thread", payload["items"][0])

    def test_cli_mock_history_jsonl_outputs_items_without_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = StringIO()
            with redirect_stdout(out):
                rc = cli.main(
                    [
                        "history",
                        "--user",
                        "sama",
                        "--mock",
                        "--jsonl",
                    ]
                )

            self.assertEqual(rc, 0)
            lines = [json.loads(line) for line in out.getvalue().splitlines()]
            self.assertEqual([line["id"] for line in lines], ["100"])
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_default_cookie_path_prefers_twitter_fetch_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            new_runtime = home / ".twitter-fetch"
            old_runtime = home / "ai-workspace/.twitter-monitor"
            new_runtime.mkdir()
            old_runtime.mkdir(parents=True)
            new_cookie = new_runtime / ".cookies.json"
            old_cookie = old_runtime / ".cookies.json"
            new_cookie.write_text('{"auth_token":"new","ct0":"new"}')
            old_cookie.write_text('{"auth_token":"old","ct0":"old"}')
            original_home = os.environ.get("HOME")
            os.environ["HOME"] = str(home)
            try:
                self.assertEqual(cli.default_cookie_path(), new_cookie)
            finally:
                if original_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = original_home

    def test_default_cookie_path_honors_env_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            cookie = Path(tmp) / "cookies.json"
            cookie.write_text('{"auth_token":"env","ct0":"env"}')
            original = os.environ.get("TWITTER_FETCH_COOKIES")
            os.environ["TWITTER_FETCH_COOKIES"] = str(cookie)
            try:
                self.assertEqual(cli.default_cookie_path(), cookie)
            finally:
                if original is None:
                    os.environ.pop("TWITTER_FETCH_COOKIES", None)
                else:
                    os.environ["TWITTER_FETCH_COOKIES"] = original

    def test_default_cookie_path_does_not_fall_back_to_monitor_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            old_runtime = home / "ai-workspace/.twitter-monitor"
            old_runtime.mkdir(parents=True)
            old_cookie = old_runtime / ".cookies.json"
            old_cookie.write_text('{"auth_token":"old","ct0":"old"}')
            original_home = os.environ.get("HOME")
            os.environ["HOME"] = str(home)
            try:
                self.assertEqual(
                    cli.default_cookie_path(), home / ".twitter-fetch/.cookies.json"
                )
            finally:
                if original_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = original_home

    def test_ensure_runtime_creates_dirs_and_cookie_example(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = os.environ.get("TWITTER_FETCH_RUNTIME")
            os.environ["TWITTER_FETCH_RUNTIME"] = str(Path(tmp) / "runtime")
            try:
                runtime = cli.ensure_runtime()
            finally:
                if original is None:
                    os.environ.pop("TWITTER_FETCH_RUNTIME", None)
                else:
                    os.environ["TWITTER_FETCH_RUNTIME"] = original

            self.assertTrue((runtime / "cache").is_dir())
            self.assertTrue((runtime / "logs").is_dir())
            self.assertTrue((runtime / "tmp").is_dir())
            self.assertTrue((runtime / ".cookies.example.json").exists())

    def test_history_without_cookies_returns_setup_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = StringIO()
            with redirect_stdout(out):
                rc = cli.main(
                    [
                        "history",
                        "--user",
                        "sama",
                        "--cookie-file",
                        str(Path(tmp) / "missing.json"),
                    ]
                )
            payload = json.loads(out.getvalue())
            self.assertEqual(rc, 1)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["error"]["code"], "missing_cookies")
            self.assertIn("TWITTER_FETCH_COOKIES", payload["error"]["message"])

    def test_save_cookies_writes_0600_without_printing_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".twitter-fetch/.cookies.json"
            out = StringIO()
            stdin = StringIO(
                json.dumps(
                    {"auth_token": "auth-token-value", "ct0": "ct0-value"}
                )
            )
            original_stdin = sys.stdin
            sys.stdin = stdin
            with redirect_stdout(out):
                try:
                    rc = save_cookies.main(
                        [
                            "--stdin-json",
                            "--output",
                            str(path),
                        ]
                    )
                finally:
                    sys.stdin = original_stdin
            self.assertEqual(rc, 0)
            saved = json.loads(path.read_text())
            self.assertEqual(saved["auth_token"], "auth-token-value")
            self.assertEqual(saved["ct0"], "ct0-value")
            mode = path.stat().st_mode & 0o777
            self.assertEqual(mode, 0o600)
            self.assertNotIn("auth-token-value", out.getvalue())
            self.assertNotIn("ct0-value", out.getvalue())

    def test_runner_missing_uv_prints_install_guidance_without_installing(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            proc = subprocess.run(
                [
                    "/bin/bash",
                    str(RUNNER),
                    "single",
                    "--url",
                    "https://x.com/sama/status/123",
                    "--mock",
                ],
                capture_output=True,
                text=True,
                env={**os.environ, "PATH": "/bin:/usr/bin", "HOME": str(home)},
            )
            runtime = home / ".twitter-fetch"
            self.assertEqual(proc.returncode, 127)
            self.assertTrue((runtime / "cache").is_dir())
            self.assertTrue((runtime / ".cookies.example.json").exists())
            self.assertIn("twitter-fetch requires uv", proc.stderr)
            self.assertIn("bootstrap.sh --install-uv", proc.stderr)

    def test_runner_uses_runtime_venv_outside_skill_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            proc = subprocess.run(
                [
                    "/bin/bash",
                    str(RUNNER),
                    "history",
                    "--user",
                    "sama",
                    "--mock",
                    "--jsonl",
                ],
                capture_output=True,
                text=True,
                env={**os.environ, "HOME": str(home)},
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue((home / ".twitter-fetch/venv").exists())
            self.assertFalse((SKILL_ROOT / ".venv").exists())

    def test_bootstrap_check_missing_uv_does_not_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                ["/bin/bash", str(BOOTSTRAP), "--check"],
                capture_output=True,
                text=True,
                env={**os.environ, "PATH": tmp},
            )
        self.assertEqual(proc.returncode, 1)
        self.assertIn("uv: missing", proc.stdout)
        self.assertIn("--install-uv", proc.stdout)

    def test_bootstrap_init_runtime_creates_twitter_fetch_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                ["/bin/bash", str(BOOTSTRAP), "--init-runtime"],
                capture_output=True,
                text=True,
                env={**os.environ, "HOME": tmp},
            )
            runtime = Path(tmp) / ".twitter-fetch"
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue((runtime / "cache").is_dir())
            self.assertTrue((runtime / "logs").is_dir())
            self.assertTrue((runtime / "tmp").is_dir())
            self.assertTrue((runtime / ".cookies.example.json").exists())


if __name__ == "__main__":
    unittest.main()
