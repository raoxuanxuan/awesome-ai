# twitter-fetch JSON Schema

Every command writes one JSON object to stdout.

## Envelope

```json
{
  "ok": true,
  "mode": "single | timeline | thread | replies | search | history",
  "source": "fxtwitter | syndication | nitter | direct_nitter | browseros | graphql | auto | mock",
  "fetched_at": "UTC ISO timestamp",
  "input": {},
  "items": [],
  "error": null,
  "meta": {}
}
```

When `ok=false`, `items` is empty unless a provider returned partial data.
`meta` is optional and appears only when a command has extra machine-readable
pagination or provider metadata.

## Error

```json
{
  "code": "network_error",
  "message": "human readable error",
  "provider": "fxtwitter",
  "retryable": true
}
```

## Tweet Item

```json
{
  "id": "123",
  "url": "https://x.com/user/status/123",
  "author": "Display Name",
  "screen_name": "user",
  "created_at": "2026-01-01T00:00:00Z",
  "lang": "en",
  "text": "preview or tweet text",
  "full_text": "complete tweet text where available",
  "is_article": false,
  "article": null,
  "media": null,
  "media_count": 0,
  "stats": {
    "likes": 0,
    "retweets": 0,
    "bookmarks": 0,
    "views": 0,
    "replies": 0,
    "quotes": 0
  },
  "conversation_id": "123",
  "is_reply": false,
  "in_reply_to": "",
  "is_thread_part": false,
  "is_quote": false,
  "is_retweet": false,
  "quote": null
}
```

When `single` is called with `--include-thread`, `--context thread`, or `--context full`, the first item may include:

```json
{
  "thread": {
    "ok": true,
    "source": "syndication",
    "items": [],
    "error": null
  }
}
```

Default `single` output does not include `thread`.

## Search Meta

`search` returns normalized tweet items using the standard tweet item schema.
It may include:

```json
{
  "result_count": 20,
  "query": "NVDA priced in lang:en -filter:replies"
}
```

The `input` object includes the original `query`, expanded `raw_query`, `limit`,
`mode`, optional filters, and the cookie file path. It must not include cookie
values.

## History Meta

`history` returns a `meta` object in JSON envelope mode:

```json
{
  "user_id": "123",
  "page_count": 2,
  "next_cursor": "cursor",
  "newest_id": "999",
  "oldest_id": "111",
  "reached_cutoff": false,
  "reached_since_id": true,
  "exhausted": false
}
```

`history --jsonl` writes only normalized tweet items, one JSON object per line.
It does not write markdown files or state files.

## Compatibility Notes

Legacy wrappers convert this schema back to their previous shapes. New consumers should depend on this schema directly.
