# KOL Tools

KOL Tools is a private KOL digital-twin plugin for Codex and Claude Code.

## What It Does

- Maintains raw KOL archives under `/Users/saberrao/vault/kol/`.
- Cleans low-information tweets without deleting raw data.
- Preserves substantive replies and routes them into methods, positions, sources, voice, or timeline.
- Builds deterministic indexes and stats.
- Provides prompts and scripts for KOL distillation, ask, and debate workflows.

## What It Does Not Do

- It does not implement low-level X/Twitter fetching itself. It calls `twitter-tools/twitter-fetch`.
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

## Common Commands

```bash
python3 plugins/kol-tools/skills/kol-clean/scripts/kol_clean.py TJ_Research --vault /Users/saberrao/vault/kol --dry-run
python3 plugins/kol-tools/skills/kol-index/scripts/kol_index.py TJ_Research --vault /Users/saberrao/vault/kol --dry-run
python3 plugins/kol-tools/scripts/registry_health.py --vault /Users/saberrao/vault/kol
python3 plugins/kol-tools/scripts/kol_refresh.py --vault /Users/saberrao/vault/kol --handle TJ_Research --incremental --max-pages 1 --dry-run
```

## Privacy

Raw tweets and subscriber-only content remain private. Do not publish generated twin output as if it were written by the KOL.
