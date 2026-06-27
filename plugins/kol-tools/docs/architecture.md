# KOL Twin LLM Wiki Architecture

KOL Twin uses the LLM Wiki pattern as its durable memory layer, then adds
KOL-specific evidence, persona, stance, timeline, and incremental audit layers.

The goal is not to store tweets in Markdown. The goal is to compile a KOL's
public expression into a queryable, auditable, continuously updated decision
model.

```text
Karpathy-style LLM Wiki pattern
  + KOL-specific evidence pipeline
  + persona / stance / timeline schema
  + incremental distill workflow
  = KOL Twin Wiki System
```

## System Shape

```text
X/Twitter data
  -> twitter-fetch
  -> tweet-pool
  -> KOL raw archive
  -> kol-clean
  -> kol-index
  -> kol-delta
  -> kol-distill prompt-pack
  -> review / risk gate
  -> KOL LLM Wiki
  -> kol-ask / kol-debate
```

`invest wiki` and `ai wiki` are cross-domain context sources for answering, not
KOL-owned evidence.

## Layer 1: Evidence

Evidence is the immutable-ish source layer.

```text
tweet-pool/
  tweets/<tweet_id>.json
  authors/<handle>.json
  consumers/kol-tools.json

vault/kol/<handle>/raw/tweets/*.md
```

Responsibilities:

- Preserve original tweet, reply, quote, article, and subscriber-import facts.
- Keep tweet id, URL, timestamp, author, metrics, and relationship metadata.
- Avoid summarization, stance extraction, persona modeling, or answering.
- Keep raw data out of git and runtime state out of durable wiki pages.

`tweet-pool` is a normalized fetch cache, not a business queue. KOL-specific
state belongs to KOL tools and the KOL vault.

## Layer 2: Clean And Index

Clean/index turns raw evidence into deterministic, explainable ingest material.

```text
vault/kol/<handle>/wiki/.clean_corpus.jsonl
vault/kol/<handle>/wiki/.ingest_index.jsonl
vault/kol/<handle>/wiki/.ingest_stats.json
```

Responsibilities:

- Score quality as `high`, `medium`, `low`, or `noise`.
- Route evidence into `distill`, `voice`, `position`, or `timeline`.
- Preserve substantive replies without letting social replies pollute the twin.
- Build deterministic indexes and stats for downstream delta/distill.

Reply policy:

- Replies do not enter `distill` because they are long.
- Replies enter `distill` only when they contain durable signals such as ticker,
  number, method, position, reasoning, timeline, or investment semantics.
- Replies without durable signals may remain voice/context material.

Production `kol-index` requires `.clean_corpus.jsonl` by default. Raw fallback is
reserved for explicit legacy repair with `--legacy-raw`.

## Layer 3: LLM Wiki Compiler

This is the Karpathy LLM Wiki pattern applied to KOL evidence. It compiles
cleaned evidence into human-readable and LLM-readable Markdown.

Input:

```text
.clean_corpus.jsonl
.ingest_index.jsonl
.ingest_delta.json
```

Output:

```text
vault/kol/<handle>/wiki/
  _index.md
  soul.md
  timeline.md
  methods/*.md
  positions/*.md
  sources/*.md
```

The wiki is the primary long-term memory. Embedding or vector search can be
added later as auxiliary recall, but it must not replace the compiled Markdown
memory.

## Layer 4: KOL-Specific Schema

Generic LLM Wiki pages are usually organized around concepts, entities, topics,
or queries. KOL Twin uses a persona-grounded schema.

### `sources/*.md`

Topic-level evidence summaries.

Recommended structure:

```text
# Topic

## Scope
## Key Evidence
## Recurring Claims
## Contradictions Or Open Questions
## Related Methods
## Related Positions
## Evidence
- tweet_id, date, URL, short quote
```

### `methods/*.md`

Stable analysis frameworks repeatedly used by the KOL.

Recommended structure:

```text
# Method

## Core Rule
## Applies When
## Does Not Apply When
## Signals
## Failure Conditions
## Related Sources
## Related Positions
## Evidence
- tweet_id, date, URL, short quote
```

### `positions/*.md`

KOL stance on a ticker, company, asset, or event.

Recommended structure:

```text
# Position

## Current Stance
## Stance Strength
## Reasons
## Evolution
## Relevant Methods
## Risks / Disconfirming Evidence
## Evidence
- tweet_id, date, URL, short quote
```

### `timeline.md`

Opinion evolution and contradiction resolution.

Recommended structure:

```text
# Timeline

## Issue
### Starting View
### Change Trigger
### Current View
### Evidence Chain
```

### `soul.md`

Persona, language, comfort zone, biases, and high-level methods.

Recommended structure:

```text
# KOL Soul

## Identity And Coverage
## Core Methods
## Communication Style
## Signature Phrases
## Do Not Say
## Known Biases
## Out Of Coverage
## Trust Level
## Evidence Anchors
```

`soul.md` is the highest-risk layer. Updates to it should be conservative and
should require stronger evidence than source or method updates.

## Layer 5: Incremental Distill Workflow

KOLs keep publishing, so the wiki must be continuously maintained.

```text
kol_delta
  -> prompt-pack
  -> risk_assessment
  -> apply
  -> validate
  -> commit watermark
```

Workflow:

1. `kol_delta` finds new usable items after the ingest watermark.
2. `kol_distill --mode prompt-pack` creates a review workspace.
3. Risk gate classifies the run as `auto_eligible`, `agent_review_required`,
   `user_review_required`, or `blocked`.
4. `apply` writes durable wiki changes only when the risk gate allows it.
5. `validate` checks that every delta tweet id is covered by durable wiki pages.
6. `commit` advances `.ingest_meta.json` only after validation.

The watermark must not advance before durable wiki coverage is verified.

## Layer 6: Query Runtime

`kol-ask` and `kol-debate` read the compiled wiki, not raw tweets.

`kol-ask` loads:

```text
soul.md
methods/*.md
relevant positions/*.md
relevant sources/*.md
timeline.md when relevant
invest wiki / ai wiki context when relevant
```

Output must distinguish:

- Explicit KOL statement.
- Methodology-based inference.
- Out-of-coverage question.
- Known bias or weak evidence.

Every answer should include machine-readable metadata:

```text
confidence: high|medium|low
in_comfort_zone: yes|no
primary_sources: [tweet_id, ...]
wikilinks_used: [...]
caveats: ...
```

## Layer 7: Debate Runtime

`kol-debate` runs several KOL twins over the same question.

```text
Round 1: each KOL answers independently
Round 2: each KOL critiques other answers
Synthesis: summarize consensus, disagreement, blind spots, and confidence
```

The value comes from having each KOL load its own evidence-backed wiki, not from
asking generic agents to role-play.

## Directory Target

```text
vault/kol/
  _cross/
    _registry.md
    topic_registry.md
    debates/
    schemas/
      method.schema.md
      position.schema.md
      source.schema.md
      soul.schema.md

  <handle>/
    raw/
      tweets/*.md
      .backfill_state.json

    wiki/
      _index.md
      soul.md
      timeline.md

      methods/
      positions/
      sources/

      .clean_corpus.jsonl
      .ingest_index.jsonl
      .ingest_stats.json
      .ingest_delta.json
      .ingest_meta.json

      .distill_prompt_packs/
        <pack-id>/
          manifest.json
          schema_manifest.json
          risk_assessment.json
          delta_items.jsonl
          delta_brief.md
          schemas/
          prompts/
```

## Plugin Boundaries

```text
twitter-tools
  twitter-fetch        # fetch X/Twitter data
  tweet-pool           # canonical normalized tweet cache
  twitter-media-fetch  # download media
  twitter-monitor      # monitor new posts and notify/review

kol-tools
  kol-refresh          # KOL fetch orchestration and raw archive writes
  kol-clean            # deterministic cleaning
  kol-index            # deterministic indexing
  kol-delta            # incremental boundary detection
  kol-distill          # wiki compilation and audit
  kol-ask              # single-KOL answering
  kol-debate           # multi-KOL debate

kol-twin
  user-facing persona runtime skill
```

## Architecture Principles

1. Raw evidence is preserved and not rewritten by distillation.
2. `tweet-pool` is a canonical fetch cache, not downstream workflow state.
3. Clean/index must remain deterministic and explainable.
4. Markdown wiki is the primary memory; embeddings are optional recall helpers.
5. Durable wiki claims must cite tweet ids or clearly mark inference.
6. `soul.md` updates are high-risk and conservative.
7. Answers must separate explicit evidence from inferred stance.
8. Watermarks advance only after durable wiki validation.
9. KOL Twin output is private decision support, not impersonation.
