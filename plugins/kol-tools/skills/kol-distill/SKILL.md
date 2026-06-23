---
name: kol-distill
description: Distill cleaned KOL corpora into sources, methods, positions, timeline, and soul wiki artifacts. Use after kol-clean and kol-index when a KOL archive needs first ingest or incremental knowledge updates.
---

# KOL Distill

Use this skill to convert cleaned, indexed KOL evidence into the durable KOL twin wiki.

## Boundary

- Reads `.clean_corpus.jsonl`, `.ingest_index.jsonl`, `.topic_buckets.json`, existing wiki pages, and `_cross/topic_registry.md`.
- `prompt-pack` mode writes only a review workspace under `wiki/.distill_prompt_packs/`.
- Writes KOL wiki artifacts only when the user explicitly asks to ingest or update.
- Keeps raw tweets untouched.
- Keeps tweet ids and links as evidence.
- Does not fetch X/Twitter.
- Does not answer user questions directly; use `kol-ask` after distillation.
- Does not advance `.ingest_meta.json`; only `kol-delta --commit` may do that after reviewed wiki changes.

## Workflow

1. Run `kol-clean`.
2. Run `kol-index`.
3. Run `kol-delta` until status is `ready`.
4. Generate a prompt pack:

```bash
python3 plugins/kol-tools/scripts/kol_distill.py <handle> \
  --vault /Users/saberrao/vault/kol \
  --mode prompt-pack
```

5. Review the generated `manifest.json`, `delta_brief.md`, `backup_plan.json`, and `prompts/*.md`.
6. Only after review, use the prompts to update `sources`, `methods`, `positions`, then `timeline`, `soul`, `_index.md`, and `_log.md`.
7. Commit the ingest watermark with `kol-delta --commit` only after the wiki updates are complete.

See `references/workflow.md` and `references/usage.md`.
