# Bootstrap KOL Wiki Prompt

Build the initial durable KOL wiki from this prompt pack.

Read first:

- `manifest.json`
- `schema_manifest.json`
- `risk_assessment.json`
- `delta_items.jsonl`
- `delta_brief.md`

Write or update these durable pages only after review:

- `wiki/_index.md`
- `wiki/soul.md`
- `wiki/timeline.md`
- `wiki/sources/*.md`
- `wiki/methods/*.md`
- `wiki/positions/*.md`

Rules:

- Every durable claim must cite tweet ids.
- Mark inferred stance as inferred.
- Preserve out-of-coverage boundaries.
- Do not advance `.ingest_meta.json`.
- Treat `soul.md` as high risk.
