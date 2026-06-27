#!/usr/bin/env python3
"""Build RMS/CLS log query parameters for QMX lyric diagnosis."""

from __future__ import annotations

import argparse
import json
from typing import Any


CACHED_TERMS = [
    "KMR歌词起唱点信息",
    "开始清洗第三方歌词",
    "媒资没有返回起唱点",
    "lrc内容",
    "第三方歌词清洗结果",
]


def quote_term(term: str) -> str:
    escaped = term.replace('"', r'\"')
    return f'"{escaped}"'


def build_query(args: argparse.Namespace) -> str:
    if args.trace_id:
        return f'traceID: "{args.trace_id}"'
    if not args.mixsongid:
        raise ValueError("mixsongid or trace-id is required")
    terms = args.term or CACHED_TERMS
    joined_terms = " OR ".join(quote_term(term) for term in terms)
    if args.mixsongid_query_mode == "field":
        field = args.mixsongid_field
        return f"{field}: {args.mixsongid} AND ({joined_terms})"
    return f"{quote_term(args.mixsongid)} AND ({joined_terms})"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mixsongid", help="QMX/Vemus mixsongid.")
    parser.add_argument("--trace-id", help="Trace ID. Overrides mixsongid query.")
    parser.add_argument("--term", action="append", help="Log message term. Repeatable.")
    parser.add_argument(
        "--mixsongid-query-mode",
        choices=["text", "field"],
        default="text",
        help="Use text search by default because CLS mixsongid fields may be unindexed.",
    )
    parser.add_argument("--mixsongid-field", default="mixsongid", help="Log field name when --mixsongid-query-mode=field.")
    parser.add_argument("--rms-id", default="11367", help="RMS project ID.")
    parser.add_argument("--project", default="qmx_user_asset", help="Project name.")
    parser.add_argument("--region", default="ap-guangzhou", help="CLS region.")
    parser.add_argument("--limit", type=int, default=100, help="Initial page size.")
    parser.add_argument("--start-time", help="YYYY-MM-DD HH:mm:ss")
    parser.add_argument("--end-time", help="YYYY-MM-DD HH:mm:ss")
    parser.add_argument("--format", choices=["json", "markdown"], default="json")
    args = parser.parse_args()

    query = build_query(args)
    params: dict[str, Any] = {
        "rmsId": args.rms_id,
        "project": args.project,
        "region": args.region,
        "queryStr": query,
        "limit": args.limit,
        "startTime": args.start_time,
        "endTime": args.end_time,
        "mixsongidQueryMode": args.mixsongid_query_mode if args.mixsongid else None,
        "termSource": "custom" if args.term else "cached_fast_path",
        "terms": args.term or CACHED_TERMS,
    }

    if args.format == "json":
        print(json.dumps(params, ensure_ascii=False, indent=2))
    else:
        print("**RMS/CLS 查询参数**")
        for key, value in params.items():
            if value is not None:
                print(f"- {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
