# KOL Clean Schema

`kol-clean` writes one JSON object per line to:

```text
<vault>/<handle>/wiki/.clean_corpus.jsonl
```

## Fields

```json
{
  "id": "2053264927947673822",
  "date": "2026-05-10T00:00:00Z",
  "url": "https://x.com/TJ_Research/status/2053264927947673822",
  "text": "tweet body",
  "is_reply": false,
  "is_quote": false,
  "is_retweet": false,
  "conversation_id": "2053264927947673822",
  "reply_to": null,
  "quality": "high",
  "content_density": 0.86,
  "routing": {
    "distill": true,
    "voice": true,
    "timeline": false,
    "position": true
  },
  "reasons": ["has_ticker", "has_reasoning", "has_position"],
  "source_type": "x_public",
  "visibility": "private"
}
```

## Quality

- `high`: strong investment, method, reasoning, ticker, or position signal.
- `medium`: useful content with at least one durable signal.
- `low`: weak content, useful mostly for voice or context.
- `noise`: social, empty, URL-only, mention-only, or low-density content.

## Routing

- `distill`: eligible for methods, positions, sources, or timeline distillation.
- `voice`: eligible for tone/style sampling.
- `timeline`: eligible for stance evolution or reversal review.
- `position`: eligible for symbol/company position pages.
