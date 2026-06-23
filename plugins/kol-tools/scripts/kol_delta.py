#!/usr/bin/env python3
"""Compute and commit KOL incremental ingest boundaries.

Compute mode is safe for automation: it refreshes no LLM-written wiki content and
does not move the ingest watermark unless bootstrapping an existing archive.
Commit mode is the final step after a successful manual/agent integration.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kol_common import DEFAULT_VAULT, wiki_dir


DEFAULT_CAP = 120


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def meta_path(vault: Path, handle: str) -> Path:
    return wiki_dir(vault, handle) / ".ingest_meta.json"


def clean_index_path(vault: Path, handle: str) -> Path:
    return wiki_dir(vault, handle) / ".clean_corpus.jsonl"


def ingest_index_path(vault: Path, handle: str) -> Path:
    return wiki_dir(vault, handle) / ".ingest_index.jsonl"


def load_meta(vault: Path, handle: str) -> dict[str, Any] | None:
    path = meta_path(vault, handle)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def is_usable(item: dict[str, Any]) -> bool:
    if item.get("is_retweet"):
        return False
    if item.get("low_content"):
        return False
    if item.get("quality") == "noise":
        return False
    routing = item.get("routing")
    if isinstance(routing, dict) and routing:
        return bool(routing.get("distill"))
    return True


def load_docs(vault: Path, handle: str) -> tuple[list[dict[str, Any]], Path]:
    path = clean_index_path(vault, handle)
    if not path.exists():
        path = ingest_index_path(vault, handle)
    if not path.exists():
        raise FileNotFoundError(f"no clean or ingest index for {handle}")
    docs = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            item = json.loads(line)
            if is_usable(item):
                docs.append(item)
    return docs, path


def write_bootstrap(vault: Path, handle: str, max_id: str, count: int) -> dict[str, Any]:
    meta = {
        "ingest_watermark_id": max_id,
        "last_ingest": today(),
        "tweet_count_indexed": count,
        "history": [{
            "date": today(),
            "event": "bootstrap",
            "added": 0,
            "watermark": max_id,
        }],
    }
    out = meta_path(vault, handle)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return meta


def write_delta_files(vault: Path, handle: str, delta: list[dict[str, Any]], wm_old: str, source: Path) -> dict[str, Any]:
    wdir = wiki_dir(vault, handle)
    tsv = wdir / ".ingest_delta.tsv"
    js = wdir / ".ingest_delta.json"
    with tsv.open("w", encoding="utf-8") as fh:
        for item in delta:
            text = (item.get("text") or "").replace("\t", " ").replace("\n", " ").strip()[:280]
            flag = "R" if item.get("is_reply") else "T"
            fh.write(f"{item['id']}\t{str(item.get('date',''))[:10]}\t{item.get('lang','')}\t{flag}\t{text}\n")
    wm_new = str(max(int(item["id"]) for item in delta))
    info = {
        "handle": handle,
        "status": "ready",
        "delta": len(delta),
        "replies": sum(1 for item in delta if item.get("is_reply")),
        "watermark_old": str(wm_old),
        "watermark_proposed": wm_new,
        "date_range": [str(delta[0].get("date", ""))[:10], str(delta[-1].get("date", ""))[:10]],
        "source": str(source),
        "delta_tsv": str(tsv),
    }
    js.write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return info


def compute(vault: Path, handle: str, cap: int) -> dict[str, Any]:
    docs, source = load_docs(vault, handle)
    if not docs:
        return {"handle": handle, "status": "error", "msg": "0 usable docs", "source": str(source)}
    docs.sort(key=lambda item: int(item["id"]))
    max_id = str(max(int(item["id"]) for item in docs))
    meta = load_meta(vault, handle)
    if meta is None or not meta.get("ingest_watermark_id"):
        write_bootstrap(vault, handle, max_id, len(docs))
        return {
            "handle": handle,
            "status": "bootstrap",
            "delta": 0,
            "watermark": max_id,
            "usable_total": len(docs),
            "source": str(source),
        }

    wm = int(meta["ingest_watermark_id"])
    delta = [item for item in docs if int(item["id"]) > wm]
    if not delta:
        return {
            "handle": handle,
            "status": "none",
            "delta": 0,
            "watermark": str(wm),
            "usable_total": len(docs),
            "source": str(source),
        }
    if len(delta) > cap:
        return {
            "handle": handle,
            "status": "over_cap",
            "delta": len(delta),
            "cap": cap,
            "watermark": str(wm),
            "watermark_proposed": str(max(int(item["id"]) for item in delta)),
            "usable_total": len(docs),
            "source": str(source),
            "msg": "delta exceeds cap; manual kol-distill review required",
        }
    info = write_delta_files(vault, handle, delta, str(wm), source)
    info["usable_total"] = len(docs)
    return info


def commit(vault: Path, handle: str, watermark: str, added: int) -> dict[str, Any]:
    meta = load_meta(vault, handle)
    if meta is None or not meta.get("ingest_watermark_id"):
        return {
            "handle": handle,
            "status": "commit_refused",
            "msg": "no .ingest_meta.json / no watermark; run compute first",
        }
    old = str(meta["ingest_watermark_id"])
    try:
        if int(watermark) <= int(old):
            return {
                "handle": handle,
                "status": "commit_noop",
                "msg": f"proposed {watermark} <= current {old}",
                "watermark": old,
            }
    except ValueError:
        return {
            "handle": handle,
            "status": "commit_refused",
            "msg": f"non-numeric watermark old={old!r} new={watermark!r}",
        }

    meta["ingest_watermark_id"] = str(watermark)
    meta["last_ingest"] = today()
    meta.setdefault("history", []).append({
        "date": today(),
        "event": "incremental",
        "added": added,
        "watermark": str(watermark),
    })
    meta_path(vault, handle).write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "handle": handle,
        "status": "committed",
        "watermark": str(watermark),
        "added": added,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compute or commit KOL ingest delta.")
    parser.add_argument("handle")
    parser.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    parser.add_argument("--cap", type=int, default=DEFAULT_CAP)
    parser.add_argument("--commit", metavar="MAX_ID")
    parser.add_argument("--added", type=int, default=0)
    args = parser.parse_args(argv)
    try:
        result = commit(args.vault, args.handle, args.commit, args.added) if args.commit else compute(args.vault, args.handle, args.cap)
    except Exception as exc:  # noqa: BLE001
        result = {"handle": args.handle, "status": "error", "error": str(exc)}
        print(json.dumps(result, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") not in {"error", "commit_refused"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
