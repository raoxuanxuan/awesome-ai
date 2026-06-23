#!/usr/bin/env python3
"""Compatibility entrypoint for the kol-index skill script."""

from __future__ import annotations

import runpy
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "kol-index"
    / "scripts"
    / "kol_index.py"
)


if __name__ == "__main__":
    runpy.run_path(str(SCRIPT), run_name="__main__")
