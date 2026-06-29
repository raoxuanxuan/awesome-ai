# substack-fetch Usage

## Fetch and Write Artifacts

```bash
skills/substack-fetch/bin/substack-fetch fetch \
  --url "https://damnang2.substack.com/p/is-cxmt-a-threat-or-an-illusion" \
  --out ~/Downloads/substack \
  --pretty
```

The output directory is:

```text
<out>/<publication-host-without-tld>/<YYYY-MM-DD>-<slug>/
```

Files:

- `content.json`: normalized content.
- `<YYYY-MM-DD>-<slug>.md`: original Markdown for local reading.
- `post.json`: raw Substack API response.
- `body.html`: raw `body_html`.

## JSON Only

```bash
skills/substack-fetch/bin/substack-fetch fetch \
  --url "https://example.substack.com/p/post" \
  --no-artifacts \
  --pretty
```

## Downstream Media Download

```bash
skills/substack-media-fetch/bin/substack-media-fetch download \
  --input /path/to/content.json \
  --output-dir /path/to/assets \
  --prefix yyyy-mm-dd-slug \
  --pretty
```

## Exit Codes

- `0`: fetch succeeded.
- `1`: fetch failed or output write failed.
- `2`: invalid CLI arguments.
