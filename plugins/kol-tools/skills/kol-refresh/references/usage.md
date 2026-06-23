# KOL Refresh Usage

`kol-refresh` is the KOL layer above `twitter-fetch`.

Planned dry-run shape:

```bash
python3 plugins/kol-tools/scripts/kol_refresh.py \
  --vault /Users/saberrao/vault/kol \
  --handle TJ_Research \
  --incremental \
  --max-pages 1 \
  --dry-run
```

Planned write shape:

```bash
python3 plugins/kol-tools/scripts/kol_refresh.py \
  --vault /Users/saberrao/vault/kol \
  --handle TJ_Research \
  --incremental \
  --max-pages 1
```

The command will delegate fetching to `twitter-fetch history`. It will not ask for cookies itself; use `twitter-fetch` setup for X/Twitter login state.
