#!/usr/bin/env python3
"""Build single-KOL ask context packs without calling a model."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kol_common import DEFAULT_VAULT, wiki_dir


def now_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def registry_path(vault: Path) -> Path:
    return vault / "_cross" / "_registry.md"


def parse_list_value(value: str) -> list[str]:
    raw = value.strip().strip("[]")
    if not raw:
        return []
    return [part.strip().strip("`").strip() for part in raw.split(",") if part.strip()]


def parse_registry(vault: Path) -> list[dict[str, Any]]:
    path = registry_path(vault)
    if not path.exists():
        raise FileNotFoundError(f"missing registry: {path}")
    entries = []
    current: dict[str, Any] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        section = re.match(r"^##\s+@?([A-Za-z0-9_]+)", line.strip())
        if section:
            if current:
                entries.append(current)
            current = {"section": section.group(1), "aliases": []}
            continue
        if current is None:
            continue
        match = re.match(r"^-\s+([A-Za-z_]+):\s+(.+)$", line.strip())
        if not match:
            continue
        key, value = match.groups()
        value = value.strip()
        if key == "handle":
            current["handle"] = value.strip("`")
        elif key == "aliases":
            current["aliases"] = parse_list_value(value)
        elif key == "path":
            current["path"] = value.strip("`")
        elif key == "domain":
            current["domain"] = parse_list_value(value)
    if current:
        entries.append(current)
    return entries


def resolve_handle(vault: Path, name: str) -> dict[str, Any]:
    needle = name.strip().lstrip("@").lower()
    entries = parse_registry(vault)
    for entry in entries:
        handle = str(entry.get("handle") or entry.get("section") or "")
        aliases = [str(alias) for alias in entry.get("aliases") or []]
        candidates = [handle, entry.get("section", ""), *aliases]
        if any(needle == str(candidate).strip().lstrip("@").lower() for candidate in candidates):
            entry["handle"] = handle
            return entry
    registered = ", ".join(sorted(str(entry.get("handle") or entry.get("section")) for entry in entries))
    raise RuntimeError(f"未注册的 KOL: {name}; 当前已注册: {registered}")


def text_tokens(text: str) -> set[str]:
    tokens = set(re.findall(r"[A-Za-z0-9_.$]+", text.lower()))
    for chunk in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        tokens.add(chunk)
    return tokens


def file_score(path: Path, question: str) -> int:
    q = question.lower()
    stem = path.stem.lower()
    score = 0
    if stem and stem in q:
        score += 8
    if path.stem in question:
        score += 8
    content = path.read_text(encoding="utf-8", errors="ignore")
    for token in text_tokens(question):
        if not token:
            continue
        if token in stem:
            score += 3
        if token.lower() in content.lower():
            score += 1
    return score


def select_ranked(paths: list[Path], question: str, limit: int, *, include_zero: bool = False) -> list[Path]:
    scored = [(file_score(path, question), path) for path in paths if path.exists()]
    if not include_zero:
        scored = [(score, path) for score, path in scored if score > 0]
    scored.sort(key=lambda item: (-item[0], str(item[1])))
    return [path for _, path in scored[:limit]]


def collect_context_files(vault: Path, handle: str, question: str) -> list[dict[str, str]]:
    wdir = wiki_dir(vault, handle)
    selected: list[Path] = []
    soul = wdir / "soul.md"
    if soul.exists():
        selected.append(soul)
    methods = sorted((wdir / "methods").glob("*.md")) if (wdir / "methods").exists() else []
    positions = sorted((wdir / "positions").glob("*.md")) if (wdir / "positions").exists() else []
    sources = sorted((wdir / "sources").glob("*.md")) if (wdir / "sources").exists() else []
    selected.extend(select_ranked(methods, question, 8, include_zero=False))
    selected.extend(select_ranked(positions, question, 6, include_zero=False))
    selected.extend(select_ranked(sources, question, 8, include_zero=False))
    timeline = wdir / "timeline.md"
    if timeline.exists() and file_score(timeline, question) > 0:
        selected.append(timeline)

    deduped = []
    seen = set()
    for path in selected:
        resolved = str(path)
        if resolved not in seen:
            seen.add(resolved)
            deduped.append({"path": resolved, "relative": str(path.relative_to(wdir))})
    return deduped


def render_context(handle: str, question: str, files: list[dict[str, str]]) -> str:
    chunks = [
        f"# {handle} Ask Context",
        "",
        f"Question: {question}",
        "",
        "## Selected Files",
    ]
    for item in files:
        path = Path(item["path"])
        chunks.extend([
            "",
            f"### {item['relative']}",
            "",
            path.read_text(encoding="utf-8", errors="ignore"),
        ])
    return "\n".join(chunks).rstrip() + "\n"


def render_prompt(handle: str, question: str, context_file: Path) -> str:
    return f"""# KOL Ask Prompt

你是基于 {handle} 公开推文档案构建的决策辅助 twin。

关键边界：
- 你不是 {handle} 本人，不冒充本人实时发言。
- 不预测具体时间和价格点位。
- 如果档案没有覆盖，明确说“超出覆盖范围”。
- 使用第一人称只是模拟档案视角，不代表本人新发言。

先阅读上下文：

`{context_file}`

用户问题：

{question}

输出要求：
- 引用使用 `[[wikilink]]` 指向上下文里的 KOL wiki 文件。
- 结尾必须包含 metadata block：

```meta
confidence: 高|中|低
in_comfort_zone: yes|no
primary_sources: []
wikilinks_used: []
caveats: ""
```
"""


def write_context_pack(vault: Path, handle: str, question: str, pack_id: str) -> Path:
    wdir = wiki_dir(vault, handle)
    workspace = wdir / ".ask_context_packs" / pack_id
    files = collect_context_files(vault, handle, question)
    workspace.mkdir(parents=True, exist_ok=True)
    context_path = workspace / "context.md"
    context_path.write_text(render_context(handle, question, files), encoding="utf-8")
    (workspace / "prompt.md").write_text(render_prompt(handle, question, context_path), encoding="utf-8")
    write_json(
        workspace / "manifest.json",
        {
            "handle": handle,
            "mode": "context-pack",
            "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "question": question,
            "selected_files": files,
            "context": str(context_path),
            "prompt": str(workspace / "prompt.md"),
        },
    )
    return workspace


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare single-KOL ask context packs")
    parser.add_argument("name", help="KOL handle or alias")
    parser.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    parser.add_argument("--question", required=True)
    parser.add_argument("--mode", choices=("context-pack",), default="context-pack")
    parser.add_argument("--pack-id", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        entry = resolve_handle(args.vault, args.name)
        handle = str(entry["handle"])
        pack_id = args.pack_id or f"ask-{now_compact()}"
        workspace = write_context_pack(args.vault, handle, args.question, pack_id)
        print(
            json.dumps(
                {
                    "handle": handle,
                    "status": "context_pack_ready",
                    "workspace": str(workspace),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"name": args.name, "status": "error", "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
