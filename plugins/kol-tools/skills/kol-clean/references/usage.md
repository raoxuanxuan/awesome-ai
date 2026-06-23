# KOL Clean Usage

Run from the plugin root or pass an absolute script path.

```bash
python3 skills/kol-clean/scripts/kol_clean.py TJ_Research --vault /Users/saberrao/vault/kol --dry-run
python3 skills/kol-clean/scripts/kol_clean.py TJ_Research --vault /Users/saberrao/vault/kol --write
```

Defaults:

```bash
export KOL_TOOLS_VAULT=/Users/saberrao/vault/kol
```

`--dry-run` prints JSON stats and does not write files.

`--write` writes:

```text
<vault>/<handle>/wiki/.clean_corpus.jsonl
```

Raw files are never deleted.
