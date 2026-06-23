# twitter-media-fetch Manifest Schema

Every command writes one JSON object to stdout.

## Manifest

```json
{
  "ok": true,
  "downloaded": [],
  "failed": [],
  "count": 0
}
```

`ok` is false when any media download fails. Successful downloads are still listed in `downloaded`.

## Downloaded Item

```json
{
  "source_url": "https://pbs.twimg.com/media/...",
  "filename": "slug-cover.jpg",
  "path": "/absolute/path/slug-cover.jpg",
  "media_type": "image",
  "bytes": 12345,
  "sha256": "hex digest",
  "skipped": false
}
```

`skipped` appears only when the target file already existed and was not overwritten.

## Failed Item

```json
{
  "source_url": "https://pbs.twimg.com/media/...",
  "error": "human readable error"
}
```

Input parsing failures use the same envelope shape with a single failed item that contains only `error`.
