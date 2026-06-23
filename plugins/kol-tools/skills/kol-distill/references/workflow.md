# KOL Distill Workflow

Inputs:

- `<vault>/<handle>/wiki/.clean_corpus.jsonl`
- `<vault>/<handle>/wiki/.ingest_index.jsonl`
- `<vault>/<handle>/wiki/.ingest_meta.json`
- `<vault>/<handle>/wiki/.ingest_delta.tsv` for incremental distillation
- `<vault>/_cross/topic_registry.md`
- Existing `sources`, `methods`, `positions`, `timeline.md`, and `soul.md` when incrementally updating.

Outputs:

- `wiki/.distill_prompt_packs/<pack-id>/manifest.json`
- `wiki/.distill_prompt_packs/<pack-id>/delta_items.jsonl`
- `wiki/.distill_prompt_packs/<pack-id>/delta_brief.md`
- `wiki/.distill_prompt_packs/<pack-id>/backup_plan.json`
- `wiki/.distill_prompt_packs/<pack-id>/prompts/*.md`
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

- Start with `prompt-pack` mode for incremental ingest. It does not mutate durable wiki pages.
- Back up any existing wiki file before modifying it.
- Every durable claim must cite tweet ids or source pages.
- Replies marked substantive by `kol-clean` are first-class evidence.
- Subscriber-only content must be marked private and should not be quoted in public-facing text.
- Do not rewrite voice samples during small incremental ingest unless explicitly asked.

Incremental boundary:

```bash
python3 plugins/kol-tools/scripts/kol_delta.py <handle> --vault /Users/saberrao/vault/kol --cap 120
```

If status is `ready`, integrate `.ingest_delta.tsv` into existing wiki pages, then commit:

```bash
python3 plugins/kol-tools/scripts/kol_distill.py <handle> \
  --vault /Users/saberrao/vault/kol \
  --mode prompt-pack
```

Review the generated workspace before editing wiki files. After sources/methods/positions/timeline/soul/index/log are updated, commit the watermark:

```bash
python3 plugins/kol-tools/scripts/kol_delta.py <handle> --vault /Users/saberrao/vault/kol --commit <watermark_proposed> --added <n>
```

Prompt templates live in `plugins/kol-tools/templates/`.
