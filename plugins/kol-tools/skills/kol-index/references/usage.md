# KOL Index Usage

```bash
python3 skills/kol-clean/scripts/kol_clean.py TJ_Research --vault /Users/saberrao/vault/kol --write
python3 skills/kol-index/scripts/kol_index.py TJ_Research --vault /Users/saberrao/vault/kol --dry-run
python3 skills/kol-index/scripts/kol_index.py TJ_Research --vault /Users/saberrao/vault/kol
```

Input preference:

1. `<vault>/<handle>/wiki/.clean_corpus.jsonl`

Production index builds require clean corpus by default. Raw Markdown fallback
is retained only for legacy repair:

```bash
python3 skills/kol-index/scripts/kol_index.py TJ_Research \
  --vault /Users/saberrao/vault/kol \
  --legacy-raw \
  --dry-run
```

`--dry-run` prints stats and does not write files.
