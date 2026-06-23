# KOL Refresh Usage

`kol-refresh` is the KOL layer above `twitter-fetch`.

Dry-run shape:

```bash
python3 plugins/kol-tools/scripts/kol_refresh.py \
  --vault /Users/saberrao/vault/kol \
  --handle TJ_Research \
  --incremental \
  --max-pages 1 \
  --dry-run
```

Write shape:

```bash
python3 plugins/kol-tools/scripts/kol_refresh.py \
  --vault /Users/saberrao/vault/kol \
  --handle TJ_Research \
  --incremental \
  --max-pages 1
```

The command will delegate fetching to `twitter-fetch history`. It will not ask for cookies itself; use `twitter-fetch` setup for X/Twitter login state.

Fixture/import mode:

```bash
python3 plugins/kol-tools/scripts/kol_refresh.py \
  --vault /tmp/kol-vault \
  --handle sample \
  --input-jsonl plugins/kol-tools/scripts/tests/fixtures/twitter_fetch_history.jsonl \
  --dry-run
```
