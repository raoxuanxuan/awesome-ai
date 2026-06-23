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

## Script

Use the plugin-level script:

```bash
python3 plugins/kol-tools/scripts/kol_refresh.py --handle <handle> --incremental --max-pages 1 --dry-run
```

## Workflow

1. Confirm the KOL exists in `/Users/saberrao/vault/kol/_cross/_registry.md`.
2. Confirm `twitter-fetch history` works for the handle.
3. Run dry-run before any raw write.
4. Write raw tweet Markdown by tweet id.
5. Update only KOL-owned `.backfill_state.json`.

See `references/usage.md`.
