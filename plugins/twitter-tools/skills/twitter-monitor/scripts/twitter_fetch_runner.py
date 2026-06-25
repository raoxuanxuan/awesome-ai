#!/usr/bin/env python3
"""Resolve and call the installed twitter-fetch runner."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Iterable, Mapping


ENV_BIN = "TWITTER_FETCH_BIN"
ENV_TIMEOUT = "TWITTER_MONITOR_FETCH_TIMEOUT_SECONDS"
DEFAULT_FETCH_TIMEOUT_SECONDS = 180
RUNNER_RELATIVE_PATH = Path("skills/twitter-fetch/bin/twitter-fetch")


def is_executable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def iter_plugin_runners(home: Path) -> Iterable[Path]:
    roots = [
        home / ".codex/plugins/cache",
        home / ".claude/plugins/cache",
        home / ".agents/plugins/cache",
    ]
    for root in roots:
        if not root.exists():
            continue
        matches = [
            path for path in root.glob(f"**/{RUNNER_RELATIVE_PATH}") if is_executable(path)
        ]
        matches.sort(key=lambda p: (p.stat().st_mtime, str(p)), reverse=True)
        yield from matches


def iter_source_runners(home: Path) -> Iterable[Path]:
    candidates = [
        home / "ai-workspace/awesome-ai/plugins/twitter-tools/skills/twitter-fetch/bin/twitter-fetch",
        home / ".codex/skills/twitter-fetch/bin/twitter-fetch",
        home / ".claude/skills/twitter-fetch/bin/twitter-fetch",
        home / ".agents/skills/twitter-fetch/bin/twitter-fetch",
    ]
    for candidate in candidates:
        if is_executable(candidate):
            yield candidate


def resolve_twitter_fetch_bin(
    env: Mapping[str, str] | None = None,
    path: str | None = None,
    home: Path | None = None,
) -> Path:
    env = env if env is not None else os.environ
    path = path if path is not None else env.get("PATH", "")
    home = home if home is not None else Path.home()

    override = env.get(ENV_BIN)
    if override:
        override_path = Path(override).expanduser()
        if is_executable(override_path):
            return override_path
        raise RuntimeError(f"{ENV_BIN} is set but not executable: {override_path}")

    from_path = shutil.which("twitter-fetch", path=path)
    if from_path:
        return Path(from_path)

    for runner in iter_plugin_runners(home):
        return runner

    for runner in iter_source_runners(home):
        return runner

    raise RuntimeError(
        "twitter-fetch runner not found. Install twitter-tools, "
        f"or set {ENV_BIN}=/absolute/path/to/bin/twitter-fetch."
    )


def fetch_timeout_seconds(env: Mapping[str, str] | None = None) -> int:
    env = env if env is not None else os.environ
    raw = env.get(ENV_TIMEOUT)
    if raw is None or raw == "":
        return DEFAULT_FETCH_TIMEOUT_SECONDS
    try:
        timeout = int(raw)
    except ValueError:
        return DEFAULT_FETCH_TIMEOUT_SECONDS
    return max(timeout, 1)


def run_twitter_fetch(args: list[str]) -> dict:
    runner = resolve_twitter_fetch_bin()
    timeout = fetch_timeout_seconds()
    try:
        completed = subprocess.run(
            [str(runner), *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        command = " ".join(str(part) for part in args)
        raise RuntimeError(f"twitter-fetch timed out after {timeout}s: {command}") from exc
    if completed.returncode != 0:
        raise RuntimeError(
            "twitter-fetch failed "
            f"(exit {completed.returncode}): {completed.stderr.strip() or completed.stdout.strip()}"
        )
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"twitter-fetch returned non-JSON output: {exc}") from exc
