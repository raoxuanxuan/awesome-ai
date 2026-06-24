#!/usr/bin/env python3
"""stdin/stdout adapter for running KOL ask/debate prompts with Codex CLI."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one prompt with Codex CLI.")
    parser.add_argument("--codex-bin", default=os.environ.get("KOL_CODEX_BIN", "codex"))
    parser.add_argument("--cd", type=Path, default=Path.cwd(), help="working directory passed to codex exec")
    parser.add_argument("--model", default=os.environ.get("KOL_CODEX_MODEL", ""))
    parser.add_argument("--profile", default=os.environ.get("KOL_CODEX_PROFILE", ""))
    parser.add_argument("--timeout", type=int, default=int(os.environ.get("KOL_RUNNER_TIMEOUT", "1200")))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    prompt = sys.stdin.read()
    cmd = [
        args.codex_bin,
        "exec",
        "--sandbox",
        "read-only",
        "--ask-for-approval",
        "never",
        "--skip-git-repo-check",
        "--ephemeral",
        "--color",
        "never",
        "--cd",
        str(args.cd),
    ]
    if args.model:
        cmd.extend(["--model", args.model])
    if args.profile:
        cmd.extend(["--profile", args.profile])
    cmd.append("-")
    completed = subprocess.run(
        cmd,
        input=prompt,
        text=True,
        capture_output=True,
        timeout=args.timeout,
        check=False,
        cwd=str(args.cd),
    )
    sys.stdout.write(completed.stdout)
    sys.stderr.write(completed.stderr)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
