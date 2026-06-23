# KOL Tools Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the existing local KOL digital-twin project into a dual Codex/Claude plugin that separates X/Twitter fetching, KOL corpus cleaning, deterministic indexing, LLM distillation, single-KOL asking, and multi-KOL debate.

**Architecture:** `twitter-tools/twitter-fetch` remains the lower-level X/Twitter data fetcher and emits JSON/JSONL only. The new `kol-tools` plugin owns KOL-specific vault writes, raw backfill state, cleaning/scoring, index metadata, distillation prompts, and ask/debate runtime. The existing `/Users/saberrao/vault/kol/` remains the authoritative data and knowledge vault; the plugin contains code, docs, prompts, and tests only.

**Tech Stack:** Python 3 standard library, existing `twitter-fetch` CLI, Markdown/YAML/JSONL vault artifacts, Codex/Claude plugin manifests, unittest/pytest-compatible tests.

---

## Scope And Non-Goals

This refactor must preserve the valuable existing KOL artifacts:

- `wiki/soul.md`
- `wiki/methods/*.md`
- `wiki/positions/*.md`
- `wiki/sources/*.md`
- `wiki/timeline.md`
- `wiki/.ingest_index.jsonl`
- `wiki/.ingest_meta.json`
- `raw/tweets/*.md`
- `_cross/_registry.md`
- `_cross/topic_registry.md`
- `_cross/debates/*`

This refactor must remove direct reliance on the retired local path:

```text
/Users/saberrao/.codex/skills/twitter-monitor/scripts/fetch_user_history.py
```

Non-goals for the first implementation pass:

- Do not rewrite all existing KOL wiki pages.
- Do not delete existing raw tweets.
- Do not publish or commit runtime KOL raw data.
- Do not expose paid subscriber content outside the private vault.
- Do not force a vector database; start with deterministic JSON/JSONL and Markdown routing.

## Target Capability Model

The plugin should expose these agent-facing skills:

```text
kol-refresh
  Fetch or import KOL raw content and update raw backfill state.

kol-clean
  Score raw tweets/replies/quotes and produce a clean corpus for downstream distillation.

kol-index
  Build deterministic .ingest_index.jsonl and .ingest_stats.json from raw Markdown.

kol-distill
  Turn clean/indexed corpus into sources/methods/positions/timeline/soul using prompts.

kol-ask
  Answer a user question from one KOL's archive plus relevant invest wiki context.

kol-debate
  Orchestrate multiple KOL twins into blind round, rebuttal round, and synthesis.
```

The first execution phase should create `kol-tools` with `kol-clean`, `kol-index`, and basic docs first. `kol-refresh`, `kol-distill`, `kol-ask`, and `kol-debate` are added after the plugin skeleton and clean/index migration are stable.

## Data Contract

### Raw Layer

Path:

```text
/Users/saberrao/vault/kol/<handle>/raw/tweets/<tweet_id>.md
/Users/saberrao/vault/kol/<handle>/raw/.backfill_state.json
```

Raw files are audit evidence. Do not delete raw tweets during cleaning. Low-quality content is tagged out of downstream use instead.

### Clean Layer

New generated file:

```text
/Users/saberrao/vault/kol/<handle>/wiki/.clean_corpus.jsonl
```

Each line should contain:

```json
{
  "id": "2053264927947673822",
  "date": "2026-05-10T00:00:00Z",
  "url": "https://x.com/TJ_Research/status/2053264927947673822",
  "text": "tweet body",
  "is_reply": false,
  "is_quote": false,
  "is_retweet": false,
  "conversation_id": "2053264927947673822",
  "reply_to": null,
  "quality": "high",
  "content_density": 0.86,
  "routing": {
    "distill": true,
    "voice": true,
    "timeline": false,
    "position": true
  },
  "reasons": ["has_ticker", "has_reasoning", "has_position"],
  "source_type": "x_public",
  "visibility": "private"
}
```

Allowed `quality` values:

```text
high
medium
low
noise
```

Allowed `source_type` values:

```text
x_public
x_reply
x_quote
x_subscriber
manual_article
unknown
```

Allowed `visibility` values:

```text
public_reference
private
subscriber_private
```

### Index Layer

Existing generated files remain:

```text
/Users/saberrao/vault/kol/<handle>/wiki/.ingest_index.jsonl
/Users/saberrao/vault/kol/<handle>/wiki/.ingest_stats.json
/Users/saberrao/vault/kol/<handle>/wiki/.ingest_meta.json
```

`kol-index` can initially keep the current `.ingest_index.jsonl` schema for compatibility, then add clean fields only when downstream code is ready.

### Registry Layer

Keep human-facing Markdown for now:

```text
/Users/saberrao/vault/kol/_cross/_registry.md
```

Add a machine-readable health report before converting the registry itself:

```text
/Users/saberrao/vault/kol/_cross/registry_health.json
```

This avoids a risky registry format migration at the same time as plugin migration.

## File Structure

Create:

```text
plugins/kol-tools/
  .codex-plugin/plugin.json
  .claude-plugin/plugin.json
  README.md
  skills/
    kol-clean/
      SKILL.md
      agents/openai.yaml
      references/schema.md
      references/usage.md
      scripts/kol_clean.py
      scripts/tests/test_kol_clean.py
    kol-index/
      SKILL.md
      agents/openai.yaml
      references/schema.md
      references/usage.md
      scripts/kol_index.py
      scripts/tests/test_kol_index.py
    kol-refresh/
      SKILL.md
      agents/openai.yaml
      references/usage.md
      scripts/kol_refresh.py
      scripts/twitter_fetch_runner.py
      scripts/tests/test_kol_refresh_cli.py
    kol-ask/
      SKILL.md
      agents/openai.yaml
      references/runtime.md
    kol-debate/
      SKILL.md
      agents/openai.yaml
      references/runtime.md
      scripts/kol_debate.py
      scripts/tests/test_kol_debate_cli.py
  templates/
    persona-system-prompt.md
    kol-ingest-phaseB-cluster.md
    kol-ingest-phaseC-sources.md
    kol-ingest-phaseC-methods-positions.md
    kol-ingest-phaseC-timeline-soul.md
  scripts/
    registry_health.py
    tests/test_registry_health.py
```

Modify:

```text
.agents/plugins/marketplace.json
.claude-plugin/marketplace.json
```

Do not modify in phase 1:

```text
/Users/saberrao/vault/kol/**/*
/Users/saberrao/.codex/skills/kol-twin/**/*
```

Phase 1 is packaging and read-only-compatible scripts only. Vault writes begin only when running explicit test commands against temporary fixtures or when the user confirms migration.

## Task 1: Create `kol-tools` Plugin Skeleton

**Files:**

- Create: `plugins/kol-tools/.codex-plugin/plugin.json`
- Create: `plugins/kol-tools/.claude-plugin/plugin.json`
- Create: `plugins/kol-tools/README.md`
- Modify: `.agents/plugins/marketplace.json`
- Modify: `.claude-plugin/marketplace.json`

- [ ] **Step 1: Add Codex plugin manifest**

Create `plugins/kol-tools/.codex-plugin/plugin.json`:

```json
{
  "name": "kol-tools",
  "version": "0.1.0",
  "description": "Build and query private KOL digital-twin archives from fetched social content.",
  "author": {
    "name": "saberrao"
  },
  "skills": "./skills/",
  "interface": {
    "displayName": "KOL Tools",
    "shortDescription": "Build and query KOL digital twins.",
    "longDescription": "KOL Tools turns fetched X/Twitter history, replies, quotes, subscriber imports, and manual articles into private KOL archives with cleaning, deterministic indexing, distillation prompts, single-KOL ask, and multi-KOL debate workflows. It depends on twitter-tools for X/Twitter fetching and keeps private vault data outside the plugin.",
    "developerName": "saberrao",
    "category": "Productivity",
    "capabilities": [
      "Refresh KOL raw archives",
      "Clean low-density posts",
      "Index KOL corpora",
      "Distill KOL methods and positions",
      "Ask one KOL twin",
      "Debate multiple KOL twins"
    ],
    "defaultPrompt": "Use private KOL archives to refresh, distill, ask, or debate KOL digital twins."
  }
}
```

- [ ] **Step 2: Add Claude plugin manifest**

Create `plugins/kol-tools/.claude-plugin/plugin.json` with the same fields as the Codex manifest. Keep version equal to `0.1.0`.

- [ ] **Step 3: Add human README**

Create `plugins/kol-tools/README.md` with these sections:

```markdown
# KOL Tools

KOL Tools is a private KOL digital-twin plugin for Codex and Claude Code.

## What It Does

- Maintains raw KOL archives under `/Users/saberrao/vault/kol/`.
- Cleans low-information tweets without deleting raw data.
- Preserves substantive replies and routes them into methods, positions, sources, voice, or timeline.
- Builds deterministic indexes and stats.
- Provides prompts and scripts for KOL distillation, ask, and debate workflows.

## What It Does Not Do

- It does not fetch X/Twitter directly inside the low-level fetcher. It calls `twitter-tools/twitter-fetch`.
- It does not publish KOL twin output.
- It does not commit raw tweets, cookies, subscriber posts, or runtime state.
- It does not impersonate a KOL as the real person.

## Runtime Data

The authoritative KOL vault is:

```text
/Users/saberrao/vault/kol/
```

Override:

```bash
export KOL_TOOLS_VAULT=/path/to/kol
```

## Install

From the `awesome-ai` repository root:

```bash
codex plugin marketplace add .
codex plugin add kol-tools@awesome-ai
claude plugin marketplace add ./
claude plugin install kol-tools@awesome-ai
```

## First Run

The plugin can create derived files such as `.clean_corpus.jsonl`, `.ingest_index.jsonl`, and health reports. It will not create credentials or scrape browser cookies.

## Privacy

Raw tweets and subscriber-only content remain private. Do not publish generated twin output as if it were written by the KOL.
```

- [ ] **Step 4: Register plugin in marketplaces**

Append a `kol-tools` entry to `.agents/plugins/marketplace.json`:

```json
{
  "name": "kol-tools",
  "source": {
    "source": "local",
    "path": "./plugins/kol-tools"
  },
  "policy": {
    "installation": "AVAILABLE",
    "authentication": "ON_INSTALL"
  },
  "category": "Productivity"
}
```

Append the equivalent entry to `.claude-plugin/marketplace.json`.

- [ ] **Step 5: Validate JSON**

Run:

```bash
python3 -m json.tool plugins/kol-tools/.codex-plugin/plugin.json >/dev/null
python3 -m json.tool plugins/kol-tools/.claude-plugin/plugin.json >/dev/null
python3 -m json.tool .agents/plugins/marketplace.json >/dev/null
python3 -m json.tool .claude-plugin/marketplace.json >/dev/null
```

Expected: all commands exit `0`.

## Task 2: Implement `kol-clean`

**Files:**

- Create: `plugins/kol-tools/skills/kol-clean/SKILL.md`
- Create: `plugins/kol-tools/skills/kol-clean/agents/openai.yaml`
- Create: `plugins/kol-tools/skills/kol-clean/references/schema.md`
- Create: `plugins/kol-tools/skills/kol-clean/references/usage.md`
- Create: `plugins/kol-tools/skills/kol-clean/scripts/kol_clean.py`
- Create: `plugins/kol-tools/skills/kol-clean/scripts/tests/test_kol_clean.py`

- [ ] **Step 1: Write tests for quality scoring**

Create tests that cover:

```python
from kol_clean import classify_text


def test_reply_with_finance_signal_is_not_noise():
    item = classify_text("@abc 这个用 forward PE 看，不看 TTM。", is_reply=True)
    assert item["quality"] in {"high", "medium"}
    assert item["routing"]["distill"] is True
    assert "has_method_keyword" in item["reasons"]


def test_short_social_reply_is_noise_for_distill_but_voice_candidate():
    item = classify_text("@abc 哈哈哈", is_reply=True)
    assert item["quality"] == "noise"
    assert item["routing"]["distill"] is False
    assert item["routing"]["voice"] is True


def test_ticker_reasoning_is_high_quality():
    item = classify_text("$NVDA PEG 1 倍不贵，因为未来三年 EPS 增速还在。", is_reply=False)
    assert item["quality"] == "high"
    assert item["routing"]["position"] is True
    assert "has_ticker" in item["reasons"]
    assert "has_reasoning" in item["reasons"]
```

- [ ] **Step 2: Implement `classify_text`**

Implement deterministic heuristics:

```text
signals:
  has_ticker: `$[A-Za-z]{1,6}`
  has_percent_or_number: percentage or large number
  has_method_keyword: FPE, PE, PEG, capex, ARR, 估值, 降息, 加仓, 减仓, 看多, 看空, 左侧, 右侧, 仓位
  has_reasoning: 因为, 所以, 但是, 如果, 只要, 证伪, ROI, 现金流
  has_url_only: URL-only after stripping whitespace
  is_social_short_reply: reply with stripped length < 20 and no signal
```

Routing rules:

```text
distill = high or medium
position = has_ticker or has_position_keyword
timeline = has_time_change_keyword
voice = any non-empty text, including social replies
```

- [ ] **Step 3: Implement raw Markdown parser**

Parse existing frontmatter/body files from:

```text
<vault>/<handle>/raw/tweets/*.md
```

Do not require PyYAML. Use the existing simple `key: value` parser style from `ingest_index_build.py`.

- [ ] **Step 4: Implement CLI**

CLI:

```bash
python3 scripts/kol_clean.py TJ_Research --vault /Users/saberrao/vault/kol --dry-run
python3 scripts/kol_clean.py TJ_Research --vault /Users/saberrao/vault/kol --write
```

Behavior:

```text
--dry-run prints JSON stats only
--write writes <vault>/<handle>/wiki/.clean_corpus.jsonl and prints JSON stats
```

Expected stats keys:

```json
{
  "handle": "TJ_Research",
  "total": 2607,
  "quality": {"high": 100, "medium": 200, "low": 300, "noise": 400},
  "replies": 1614,
  "substantive_replies": 878,
  "output": "/Users/saberrao/vault/kol/TJ_Research/wiki/.clean_corpus.jsonl"
}
```

- [ ] **Step 5: Run tests**

Run:

```bash
PYTHONPATH=plugins/kol-tools/skills/kol-clean/scripts \
python3 -m unittest discover plugins/kol-tools/skills/kol-clean/scripts/tests -v
```

Expected: all tests pass.

## Task 3: Migrate `kol-index` From Existing Indexer

**Files:**

- Create: `plugins/kol-tools/skills/kol-index/SKILL.md`
- Create: `plugins/kol-tools/skills/kol-index/agents/openai.yaml`
- Create: `plugins/kol-tools/skills/kol-index/references/schema.md`
- Create: `plugins/kol-tools/skills/kol-index/references/usage.md`
- Create: `plugins/kol-tools/skills/kol-index/scripts/kol_index.py`
- Create: `plugins/kol-tools/skills/kol-index/scripts/tests/test_kol_index.py`

- [ ] **Step 1: Copy behavior, not backup files**

Port the behavior from:

```text
/Users/saberrao/.codex/skills/kol-twin/scripts/ingest_index_build.py
```

Do not copy `__pycache__` or `*.bak-*`.

- [ ] **Step 2: Add support for `.clean_corpus.jsonl`**

Input preference:

```text
1. If wiki/.clean_corpus.jsonl exists, build index from it.
2. Otherwise parse raw/tweets/*.md directly for backward compatibility.
```

- [ ] **Step 3: Preserve current output schema**

Maintain fields expected by existing downstream files:

```json
{
  "id": "2053264927947673822",
  "date": "2026-05-10T00:00:00Z",
  "lang": "zh",
  "is_retweet": false,
  "is_quote": false,
  "is_thread_part": false,
  "conversation_id": "2053264927947673822",
  "is_reply": false,
  "reply_to": null,
  "favorite_count": 0,
  "retweet_count": 0,
  "reply_count": 0,
  "view_count": 0,
  "media_count": 0,
  "length": 120,
  "low_content": false,
  "text": "body",
  "url": "https://x.com/user/status/id"
}
```

If clean fields exist, append:

```json
{
  "quality": "high",
  "content_density": 0.86,
  "routing": {"distill": true},
  "reasons": ["has_ticker"]
}
```

- [ ] **Step 4: Add CLI**

CLI:

```bash
python3 scripts/kol_index.py TJ_Research --vault /Users/saberrao/vault/kol
```

Output:

```text
wiki/.ingest_index.jsonl
wiki/.ingest_stats.json
```

- [ ] **Step 5: Run compatibility smoke**

Run:

```bash
python3 plugins/kol-tools/skills/kol-index/scripts/kol_index.py TJ_Research --vault /Users/saberrao/vault/kol --dry-run
```

Expected: prints stats and does not write files.

## Task 4: Implement Registry Health Check

**Files:**

- Create: `plugins/kol-tools/scripts/registry_health.py`
- Create: `plugins/kol-tools/scripts/tests/test_registry_health.py`

- [ ] **Step 1: Detect registry/meta drift**

Health checker should compare:

```text
_cross/_registry.md
<handle>/.meta.yaml
<handle>/wiki/soul.md
<handle>/wiki/.ingest_stats.json
```

It should report:

```json
{
  "handle": "LinQingV",
  "severity": "warning",
  "issue": "meta_skeleton_but_registry_ingested",
  "registry_last_ingest": "2026-05-15",
  "meta_last_ingest": null
}
```

- [ ] **Step 2: Keep it read-only by default**

CLI:

```bash
python3 plugins/kol-tools/scripts/registry_health.py --vault /Users/saberrao/vault/kol
```

Default output: JSON to stdout only.

Optional write:

```bash
python3 plugins/kol-tools/scripts/registry_health.py --vault /Users/saberrao/vault/kol --write
```

Writes:

```text
/Users/saberrao/vault/kol/_cross/registry_health.json
```

## Task 5: Replace Raw Refresh Dependency With `twitter-fetch history`

**Files:**

- Create: `plugins/kol-tools/skills/kol-refresh/SKILL.md`
- Create: `plugins/kol-tools/skills/kol-refresh/agents/openai.yaml`
- Create: `plugins/kol-tools/skills/kol-refresh/references/usage.md`
- Create: `plugins/kol-tools/skills/kol-refresh/scripts/twitter_fetch_runner.py`
- Create: `plugins/kol-tools/skills/kol-refresh/scripts/kol_refresh.py`
- Create: `plugins/kol-tools/skills/kol-refresh/scripts/tests/test_kol_refresh_cli.py`

- [ ] **Step 1: Implement caller-managed state**

`kol-refresh` owns:

```text
<vault>/<handle>/raw/.backfill_state.json
```

State fields:

```json
{
  "handle": "TJ_Research",
  "newest_id": "2053264927947673822",
  "cursor": "opaque",
  "total_fetched": 2607,
  "last_fetch": "2026-06-23T00:00:00Z",
  "source": "twitter-fetch history"
}
```

- [ ] **Step 2: Call installed/source `twitter-fetch history`**

Use the source path first during development:

```text
plugins/twitter-tools/skills/twitter-fetch/bin/twitter-fetch
```

Command shape:

```bash
bin/twitter-fetch history --user TJ_Research --since-id <newest_id> --cursor <cursor> --jsonl
```

Do not make `twitter-fetch` write KOL files or state.

- [ ] **Step 3: Convert normalized JSONL to raw Markdown**

Write one file per tweet:

```text
<vault>/<handle>/raw/tweets/<id>.md
```

Use existing frontmatter-compatible fields:

```yaml
---
id: "..."
url: "..."
created_at: "..."
lang: "..."
is_reply: true
in_reply_to: "..."
is_quote: false
conversation_id: "..."
source_type: "x_reply"
---
body
```

- [ ] **Step 4: Add dry-run**

CLI:

```bash
python3 scripts/kol_refresh.py TJ_Research --vault /Users/saberrao/vault/kol --max-pages 1 --dry-run
```

Expected: prints counts, proposed newest id, proposed cursor, and no file writes.

- [ ] **Step 5: Replace old daily refresh script only after smoke**

Only after `kol-refresh` smoke passes:

```text
old: ~/.codex/skills/kol-twin/scripts/daily_refresh.py
new: plugins/kol-tools/skills/kol-refresh/scripts/kol_refresh.py --all-v2
```

Keep old local skill untouched until plugin install is validated.

## Task 6: Add `kol-distill` As Prompt-Orchestrated Layer

**Files:**

- Create: `plugins/kol-tools/skills/kol-distill/SKILL.md`
- Create: `plugins/kol-tools/skills/kol-distill/agents/openai.yaml`
- Create: `plugins/kol-tools/skills/kol-distill/references/usage.md`
- Copy: existing templates into `plugins/kol-tools/templates/`

- [ ] **Step 1: Copy templates**

Copy from:

```text
/Users/saberrao/.codex/skills/kol-twin/templates/
```

To:

```text
plugins/kol-tools/templates/
```

Do not copy backup files ending with `.bak-*`.

- [ ] **Step 2: Update prompts to consume clean corpus**

Phase B input should prefer:

```text
wiki/.clean_corpus.jsonl
```

And fall back to:

```text
wiki/.ingest_index.jsonl
```

- [ ] **Step 3: Define LLM write guard**

`kol-distill` instructions must require:

```text
1. backup files before editing
2. never rewrite all pages during incremental ingest
3. cite tweet ids in generated pages
4. update .ingest_meta.json only after successful page writes
5. subscriber_private content can inform private twin but must not be copied into public-facing docs
```

## Task 7: Add `kol-ask`

**Files:**

- Create: `plugins/kol-tools/skills/kol-ask/SKILL.md`
- Create: `plugins/kol-tools/skills/kol-ask/agents/openai.yaml`
- Create: `plugins/kol-tools/skills/kol-ask/references/runtime.md`

- [ ] **Step 1: Port current ask workflow**

Port from existing `kol-twin/SKILL.md`:

```text
resolve handle
load soul
load relevant methods
load relevant positions/sources
load timeline if matched
load invest wiki _index and selected pages
compose persona prompt
answer with meta block
```

- [ ] **Step 2: Add retrieval budget**

Runtime should avoid loading all large files every time:

```text
soul.md full
top 6 matching methods
top 8 matching sources/positions
timeline relevant sections only if matched
invest wiki 2-5 pages
```

- [ ] **Step 3: Enforce safety**

Every answer must state through framing:

```text
not the real KOL
based on public/private local archive
no future price target
out of coverage when needed
```

## Task 8: Add Portable `kol-debate`

**Files:**

- Create: `plugins/kol-tools/skills/kol-debate/SKILL.md`
- Create: `plugins/kol-tools/skills/kol-debate/agents/openai.yaml`
- Create: `plugins/kol-tools/skills/kol-debate/references/runtime.md`
- Create: `plugins/kol-tools/skills/kol-debate/scripts/kol_debate.py`
- Create: `plugins/kol-tools/skills/kol-debate/scripts/tests/test_kol_debate_cli.py`

- [ ] **Step 1: Port debate workspace format**

Preserve:

```text
_cross/debates/<timestamp>/
  question.md
  turns/r1-<handle>.md
  turns/r2-<handle>.md
  verdict.json
  verdict.md
```

- [ ] **Step 2: Remove hard-coded `claude --print`**

Replace direct subprocess call with runner abstraction:

```text
--runner claude
--runner manual
```

Initial implementation can support:

```text
manual: write prompt files and ask current agent to fill outputs
claude: use claude --print only when explicitly selected
```

Codex runtime should use skill instructions rather than trying to shell out to `codex`.

## Task 9: Fresh Install And Migration

**Files:**

- Modify only after plugin validates:
  - maybe move `/Users/saberrao/.codex/skills/kol-twin` to `/Users/saberrao/.codex/skills.disabled/kol-twin`

- [ ] **Step 1: Validate source tests**

Run:

```bash
python3 -m unittest discover plugins/kol-tools -v
python3 -m json.tool plugins/kol-tools/.codex-plugin/plugin.json >/dev/null
python3 -m json.tool plugins/kol-tools/.claude-plugin/plugin.json >/dev/null
```

- [ ] **Step 2: Install plugin locally**

Run from repo root:

```bash
codex plugin marketplace add .
codex plugin add kol-tools@awesome-ai
claude plugin marketplace add ./
claude plugin install kol-tools@awesome-ai
```

- [ ] **Step 3: Verify installed inventory**

Run:

```bash
codex plugin list
claude plugin list
```

Expected: `kol-tools` appears on both sides.

- [ ] **Step 4: Smoke test installed scripts**

Use dry-run/read-only commands first:

```bash
python3 plugins/kol-tools/skills/kol-clean/scripts/kol_clean.py TJ_Research --vault /Users/saberrao/vault/kol --dry-run
python3 plugins/kol-tools/skills/kol-index/scripts/kol_index.py TJ_Research --vault /Users/saberrao/vault/kol --dry-run
python3 plugins/kol-tools/scripts/registry_health.py --vault /Users/saberrao/vault/kol
```

Expected: JSON stats/health output, no raw data printed.

## Risk Controls

- Keep raw tweets immutable. Cleaning only labels and routes.
- Subscriber content remains `subscriber_private`.
- Do not print cookies, auth tokens, or raw subscriber article text.
- Do not disable old `kol-twin` until `kol-tools` is installed and smoke-tested.
- Do not replace daily refresh automation until `kol-refresh --dry-run` and one explicit small write test pass.
- Keep registry Markdown as human view until a machine registry migration is separately planned.

## Verification Matrix

| Capability | Verification |
| --- | --- |
| Plugin manifests | `python3 -m json.tool` |
| Marketplace entries | `python3 -m json.tool .agents/plugins/marketplace.json .claude-plugin/marketplace.json` |
| Clean scoring | `python3 -m unittest discover plugins/kol-tools/skills/kol-clean/scripts/tests -v` |
| Index compatibility | `kol_index.py TJ_Research --dry-run` |
| Registry drift | `registry_health.py --vault /Users/saberrao/vault/kol` reports LinQingV drift |
| Refresh isolation | `kol_refresh.py --dry-run` writes nothing and calls `twitter-fetch history` |
| Privacy | grep output/logs for `auth_token`, `ct0`, subscriber article dumps |
| Install | `codex plugin list`, `claude plugin list` |

## Recommended Execution Order

1. Task 1: plugin skeleton and marketplaces.
2. Task 2: `kol-clean` with tests.
3. Task 3: `kol-index` migration with dry-run compatibility.
4. Task 4: registry health check.
5. Commit phase 1.
6. Task 5: `kol-refresh` replacing old raw dependency.
7. Commit phase 2.
8. Task 6 and Task 7: distill and ask.
9. Commit phase 3.
10. Task 8: portable debate.
11. Commit phase 4.
12. Fresh install validation.

## First Implementation Checkpoint

The first coding checkpoint should stop after Tasks 1-4. At that point, the plugin exists, cleaning/indexing is testable, registry drift is visible, and no production KOL refresh behavior has been changed.
