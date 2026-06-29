---
name: substack-media-fetch
description: Use when Codex needs to download media referenced by substack-fetch normalized content JSON, produce a local media manifest for reading, translation, or Obsidian workflows, or troubleshoot Substack image download output without refetching articles or writing Markdown.
---

# Substack Media Fetch

`substack-media-fetch` downloads media referenced by `substack-fetch` normalized content JSON and emits a JSON manifest.

It is a side-effecting file downloader. It must not fetch Substack posts, translate, summarize, write Markdown, update Obsidian vaults, or maintain source state.

## Inputs

Use `substack-fetch` first and pass its `content.json`:

```bash
skills/substack-media-fetch/bin/substack-media-fetch download \
  --input /path/to/content.json \
  --output-dir /path/to/assets \
  --prefix yyyy-mm-dd-slug \
  --pretty
```

It also accepts explicit URLs:

```bash
skills/substack-media-fetch/bin/substack-media-fetch download \
  --urls "https://substackcdn.com/image/..." \
  --output-dir /path/to/assets \
  --prefix post-slug \
  --pretty
```

## Output

The command writes a manifest JSON object to stdout:

```json
{
  "ok": true,
  "downloaded": [
    {
      "source_url": "https://substackcdn.com/image/...",
      "filename": "post-slug-cover.jpg",
      "path": "/path/to/assets/post-slug-cover.jpg",
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

- Caller owns `--output-dir`, `--prefix`, and naming meaning.
- Caller owns Obsidian wikilinks, Markdown generation, frontmatter, and vault layout.
- Existing files are not overwritten; they are reported with `skipped: true`.
- A partial failure exits non-zero and still prints a manifest with successful and failed entries.
