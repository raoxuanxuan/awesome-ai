# twitter-media-fetch Usage

## Download From twitter-fetch JSON

```bash
skills/twitter-fetch/bin/twitter-fetch single \
  --url "https://x.com/user/status/123" \
  --include-thread \
  --pretty > tweet.json

skills/twitter-media-fetch/bin/twitter-media-fetch download \
  --input tweet.json \
  --output-dir /path/to/assets \
  --prefix my-slug \
  --pretty
```

Use `--input -` to read the JSON envelope from stdin.

## Download Explicit URLs

```bash
skills/twitter-media-fetch/bin/twitter-media-fetch download \
  --urls "https://pbs.twimg.com/media/..." "https://pbs.twimg.com/media/..." \
  --output-dir /path/to/assets \
  --prefix my-slug \
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
