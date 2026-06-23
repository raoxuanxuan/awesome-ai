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

## Mark Consumer State

```bash
plugins/twitter-tools/skills/tweet-pool/bin/tweet-pool consumer set \
  --consumer kol-twin \
  --tweet-id 123 \
  --status raw_written \
  --output /Users/saberrao/vault/kol/karpathy/raw/tweets/123.md
```

`consumer set` does not modify `tweets/<tweet_id>.json`.
