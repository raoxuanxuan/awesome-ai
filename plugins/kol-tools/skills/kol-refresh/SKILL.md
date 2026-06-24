---
name: kol-refresh
description: Refresh private KOL raw archives by delegating X/Twitter fetching to twitter-fetch, canonicalizing tweets through tweet-pool, and writing KOL-owned raw/state files. Use when a KOL needs initial history backfill or incremental raw updates.
---

# KOL Refresh

Use this skill for KOL-specific raw archive maintenance.

## Boundary

- Calls `twitter-tools/twitter-fetch history` for X/Twitter data.
- Requires `twitter-tools/tweet-pool` as the canonical normalized tweet cache.
- Writes raw Markdown from tweet-pool canonical tweets, not directly from one fetch payload.
- Owns KOL raw files under `/Users/saberrao/vault/kol/<handle>/raw/tweets/`.
- Owns KOL refresh state under `/Users/saberrao/vault/kol/<handle>/raw/.backfill_state.json`.
- Writes KOL consumer status to `tweet-pool/consumers/kol-tools.json`.
- Does not implement low-level X/Twitter GraphQL fetching.
- Does not clean, summarize, distill, ask, or debate.
- Does not write Obsidian vaults outside the KOL vault.
- Historical raw archive migration is handled by `kol_pool_backfill.py`. It is
  a one-time compatibility path into tweet-pool, not the normal refresh path.

## Script

Use the plugin-level script:

```bash
python3 plugins/kol-tools/scripts/kol_refresh.py --handle <handle> --incremental --max-pages 1 --dry-run
```

For old raw archives that predate tweet-pool:

```bash
python3 plugins/kol-tools/scripts/kol_pool_backfill.py --vault /Users/saberrao/vault/kol --all --dry-run
python3 plugins/kol-tools/scripts/kol_pool_backfill.py --vault /Users/saberrao/vault/kol --all
```

## Workflow

1. Confirm the KOL exists in `/Users/saberrao/vault/kol/_cross/_registry.md`.
2. Confirm `twitter-fetch history` works for the handle.
3. Confirm `tweet-pool ensure` works.
4. Run dry-run before any raw write.
5. Fetch payload, ingest it into tweet-pool, then export root tweet IDs from the pool.
6. Write raw tweet Markdown by tweet id from the exported canonical tweets.
7. Update KOL-owned `.backfill_state.json` and tweet-pool consumer status.

See `references/usage.md`.
