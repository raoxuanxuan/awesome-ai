# KOL Twin Rollout Results

Date: 2026-06-27

## Repository Work

Implemented rollout tooling:

- `kol_wiki_inventory.py`
- `kol_schema_validate.py`
- `kol_rollout.py`
- `kol_distill.py --mode bootstrap-pack`
- `kol_distill.py --mode repair-pack`
- schema-aware `kol_distill.py --mode validate`
- rollout and evaluation documentation

## Real Vault Inventory

Runtime report:

```text
/Users/saberrao/vault/kol/_cross/rollout_report_2026-06-27.json
```

Summary:

- 12 KOL handles inspected.
- 11 handles are `existing_mature_wiki`.
- 1 handle is `bootstrap_required`: `AswathDamodaran`.
- All 12 handles have nonzero `.clean_corpus.jsonl` and `.ingest_index.jsonl`.
- All handles currently have schema debt under the new stricter wiki schema.
- `LinQingV` has a mature wiki but no `.ingest_meta.json`; watermark handling
  needs a separate initialization step before normal delta commits.

## TJ_Research Pilot

Inventory:

- route: `existing_mature_wiki`
- clean/index count: 2,629
- current delta: `none`
- existing old pack:
  `/Users/saberrao/vault/kol/TJ_Research/wiki/.distill_prompt_packs/delta-2069392786437087338-20260623-150543`

Old pack validation:

- failed because the old pack lacked `risk_assessment.json` and
  `schema_manifest.json`.
- tweet id coverage itself was present.

Repair pack:

```text
/Users/saberrao/vault/kol/TJ_Research/wiki/.distill_prompt_packs/tj-repair-2069392786437087338
```

Repair result:

- delta items: 17
- risk: `high`
- review status: `user_review_required`
- blockers: none
- validation writes `validation_result.json` but keeps
  `safe_to_commit_watermark: false` until a reviewed apply result exists.
- no durable wiki page was modified by the repair pack.

## AswathDamodaran Bootstrap

Bootstrap pack:

```text
/Users/saberrao/vault/kol/AswathDamodaran/wiki/.distill_prompt_packs/AswathDamodaran-bootstrap-001
```

Result:

- selected clean/distill items: 5
- risk: `blocked`
- all 5 selected items were flagged as private/subscriber evidence.
- no durable wiki page was modified.

## Tier 1 Query Runtime Evaluation

Generated context packs:

```text
/Users/saberrao/vault/kol/TJ_Research/wiki/.ask_context_packs/eval-tj-ai-capex-20260627
/Users/saberrao/vault/kol/tig88411109/wiki/.ask_context_packs/eval-tig-open-model-capex-20260627
```

TJ context-pack included:

- `soul.md`
- `methods/ai-capex-roi.md`
- `methods/ai-fundamental-validation.md`
- AI capex / AI compute source pages
- related OpenAI / large-cap tech position pages
- `timeline.md`

tig context-pack included:

- `soul.md`
- `methods/capex-roi-audit.md`
- cognition / two-book / event-probability methods
- AI compute and HBM source pages
- `timeline.md`

## Remaining Review Queue

- Review TJ repair pack before any forced apply.
- Resolve AswathDamodaran private/subscriber evidence blockers before bootstrap
  can proceed.
- Decide whether to bulk-repair historical schema debt for existing mature
  wikis or only enforce schema on newly applied packs.
- Initialize or repair `.ingest_meta.json` for `LinQingV` before normal delta
  watermark commits.
