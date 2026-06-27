# KOL Distill Usage

`kol-distill` turns a ready ingest delta into a reviewable distillation workspace.

Start with a prompt pack:

```bash
python3 plugins/kol-tools/scripts/kol_distill.py TJ_Research \
  --vault /Users/saberrao/vault/kol \
  --mode prompt-pack \
  --policy balanced
```

For deterministic tests or repeatable review:

```bash
python3 plugins/kol-tools/scripts/kol_distill.py TJ_Research \
  --vault /Users/saberrao/vault/kol \
  --mode prompt-pack \
  --pack-id manual-review-001
```

The command requires:

```text
vault/kol/<handle>/wiki/.ingest_delta.json
vault/kol/<handle>/wiki/.clean_corpus.jsonl or the source path recorded in .ingest_delta.json
```

It writes:

```text
vault/kol/<handle>/wiki/.distill_prompt_packs/<pack-id>/
├── manifest.json
├── schema_manifest.json
├── risk_assessment.json
├── delta_items.jsonl
├── delta_brief.md
├── backup_plan.json
├── schemas/
│   ├── source.schema.md
│   ├── method.schema.md
│   ├── position.schema.md
│   ├── timeline.schema.md
│   └── soul.schema.md
└── prompts/
    ├── 01-sources.md
    ├── 02-methods-positions.md
    └── 03-timeline-soul.md
```

It does not write:

```text
sources/*.md
methods/*.md
positions/*.md
timeline.md
soul.md
_index.md
_log.md
.ingest_meta.json
```

## Risk Policy

`--policy balanced` is the default. It classifies each run:

| review_status | Meaning | User review |
| --- | --- | --- |
| `auto_eligible` | Small source/index-log-only delta. | Not required after validators pass. |
| `agent_review_required` | Existing method/position updates or medium delta. | Not required unless validators fail. |
| `user_review_required` | New method/position, `timeline.md`, `soul.md`, or large delta. | Required before apply/commit. |
| `blocked` | Private/subscriber evidence, schema mismatch, or missing required fields. | Required after blockers are fixed. |

For maximum caution:

```bash
python3 plugins/kol-tools/scripts/kol_distill.py TJ_Research \
  --vault /Users/saberrao/vault/kol \
  --mode prompt-pack \
  --policy conservative
```

## Apply / Validate / Commit

Before applying packs across an existing vault, inspect readiness:

```bash
python3 plugins/kol-tools/scripts/kol_wiki_inventory.py \
  --vault /Users/saberrao/vault/kol
```

Schema-check a single KOL:

```bash
python3 plugins/kol-tools/scripts/kol_schema_validate.py TJ_Research \
  --vault /Users/saberrao/vault/kol
```

Historical wiki pages may fail schema validation until a repair pack is
reviewed. Treat that as rollout debt, not as permission to auto-rewrite
`soul.md`, `timeline.md`, methods, or positions.

Apply a low-risk pack:

```bash
python3 plugins/kol-tools/scripts/kol_distill.py TJ_Research \
  --vault /Users/saberrao/vault/kol \
  --mode apply \
  --pack-id <pack-id>
```

Default `apply` only accepts `auto_eligible` packs. It writes:

```text
wiki/.distill_prompt_packs/<pack-id>/apply_result.json
```

It backs up changed files and appends tweet-id-cited evidence to the selected
source pages plus `_log.md`.

For a reviewed non-auto pack:

```bash
python3 plugins/kol-tools/scripts/kol_distill.py TJ_Research \
  --vault /Users/saberrao/vault/kol \
  --mode apply \
  --pack-id <pack-id> \
  --force
```

Blocked packs still refuse to apply.

Validate coverage:

```bash
python3 plugins/kol-tools/scripts/kol_distill.py TJ_Research \
  --vault /Users/saberrao/vault/kol \
  --mode validate \
  --pack-id <pack-id>
```

This writes `validation_result.json` and checks every delta tweet id appears in
durable wiki files, not merely inside the prompt pack. It also refuses to mark a
pack safe when `risk_assessment.json`, `schema_manifest.json`, or copied schema
files are missing. Schema validation is part of the gate: changed durable pages
must contain the required evidence sections and tweet-id anchors.

Commit watermark:

```bash
python3 plugins/kol-tools/scripts/kol_distill.py TJ_Research \
  --vault /Users/saberrao/vault/kol \
  --mode commit \
  --pack-id <pack-id>
```

`commit` refuses unless `validation_result.json` has
`safe_to_commit_watermark: true`.

`kol_delta.py --commit` remains a lower-level primitive for emergency repair.
Normal distillation should use `kol_distill.py --mode commit` so validation and
watermark movement stay coupled.
