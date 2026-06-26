#!/usr/bin/env python3
"""Mark notification events or digest days as delivered."""

from __future__ import annotations

import argparse
import os
from pathlib import Path


DEFAULT_RUNTIME = Path.home() / "vault" / ".notification-center"


def runtime_dir() -> Path:
    override = os.environ.get("NOTIFICATION_CENTER_RUNTIME")
    if override:
        return Path(override).expanduser()
    return DEFAULT_RUNTIME


def main() -> int:
    parser = argparse.ArgumentParser(description="Mark notification center entries as delivered")
    parser.add_argument("--runtime", help="Notification center runtime directory")
    parser.add_argument("--id", action="append", default=[])
    parser.add_argument("--digest", help="Mark digest delivered for YYYY-MM-DD")
    args = parser.parse_args()

    runtime = Path(args.runtime).expanduser() if args.runtime else runtime_dir()
    delivered_dir = runtime / ".delivered"
    digest_dir = runtime / ".digest"
    delivered_dir.mkdir(parents=True, exist_ok=True)
    digest_dir.mkdir(parents=True, exist_ok=True)

    for entry_id in args.id:
        (delivered_dir / entry_id).touch()
    if args.digest:
        (digest_dir / args.digest).touch()
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
