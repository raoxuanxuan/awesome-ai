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

## Distill Eligibility

`kol-clean` keeps raw data intact, then routes each item by deterministic
signals.

- Root tweets and quote tweets enter `distill` when they have method, position,
  reasoning, timeline, ticker, number, or sufficient non-social content.
- Replies do not enter `distill` from length alone. A reply must have a durable
  signal such as ticker, number, method, position, reasoning, or timeline
  language.
- Replies without a durable signal are kept as `voice` context when non-empty,
  but are not sent to distillation.

This preserves substantive replies while reducing long social replies that add
style but little durable knowledge.
