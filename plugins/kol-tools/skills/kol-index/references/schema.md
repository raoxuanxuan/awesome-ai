# KOL Index Schema

`kol-index` writes:

```text
<vault>/<handle>/wiki/.ingest_index.jsonl
<vault>/<handle>/wiki/.ingest_stats.json
```

Each `.ingest_index.jsonl` line preserves the existing KOL schema:

```json
{
  "id": "2053264927947673822",
  "date": "2026-05-10T00:00:00Z",
  "lang": "zh",
  "is_retweet": false,
  "is_quote": false,
  "is_thread_part": false,
  "conversation_id": "2053264927947673822",
  "is_reply": false,
  "reply_to": null,
  "favorite_count": 0,
  "retweet_count": 0,
  "reply_count": 0,
  "view_count": 0,
  "media_count": 0,
  "length": 120,
  "low_content": false,
  "text": "body",
  "url": "https://x.com/user/status/id"
}
```

When built from `.clean_corpus.jsonl`, clean fields are appended:

```json
{
  "quality": "high",
  "content_density": 0.86,
  "routing": {"distill": true},
  "reasons": ["has_ticker"]
}
```
