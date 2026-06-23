---
name: kol-refresh
description: Refresh private KOL raw archives by delegating X/Twitter fetching to twitter-fetch and writing KOL-owned raw/state files. Use when a KOL needs initial history backfill or incremental raw updates.
---

# KOL Refresh

Use this skill for KOL-specific raw archive maintenance.

## Boundary

- Calls `twitter-tools/twitter-fetch history` for X/Twitter data.
- Owns KOL raw files under `/Users/saberrao/vault/kol/<handle>/raw/tweets/`.
- Owns KOL refresh state under `/Users/saberrao/vault/kol/<handle>/raw/.backfill_state.json`.
- Does not implement low-level X/Twitter GraphQL fetching.
- Does not clean, summarize, distill, ask, or debate.
- Does not write Obsidian vaults outside the KOL vault.

## Phase 1 Status

This plugin phase provides the skill boundary and user-facing contract. The write-capable `kol_refresh.py` implementation lands in the next phase after `kol-clean` and health checks are validated.

## Workflow

1. Confirm the KOL exists in `/Users/saberrao/vault/kol/_cross/_registry.md`.
2. Confirm `twitter-fetch history` works for the handle.
3. Run dry-run before any raw write.
4. Write raw tweet Markdown by tweet id.
5. Update only KOL-owned `.backfill_state.json`.

See `references/usage.md`.
