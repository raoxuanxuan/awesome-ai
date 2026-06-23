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
- `wiki/.distill_prompt_packs/<pack-id>/risk_assessment.json`
- `wiki/.distill_prompt_packs/<pack-id>/delta_items.jsonl`
- `wiki/.distill_prompt_packs/<pack-id>/delta_brief.md`
- `wiki/.distill_prompt_packs/<pack-id>/backup_plan.json`
- `wiki/.distill_prompt_packs/<pack-id>/apply_result.json` after apply
- `wiki/.distill_prompt_packs/<pack-id>/validation_result.json` after validate
- `wiki/.distill_prompt_packs/<pack-id>/commit_result.json` after commit
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
- Use the risk gate in `risk_assessment.json`: auto-eligible deltas do not require user review, medium deltas require agent review, high-risk deltas require user review, blocked deltas must not be applied.
- Use `apply` only after the risk gate allows it. Default apply accepts `auto_eligible`; reviewed non-auto packs require `--force`; blocked packs always refuse.
- Use `validate` before `commit`. Validation checks durable wiki coverage for every delta id and excludes prompt-pack files from coverage.
- Use `commit` only after validation writes `safe_to_commit_watermark: true`.
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

Then choose the path from `risk_assessment.json`:

- `auto_eligible`: apply, validate, and commit directly.
- `agent_review_required`: have the agent review/update the wiki, then validate and commit. Use `apply --force` only when the generated append-only source update is the intended change.
- `user_review_required`: require user approval before durable wiki changes, then validate and commit.
- `blocked`: fix blockers first; do not apply or commit.

For the common auto-eligible path:

```bash
python3 plugins/kol-tools/scripts/kol_distill.py <handle> --vault /Users/saberrao/vault/kol --mode apply --pack-id <pack-id>
python3 plugins/kol-tools/scripts/kol_distill.py <handle> --vault /Users/saberrao/vault/kol --mode validate --pack-id <pack-id>
python3 plugins/kol-tools/scripts/kol_distill.py <handle> --vault /Users/saberrao/vault/kol --mode commit --pack-id <pack-id>
```

Prompt templates live in `plugins/kol-tools/templates/`.
