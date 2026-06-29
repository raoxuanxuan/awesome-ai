# substack-media-fetch Usage

## Download From substack-fetch JSON

```bash
skills/substack-fetch/bin/substack-fetch fetch \
  --url "https://example.substack.com/p/post" \
  --out ~/Downloads/substack \
  --pretty

skills/substack-media-fetch/bin/substack-media-fetch download \
  --input ~/Downloads/substack/example/YYYY-MM-DD-post/content.json \
  --output-dir ~/Downloads/substack/example/YYYY-MM-DD-post/assets \
  --prefix YYYY-MM-DD-post \
  --pretty
```

Use `--input -` to read the normalized content JSON from stdin.

## Download Explicit URLs

```bash
skills/substack-media-fetch/bin/substack-media-fetch download \
  --urls "https://substackcdn.com/image/..." "https://substackcdn.com/image/..." \
  --output-dir /path/to/assets \
  --prefix post-slug \
  --pretty
```

## Naming

- First media file: `{prefix}-cover.{ext}`
- Later files: `{prefix}-img01.{ext}`, `{prefix}-img02.{ext}`, ...

Existing files are not overwritten; the manifest entry includes `skipped: true`.

## Exit Codes

- `0`: all requested media downloaded or already existed.
- `1`: input parsing failed or at least one media item failed.
- `2`: invalid CLI arguments.
