# substack-fetch Content JSON

`substack-fetch` emits a normalized content object designed for `substack-media-fetch` and `content-to-obsidian`.

```json
{
  "source": {
    "platform": "substack",
    "url": "https://example.substack.com/p/post",
    "id": "123",
    "slug": "post",
    "publication": "example.substack.com"
  },
  "author": {
    "name": "Author",
    "handle": "author"
  },
  "title": "Post title",
  "subtitle": "Post subtitle",
  "published_at": "2026-04-11T22:54:42.748Z",
  "updated_at": "2026-06-27T07:49:59.241Z",
  "lang": "en",
  "content_type": "article",
  "text": "Plain text body",
  "markdown": "Original Markdown body",
  "html": "<p>Body HTML</p>",
  "sections": [
    {"level": 2, "title": "Section", "text": "Section text"}
  ],
  "media": [
    {
      "source_url": "https://substackcdn.com/image/...",
      "alt": "",
      "kind": "image",
      "role": "cover"
    }
  ],
  "stats": {
    "wordcount": 6561,
    "reactions": {"❤": 45},
    "comment_count": 8,
    "restacks": 4
  },
  "translation": {
    "preferred": true,
    "target_lang": "zh-CN",
    "reason": "source language appears non-Chinese"
  },
  "references": []
}
```

## Translation Hints

`translation.preferred` is a hint for downstream ingestion. `substack-fetch` does not generate translations.

## Media

Media items are extracted from `body_html` and `cover_image`. `substack-fetch` does not download them.
