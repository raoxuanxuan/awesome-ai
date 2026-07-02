from __future__ import annotations

import argparse
import json
import os
import sys
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from . import models, providers


def runtime_dir() -> Path:
    override = os.environ.get("TWITTER_FETCH_RUNTIME")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".twitter-fetch"


def default_cookie_path() -> Path:
    override = os.environ.get("TWITTER_FETCH_COOKIES")
    if override:
        return Path(override).expanduser()
    return runtime_dir() / ".cookies.json"


def ensure_runtime() -> Path:
    runtime = runtime_dir()
    for child in ("cache", "logs", "tmp"):
        (runtime / child).mkdir(parents=True, exist_ok=True)
    example = runtime / ".cookies.example.json"
    if not example.exists():
        example.write_text(
            '{\n  "auth_token": "",\n  "ct0": ""\n}\n',
            encoding="utf-8",
        )
        try:
            example.chmod(0o600)
        except OSError:
            pass
    return runtime


def _cookie_error(cookie_file: str) -> dict | None:
    path = Path(cookie_file).expanduser()
    hint = (
        "Twitter cookies are required for this command. "
        f"Put a JSON cookies file at {path} or set TWITTER_FETCH_COOKIES. "
        'Expected keys: "auth_token" and "ct0".'
    )
    if not path.exists():
        return models.standard_error(
            "missing_cookies",
            hint,
            provider="runtime",
            retryable=False,
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return models.standard_error(
            "invalid_cookies",
            f"{hint} Could not parse JSON: {exc}",
            provider="runtime",
            retryable=False,
        )
    auth_token = data.get("auth_token", "")
    ct0 = data.get("ct0", "")
    if not auth_token or not ct0 or auth_token == "从浏览器复制":
        return models.standard_error(
            "invalid_cookies",
            hint,
            provider="runtime",
            retryable=False,
        )
    return None


def _print(payload: dict, pretty: bool) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2 if pretty else None))


def _print_jsonl(items: list[dict]) -> None:
    for item in items:
        print(json.dumps(item, ensure_ascii=False, separators=(",", ":")))


def _single(args: argparse.Namespace) -> int:
    if args.mock:
        payload = models.standard_response(
            mode="single",
            source="mock",
            input_value={"url": args.url},
            items=[models.mock_tweet(args.url)],
        )
    else:
        payload = providers.fetch_single_fxtwitter(args.url, timeout=args.timeout)
    if payload["ok"] and payload["items"] and _should_include_thread(args):
        thread_payload = _mock_thread_payload(args.url) if args.mock else providers.fetch_thread_syndication(args.url)
        payload["input"]["context"] = args.context
        payload["items"][0]["thread"] = {
            "ok": thread_payload.get("ok", False),
            "source": thread_payload.get("source", ""),
            "items": thread_payload.get("items", []),
            "error": thread_payload.get("error"),
        }
    _print(payload, args.pretty)
    return 0 if payload["ok"] else 1


def _should_include_thread(args: argparse.Namespace) -> bool:
    return bool(args.include_thread or args.context in {"thread", "full"})


def _mock_thread_payload(url: str) -> dict:
    root = models.mock_tweet(url)
    child = {
        **root,
        "id": str(int(root["id"]) + 1),
        "is_thread_part": True,
        "conversation_id": root["id"],
    }
    return models.standard_response(
        mode="thread",
        source="mock",
        input_value={"url": url},
        items=[root, child],
    )


def _timeline(args: argparse.Namespace) -> int:
    if args.mock:
        payload = models.standard_response(
            mode="timeline",
            source="mock",
            input_value={"user": args.user, "limit": args.limit},
            items=models.mock_timeline(args.user)[: args.limit],
        )
    else:
        payload = providers.fetch_timeline_syndication(
            args.user, limit=args.limit, cookie_file=args.cookie_file
        )
    _print(payload, args.pretty)
    return 0 if payload["ok"] else 1


def _thread(args: argparse.Namespace) -> int:
    if args.mock:
        payload = _mock_thread_payload(args.url)
    else:
        payload = providers.fetch_thread_syndication(args.url, limit=args.limit)
    _print(payload, args.pretty)
    return 0 if payload["ok"] else 1


def _replies(args: argparse.Namespace) -> int:
    if args.mock:
        payload = models.standard_response(
            mode="replies",
            source="mock",
            input_value={"url": args.url, "provider": args.provider},
            items=[],
        )
    else:
        payload = providers.fetch_replies(
            args.url,
            provider=args.provider,
            cookie_file=args.cookie_file,
            port=args.port,
            nitter=args.nitter,
            browseros_endpoint=args.browseros_endpoint,
        )
    _print(payload, args.pretty)
    return 0 if payload["ok"] else 1


def _search_input(args: argparse.Namespace) -> dict:
    return {
        "query": args.query,
        "limit": args.limit,
        "mode": args.mode,
        "lang": args.lang,
        "since_time": args.since_time,
        "until_time": args.until_time,
        "exclude_replies": args.exclude_replies,
        "exclude_retweets": args.exclude_retweets,
        "cookie_file": args.cookie_file,
    }


def _search(args: argparse.Namespace) -> int:
    if args.mock:
        payload = models.standard_response(
            mode="search",
            source="mock",
            input_value=_search_input(args),
            items=models.mock_timeline("search")[: args.limit],
            meta={"result_count": min(args.limit, 1), "query": args.query},
        )
        _print(payload, args.pretty)
        return 0
    cookie_error = _cookie_error(args.cookie_file)
    if cookie_error is not None:
        payload = models.standard_response(
            mode="search",
            source="runtime",
            input_value=_search_input(args),
            error=cookie_error,
        )
        _print(payload, args.pretty)
        return 1
    payload = providers.fetch_search_graphql(
        args.query,
        cookie_file=args.cookie_file,
        limit=args.limit,
        mode=args.mode,
        lang=args.lang,
        since_time=args.since_time,
        until_time=args.until_time,
        exclude_replies=args.exclude_replies,
        exclude_retweets=args.exclude_retweets,
    )
    _print(payload, args.pretty)
    return 0 if payload["ok"] else 1


def _history(args: argparse.Namespace) -> int:
    if args.mock:
        payload = models.standard_response(
            mode="history",
            source="mock",
            input_value={
                "user": args.user,
                "months": args.months,
                "incremental": args.incremental,
                "since_id": args.since_id,
                "cursor": args.cursor,
                "max_pages": args.max_pages,
            },
            items=models.mock_timeline(args.user),
            meta={
                "user_id": "mock",
                "page_count": 1,
                "next_cursor": None,
                "newest_id": "100",
                "oldest_id": "100",
                "reached_cutoff": False,
                "reached_since_id": False,
                "exhausted": True,
            },
        )
        _print_jsonl(payload["items"]) if args.jsonl else _print(payload, args.pretty)
        return 0
    cookie_error = _cookie_error(args.cookie_file)
    if cookie_error is not None:
        payload = models.standard_response(
            mode="history",
            source="runtime",
            input_value={
                "user": args.user,
                "months": args.months,
                "incremental": args.incremental,
                "since_id": args.since_id,
                "cursor": args.cursor,
                "max_pages": args.max_pages,
                "cookie_file": args.cookie_file,
            },
            error=cookie_error,
        )
        _print(payload, args.pretty)
        return 1
    since_id = args.since_id
    payload = providers.fetch_history_graphql(
        args.user,
        cookie_file=args.cookie_file,
        months=args.months,
        page_size=args.page_size,
        sleep_s=args.sleep,
        cursor=args.cursor,
        since_id=since_id,
        max_pages=args.max_pages,
    )
    payload["input"]["incremental"] = args.incremental
    _print_jsonl(payload["items"]) if args.jsonl and payload["ok"] else _print(
        payload, args.pretty
    )
    return 0 if payload["ok"] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="twitter_fetch.py",
        description="Fetch and normalize X/Twitter content as standard JSON.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    single = sub.add_parser("single", help="Fetch one tweet or X Article")
    single.add_argument("--url", required=True)
    single.add_argument("--timeout", type=int, default=30)
    single.add_argument(
        "--include-thread",
        action="store_true",
        help="Attach discovered same-author thread context under items[0].thread",
    )
    single.add_argument(
        "--context",
        choices=["single", "thread", "full"],
        default="single",
        help="Context expansion level (default: single)",
    )
    single.add_argument("--pretty", action="store_true")
    single.add_argument("--mock", action="store_true", help=argparse.SUPPRESS)
    single.set_defaults(func=_single)

    timeline = sub.add_parser("timeline", help="Fetch a user's recent timeline")
    timeline.add_argument("--user", required=True)
    timeline.add_argument("--limit", type=int, default=20)
    timeline.add_argument("--cookie-file", default=str(default_cookie_path()))
    timeline.add_argument("--pretty", action="store_true")
    timeline.add_argument("--mock", action="store_true", help=argparse.SUPPRESS)
    timeline.set_defaults(func=_timeline)

    thread = sub.add_parser("thread", help="Discover tweets in a thread")
    thread.add_argument("--url", required=True)
    thread.add_argument("--limit", type=int, default=50)
    thread.add_argument("--pretty", action="store_true")
    thread.add_argument("--mock", action="store_true", help=argparse.SUPPRESS)
    thread.set_defaults(func=_thread)

    replies = sub.add_parser("replies", help="Fetch replies best-effort")
    replies.add_argument("--url", required=True)
    replies.add_argument(
        "--provider",
        choices=["auto", "graphql", "browseros", "camofox_nitter", "direct_nitter"],
        default="auto",
        help="Replies provider chain or explicit provider (default: auto)",
    )
    replies.add_argument("--cookie-file", default=str(default_cookie_path()))
    replies.add_argument("--port", type=int, default=9377)
    replies.add_argument("--nitter", default="nitter.net")
    replies.add_argument("--browseros-endpoint", default="http://127.0.0.1:9000/mcp")
    replies.add_argument("--pretty", action="store_true")
    replies.add_argument("--mock", action="store_true", help=argparse.SUPPRESS)
    replies.set_defaults(func=_replies)

    search = sub.add_parser("search", help="Search X/Twitter by keyword query")
    search.add_argument("--query", required=True)
    search.add_argument("--limit", type=int, default=20)
    search.add_argument(
        "--mode",
        choices=["live", "top"],
        default="live",
        help="Search ranking mode: live maps to X Latest, top maps to X Top",
    )
    search.add_argument("--lang", default=None)
    search.add_argument("--since-time", default=None)
    search.add_argument("--until-time", default=None)
    search.add_argument("--exclude-replies", action="store_true")
    search.add_argument("--exclude-retweets", action="store_true")
    search.add_argument("--cookie-file", default=str(default_cookie_path()))
    search.add_argument("--pretty", action="store_true")
    search.add_argument("--mock", action="store_true", help=argparse.SUPPRESS)
    search.set_defaults(func=_search)

    history = sub.add_parser("history", help="Fetch tweets/replies history")
    history.add_argument("--user", required=True)
    history.add_argument("--months", type=int, default=6)
    history.add_argument("--incremental", action="store_true")
    history.add_argument("--since-id", default=None)
    history.add_argument("--cursor", default=None)
    history.add_argument("--page-size", type=int, default=40)
    history.add_argument("--max-pages", type=int, default=0)
    history.add_argument("--sleep", type=float, default=1.5)
    history.add_argument("--cookie-file", default=str(default_cookie_path()))
    history.add_argument("--jsonl", action="store_true")
    history.add_argument("--pretty", action="store_true")
    history.add_argument("--mock", action="store_true", help=argparse.SUPPRESS)
    history.set_defaults(func=_history)
    return parser


def main(argv: list[str] | None = None) -> int:
    ensure_runtime()
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


def run_for_payload(argv: list[str]) -> dict:
    """Run a CLI command path and return the JSON payload it prints."""
    out = StringIO()
    with redirect_stdout(out):
        rc = main(argv)
    text = out.getvalue()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        return models.standard_response(
            mode=argv[0] if argv else "unknown",
            source="cli",
            input_value={"argv": argv},
            error=models.standard_error(
                "bad_cli_output",
                f"CLI returned rc={rc} but did not emit JSON: {exc}",
                provider="cli",
            ),
        )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
