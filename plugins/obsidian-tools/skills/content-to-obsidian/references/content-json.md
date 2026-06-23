# Content JSON

Use this schema as the handoff between source fetchers and `content-to-obsidian`.

## Object

```json
{
  "source": {
    "platform": "twitter | weibo | bilibili | csdn | weixin | substack | webpage",
    "url": "https://...",
    "id": "source-specific id"
  },
  "author": {
    "name": "Display Name",
    "handle": "screen_name_or_profile_id",
    "url": "https://..."
  },
  "title": "Original title or concise topic",
  "published_at": "2026-06-23T00:00:00Z",
  "lang": "zh | en | ...",
  "content_type": "tweet | thread | article | post | video | webpage",
  "text": "Main text content",
  "sections": [
    {"heading": "Section title", "text": "Section body"}
  ],
  "media": [
    {"url": "https://...", "type": "image", "alt": "optional"}
  ],
  "stats": {
    "likes": 0,
    "retweets": 0,
    "views": 0
  },
  "references": [
    {"type": "quote", "url": "https://...", "text": "..."}
  ],
  "raw": {}
}
```

## Required Fields

- `source.platform`
- `source.url`
- `title` or `text`
- `content_type`

## Field Notes

- `text` should be the readable main body, not raw HTML.
- `sections` preserves structure when a source fetcher has headings or thread parts.
- `media` is optional metadata. Media download is handled by a source-specific media fetcher or a generic media fetcher before `content-to-obsidian` writes Markdown.
- `references` is for quote tweets, cited posts, related source links, or embedded cross-source references.
- `raw` is optional source-specific debug context. Do not dump large HTML snapshots into final Markdown.

## Twitter Mapping

Map `twitter-fetch` output to Content JSON as follows:

| Content JSON | twitter-fetch |
| --- | --- |
| `source.platform` | `"twitter"` |
| `source.url` | `item.url` |
| `source.id` | `item.id` |
| `author.name` | `item.author` |
| `author.handle` | `item.screen_name` |
| `title` | `item.article.title` or generated topic |
| `published_at` | `item.created_at` |
| `lang` | `item.lang` |
| `content_type` | `thread`, `article`, or `tweet` based on item fields |
| `text` | `item.article.full_text` or `item.full_text` or `item.text` |
| `sections` | thread items when present |
| `stats` | `item.stats` |
| `references` | `item.quote` when present |

## Chinese Platform Mapping

Map `china-content-fetcher` output as follows:

| Content JSON | china-content-fetcher |
| --- | --- |
| `source.platform` | `platform` |
| `source.url` | `url` |
| `author.name` | `author` |
| `title` | `title` |
| `published_at` | `published_at` |
| `text` | `content` |
| `stats` | `stats` |
| `references` | `comments` or explicit source links when useful |
