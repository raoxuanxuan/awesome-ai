#!/usr/bin/env python3
"""Build or run multi-KOL debate prompt packs with an external runner."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kol_ask import collect_context_files, render_context, resolve_handle
from kol_common import DEFAULT_VAULT


def now_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_kols(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def debate_root(vault: Path) -> Path:
    return vault / "_cross" / "debates"


def workspace_path(vault: Path, pack_id: str) -> Path:
    if not pack_id:
        raise RuntimeError("--pack-id is required when loading an existing debate workspace")
    return debate_root(vault) / pack_id


def safety_rules(handle: str) -> str:
    return "\n".join(
        [
            f"- 你不是 {handle} 本人，不冒充本人实时发言。",
            "- 不预测具体时间和价格点位。",
            "- 如果档案没有覆盖，明确说“超出覆盖范围”。",
            "- 使用第一人称只是模拟档案视角，不代表本人新发言。",
            "- 结尾必须包含 confidence / in_comfort_zone / primary_sources / wikilinks_used / caveats。",
        ]
    )


def render_round1_prompt(handle: str, question: str, context_file: Path) -> str:
    return f"""# Debate Round 1 Prompt

辩题：

{question}

你是基于 {handle} 档案构建的决策辅助 twin。

关键边界：
{safety_rules(handle)}

阅读你的上下文：

`{context_file}`

这是第 1 轮，你看不到其他 KOL 的发言。

请输出：
- 明确立场：看多 / 看空 / 中立 / 超出覆盖。
- 3-5 条核心论据，每条引用 `[[wikilink]]`。
- 明确你的方法论和已知偏见。
- 不要客套，不要模仿其他 KOL。

```meta
confidence: 高|中|低
in_comfort_zone: yes|no
primary_sources: []
wikilinks_used: []
caveats: ""
```
"""


def render_round2_prompt(handle: str, question: str, context_file: Path, handles: list[str]) -> str:
    others = [other for other in handles if other != handle]
    turn_refs = "\n".join(f"- `../turns/r1-{other}.md`" for other in others)
    return f"""# Debate Round 2 Prompt

辩题：

{question}

你是基于 {handle} 档案构建的决策辅助 twin。

关键边界：
{safety_rules(handle)}

阅读你的上下文：

`{context_file}`

阅读其他 KOL 第 1 轮发言：

{turn_refs}

这是第 2 轮。请只回应真正分歧：
- 找出与你方法论不同的判断前提。
- 如果对方某点说服了你，明确承认。
- 如果对方超出证据，指出哪里超出。
- 守住你的档案边界，不要漂移成对方风格。

```meta
confidence: 高|中|低
in_comfort_zone: yes|no
primary_sources: []
wikilinks_used: []
caveats: ""
```
"""


def render_synth_prompt(question: str, handles: list[str], rounds: int) -> str:
    refs = []
    for round_number in range(1, rounds + 1):
        for handle in handles:
            refs.append(f"- `../turns/r{round_number}-{handle}.md`")
    return f"""# Debate Synthesizer Prompt

辩题：

{question}

参与者：

{", ".join(handles)}

读取这些发言：

{chr(10).join(refs)}

请只输出 JSON，不要额外文字。

Schema:

```json
{{
  "question": "...",
  "participants": ["..."],
  "rounds_held": {rounds},
  "立场摘要": [
    {{
      "name": "@handle",
      "立场": "看多|看空|中立|超出覆盖",
      "信心度": "高|中|低",
      "in_comfort_zone": true,
      "核心论据": ["..."]
    }}
  ],
  "共识点": ["..."],
  "分歧点": [
    {{
      "议题": "...",
      "支持方": ["@x"],
      "反方": ["@y"],
      "分歧本质": "..."
    }}
  ],
  "支持比例": {{
    "人头": {{}},
    "信心度加权": {{}}
  }},
  "辩论质量": "充分|不充分|失败(无真分歧)",
  "盲点提示": "...",
  "推荐行动": "..."
}}
```
"""


def render_readme(question: str, handles: list[str], rounds: int) -> str:
    return f"""# KOL Debate Prompt Pack

Question:

{question}

Participants:

{", ".join(handles)}

How to use:

1. Run each `prompts/r1-<handle>.md` independently and save outputs under `turns/r1-<handle>.md`.
2. If `rounds >= 2`, run each `prompts/r2-<handle>.md` after all Round 1 outputs exist.
3. Run `prompts/synthesize.md` after all turns exist and save JSON to `verdict.json`.

To automate this with any CLI that reads prompt text from stdin and writes the
answer to stdout, run:

```bash
python3 plugins/kol-tools/scripts/kol_debate.py \\
  --vault /Users/saberrao/vault/kol \\
  --kols {",".join(handles)} \\
  --question "{question}" \\
  --rounds {rounds} \\
  --mode run \\
  --pack-id <pack-id> \\
  --runner-command "<your-runner-command>"
```
"""


def write_prompt_pack(vault: Path, names: list[str], question: str, rounds: int, pack_id: str) -> tuple[Path, list[str]]:
    resolved = [resolve_handle(vault, name)["handle"] for name in names]
    if len(set(resolved)) < 2:
        raise RuntimeError("至少 2 个不同 KOL 才能辩论")
    handles = list(dict.fromkeys(resolved))
    workspace = debate_root(vault) / pack_id
    contexts_dir = workspace / "contexts"
    prompts_dir = workspace / "prompts"
    contexts_dir.mkdir(parents=True, exist_ok=True)
    prompts_dir.mkdir(parents=True, exist_ok=True)
    (workspace / "turns").mkdir(exist_ok=True)
    (workspace / "question.md").write_text(question + "\n", encoding="utf-8")

    context_paths: dict[str, str] = {}
    selected: dict[str, list[dict[str, str]]] = {}
    for handle in handles:
        files = collect_context_files(vault, handle, question)
        selected[handle] = files
        context_path = contexts_dir / f"{handle}.md"
        context_path.write_text(render_context(handle, question, files), encoding="utf-8")
        context_paths[handle] = str(context_path)
        (prompts_dir / f"r1-{handle}.md").write_text(
            render_round1_prompt(handle, question, context_path),
            encoding="utf-8",
        )
    if rounds >= 2:
        for handle in handles:
            (prompts_dir / f"r2-{handle}.md").write_text(
                render_round2_prompt(handle, question, Path(context_paths[handle]), handles),
                encoding="utf-8",
            )
    (prompts_dir / "synthesize.md").write_text(
        render_synth_prompt(question, handles, rounds),
        encoding="utf-8",
    )
    (workspace / "README.md").write_text(render_readme(question, handles, rounds), encoding="utf-8")
    write_json(
        workspace / "manifest.json",
        {
            "mode": "prompt-pack",
            "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "question": question,
            "handles": handles,
            "rounds": rounds,
            "executes_model": False,
            "contexts": context_paths,
            "selected_files": selected,
            "prompts": {
                "round1": [str(prompts_dir / f"r1-{handle}.md") for handle in handles],
                "round2": [str(prompts_dir / f"r2-{handle}.md") for handle in handles] if rounds >= 2 else [],
                "synthesize": str(prompts_dir / "synthesize.md"),
            },
        },
    )
    return workspace, handles


def parse_runner_command(value: str) -> list[str]:
    argv = shlex.split(value)
    if not argv:
        raise RuntimeError("--runner-command cannot be empty")
    return argv


def runner_metadata(runner_argv: list[str]) -> dict[str, Any]:
    return {
        "executable": runner_argv[0],
        "arg_count": len(runner_argv),
    }


def run_prompt(runner_argv: list[str], prompt_path: Path, output_path: Path, timeout: int) -> dict[str, Any]:
    prompt = prompt_path.read_text(encoding="utf-8")
    started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    completed = subprocess.run(
        runner_argv,
        input=prompt,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(completed.stdout, encoding="utf-8")
    if completed.stderr:
        (output_path.with_suffix(output_path.suffix + ".stderr")).write_text(completed.stderr, encoding="utf-8")
    return {
        "prompt": str(prompt_path),
        "output": str(output_path),
        "returncode": completed.returncode,
        "started_at": started,
        "completed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "stderr": str(output_path.with_suffix(output_path.suffix + ".stderr")) if completed.stderr else "",
    }


def extract_json(text: str) -> Any:
    stripped = text.strip()
    if not stripped:
        raise RuntimeError("runner produced empty verdict")
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    fence = "```json"
    if fence in stripped:
        start = stripped.index(fence) + len(fence)
        end = stripped.find("```", start)
        if end != -1:
            return json.loads(stripped[start:end].strip())
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(stripped[start : end + 1])
    raise RuntimeError("runner verdict is not valid JSON")


def load_workspace(vault: Path, pack_id: str) -> tuple[Path, dict[str, Any]]:
    workspace = workspace_path(vault, pack_id)
    manifest_path = workspace / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"missing debate manifest: {manifest_path}")
    return workspace, read_json(manifest_path)


def ensure_prompt_pack(vault: Path, names: list[str], question: str, rounds: int, pack_id: str) -> tuple[Path, dict[str, Any]]:
    workspace = workspace_path(vault, pack_id)
    if (workspace / "manifest.json").exists():
        workspace, manifest = load_workspace(vault, pack_id)
        expected_handles = list(dict.fromkeys(resolve_handle(vault, name)["handle"] for name in names))
        if manifest.get("question") != question:
            raise RuntimeError(f"existing pack-id has different question: {pack_id}")
        if manifest.get("handles") != expected_handles:
            raise RuntimeError(f"existing pack-id has different participants: {pack_id}")
        if int(manifest.get("rounds") or 0) != rounds:
            raise RuntimeError(f"existing pack-id has different rounds: {pack_id}")
        return workspace, manifest
    write_prompt_pack(vault, names, question, rounds, pack_id)
    return load_workspace(vault, pack_id)


def update_manifest(workspace: Path, updates: dict[str, Any]) -> dict[str, Any]:
    manifest_path = workspace / "manifest.json"
    manifest = read_json(manifest_path)
    manifest.update(updates)
    write_json(manifest_path, manifest)
    return manifest


def run_debate_workspace(
    vault: Path,
    names: list[str],
    question: str,
    rounds: int,
    pack_id: str,
    runner_command: str,
    timeout: int,
) -> tuple[int, dict[str, Any]]:
    if not pack_id:
        pack_id = f"debate-{now_compact()}"
    workspace, manifest = ensure_prompt_pack(vault, names, question, rounds, pack_id)
    runner_argv = parse_runner_command(runner_command)
    prompts = manifest.get("prompts", {})
    handles = list(manifest.get("handles") or [])
    turns_dir = workspace / "turns"
    run_steps: list[dict[str, Any]] = []

    for handle in handles:
        prompt = Path(prompts["round1"][handles.index(handle)])
        run_steps.append(run_prompt(runner_argv, prompt, turns_dir / f"r1-{handle}.md", timeout))
    if int(manifest.get("rounds") or rounds) >= 2:
        round2_prompts = list(prompts.get("round2") or [])
        for handle, prompt in zip(handles, round2_prompts):
            run_steps.append(run_prompt(runner_argv, Path(prompt), turns_dir / f"r2-{handle}.md", timeout))

    verdict_raw = workspace / "verdict.raw.md"
    run_steps.append(run_prompt(runner_argv, Path(prompts["synthesize"]), verdict_raw, timeout))
    failed = [step for step in run_steps if step["returncode"] != 0]
    if failed:
        update_manifest(workspace, {"run_status": "failed", "executes_model": True, "run_steps": run_steps})
        return 2, {"status": "run_failed", "workspace": str(workspace), "failed_steps": failed, "steps": run_steps}

    verdict = extract_json(verdict_raw.read_text(encoding="utf-8"))
    write_json(workspace / "verdict.json", verdict)
    (workspace / "verdict.md").write_text(
        "# KOL Debate Verdict\n\n"
        f"Question: {manifest.get('question')}\n\n"
        "```json\n"
        + json.dumps(verdict, ensure_ascii=False, indent=2)
        + "\n```\n",
        encoding="utf-8",
    )
    update_manifest(
        workspace,
        {
            "run_status": "complete",
            "executed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "executes_model": True,
            "runner": runner_metadata(runner_argv),
            "run_steps": run_steps,
            "verdict": str(workspace / "verdict.json"),
        },
    )
    return 0, {
        "status": "run_complete",
        "workspace": str(workspace),
        "handles": handles,
        "rounds": manifest.get("rounds"),
        "turns": [step["output"] for step in run_steps[:-1]],
        "verdict": str(workspace / "verdict.json"),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare multi-KOL debate prompt packs")
    parser.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    parser.add_argument("--kols", required=True, help="Comma-separated handles or aliases")
    parser.add_argument("--question", "--q", dest="question", required=True)
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--mode", choices=("prompt-pack", "run"), default="prompt-pack")
    parser.add_argument("--pack-id", default="")
    parser.add_argument("--runner-command", default="", help="external command that reads prompt from stdin and writes answer to stdout")
    parser.add_argument("--timeout", type=int, default=600)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        names = parse_kols(args.kols)
        if len(names) < 2:
            raise RuntimeError("至少 2 个 KOL 才能辩论")
        rounds = max(1, args.rounds)
        pack_id = args.pack_id or f"debate-{now_compact()}"
        if args.mode == "run":
            if not args.runner_command:
                raise RuntimeError("--runner-command is required for --mode run")
            rc, result = run_debate_workspace(
                args.vault,
                names,
                args.question,
                rounds,
                pack_id,
                args.runner_command,
                args.timeout,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return rc
        workspace, handles = write_prompt_pack(args.vault, names, args.question, rounds, pack_id)
        print(
            json.dumps(
                {
                    "status": "prompt_pack_ready",
                    "workspace": str(workspace),
                    "handles": handles,
                    "rounds": rounds,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
