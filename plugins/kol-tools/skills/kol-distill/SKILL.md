---
name: kol-distill
description: Distill cleaned KOL corpora into sources, methods, positions, timeline, and soul wiki artifacts. Use after kol-clean and kol-index when a KOL archive needs first ingest or incremental knowledge updates.
---

# KOL Distill

Use this skill to convert cleaned, indexed KOL evidence into the durable KOL twin wiki.

## Boundary

- Reads `.clean_corpus.jsonl`, `.ingest_index.jsonl`, `.topic_buckets.json`, existing wiki pages, and `_cross/topic_registry.md`.
- Writes KOL wiki artifacts only when the user explicitly asks to ingest or update.
- Keeps raw tweets untouched.
- Keeps tweet ids and links as evidence.
- Does not fetch X/Twitter.
- Does not answer user questions directly; use `kol-ask` after distillation.

## Workflow

1. Run `kol-clean`.
2. Run `kol-index`.
3. Phase B: cluster usable items into topic buckets.
4. Phase C: compile `sources`, `methods`, `positions`, then `timeline` and `soul`.
5. Write `_index.md`, `_log.md`, and `.distill_meta.json`.

See `references/workflow.md`.
