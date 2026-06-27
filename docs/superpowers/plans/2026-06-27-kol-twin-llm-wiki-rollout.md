# KOL Twin LLM Wiki Rollout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the existing 12 KOL / 17,973 cleaned tweet corpus into a schema-governed, evidence-backed, incremental KOL Twin LLM Wiki system.

**Architecture:** Keep `tweet-pool` and raw archives as evidence layers, keep `kol-clean` and `kol-index` deterministic, then use `kol-distill` to compile evidence into `sources/`, `methods/`, `positions/`, `timeline.md`, and `soul.md`. Every durable wiki update must pass schema validation, tweet-id coverage validation, risk gating, and watermark discipline.

**Tech Stack:** Python 3 stdlib, local Markdown files under `/Users/saberrao/vault/kol`, existing `kol-tools` scripts/tests, Codex/Claude-compatible plugin layout.

---

## Current Baseline

- Repo: `/Users/saberrao/ai-workspace/awesome-ai`
- Plugin: `/Users/saberrao/ai-workspace/awesome-ai/plugins/kol-tools`
- KOL vault: `/Users/saberrao/vault/kol`
- Existing corpus:
  - 12 KOL handles
  - 17,973 clean/index docs
  - 8,631 low/noise docs
  - all `.ingest_index.jsonl` sources point to `.clean_corpus.jsonl`
- Recent commits already landed:
  - `966432f feat: tighten kol clean index pipeline`
  - `826ca8c docs: define kol twin llm wiki architecture`
  - `7742e3a feat: bundle kol wiki schemas in distill packs`

## File Structure

Create:

- `plugins/kol-tools/scripts/kol_wiki_inventory.py`
  - Reports per-KOL wiki readiness, clean/index counts, existing durable pages, stale/missing pack artifacts, and recommended action.
- `plugins/kol-tools/scripts/tests/test_kol_wiki_inventory.py`
  - Unit tests for inventory classification.
- `plugins/kol-tools/scripts/kol_schema_validate.py`
  - Validates durable KOL wiki pages against the Markdown schemas in `plugins/kol-tools/schemas/`.
- `plugins/kol-tools/scripts/tests/test_kol_schema_validate.py`
  - Unit tests for schema validation and evidence coverage expectations.
- `plugins/kol-tools/scripts/kol_rollout.py`
  - Batch orchestrator for inventory, prompt-pack generation, safe auto apply/validate/commit, and review-queue reporting.
- `plugins/kol-tools/scripts/tests/test_kol_rollout.py`
  - Unit tests for dry-run planning and risk-aware batch behavior.
- `plugins/kol-tools/templates/bootstrap-wiki-prompt.md`
  - Prompt template for first full wiki compile when a KOL has no durable wiki.
- `plugins/kol-tools/templates/review-pack-summary.md`
  - Prompt/report template for user/agent review of high-risk packs.
- `plugins/kol-tools/docs/rollout.md`
  - Human guide for running the full rollout.

Modify:

- `plugins/kol-tools/scripts/kol_distill.py`
  - Add bootstrap prompt-pack support and schema-aware validation hooks.
- `plugins/kol-tools/scripts/tests/test_kol_distill.py`
  - Add tests for bootstrap packs and schema validation integration.
- `plugins/kol-tools/skills/kol-distill/references/usage.md`
  - Document bootstrap/incremental rollout flows.
- `plugins/kol-tools/docs/architecture.md`
  - Link the rollout and validation tools.
- `plugins/kol-tools/README.md`
  - Add the rollout entry command.

Do not modify:

- `/Users/saberrao/vault/kol/<handle>/raw/tweets/*.md`
- `tweet-pool` runtime content
- Twitter cookies or fetch runtime
- KOL wiki watermarks before validation succeeds

---

## Rollout Model

Each KOL is processed through one of three routes:

```text
Route A: existing mature wiki
  -> validate current durable wiki
  -> repair old/incomplete prompt packs
  -> process only new delta

Route B: partial wiki
  -> schema validate existing pages
  -> generate bootstrap repair pack
  -> apply reviewed updates
  -> validate all evidence

Route C: no durable wiki
  -> generate bootstrap prompt pack from selected high/medium clean corpus
  -> user/agent review
  -> write full wiki
  -> validate
  -> initialize ingest watermark
```

Expected initial route assignment should be discovered by `kol_wiki_inventory.py`, not hardcoded. `TJ_Research` is likely Route A; other KOLs may be B or C depending on existing `wiki/*.md` coverage.

---

## Task 1: Wiki Inventory

**Files:**
- Create: `plugins/kol-tools/scripts/kol_wiki_inventory.py`
- Create: `plugins/kol-tools/scripts/tests/test_kol_wiki_inventory.py`

- [ ] **Step 1: Write failing tests for KOL readiness classification**

Add this test file:

```python
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kol_wiki_inventory import classify_handle, inventory_vault


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


class KolWikiInventoryTests(unittest.TestCase):
    def test_classifies_mature_wiki_with_clean_index_and_core_pages(self):
        with tempfile.TemporaryDirectory() as td:
            vault = Path(td)
            wiki = vault / "h" / "wiki"
            wiki.mkdir(parents=True)
            write_jsonl(wiki / ".clean_corpus.jsonl", [{"id": "1", "text": "x", "routing": {"distill": True}}])
            write_jsonl(wiki / ".ingest_index.jsonl", [{"id": "1", "text": "x"}])
            (wiki / ".ingest_stats.json").write_text(json.dumps({"total": 1, "source": str(wiki / ".clean_corpus.jsonl")}), encoding="utf-8")
            for name in ["_index.md", "soul.md", "timeline.md"]:
                (wiki / name).write_text(f"# {name}\n", encoding="utf-8")
            for subdir in ["sources", "methods", "positions"]:
                (wiki / subdir).mkdir()
                (wiki / subdir / "sample.md").write_text("# sample\n\n## Evidence\n- 1\n", encoding="utf-8")

            result = classify_handle(vault, "h")

            self.assertEqual(result["route"], "existing_mature_wiki")
            self.assertEqual(result["clean_count"], 1)
            self.assertTrue(result["index_source_is_clean"])

    def test_classifies_no_wiki_as_bootstrap_required(self):
        with tempfile.TemporaryDirectory() as td:
            vault = Path(td)
            wiki = vault / "h" / "wiki"
            wiki.mkdir(parents=True)
            write_jsonl(wiki / ".clean_corpus.jsonl", [{"id": "1", "text": "x", "routing": {"distill": True}}])
            write_jsonl(wiki / ".ingest_index.jsonl", [{"id": "1", "text": "x"}])
            (wiki / ".ingest_stats.json").write_text(json.dumps({"total": 1, "source": str(wiki / ".clean_corpus.jsonl")}), encoding="utf-8")

            result = classify_handle(vault, "h")

            self.assertEqual(result["route"], "bootstrap_required")
            self.assertIn("missing soul.md", result["issues"])

    def test_inventory_vault_lists_all_handles(self):
        with tempfile.TemporaryDirectory() as td:
            vault = Path(td)
            for handle in ["a", "b"]:
                wiki = vault / handle / "wiki"
                wiki.mkdir(parents=True)
                write_jsonl(wiki / ".clean_corpus.jsonl", [{"id": "1", "text": "x"}])
            result = inventory_vault(vault)
            self.assertEqual([item["handle"] for item in result["handles"]], ["a", "b"])
```

- [ ] **Step 2: Run tests and verify red**

Run:

```bash
python3 -m unittest plugins/kol-tools/scripts/tests/test_kol_wiki_inventory.py
```

Expected: FAIL with `ModuleNotFoundError: No module named 'kol_wiki_inventory'`.

- [ ] **Step 3: Implement inventory script**

Create `plugins/kol-tools/scripts/kol_wiki_inventory.py`:

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from kol_common import DEFAULT_VAULT


CORE_FILES = ("_index.md", "soul.md", "timeline.md")
CONTENT_DIRS = ("sources", "methods", "positions")


def count_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def markdown_count(path: Path) -> int:
    if not path.exists():
        return 0
    return len([p for p in path.glob("*.md") if p.is_file()])


def classify_handle(vault: Path, handle: str) -> dict[str, Any]:
    wiki = vault / handle / "wiki"
    clean = wiki / ".clean_corpus.jsonl"
    index = wiki / ".ingest_index.jsonl"
    stats = wiki / ".ingest_stats.json"
    meta = wiki / ".ingest_meta.json"
    issues: list[str] = []

    clean_count = count_jsonl(clean)
    index_count = count_jsonl(index)
    stats_payload = read_json(stats)
    index_source = str(stats_payload.get("source") or "")
    index_source_is_clean = index_source.endswith("/wiki/.clean_corpus.jsonl")

    if not clean.exists():
        issues.append("missing .clean_corpus.jsonl")
    if not index.exists():
        issues.append("missing .ingest_index.jsonl")
    if not stats.exists():
        issues.append("missing .ingest_stats.json")
    if stats.exists() and not index_source_is_clean:
        issues.append("index source is not clean corpus")

    core_present = {name: (wiki / name).exists() for name in CORE_FILES}
    for name, exists in core_present.items():
        if not exists:
            issues.append(f"missing {name}")

    content_counts = {name: markdown_count(wiki / name) for name in CONTENT_DIRS}
    if sum(content_counts.values()) == 0:
        issues.append("missing durable content pages")

    if clean_count == 0 or index_count == 0:
        route = "not_ready"
    elif all(core_present.values()) and sum(content_counts.values()) > 0 and index_source_is_clean:
        route = "existing_mature_wiki"
    elif any(core_present.values()) or sum(content_counts.values()) > 0:
        route = "partial_wiki_repair"
    else:
        route = "bootstrap_required"

    return {
        "handle": handle,
        "route": route,
        "issues": issues,
        "clean_count": clean_count,
        "index_count": index_count,
        "index_source": index_source,
        "index_source_is_clean": index_source_is_clean,
        "core_present": core_present,
        "content_counts": content_counts,
        "has_ingest_meta": meta.exists(),
    }


def iter_handles(vault: Path) -> list[str]:
    return sorted(
        p.name
        for p in vault.iterdir()
        if p.is_dir() and not p.name.startswith(".") and p.name != "_cross" and (p / "wiki").is_dir()
    )


def inventory_vault(vault: Path) -> dict[str, Any]:
    handles = [classify_handle(vault, handle) for handle in iter_handles(vault)]
    by_route: dict[str, int] = {}
    for item in handles:
        by_route[item["route"]] = by_route.get(item["route"], 0) + 1
    return {"vault": str(vault), "handles": handles, "by_route": by_route}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect KOL wiki rollout readiness.")
    parser.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    parser.add_argument("--handle")
    args = parser.parse_args(argv)

    result = classify_handle(args.vault, args.handle) if args.handle else inventory_vault(args.vault)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests and verify green**

Run:

```bash
python3 -m unittest plugins/kol-tools/scripts/tests/test_kol_wiki_inventory.py
```

Expected: OK.

- [ ] **Step 5: Run inventory on real vault**

Run:

```bash
python3 plugins/kol-tools/scripts/kol_wiki_inventory.py --vault /Users/saberrao/vault/kol
```

Expected:

- JSON prints 12 handles.
- Every handle has nonzero `clean_count`.
- Any `bootstrap_required` or `partial_wiki_repair` handle is visible before rollout.

- [ ] **Step 6: Commit**

```bash
git add plugins/kol-tools/scripts/kol_wiki_inventory.py plugins/kol-tools/scripts/tests/test_kol_wiki_inventory.py
git commit -m "feat: add kol wiki inventory"
```

---

## Task 2: Schema Validator

**Files:**
- Create: `plugins/kol-tools/scripts/kol_schema_validate.py`
- Create: `plugins/kol-tools/scripts/tests/test_kol_schema_validate.py`
- Modify: `plugins/kol-tools/docs/architecture.md`
- Modify: `plugins/kol-tools/skills/kol-distill/references/usage.md`

- [ ] **Step 1: Write failing tests for Markdown schema validation**

Create `plugins/kol-tools/scripts/tests/test_kol_schema_validate.py`:

```python
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kol_schema_validate import validate_file, validate_handle


class KolSchemaValidateTests(unittest.TestCase):
    def test_source_page_requires_evidence_section_and_tweet_id(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "sources" / "AI.md"
            path.parent.mkdir()
            path.write_text("# AI\n\n## Scope\ntext\n", encoding="utf-8")

            result = validate_file(path, "source")

            self.assertFalse(result["ok"])
            self.assertIn("missing section: ## Evidence", result["issues"])
            self.assertIn("missing tweet id evidence", result["issues"])

    def test_method_page_with_required_sections_and_tweet_id_passes(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "methods" / "m.md"
            path.parent.mkdir()
            path.write_text(
                "# M\n\n"
                "## Core Rule\nrule\n"
                "## Applies When\ncase\n"
                "## Does Not Apply When\ncase\n"
                "## Signals\nsignal\n"
                "## Failure Conditions\nfail\n"
                "## Related Sources\nsource\n"
                "## Related Positions\npos\n"
                "## Evidence\n- 2067851206475608569\n",
                encoding="utf-8",
            )

            result = validate_file(path, "method")

            self.assertTrue(result["ok"])

    def test_validate_handle_checks_core_and_subdirectories(self):
        with tempfile.TemporaryDirectory() as td:
            vault = Path(td)
            wiki = vault / "h" / "wiki"
            (wiki / "sources").mkdir(parents=True)
            (wiki / "sources" / "topic.md").write_text("# Topic\n\n## Evidence\n- 123\n", encoding="utf-8")
            (wiki / "soul.md").write_text("# Soul\n\n## Evidence Anchors\n- 123\n", encoding="utf-8")

            result = validate_handle(vault, "h")

            self.assertFalse(result["ok"])
            self.assertGreaterEqual(len(result["files"]), 2)
```

- [ ] **Step 2: Run tests and verify red**

Run:

```bash
python3 -m unittest plugins/kol-tools/scripts/tests/test_kol_schema_validate.py
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement schema validator**

Create `plugins/kol-tools/scripts/kol_schema_validate.py`:

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from kol_common import DEFAULT_VAULT, wiki_dir


REQUIRED_SECTIONS = {
    "source": ["## Evidence"],
    "method": ["## Core Rule", "## Applies When", "## Does Not Apply When", "## Signals", "## Failure Conditions", "## Related Sources", "## Related Positions", "## Evidence"],
    "position": ["## Current Stance", "## Stance Strength", "## Reasons", "## Evolution", "## Relevant Methods", "## Risks / Disconfirming Evidence", "## Evidence"],
    "timeline": ["### Evidence Chain"],
    "soul": ["## Evidence Anchors"],
}

TWEET_ID_RE = re.compile(r"(?<!\\d)\\d{8,}(?!\\d)")


def infer_kind(path: Path) -> str:
    parts = set(path.parts)
    if "sources" in parts:
        return "source"
    if "methods" in parts:
        return "method"
    if "positions" in parts:
        return "position"
    if path.name == "timeline.md":
        return "timeline"
    if path.name == "soul.md":
        return "soul"
    return "generic"


def validate_file(path: Path, kind: str | None = None) -> dict[str, Any]:
    kind = kind or infer_kind(path)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    issues: list[str] = []
    if not path.exists():
        issues.append("file does not exist")
    for section in REQUIRED_SECTIONS.get(kind, []):
        if section not in text:
            issues.append(f"missing section: {section}")
    if kind in {"source", "method", "position", "timeline", "soul"} and not TWEET_ID_RE.search(text):
        issues.append("missing tweet id evidence")
    return {"path": str(path), "kind": kind, "ok": not issues, "issues": issues}


def durable_files(vault: Path, handle: str) -> list[Path]:
    wdir = wiki_dir(vault, handle)
    files = []
    for name in ["soul.md", "timeline.md"]:
        if (wdir / name).exists():
            files.append(wdir / name)
    for subdir in ["sources", "methods", "positions"]:
        root = wdir / subdir
        if root.exists():
            files.extend(sorted(root.glob("*.md")))
    return files


def validate_handle(vault: Path, handle: str) -> dict[str, Any]:
    files = [validate_file(path) for path in durable_files(vault, handle)]
    return {
        "handle": handle,
        "ok": all(item["ok"] for item in files),
        "files": files,
        "issue_count": sum(len(item["issues"]) for item in files),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate KOL wiki Markdown schema.")
    parser.add_argument("handle")
    parser.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    args = parser.parse_args(argv)
    result = validate_handle(args.vault, args.handle)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests and verify green**

Run:

```bash
python3 -m unittest plugins/kol-tools/scripts/tests/test_kol_schema_validate.py
```

Expected: OK.

- [ ] **Step 5: Run validator on TJ**

Run:

```bash
python3 plugins/kol-tools/scripts/kol_schema_validate.py TJ_Research --vault /Users/saberrao/vault/kol
```

Expected:

- If it returns 2, inspect JSON issues.
- Do not rewrite TJ wiki in this task.
- Use results to drive later repair packs.

- [ ] **Step 6: Commit**

```bash
git add plugins/kol-tools/scripts/kol_schema_validate.py plugins/kol-tools/scripts/tests/test_kol_schema_validate.py plugins/kol-tools/docs/architecture.md plugins/kol-tools/skills/kol-distill/references/usage.md
git commit -m "feat: add kol wiki schema validator"
```

---

## Task 3: Bootstrap Prompt Pack Mode

**Files:**
- Modify: `plugins/kol-tools/scripts/kol_distill.py`
- Modify: `plugins/kol-tools/scripts/tests/test_kol_distill.py`
- Create: `plugins/kol-tools/templates/bootstrap-wiki-prompt.md`
- Modify: `plugins/kol-tools/skills/kol-distill/references/usage.md`

- [ ] **Step 1: Write failing test for bootstrap-pack**

Append to `plugins/kol-tools/scripts/tests/test_kol_distill.py`:

```python
    def test_bootstrap_pack_uses_selected_high_medium_items_without_delta_file(self):
        with tempfile.TemporaryDirectory() as td:
            vault = Path(td) / "vault"
            wiki = vault / "h" / "wiki"
            wiki.mkdir(parents=True)
            clean = wiki / ".clean_corpus.jsonl"
            write_jsonl(clean, [
                {"id": "1", "date": "2026-01-01", "text": "$NVDA 因为需求强", "quality": "high", "routing": {"distill": True}},
                {"id": "2", "date": "2026-01-02", "text": "普通闲聊", "quality": "low", "routing": {"distill": False}},
                {"id": "3", "date": "2026-01-03", "text": "现金流和估值是关键", "quality": "medium", "routing": {"distill": True}},
            ])

            out = StringIO()
            with redirect_stdout(out):
                rc = main([
                    "h",
                    "--vault",
                    str(vault),
                    "--mode",
                    "bootstrap-pack",
                    "--pack-id",
                    "bootstrap-test",
                    "--bootstrap-limit",
                    "10",
                ])

            self.assertEqual(rc, 0)
            result = json.loads(out.getvalue())
            self.assertEqual(result["status"], "bootstrap_pack_ready")
            workspace = Path(result["workspace"])
            rows = [json.loads(line) for line in (workspace / "delta_items.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual([row["id"] for row in rows], ["1", "3"])
            self.assertTrue((workspace / "prompts" / "00-bootstrap-wiki.md").exists())
```

- [ ] **Step 2: Run distill tests and verify red**

Run:

```bash
python3 -m unittest plugins/kol-tools/scripts/tests/test_kol_distill.py
```

Expected: FAIL because `bootstrap-pack` is not a valid mode.

- [ ] **Step 3: Implement bootstrap-pack CLI mode**

Modify `plugins/kol-tools/scripts/kol_distill.py`:

- Add `bootstrap-pack` to `--mode` choices.
- Add `--bootstrap-limit` default `300`.
- Add `load_bootstrap_items(vault, handle, limit)`:

```python
def load_bootstrap_items(vault: Path, handle: str, limit: int) -> list[dict[str, Any]]:
    clean = wiki_dir(vault, handle) / ".clean_corpus.jsonl"
    rows = []
    for row in load_jsonl(clean):
        routing = row.get("routing") if isinstance(row.get("routing"), dict) else {}
        if row.get("quality") in {"high", "medium"} and routing.get("distill"):
            rows.append(normalize_item(row))
    rows.sort(key=lambda item: (item.get("quality") != "high", item.get("date", ""), item.get("id", "")))
    return rows[:limit]
```

- Add bootstrap `info` shape:

```python
info = {
    "handle": args.handle,
    "status": "ready",
    "delta": len(items),
    "replies": sum(1 for item in items if item.get("is_reply")),
    "watermark_old": "bootstrap",
    "watermark_proposed": max((item["id"] for item in items), default="bootstrap"),
    "date_range": [items[0]["date"], items[-1]["date"]] if items else [],
    "source": str(wiki_dir(args.vault, args.handle) / ".clean_corpus.jsonl"),
}
```

- Write `prompts/00-bootstrap-wiki.md` using `plugins/kol-tools/templates/bootstrap-wiki-prompt.md`.

- [ ] **Step 4: Add bootstrap template**

Create `plugins/kol-tools/templates/bootstrap-wiki-prompt.md`:

```markdown
# Bootstrap KOL Wiki Prompt

Build the initial durable KOL wiki from this prompt pack.

Read first:

- `manifest.json`
- `schema_manifest.json`
- `delta_items.jsonl`
- `delta_brief.md`

Write or update these durable pages only after review:

- `wiki/_index.md`
- `wiki/soul.md`
- `wiki/timeline.md`
- `wiki/sources/*.md`
- `wiki/methods/*.md`
- `wiki/positions/*.md`

Rules:

- Every durable claim must cite tweet ids.
- Mark inferred stance as inferred.
- Preserve out-of-coverage boundaries.
- Do not advance `.ingest_meta.json`.
- Treat `soul.md` as high risk.
```

- [ ] **Step 5: Run tests and verify green**

Run:

```bash
python3 -m unittest plugins/kol-tools/scripts/tests/test_kol_distill.py
```

Expected: OK.

- [ ] **Step 6: Commit**

```bash
git add plugins/kol-tools/scripts/kol_distill.py plugins/kol-tools/scripts/tests/test_kol_distill.py plugins/kol-tools/templates/bootstrap-wiki-prompt.md plugins/kol-tools/skills/kol-distill/references/usage.md
git commit -m "feat: add kol bootstrap distill packs"
```

---

## Task 4: Schema-Aware Validate Integration

**Files:**
- Modify: `plugins/kol-tools/scripts/kol_distill.py`
- Modify: `plugins/kol-tools/scripts/tests/test_kol_distill.py`
- Modify: `plugins/kol-tools/scripts/kol_schema_validate.py`
- Modify: `plugins/kol-tools/scripts/tests/test_kol_schema_validate.py`

- [ ] **Step 1: Write failing test that `kol_distill validate` includes schema issues**

Append to `test_kol_distill.py`:

```python
    def test_validate_reports_schema_issues_for_changed_files(self):
        with tempfile.TemporaryDirectory() as td:
            vault = self.build_low_risk_vault(Path(td))
            out = StringIO()
            with redirect_stdout(out):
                self.assertEqual(main(["h", "--vault", str(vault), "--mode", "prompt-pack", "--pack-id", "schema-pack"]), 0)
            with redirect_stdout(StringIO()):
                self.assertEqual(main(["h", "--vault", str(vault), "--mode", "apply", "--pack-id", "schema-pack"]), 0)
            bad_source = vault / "h" / "wiki" / "sources" / "杂感与社区互动.md"
            bad_source.write_text("# broken\n201\n", encoding="utf-8")

            out = StringIO()
            with redirect_stdout(out):
                rc = main(["h", "--vault", str(vault), "--mode", "validate", "--pack-id", "schema-pack"])

            result = json.loads(out.getvalue())
            self.assertEqual(rc, 2)
            self.assertEqual(result["status"], "validation_failed")
            self.assertTrue(any("schema" in issue for issue in result["blockers"]))
```

- [ ] **Step 2: Run test and verify red**

Run:

```bash
python3 -m unittest plugins/kol-tools/scripts/tests/test_kol_distill.py
```

Expected: FAIL because validate currently checks tweet-id coverage but not page schema.

- [ ] **Step 3: Reuse schema validator inside distill validate**

Modify `plugins/kol-tools/scripts/kol_distill.py`:

```python
from kol_schema_validate import validate_file
```

Inside `validate_workspace`, after `markdown = durable_markdown_files(wdir)`:

```python
schema_results = [validate_file(path) for path in markdown]
for result in schema_results:
    for issue in result["issues"]:
        blockers.append(f"schema issue in {result['path']}: {issue}")
```

Add `schema_results` to `validation_result.json`.

- [ ] **Step 4: Run tests and verify green**

Run:

```bash
python3 -m unittest plugins/kol-tools/scripts/tests/test_kol_distill.py plugins/kol-tools/scripts/tests/test_kol_schema_validate.py
```

Expected: OK.

- [ ] **Step 5: Commit**

```bash
git add plugins/kol-tools/scripts/kol_distill.py plugins/kol-tools/scripts/tests/test_kol_distill.py plugins/kol-tools/scripts/kol_schema_validate.py plugins/kol-tools/scripts/tests/test_kol_schema_validate.py
git commit -m "feat: validate kol wiki schema during distill"
```

---

## Task 5: Batch Rollout Orchestrator

**Files:**
- Create: `plugins/kol-tools/scripts/kol_rollout.py`
- Create: `plugins/kol-tools/scripts/tests/test_kol_rollout.py`
- Modify: `plugins/kol-tools/README.md`
- Create: `plugins/kol-tools/docs/rollout.md`

- [ ] **Step 1: Write failing tests for dry-run rollout plan**

Create `plugins/kol-tools/scripts/tests/test_kol_rollout.py`:

```python
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kol_rollout import build_plan


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


class KolRolloutTests(unittest.TestCase):
    def test_build_plan_routes_bootstrap_and_incremental_handles(self):
        with tempfile.TemporaryDirectory() as td:
            vault = Path(td)
            for handle in ["bootstrap", "mature"]:
                wiki = vault / handle / "wiki"
                wiki.mkdir(parents=True)
                write_jsonl(wiki / ".clean_corpus.jsonl", [{"id": "1", "text": "x", "quality": "high", "routing": {"distill": True}}])
                write_jsonl(wiki / ".ingest_index.jsonl", [{"id": "1", "text": "x"}])
                (wiki / ".ingest_stats.json").write_text(json.dumps({"total": 1, "source": str(wiki / ".clean_corpus.jsonl")}), encoding="utf-8")
            mature = vault / "mature" / "wiki"
            for name in ["_index.md", "soul.md", "timeline.md"]:
                (mature / name).write_text("# ok\n- 1\n", encoding="utf-8")
            for subdir in ["sources", "methods", "positions"]:
                (mature / subdir).mkdir()
                (mature / subdir / "sample.md").write_text("# sample\n\n## Evidence\n- 1\n", encoding="utf-8")

            plan = build_plan(vault, handles=["bootstrap", "mature"])

            actions = {item["handle"]: item["action"] for item in plan["items"]}
            self.assertEqual(actions["bootstrap"], "bootstrap-pack")
            self.assertEqual(actions["mature"], "delta")
```

- [ ] **Step 2: Run test and verify red**

Run:

```bash
python3 -m unittest plugins/kol-tools/scripts/tests/test_kol_rollout.py
```

Expected: FAIL with missing module.

- [ ] **Step 3: Implement dry-run rollout plan**

Create `plugins/kol-tools/scripts/kol_rollout.py`:

```python
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from kol_common import DEFAULT_VAULT
from kol_wiki_inventory import classify_handle, iter_handles


def build_plan(vault: Path, handles: list[str] | None = None) -> dict[str, Any]:
    selected = handles or iter_handles(vault)
    items = []
    for handle in selected:
        inventory = classify_handle(vault, handle)
        if inventory["route"] == "existing_mature_wiki":
            action = "delta"
        elif inventory["route"] in {"partial_wiki_repair", "bootstrap_required"}:
            action = "bootstrap-pack"
        else:
            action = "blocked"
        items.append({"handle": handle, "action": action, "inventory": inventory})
    return {"vault": str(vault), "items": items}


def run_command(command: list[str], cwd: Path) -> dict[str, Any]:
    proc = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    payload = json.loads(proc.stdout) if proc.stdout.strip().startswith("{") else {"stdout": proc.stdout.strip()}
    payload["returncode"] = proc.returncode
    if proc.stderr.strip():
        payload["stderr"] = proc.stderr.strip()
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plan or run KOL Twin wiki rollout.")
    parser.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    parser.add_argument("--handles", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    handles = [h.strip() for h in args.handles.split(",") if h.strip()] or None
    plan = build_plan(args.vault, handles)
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests and verify green**

Run:

```bash
python3 -m unittest plugins/kol-tools/scripts/tests/test_kol_rollout.py
```

Expected: OK.

- [ ] **Step 5: Run dry-run on real vault**

Run:

```bash
python3 plugins/kol-tools/scripts/kol_rollout.py --vault /Users/saberrao/vault/kol --dry-run
```

Expected:

- Prints all handles and selected action.
- No vault files are modified.

- [ ] **Step 6: Document rollout command**

Create `plugins/kol-tools/docs/rollout.md` with:

```markdown
# KOL Twin Wiki Rollout

Start with dry-run:

```bash
python3 plugins/kol-tools/scripts/kol_rollout.py --vault /Users/saberrao/vault/kol --dry-run
```

Recommended order:

1. `TJ_Research`
2. `tig88411109`
3. `aleabitoreddit`
4. `qinbafrank`
5. remaining handles by inventory route and review cost

Never commit ingest watermarks before validation marks `safe_to_commit_watermark: true`.
```

- [ ] **Step 7: Commit**

```bash
git add plugins/kol-tools/scripts/kol_rollout.py plugins/kol-tools/scripts/tests/test_kol_rollout.py plugins/kol-tools/docs/rollout.md plugins/kol-tools/README.md
git commit -m "feat: add kol wiki rollout planner"
```

---

## Task 6: Pilot TJ_Research Audit And Repair

**Files:**
- Runtime output under `/Users/saberrao/vault/kol/TJ_Research/wiki/.distill_prompt_packs/`
- Durable wiki files only if review path requires repair

- [ ] **Step 1: Inventory TJ**

Run:

```bash
python3 plugins/kol-tools/scripts/kol_wiki_inventory.py --vault /Users/saberrao/vault/kol --handle TJ_Research
```

Expected:

- Route is `existing_mature_wiki` or `partial_wiki_repair`.
- If route is `partial_wiki_repair`, inspect issues before generating new packs.

- [ ] **Step 2: Validate TJ durable wiki schema**

Run:

```bash
python3 plugins/kol-tools/scripts/kol_schema_validate.py TJ_Research --vault /Users/saberrao/vault/kol
```

Expected:

- If validation fails, save JSON output as review context.
- Do not directly rewrite `soul.md`.

- [ ] **Step 3: Repair old TJ prompt pack audit if needed**

Known older pack:

```text
/Users/saberrao/vault/kol/TJ_Research/wiki/.distill_prompt_packs/delta-2069392786437087338-20260623-150543/
```

Run:

```bash
python3 plugins/kol-tools/scripts/kol_distill.py TJ_Research \
  --vault /Users/saberrao/vault/kol \
  --mode validate \
  --pack-id delta-2069392786437087338-20260623-150543
```

Expected:

- If validation fails because old pack lacks `risk_assessment.json` or `schema_manifest.json`, generate a fresh pack for the same delta with a new pack id.
- Do not delete the old pack.

- [ ] **Step 4: Generate fresh TJ prompt pack when needed**

Run:

```bash
python3 plugins/kol-tools/scripts/kol_distill.py TJ_Research \
  --vault /Users/saberrao/vault/kol \
  --mode prompt-pack \
  --pack-id tj-repair-2069392786437087338 \
  --policy balanced
```

Expected:

- Pack contains `schema_manifest.json`.
- Pack contains `risk_assessment.json`.
- Review status is likely `blocked` or `user_review_required` if subscriber/private evidence or soul/timeline scope exists.

- [ ] **Step 5: Review TJ result**

Open:

```text
/Users/saberrao/vault/kol/TJ_Research/wiki/.distill_prompt_packs/tj-repair-2069392786437087338/delta_brief.md
/Users/saberrao/vault/kol/TJ_Research/wiki/.distill_prompt_packs/tj-repair-2069392786437087338/risk_assessment.json
```

Expected:

- If `blocked`, do not apply.
- If `user_review_required`, prepare a short review summary before `--force`.
- If `auto_eligible`, apply/validate/commit may proceed.

- [ ] **Step 6: Commit only if validation is safe**

Only run after validation is safe:

```bash
python3 plugins/kol-tools/scripts/kol_distill.py TJ_Research \
  --vault /Users/saberrao/vault/kol \
  --mode commit \
  --pack-id <safe-pack-id>
```

Expected:

- Commit refuses unless `validation_result.json` has `safe_to_commit_watermark: true`.

---

## Task 7: Roll Out Remaining KOLs In Batches

**Files:**
- Runtime prompt packs under `/Users/saberrao/vault/kol/<handle>/wiki/.distill_prompt_packs/`
- Durable wiki files under `/Users/saberrao/vault/kol/<handle>/wiki/`

- [ ] **Step 1: Choose rollout order**

Use the initial corpus distribution:

```text
Tier 1: TJ_Research, tig88411109
Tier 2: aleabitoreddit, qinbafrank
Tier 3: tychozzz, iamai_omni, dearbaibabybus
Tier 4: Corsica267, ShanghaoJin, LinQingV, jukan05, AswathDamodaran
```

Rationale:

- Tier 1 has high value and either existing wiki or high signal density.
- Tier 2 has strong signal but larger review cost.
- Tier 3 has large corpora and needs careful topic grouping.
- Tier 4 has lower volume or noisier reply distribution.

- [ ] **Step 2: For each handle, run inventory**

Run:

```bash
python3 plugins/kol-tools/scripts/kol_wiki_inventory.py --vault /Users/saberrao/vault/kol --handle <handle>
```

Expected:

- Route determines whether to use `prompt-pack` or `bootstrap-pack`.

- [ ] **Step 3: For bootstrap handles, generate bootstrap pack**

Run:

```bash
python3 plugins/kol-tools/scripts/kol_distill.py <handle> \
  --vault /Users/saberrao/vault/kol \
  --mode bootstrap-pack \
  --pack-id <handle>-bootstrap-001 \
  --bootstrap-limit 300 \
  --policy conservative
```

Expected:

- Pack is high-risk or user-review-required.
- It writes no durable wiki pages by itself.

- [ ] **Step 4: For mature handles, compute delta**

Run:

```bash
python3 plugins/kol-tools/scripts/kol_delta.py <handle> --vault /Users/saberrao/vault/kol --cap 120
```

Expected:

- `bootstrap`: no delta to process, existing archive already watermarked.
- `none`: no new delta.
- `ready`: continue to prompt-pack.
- `over_cap`: user/agent review required before proceeding.

- [ ] **Step 5: For ready deltas, generate prompt-pack**

Run:

```bash
python3 plugins/kol-tools/scripts/kol_distill.py <handle> \
  --vault /Users/saberrao/vault/kol \
  --mode prompt-pack \
  --policy balanced
```

Expected:

- Pack has schema bundle, risk assessment, delta brief, prompts.

- [ ] **Step 6: Apply only safe packs**

For `auto_eligible`:

```bash
python3 plugins/kol-tools/scripts/kol_distill.py <handle> \
  --vault /Users/saberrao/vault/kol \
  --mode apply \
  --pack-id <pack-id>
```

For `agent_review_required` or `user_review_required`, do not apply automatically. Review `delta_brief.md`, `risk_assessment.json`, and schema prompts first. Use `--force` only after review:

```bash
python3 plugins/kol-tools/scripts/kol_distill.py <handle> \
  --vault /Users/saberrao/vault/kol \
  --mode apply \
  --pack-id <pack-id> \
  --force
```

- [ ] **Step 7: Validate after every apply**

Run:

```bash
python3 plugins/kol-tools/scripts/kol_distill.py <handle> \
  --vault /Users/saberrao/vault/kol \
  --mode validate \
  --pack-id <pack-id>
```

Expected:

- Tweet id coverage is complete.
- Schema validation is clean enough to commit.
- `safe_to_commit_watermark` is true.

- [ ] **Step 8: Commit watermark**

Run:

```bash
python3 plugins/kol-tools/scripts/kol_distill.py <handle> \
  --vault /Users/saberrao/vault/kol \
  --mode commit \
  --pack-id <pack-id>
```

Expected:

- `.ingest_meta.json` advances only after validation.

---

## Task 8: Query Runtime Evaluation

**Files:**
- Modify: `plugins/kol-tools/scripts/kol_ask.py` only if evaluation reveals missing source loading.
- Modify: `plugins/kol-tools/scripts/tests/test_kol_ask.py`
- Create: `plugins/kol-tools/docs/evaluation.md`

- [ ] **Step 1: Create evaluation questions**

Create `plugins/kol-tools/docs/evaluation.md`:

```markdown
# KOL Twin Evaluation

## TJ_Research

1. 怎么看 AI capex 是不是泡沫？
2. 怎么看 NVDA 的估值？
3. 怎么看美联储路径？
4. 哪些问题超出 TJ 的覆盖范围？

## tig88411109

1. 怎么看开源模型降价？
2. 怎么看 AI 算力需求？
3. 哪些回复体现其核心方法论？

## Expected Answer Rules

- Must include confidence.
- Must include in_comfort_zone.
- Must include wikilinks.
- Must include primary tweet ids when possible.
- Must say out of coverage instead of inventing.
```

- [ ] **Step 2: Run context-pack for each Tier 1 KOL**

Run:

```bash
python3 plugins/kol-tools/scripts/kol_ask.py TJ_Research \
  --vault /Users/saberrao/vault/kol \
  --question "怎么看 AI capex 是不是泡沫？" \
  --mode context-pack
```

Expected:

- Context pack includes `soul.md`.
- Context pack includes relevant `methods/*.md`.
- Context pack includes relevant `sources/*.md`.
- Context pack includes relevant `positions/*.md` when question includes ticker.

- [ ] **Step 3: Patch `kol_ask.py` only if context loading misses required pages**

If `methods/ai-capex-roi.md` or AI source pages are missing for AI capex questions, add a focused test in `test_kol_ask.py` and fix the selector.

- [ ] **Step 4: Commit evaluation docs or runtime fix**

```bash
git add plugins/kol-tools/docs/evaluation.md plugins/kol-tools/scripts/kol_ask.py plugins/kol-tools/scripts/tests/test_kol_ask.py
git commit -m "test: add kol twin evaluation coverage"
```

---

## Task 9: Final Verification And Report

**Files:**
- Create runtime report under `/Users/saberrao/vault/kol/_cross/rollout_report_<date>.json`
- Optionally create repo doc `plugins/kol-tools/docs/rollout-results.md`

- [ ] **Step 1: Run all tests**

Run:

```bash
python3 -m unittest discover -s plugins/kol-tools/scripts/tests -p 'test_*.py'
python3 -m py_compile plugins/kol-tools/scripts/kol_distill.py plugins/kol-tools/scripts/kol_wiki_inventory.py plugins/kol-tools/scripts/kol_schema_validate.py plugins/kol-tools/scripts/kol_rollout.py
```

Expected: all tests pass.

- [ ] **Step 2: Validate plugin and skills**

Run:

```bash
uvx --with pyyaml python /Users/saberrao/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py plugins/kol-tools
uvx --with pyyaml python /Users/saberrao/.codex/skills/.system/skill-creator/scripts/quick_validate.py plugins/kol-tools/skills/kol-distill
uvx --with pyyaml python /Users/saberrao/.codex/skills/.system/skill-creator/scripts/quick_validate.py plugins/kol-tools/skills/kol-ask
uvx --with pyyaml python /Users/saberrao/.codex/skills/.system/skill-creator/scripts/quick_validate.py plugins/kol-tools/skills/kol-debate
```

Expected: all validations pass.

- [ ] **Step 3: Run final inventory**

Run:

```bash
python3 plugins/kol-tools/scripts/kol_wiki_inventory.py --vault /Users/saberrao/vault/kol
```

Expected:

- No handle is `not_ready`.
- Any remaining `partial_wiki_repair` handle is explicitly listed with reason.

- [ ] **Step 4: Run schema validation for all processed handles**

Run:

```bash
for h in TJ_Research tig88411109 aleabitoreddit qinbafrank tychozzz iamai_omni dearbaibabybus Corsica267 ShanghaoJin LinQingV jukan05 AswathDamodaran; do
  python3 plugins/kol-tools/scripts/kol_schema_validate.py "$h" --vault /Users/saberrao/vault/kol || true
done
```

Expected:

- Critical missing evidence issues are fixed.
- Remaining noncritical schema issues are documented.

- [ ] **Step 5: Commit final code/docs**

```bash
git status --short
git add plugins/kol-tools
git commit -m "feat: productize kol twin llm wiki rollout"
```

Only commit repo code/docs. Do not commit vault runtime data.

---

## Risk Controls

- Do not mutate raw tweets.
- Do not commit vault data into git.
- Do not advance `.ingest_meta.json` without validation.
- Treat subscriber/private evidence as blocked.
- Treat `soul.md` updates as high risk.
- Require tweet id evidence for durable wiki claims.
- Keep explicit/inferred/out-of-coverage separated in query answers.
- Keep `tweet-pool` as cache, not workflow state.

## Acceptance Criteria

Code-level:

- Inventory, schema validation, bootstrap-pack, rollout planner tests pass.
- Existing 37 kol-tools tests still pass.
- Plugin validation passes.
- Distill packs include schema bundle and risk assessment.
- Validate refuses incomplete packs.

Data-level:

- Every processed KOL has:
  - `.clean_corpus.jsonl`
  - `.ingest_index.jsonl`
  - `.ingest_stats.json`
  - `_index.md`
  - `soul.md`
  - `timeline.md`
  - nonempty `sources/`, `methods/`, or `positions/` as appropriate
- Every committed pack has:
  - `manifest.json`
  - `schema_manifest.json`
  - `risk_assessment.json`
  - `validation_result.json`
  - `commit_result.json`
- Watermark moves only after `safe_to_commit_watermark: true`.

Product-level:

- `kol-ask` can answer Tier 1 KOL questions with wikilinks and confidence metadata.
- Out-of-coverage questions are rejected clearly.
- Multi-KOL debate can load at least two processed KOL wikis.

## Recommended Execution Strategy

Use subagent-driven development for Tasks 1-5 because they are independent code/tooling units. Use inline execution for Tasks 6-9 because they operate on the real vault and need tighter human-visible checkpoints.

Recommended order:

1. Implement Tasks 1-5 in repo.
2. Run pilot on `TJ_Research`.
3. Run pilot on `tig88411109`.
4. Batch remaining KOLs by tier.
5. Run query/debate evaluation.
6. Produce final rollout report.
