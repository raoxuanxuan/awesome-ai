---
name: twitter-media-fetch
description: Use when Codex needs to download X/Twitter media referenced by twitter-fetch JSON, produce a local file manifest for upper-layer archive, translation, or vault workflows, or troubleshoot media download output without writing Markdown or updating state.
---

# Twitter Media Fetch

`twitter-media-fetch` is a media downloader for normalized `twitter-fetch` output. It extracts media URLs from tweets, X Articles, quotes, and thread items, downloads files to a caller-provided directory, and emits a JSON manifest.

It is a side-effecting file downloader. It must not fetch tweets, call X/Twitter providers, summarize, translate, classify, write Markdown, update vault state, or update monitor/backfill state.

## Inputs

Use `twitter-fetch` first and pass its JSON envelope to this skill.

```bash
skills/twitter-fetch/bin/twitter-fetch single --url "https://x.com/user/status/123" --include-thread --pretty > tweet.json
skills/twitter-media-fetch/bin/twitter-media-fetch download --input tweet.json --output-dir /path/to/assets --prefix my-slug --pretty
```

The downloader reads:

- `items[].article.images`
- `items[].article.media`
- `items[].media`
- `items[].thread.items[].media`
- `items[].quote.media`

It also accepts explicit URLs:

```bash
skills/twitter-media-fetch/bin/twitter-media-fetch download --urls "https://pbs.twimg.com/media/..." --output-dir /path/to/assets --prefix my-slug --pretty
```

## Output

The command writes a manifest JSON object to stdout:

```json
{
  "ok": true,
  "downloaded": [
    {
      "source_url": "https://pbs.twimg.com/media/...",
      "filename": "my-slug-cover.jpg",
      "path": "/path/to/assets/my-slug-cover.jpg",
      "media_type": "image",
      "bytes": 12345,
      "sha256": "..."
    }
  ],
  "failed": [],
  "count": 1
}
```

For details, read `references/schema.md`. For command usage, read `references/usage.md`.

## Boundaries

- Caller owns `--output-dir`, `--prefix`, and all naming meaning.
- Caller owns Obsidian wikilinks, Markdown generation, frontmatter, and vault layout.
- Existing files are not overwritten; they are reported with `skipped: true`.
- A partial failure exits non-zero and still prints a manifest with successful and failed entries.
