---
name: kol-distill
description: Distill cleaned KOL corpora into sources, methods, positions, timeline, and soul wiki artifacts. Use after kol-clean and kol-index when a KOL archive needs first ingest or incremental knowledge updates.
---

# KOL Distill

Use this skill to convert cleaned, indexed KOL evidence into the durable KOL twin wiki.

## Boundary

- Reads `.clean_corpus.jsonl`, `.ingest_index.jsonl`, `.topic_buckets.json`, existing wiki pages, and `_cross/topic_registry.md`.
- `prompt-pack` mode writes only a review workspace under `wiki/.distill_prompt_packs/`.
- Each prompt pack includes a risk assessment so routine low-risk deltas do not require user review.
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
  --mode prompt-pack \
  --policy balanced
```

5. Read `manifest.json` or `risk_assessment.json`:
   - `auto_eligible`: agent/tooling may apply after validators pass; no user review required.
   - `agent_review_required`: agent review required; user review only if validators fail or uncertainty remains.
   - `user_review_required`: ask the user before applying or committing.
   - `blocked`: fix blockers before applying or committing.
6. Apply the generated guidance to update `sources`, `methods`, `positions`, then `timeline`, `soul`, `_index.md`, and `_log.md` according to the risk gate.
7. Commit the ingest watermark with `kol-delta --commit` only after wiki updates and validators are complete.

See `references/workflow.md` and `references/usage.md`.
