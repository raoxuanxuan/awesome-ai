#!/usr/bin/env python3
"""Shared constants and helpers for KOL Tools scripts."""

from __future__ import annotations

import os
from pathlib import Path


DEFAULT_VAULT = Path(os.environ.get("KOL_TOOLS_VAULT", "/Users/saberrao/vault/kol"))


def kol_dir(vault: Path, handle: str) -> Path:
    return vault / handle


def raw_tweets_dir(vault: Path, handle: str) -> Path:
    return kol_dir(vault, handle) / "raw" / "tweets"


def wiki_dir(vault: Path, handle: str) -> Path:
    return kol_dir(vault, handle) / "wiki"
