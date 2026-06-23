# KOL Distill Workflow

Inputs:

- `<vault>/<handle>/wiki/.clean_corpus.jsonl`
- `<vault>/<handle>/wiki/.ingest_index.jsonl`
- `<vault>/_cross/topic_registry.md`
- Existing `sources`, `methods`, `positions`, `timeline.md`, and `soul.md` when incrementally updating.

Outputs:

- `wiki/.topic_buckets.json`
- `wiki/sources/*.md`
- `wiki/methods/*.md`
- `wiki/positions/*.md`
- `wiki/timeline.md`
- `wiki/soul.md`
- `wiki/_index.md`
- `wiki/_log.md`
- `wiki/.distill_meta.json`

Rules:

- Back up any existing wiki file before modifying it.
- Every durable claim must cite tweet ids or source pages.
- Replies marked substantive by `kol-clean` are first-class evidence.
- Subscriber-only content must be marked private and should not be quoted in public-facing text.
- Do not rewrite voice samples during small incremental ingest unless explicitly asked.

Prompt templates live in `plugins/kol-tools/templates/`.
