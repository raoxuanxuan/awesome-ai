#!/usr/bin/env python3
"""stdin/stdout adapter for running KOL ask/debate prompts with Claude Code."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one prompt with Claude Code.")
    parser.add_argument("--claude-bin", default=os.environ.get("KOL_CLAUDE_BIN", "claude"))
    parser.add_argument("--cwd", type=Path, default=Path.cwd(), help="working directory for claude")
    parser.add_argument("--model", default=os.environ.get("KOL_CLAUDE_MODEL", ""))
    parser.add_argument("--timeout", type=int, default=int(os.environ.get("KOL_RUNNER_TIMEOUT", "1200")))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    prompt = sys.stdin.read()
    cmd = [
        args.claude_bin,
        "--print",
        "--input-format",
        "text",
        "--output-format",
        "text",
        "--permission-mode",
        "dontAsk",
        "--no-session-persistence",
        "--tools",
        "",
    ]
    if args.model:
        cmd.extend(["--model", args.model])
    completed = subprocess.run(
        cmd,
        input=prompt,
        text=True,
        capture_output=True,
        timeout=args.timeout,
        check=False,
        cwd=str(args.cwd),
    )
    sys.stdout.write(completed.stdout)
    sys.stderr.write(completed.stderr)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
