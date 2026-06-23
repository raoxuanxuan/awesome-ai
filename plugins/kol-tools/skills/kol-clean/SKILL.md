---
name: kol-clean
description: Clean and score private KOL raw tweet archives before indexing or distillation. Use when a KOL corpus needs low-density post filtering, substantive reply preservation, or routing into distill/voice/timeline/position uses.
---

# KOL Clean

Use this skill after raw KOL content exists under `/Users/saberrao/vault/kol/<handle>/raw/tweets/` and before `kol-index` or `kol-distill`.

## Boundary

- Reads KOL raw Markdown files.
- Scores and routes tweets, replies, quotes, subscriber imports, and manual articles.
- Writes `wiki/.clean_corpus.jsonl` only when explicitly invoked with `--write`.
- Does not fetch X/Twitter.
- Does not delete raw files.
- Does not summarize or rewrite KOL wiki pages.

## Workflow

1. Resolve the KOL vault path. Default is `/Users/saberrao/vault/kol`, override with `KOL_TOOLS_VAULT` or `--vault`.
2. Run dry-run first:

```bash
python3 scripts/kol_clean.py <handle> --dry-run
```

3. Inspect JSON stats. Confirm substantive replies are retained.
4. Write clean corpus only when needed:

```bash
python3 scripts/kol_clean.py <handle> --write
```

## References

- Usage: `references/usage.md`
- Schema: `references/schema.md`
