# KOL Distill Usage

`kol-distill` turns a ready ingest delta into a reviewable distillation workspace.

Current productized mode:

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
├── risk_assessment.json
├── delta_items.jsonl
├── delta_brief.md
├── backup_plan.json
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

After the generated prompts are reviewed and wiki files are updated, advance the
watermark explicitly:

```bash
python3 plugins/kol-tools/scripts/kol_delta.py TJ_Research \
  --vault /Users/saberrao/vault/kol \
  --commit <watermark_proposed> \
  --added <delta_count>
```
