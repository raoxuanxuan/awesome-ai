---
name: tweet-pool
description: Use when Codex needs to cache normalized X/Twitter fetch results for reuse across twitter-monitor, kol-twin, translation, or archive workflows without sharing downstream business state.
---

# Tweet Pool

`tweet-pool` is a local normalized fetch cache for X/Twitter data. It stores
`twitter-fetch` items by tweet ID so multiple downstream skills can reuse fetched
content without coupling their business state.

It is not a queue, scheduler, monitor, Obsidian writer, KOL ingester, or quality gate.

## Runtime

Authoritative runtime:

```text
/Users/saberrao/ai-workspace/content-creation/.tweet-pool/
```

Override for tests or experiments:

```bash
export TWEET_POOL_RUNTIME=/absolute/path/to/.tweet-pool
```

Runtime layout:

```text
.tweet-pool/
├── tweets/
│   └── <tweet_id>.json
├── authors/
│   └── <username>.json
├── media/
│   └── <tweet_id>/manifest.json
├── timelines/
│   └── <username>.jsonl
├── fetch_state/
│   └── <username>.json
└── consumers/
    ├── twitter-monitor.json
    └── kol-twin.json
```

## Boundaries

- The pool stores normalized tweet facts and lightweight fetch metadata.
- Consumers keep separate state under `consumers/<consumer>.json`.
- Do not treat `twitter-monitor` skipped/saved state as `kol-twin` ingest state.
- Do not make global low-quality decisions in the pool. Store signals on tweets; let each consumer decide.
- Do not write mutable runtime data into the plugin directory.

## Commands

Create the runtime layout:

```bash
tweet-pool ensure --pretty
```

Ingest a `twitter-fetch` JSON envelope:

```bash
twitter-fetch timeline --user karpathy --limit 20 --pretty \
  | tweet-pool ingest --input - --pretty
```

Export cached tweets:

```bash
tweet-pool export --tweet-ids 123,124 --pretty
tweet-pool export --user karpathy --since-id 123 --format jsonl
```

Set a consumer-specific status:

```bash
tweet-pool consumer set \
  --consumer twitter-monitor \
  --tweet-id 123 \
  --status skipped \
  --reason short_reply
```

## Integration Pattern

1. `twitter-fetch` fetches normalized data.
2. `tweet-pool ingest` writes or updates `tweets/<tweet_id>.json`.
3. A consumer exports cached tweets and applies its own policy.
4. The consumer writes only its own status file under `consumers/`.

This allows `twitter-monitor` to skip a short reply while `kol-twin` can still
ingest it as useful persona or interaction evidence.
