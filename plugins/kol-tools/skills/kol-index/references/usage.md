# KOL Index Usage

```bash
python3 skills/kol-index/scripts/kol_index.py TJ_Research --vault /Users/saberrao/vault/kol --dry-run
python3 skills/kol-index/scripts/kol_index.py TJ_Research --vault /Users/saberrao/vault/kol
```

Input preference:

1. `<vault>/<handle>/wiki/.clean_corpus.jsonl`
2. `<vault>/<handle>/raw/tweets/*.md`

`--dry-run` prints stats and does not write files.
