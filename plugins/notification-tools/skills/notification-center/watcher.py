#!/usr/bin/env python3
"""Convert watched file changes into notification center events."""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


CST = timezone(timedelta(hours=8))
SKILL_DIR = Path(__file__).resolve().parent
DEFAULT_RUNTIME = Path.home() / "vault" / ".notification-center"
DEFAULT_CONFIG = SKILL_DIR / "watch.json"
APPEND_PY = SKILL_DIR / "append.py"
WATERMARK_NAME = ".watermarks.json"
LOG_NAME = ".watcher.log"


def runtime_dir(env: dict[str, str] | None = None) -> Path:
    env = os.environ if env is None else env
    override = env.get("NOTIFICATION_CENTER_RUNTIME")
    if override:
        return Path(override).expanduser()
    return DEFAULT_RUNTIME


def now_cst() -> datetime:
    return datetime.now(CST)


def log(runtime: Path, message: str) -> None:
    runtime.mkdir(parents=True, exist_ok=True)
    with (runtime / LOG_NAME).open("a", encoding="utf-8") as fh:
        fh.write(f"{now_cst().isoformat(timespec='seconds')} {message}\n")


def expand_braces(pattern: str) -> list[str]:
    match = re.search(r"\{([^{}]+)\}", pattern)
    if not match:
        return [pattern]
    before, after = pattern[: match.start()], pattern[match.end() :]
    out: list[str] = []
    for item in match.group(1).split(","):
        out.extend(expand_braces(f"{before}{item}{after}"))
    return out


def glob_paths(pattern: str) -> list[Path]:
    paths: list[Path] = []
    for expanded in expand_braces(str(Path(pattern).expanduser())):
        paths.extend(Path(hit) for hit in glob.glob(expanded))
    return paths


def load_watermarks(runtime: Path) -> dict[str, Any]:
    path = runtime / WATERMARK_NAME
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_watermarks(runtime: Path, watermarks: dict[str, Any]) -> None:
    runtime.mkdir(parents=True, exist_ok=True)
    target = runtime / WATERMARK_NAME
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(watermarks, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(target)


def parse_frontmatter(path: Path) -> tuple[dict[str, str], str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}, ""
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end <= 0:
        return {}, text
    meta: dict[str, str] = {}
    for line in text[4:end].splitlines():
        match = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if match:
            meta[match.group(1)] = match.group(2).strip().strip("\"'")
    return meta, text[end + 5 :]


def clean_text(text: str) -> str:
    lines = []
    for line in text.splitlines():
        value = line.strip()
        if not value or value.startswith("---"):
            continue
        if re.match(r"^https?://\S+$", value):
            continue
        if value.startswith("*原文链接"):
            continue
        if value.startswith("> "):
            value = value[2:]
        if value.startswith("#"):
            value = re.sub(r"^#+\s*", "", value)
        lines.append(value)
    return "\n".join(lines).strip()


def extract_section(body: str, names: list[str]) -> str:
    lines = body.splitlines()
    out: list[str] = []
    active = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            heading = stripped[3:].strip()
            if any(name in heading for name in names):
                active = True
                continue
            if active:
                break
        elif active:
            out.append(line)
    return "\n".join(out).strip()


def artifact_summary(path: Path, chars: int) -> tuple[str, str, str]:
    meta, body = parse_frontmatter(path)
    source_url = meta.get("source", "").strip() or meta.get("url", "").strip()
    title = meta.get("title", "").strip()
    excerpt = ""
    for names in (["摘要", "TL;DR", "TLDR", "解读", "要点"], ["中文翻译", "翻译", "Translation"]):
        section = extract_section(body, names)
        if section:
            excerpt = clean_text(section)
            break
    if not excerpt:
        excerpt = clean_text(body)
    if len(excerpt) > chars:
        excerpt = excerpt[:chars].rstrip() + "..."
    if not title:
        for line in body.splitlines():
            stripped = line.strip()
            if stripped.startswith("# ") and not stripped.startswith("## "):
                title = stripped[2:].strip()
                break
    if not title:
        title = (excerpt.splitlines() or [path.stem])[0][:80]
    return title, excerpt, source_url


def append_event(
    runtime: Path,
    source: str,
    level: str,
    title: str,
    summary: str,
    *,
    dedupe_key: str,
    paths: list[str] | None = None,
    links: list[str] | None = None,
    meta: dict[str, Any] | None = None,
    dry_run: bool = False,
) -> str:
    if dry_run:
        return f"[DRY] {source} {level} {title}"
    cmd = [
        "python3",
        str(APPEND_PY),
        "--runtime",
        str(runtime),
        "--source",
        source,
        "--level",
        level,
        "--title",
        title,
        "--summary",
        summary,
        "--dedupe-key",
        dedupe_key,
    ]
    for path in paths or []:
        cmd.extend(["--path", path])
    for link in links or []:
        cmd.extend(["--link", link])
    if meta:
        cmd.extend(["--meta", json.dumps(meta, ensure_ascii=False)])
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    if result.returncode != 0:
        return f"[ERR] {source} {title}: {result.stderr.strip()}"
    return f"[OK] {source} {title}"


def handle_per_file(watch: dict[str, Any], watermarks: dict[str, Any], runtime: Path, dry_run: bool) -> tuple[int, list[str]]:
    source = watch["source"]
    last = watermarks.get(source, {}).get("mtime", 0)
    max_seen = last
    count = 0
    messages: list[str] = []
    excludes = watch.get("exclude_substrings", [])
    for path in sorted(glob_paths(watch["glob"]), key=lambda item: item.stat().st_mtime if item.exists() else 0):
        if not path.exists() or any(token in path.name for token in excludes):
            continue
        mtime = path.stat().st_mtime
        if mtime <= last:
            continue
        title, excerpt, url = artifact_summary(path, int(watch.get("summary_chars") or 280))
        messages.append(
            append_event(
                runtime,
                source,
                watch.get("level", "info"),
                title,
                excerpt,
                dedupe_key=str(path),
                paths=[str(path)],
                links=[f"source={url}"] if url else [],
                meta={"file": str(path), "mtime": int(mtime)},
                dry_run=dry_run,
            )
        )
        count += 1
        max_seen = max(max_seen, mtime)
    if count and not dry_run:
        watermarks.setdefault(source, {})["mtime"] = max_seen
    return count, messages


def handle_grouped_by_segment(
    watch: dict[str, Any],
    watermarks: dict[str, Any],
    runtime: Path,
    dry_run: bool,
    *,
    segment: str,
    label: str,
) -> tuple[int, list[str]]:
    source = watch["source"]
    grouped: dict[str, list[Path]] = {}
    for path in glob_paths(watch["glob"]):
        if not path.exists():
            continue
        parts = path.parts
        try:
            key = parts[parts.index(segment) + 1]
        except (ValueError, IndexError):
            continue
        watermark_key = f"{source}::{key}"
        if path.stat().st_mtime <= watermarks.get(watermark_key, {}).get("mtime", 0):
            continue
        grouped.setdefault(key, []).append(path)

    messages: list[str] = []
    summary_chars = int(watch.get("summary_chars") or 240)
    items_per_card = int(watch.get("items_per_card") or 5)
    for key, paths in grouped.items():
        paths.sort(key=lambda item: item.stat().st_mtime, reverse=True)
        lines: list[str] = []
        links: list[str] = []
        for path in paths[:items_per_card]:
            title, excerpt, url = artifact_summary(path, summary_chars)
            lines.append(f"**{title}**")
            if excerpt:
                lines.append(excerpt)
            if url:
                links.append(f"{title[:20]}={url}")
            lines.append("")
        if len(paths) > items_per_card:
            lines.append(f"... {len(paths) - items_per_card} more")
        messages.append(
            append_event(
                runtime,
                source,
                watch.get("level", "alert"),
                f"{label} {key}: {len(paths)} new",
                "\n".join(lines).strip(),
                dedupe_key=f"{source}:{key}:{int(max(path.stat().st_mtime for path in paths))}",
                paths=[str(path) for path in paths[:3]],
                links=links[:5],
                meta={label: key, "count": len(paths)},
                dry_run=dry_run,
            )
        )
        if not dry_run:
            watermarks.setdefault(f"{source}::{key}", {})["mtime"] = max(path.stat().st_mtime for path in paths)
    return len(grouped), messages


def handle_per_kol_window(watch: dict[str, Any], watermarks: dict[str, Any], runtime: Path, dry_run: bool) -> tuple[int, list[str]]:
    return handle_grouped_by_segment(watch, watermarks, runtime, dry_run, segment="kol", label="kol")


def handle_per_author_window(watch: dict[str, Any], watermarks: dict[str, Any], runtime: Path, dry_run: bool) -> tuple[int, list[str]]:
    source = watch["source"]
    last_key = f"{source}::__last_mtime__"
    last = watermarks.get(last_key, {}).get("mtime", 0)
    grouped: dict[str, list[Path]] = {}
    for path in glob_paths(watch["glob"]):
        if not path.exists() or path.stat().st_mtime <= last:
            continue
        meta, _ = parse_frontmatter(path)
        author = meta.get("author", "").strip()
        if not author:
            match = re.search(r"\s-\s([^\-]+)$", path.stem)
            author = match.group(1).strip() if match else "unknown"
        grouped.setdefault(author.split("(")[0].strip() or "unknown", []).append(path)

    messages: list[str] = []
    all_paths: list[Path] = []
    summary_chars = int(watch.get("summary_chars") or 240)
    items_per_card = int(watch.get("items_per_card") or 4)
    for author, paths in grouped.items():
        paths.sort(key=lambda item: item.stat().st_mtime, reverse=True)
        lines: list[str] = []
        links: list[str] = []
        for path in paths[:items_per_card]:
            title, excerpt, url = artifact_summary(path, summary_chars)
            lines.append(f"**{title}**")
            if excerpt:
                lines.append(excerpt)
            if url:
                links.append(f"{title[:20]}={url}")
            lines.append("")
        messages.append(
            append_event(
                runtime,
                source,
                watch.get("level", "alert"),
                f"{author}: {len(paths)} new",
                "\n".join(lines).strip(),
                dedupe_key=f"{source}:{author}:{int(max(path.stat().st_mtime for path in paths))}",
                paths=[str(path) for path in paths[:3]],
                links=links[:5],
                meta={"author": author, "count": len(paths)},
                dry_run=dry_run,
            )
        )
        all_paths.extend(paths)
    if all_paths and not dry_run:
        watermarks.setdefault(last_key, {})["mtime"] = max(path.stat().st_mtime for path in all_paths)
    return len(grouped), messages


HANDLERS = {
    "per-file": handle_per_file,
    "per-kol-window": handle_per_kol_window,
    "per-author-window": handle_per_author_window,
}


def set_baseline(config: dict[str, Any]) -> dict[str, Any]:
    watermarks: dict[str, Any] = {}
    for watch in config.get("watchers", []):
        mode = watch.get("mode")
        source = watch.get("source")
        if mode == "per-file":
            mtimes = [path.stat().st_mtime for path in glob_paths(watch["glob"]) if path.exists()]
            if mtimes:
                watermarks[source] = {"mtime": max(mtimes)}
        elif mode == "per-kol-window":
            for path in glob_paths(watch["glob"]):
                if not path.exists():
                    continue
                try:
                    handle = path.parts[path.parts.index("kol") + 1]
                except (ValueError, IndexError):
                    continue
                key = f"{source}::{handle}"
                watermarks.setdefault(key, {})["mtime"] = max(
                    watermarks.get(key, {}).get("mtime", 0),
                    path.stat().st_mtime,
                )
        elif mode == "per-author-window":
            mtimes = [path.stat().st_mtime for path in glob_paths(watch["glob"]) if path.exists()]
            if mtimes:
                watermarks[f"{source}::__last_mtime__"] = {"mtime": max(mtimes)}
    return watermarks


def run_watchers(runtime: Path, config_path: Path, dry_run: bool = False, baseline: bool = False) -> dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if baseline:
        watermarks = set_baseline(config)
        save_watermarks(runtime, watermarks)
        log(runtime, f"BASELINE keys={len(watermarks)}")
        return {"ok": True, "runtime": str(runtime), "baseline": len(watermarks)}

    watermarks = load_watermarks(runtime)
    total = 0
    messages: list[str] = []
    for watch in config.get("watchers", []):
        handler = HANDLERS.get(watch.get("mode"))
        if not handler:
            messages.append(f"[WARN] unknown mode {watch.get('mode')} for {watch.get('source')}")
            continue
        count, produced = handler(watch, watermarks, runtime, dry_run)
        total += count
        messages.extend(produced)
    if not dry_run:
        save_watermarks(runtime, watermarks)
    result = {"ok": True, "runtime": str(runtime), "appended": total, "messages": messages}
    log(runtime, "RUN " + json.dumps(result, ensure_ascii=False, sort_keys=True))
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Watch files and append notification events")
    parser.add_argument("--runtime", help="Notification center runtime directory")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Watcher config JSON")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--baseline", action="store_true", help="Mark current files as already seen")
    parser.add_argument("--reset", action="store_true", help="Delete watermarks")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    runtime = Path(args.runtime).expanduser() if args.runtime else runtime_dir()
    if args.reset:
        path = runtime / WATERMARK_NAME
        if path.exists():
            path.unlink()
        print(json.dumps({"ok": True, "reset": True, "runtime": str(runtime)}))
        return 0
    result = run_watchers(runtime, Path(args.config).expanduser(), dry_run=args.dry_run, baseline=args.baseline)
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.dry_run or args.baseline else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
