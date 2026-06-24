# Tweet Pool Usage

## Create Runtime

```bash
plugins/twitter-tools/skills/tweet-pool/bin/tweet-pool ensure --pretty
```

## Ingest From twitter-fetch

```bash
plugins/twitter-tools/skills/twitter-fetch/bin/twitter-fetch timeline \
  --user karpathy \
  --limit 20 \
  --pretty \
  | plugins/twitter-tools/skills/tweet-pool/bin/tweet-pool ingest --input - --pretty
```

## Use A Temporary Runtime

```bash
TWEET_POOL_RUNTIME=/tmp/.tweet-pool \
  plugins/twitter-tools/skills/tweet-pool/bin/tweet-pool ensure
```

Or:

```bash
plugins/twitter-tools/skills/tweet-pool/bin/tweet-pool \
  --runtime /tmp/.tweet-pool \
  ingest --input payload.json
```

## Export Cached Tweets

Export exact tweet IDs as a JSON envelope:

```bash
plugins/twitter-tools/skills/tweet-pool/bin/tweet-pool \
  --runtime /tmp/.tweet-pool \
  export --tweet-ids 123,124 --pretty
```

Export cached tweets for one author as JSONL:

```bash
plugins/twitter-tools/skills/tweet-pool/bin/tweet-pool \
  --runtime /tmp/.tweet-pool \
  export --user karpathy --since-id 123 --format jsonl
```

For larger ID lists, pass a JSON list or newline-separated file:

```bash
plugins/twitter-tools/skills/tweet-pool/bin/tweet-pool \
  --runtime /tmp/.tweet-pool \
  export --tweet-ids-file /tmp/tweet-ids.json --pretty
```

## Cache Timeline Windows

Write a reusable snapshot for one closed time window:

```bash
plugins/twitter-tools/skills/twitter-fetch/bin/twitter-fetch timeline \
  --user karpathy \
  --limit 50 \
  --pretty \
  | plugins/twitter-tools/skills/tweet-pool/bin/tweet-pool window put \
      --user karpathy \
      --window-start 2026-06-24T03:00:00Z \
      --window-end 2026-06-24T04:00:00Z \
      --input - \
      --limit 50 \
      --grace-minutes 10 \
      --include-items \
      --pretty
```

Read a finalized snapshot without requesting X/Twitter again:

```bash
plugins/twitter-tools/skills/tweet-pool/bin/tweet-pool window get \
  --user karpathy \
  --window-start 2026-06-24T03:00:00Z \
  --window-end 2026-06-24T04:00:00Z \
  --include-items \
  --pretty
```

## Mark Consumer State

```bash
plugins/twitter-tools/skills/tweet-pool/bin/tweet-pool consumer set \
  --consumer kol-twin \
  --tweet-id 123 \
  --status raw_written \
  --output /Users/saberrao/vault/kol/karpathy/raw/tweets/123.md
```

`consumer set` does not modify `tweets/<tweet_id>.json`.
