#!/usr/bin/env python3
"""Compatibility entrypoint for the read-only KOL health checker."""

from __future__ import annotations

from registry_health import build_report, main

__all__ = ["build_report", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
