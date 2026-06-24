# Tweet Pool Schema

The tweet pool is a normalized fetch cache, not a business queue.

## Runtime Layout

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
    └── <consumer>.json
```

## Tweet

`tweets/<tweet_id>.json` stores a `twitter-fetch` normalized item with one extra
`_pool` metadata object:

```json
{
  "id": "123",
  "url": "https://x.com/user/status/123",
  "author": "Display Name",
  "screen_name": "user",
  "created_at": "2026-06-23T10:00:00Z",
  "full_text": "tweet text",
  "_pool": {
    "first_seen_at": "2026-06-23T10:01:00Z",
    "last_seen_at": "2026-06-23T10:02:00Z",
    "sources": ["fxtwitter", "syndication"],
    "modes": ["single", "timeline"],
    "completeness": {
      "timeline": true,
      "single": true,
      "thread": false,
      "history": false,
      "media": false
    },
    "field_sources": {
      "full_text": {
        "source": "fxtwitter",
        "mode": "single",
        "updated_at": "2026-06-23T10:02:00Z"
      },
      "screen_name": {
        "source": "syndication",
        "mode": "timeline",
        "updated_at": "2026-06-23T10:01:00Z"
      }
    }
  }
}
```

## Merge Policy

Repeated ingests of the same tweet ID upsert `tweets/<tweet_id>.json`; they do
not create duplicate tweet files. Merge rules are intentionally conservative:

- Empty values do not overwrite existing non-empty values.
- Shorter `text` / `full_text` values do not replace longer canonical text.
- Empty media payloads and `media_count: 0` do not clear existing media.
- Empty quote payloads and `is_quote: false` do not clear an existing quote.
- `_pool.sources`, `_pool.modes`, and `_pool.completeness` accumulate fetch provenance.
- `_pool.field_sources` records the latest source/mode/time that actually changed each field.

## Author

```json
{
  "username": "karpathy",
  "display_name": "Andrej Karpathy",
  "avatar_url": "https://pbs.twimg.com/profile_images/...",
  "first_seen_at": "2026-06-23T10:01:00Z",
  "last_seen_at": "2026-06-23T10:02:00Z"
}
```

## Timeline Observation

`timelines/<username>.jsonl` appends one JSON object per timeline or history fetch:

```json
{
  "fetched_at": "2026-06-23T10:00:00Z",
  "mode": "timeline",
  "source": "syndication",
  "input": {"user": "karpathy", "limit": 20},
  "tweet_ids": ["123", "124"]
}
```

## Fetch State

`fetch_state/<username>.json` stores provider-neutral observation watermarks:

```json
{
  "username": "karpathy",
  "last_observed_at": "2026-06-23T10:00:00Z",
  "last_mode": "timeline",
  "last_source": "syndication",
  "last_count": 20,
  "newest_id": "124",
  "oldest_id": "100"
}
```

## Consumer State

`consumers/<consumer>.json` belongs to one downstream skill. It must not be
interpreted as global tweet status.

```json
{
  "consumer": "twitter-monitor",
  "items": {
    "123": {
      "status": "skipped",
      "updated_at": "2026-06-23T10:02:00Z",
      "reason": "short_reply"
    }
  }
}
```
