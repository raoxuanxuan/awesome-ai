#!/usr/bin/env python3
"""Heuristically classify a QMX lyric cleanup case from raw LRC/log text."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


TIME_LINE_RE = re.compile(r"^\[[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,3})?\](.*)$")
META_RE = re.compile(r"^\[([a-zA-Z]+):(.*)\]$")
CREDIT_PREFIXES = {
    "作词", "作曲", "词", "曲", "编曲", "制作人", "和声", "统筹", "项目统筹",
    "艺人统筹", "出品人", "出品", "混音师", "录音师", "词曲来源", "词协力",
    "演唱指导", "OP", "SP",
}


def read_text(args: argparse.Namespace) -> str:
    parts: list[str] = []
    if args.text:
        parts.append(args.text)
    if args.file:
        parts.append(Path(args.file).read_text(encoding="utf-8"))
    if not parts and not sys.stdin.isatty():
        parts.append(sys.stdin.read())
    return "\n".join(parts)


def extract_lrc_lines(text: str) -> tuple[dict[str, str], list[str]]:
    meta: dict[str, str] = {}
    timed: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        meta_match = META_RE.match(line)
        if meta_match:
            meta[meta_match.group(1).lower()] = meta_match.group(2).strip()
            continue
        time_match = TIME_LINE_RE.match(line)
        if time_match:
            content = time_match.group(1).strip()
            if content:
                timed.append(content)
    return meta, timed


def prefix_before_colon(line: str) -> str | None:
    for colon in ("：", ":"):
        if colon in line:
            return line.split(colon, 1)[0].strip()
    return None


def is_credit_line(line: str) -> bool:
    prefix = prefix_before_colon(line)
    return bool(prefix and prefix in CREDIT_PREFIXES)


def is_copyright(line: str) -> bool:
    return "未经" in line and ("许可" in line or "授权" in line) and any(
        word in line for word in ("翻唱", "翻录", "使用")
    )


def classify(text: str, lyric_start_time: int | None) -> dict[str, Any]:
    meta, timed = extract_lrc_lines(text)
    categories: list[str] = []
    evidence: list[str] = []

    ti = meta.get("ti", "")
    ar = meta.get("ar", "")
    if lyric_start_time is not None and lyric_start_time > 0:
        categories.append("start_time_clear_header")
        evidence.append(f"lyric_start_time={lyric_start_time} > 0")
    else:
        categories.append("no_start_time_lrc_to_txt")
        if lyric_start_time is not None:
            evidence.append(f"lyric_start_time={lyric_start_time}")

    if not ti and not ar and timed:
        categories.append("empty_metadata")
        evidence.append("[ti:] and [ar:] are empty or absent")
        if len(timed) >= 2 and is_credit_line(timed[1]):
            categories.append("empty_metadata_title_lead")
            evidence.append(f"first timed line may be title lead: {timed[0]}")

    credit_count = sum(1 for line in timed[:12] if is_credit_line(line))
    if credit_count >= 3:
        categories.append("lead_credit_block")
        evidence.append(f"{credit_count} credit-like lines appear near the top")

    trailing = [line for line in timed[-10:] if is_credit_line(line) or is_copyright(line)]
    if len(trailing) >= 2:
        categories.append("trailing_credit_residue_risk")
        evidence.append(f"{len(trailing)} trailing credit/copyright-like lines found")

    marker_lines = []
    for line in timed:
        prefix = prefix_before_colon(line)
        if prefix and line.endswith(("：", ":")):
            marker_lines.append(line)
    if marker_lines:
        categories.append("live_performer_marker_candidate")
        evidence.append("empty-suffix colon marker candidates: " + ", ".join(marker_lines[:4]))

    colon_risk = []
    for line in timed:
        prefix = prefix_before_colon(line)
        if prefix and not is_credit_line(line) and not line.endswith(("：", ":")):
            if prefix in {"词不达意", "曲终人散", "他说", "旁白", "OS"}:
                colon_risk.append(line)
    if colon_risk:
        categories.append("colon_false_positive_boundary")
        evidence.append("real-lyric colon boundary examples: " + ", ".join(colon_risk[:4]))

    if not timed:
        categories.append("upstream_lrc_missing_or_malformed")
        evidence.append("no timed LRC lines were parsed")

    return {
        "metadata": {"ti": ti, "ar": ar},
        "timed_line_count": len(timed),
        "first_timed_lines": timed[:8],
        "last_timed_lines": timed[-8:],
        "categories": categories,
        "evidence": evidence,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text", help="Raw LRC or log text.")
    parser.add_argument("--file", help="Read raw LRC or log text from file.")
    parser.add_argument("--lyric-start-time", type=int, help="Online lyric_start_time.")
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    args = parser.parse_args()

    result = classify(read_text(args), args.lyric_start_time)
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("**启发式分类**")
        print("- categories: " + ", ".join(result["categories"]))
        print("- timed_line_count: " + str(result["timed_line_count"]))
        for item in result["evidence"]:
            print(f"- evidence: {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
