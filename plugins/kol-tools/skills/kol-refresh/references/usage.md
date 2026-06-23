# KOL Refresh Usage

`kol-refresh` is the KOL layer above `twitter-fetch` and `tweet-pool`.

The write path is:

```text
twitter-fetch history
  -> tweet-pool ingest
  -> tweet-pool export root tweet IDs
  -> vault/kol/<handle>/raw/tweets/*.md
  -> tweet-pool consumers/kol-tools.json
```

This means KOL raw Markdown is written from the canonical tweet stored in
tweet-pool, not directly from one transient fetch payload.

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

It also requires `tweet-pool`. The default tweet-pool runtime is owned by the
twitter-tools plugin, and can be overridden for tests:

```bash
python3 plugins/kol-tools/scripts/kol_refresh.py \
  --vault /tmp/kol-vault \
  --handle sample \
  --input-jsonl plugins/kol-tools/scripts/tests/fixtures/twitter_fetch_history.jsonl \
  --tweet-pool-runtime /tmp/.tweet-pool
```

Fixture/import mode:

```bash
python3 plugins/kol-tools/scripts/kol_refresh.py \
  --vault /tmp/kol-vault \
  --handle sample \
  --input-jsonl plugins/kol-tools/scripts/tests/fixtures/twitter_fetch_history.jsonl \
  --tweet-pool-runtime /tmp/.tweet-pool \
  --dry-run
```

`--dry-run` does not write raw files, KOL state, or tweet-pool runtime data.
