---
name: kol-index
description: Build deterministic KOL ingest indexes and stats from cleaned corpus JSONL or raw tweet Markdown. Use before KOL distillation, incremental ingest, ask, or debate when index files need refresh.
---

# KOL Index

Use this skill after `kol-clean` or directly on legacy raw tweet Markdown.

## Boundary

- Reads `wiki/.clean_corpus.jsonl` when present.
- Requires `wiki/.clean_corpus.jsonl` by default.
- Falls back to `raw/tweets/*.md` only with explicit `--legacy-raw`.
- Writes `wiki/.ingest_index.jsonl` and `wiki/.ingest_stats.json` only when not in `--dry-run`.
- Does not fetch X/Twitter.
- Does not generate `soul.md`, methods, positions, sources, or timeline.

## Workflow

Dry-run first:

```bash
python3 plugins/kol-tools/scripts/kol_clean.py <handle> --write
python3 plugins/kol-tools/scripts/kol_index.py <handle> --dry-run
```

Write index:

```bash
python3 plugins/kol-tools/scripts/kol_index.py <handle>
```

Legacy raw fallback:

```bash
python3 plugins/kol-tools/scripts/kol_index.py <handle> --legacy-raw --dry-run
```

Default vault is `/Users/saberrao/vault/kol`, override with `KOL_TOOLS_VAULT` or `--vault`.

## References

- Usage: `references/usage.md`
- Schema: `references/schema.md`
