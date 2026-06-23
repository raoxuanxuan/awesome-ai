from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from getpass import getpass
from pathlib import Path


def runtime_dir() -> Path:
    override = os.environ.get("TWITTER_FETCH_RUNTIME")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".twitter-fetch"


def cookie_path() -> Path:
    override = os.environ.get("TWITTER_FETCH_COOKIES")
    if override:
        return Path(override).expanduser()
    return runtime_dir() / ".cookies.json"


def ensure_runtime(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    runtime = path.parent
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


def validate_cookie_value(name: str, value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{name} is empty")
    if cleaned == "从浏览器复制":
        raise ValueError(f"{name} still contains placeholder text")
    if any(ch.isspace() for ch in cleaned):
        raise ValueError(f"{name} contains whitespace")
    return cleaned


def read_json_stdin() -> dict[str, str]:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        raise ValueError(f"stdin is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("stdin JSON must be an object")
    return {
        "auth_token": str(payload.get("auth_token", "")),
        "ct0": str(payload.get("ct0", "")),
    }


def write_cookies(path: Path, auth_token: str, ct0: str) -> None:
    ensure_runtime(path)
    auth_token = validate_cookie_value("auth_token", auth_token)
    ct0 = validate_cookie_value("ct0", ct0)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps({"auth_token": auth_token, "ct0": ct0}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    try:
        tmp.chmod(0o600)
    except OSError:
        pass
    tmp.replace(path)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Save X/Twitter auth_token and ct0 cookies without printing them."
    )
    parser.add_argument("--stdin-json", action="store_true")
    parser.add_argument("--prompt", action="store_true")
    parser.add_argument("--output", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    path = Path(args.output).expanduser() if args.output else cookie_path()
    auth_token = None
    ct0 = None
    if args.stdin_json:
        values = read_json_stdin()
        auth_token = values["auth_token"]
        ct0 = values["ct0"]
    elif args.prompt:
        auth_token = getpass("auth_token: ")
        ct0 = getpass("ct0: ")
    if auth_token is None or ct0 is None:
        raise SystemExit("provide --stdin-json or --prompt")
    write_cookies(path, auth_token, ct0)
    mode = stat.S_IMODE(path.stat().st_mode)
    print(
        json.dumps(
            {
                "ok": True,
                "path": str(path),
                "mode": oct(mode),
                "message": "cookies saved",
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
