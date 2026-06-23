# KOL Tools

KOL Tools is a private KOL digital-twin plugin for Codex and Claude Code.

## What It Does

- Maintains raw KOL archives under `/Users/saberrao/vault/kol/`.
- Reuses `twitter-tools/tweet-pool` as the canonical tweet cache before writing raw KOL Markdown.
- Cleans low-information tweets without deleting raw data.
- Preserves substantive replies and routes them into methods, positions, sources, voice, or timeline.
- Builds deterministic indexes and stats.
- Generates risk-scored distillation prompt packs before KOL wiki updates.
- Provides prompts and scripts for KOL ask and debate workflows.

## What It Does Not Do

- It does not implement low-level X/Twitter fetching or global tweet caching itself. It calls `twitter-tools/twitter-fetch` and `twitter-tools/tweet-pool`.
- It does not publish KOL twin output.
- It does not commit raw tweets, cookies, subscriber posts, or runtime state.
- It does not impersonate a KOL as the real person.

## Runtime Data

The authoritative KOL vault is:

```text
/Users/saberrao/vault/kol/
```

Override:

```bash
export KOL_TOOLS_VAULT=/path/to/kol
```

KOL refresh also writes normalized tweet cache and consumer status through
`twitter-tools/tweet-pool`. By default that runtime is:

```text
/Users/saberrao/ai-workspace/content-creation/.tweet-pool/
```

Override for tests:

```bash
export TWEET_POOL_RUNTIME=/tmp/.tweet-pool
```

## Install

From the `awesome-ai` repository root:

```bash
codex plugin marketplace add .
codex plugin add kol-tools@awesome-ai
claude plugin marketplace add ./
claude plugin install kol-tools@awesome-ai
```

## First Run

The plugin can create derived files such as `.clean_corpus.jsonl`, `.ingest_index.jsonl`, and health reports. It will not create credentials or scrape browser cookies.

## Common Commands

```bash
python3 plugins/kol-tools/skills/kol-clean/scripts/kol_clean.py TJ_Research --vault /Users/saberrao/vault/kol --dry-run
python3 plugins/kol-tools/skills/kol-index/scripts/kol_index.py TJ_Research --vault /Users/saberrao/vault/kol --dry-run
python3 plugins/kol-tools/scripts/registry_health.py --vault /Users/saberrao/vault/kol
python3 plugins/kol-tools/scripts/kol_refresh.py --vault /Users/saberrao/vault/kol --handle TJ_Research --incremental --max-pages 1 --dry-run
python3 plugins/kol-tools/scripts/kol_delta.py TJ_Research --vault /Users/saberrao/vault/kol --cap 120
python3 plugins/kol-tools/scripts/kol_distill.py TJ_Research --vault /Users/saberrao/vault/kol --mode prompt-pack --policy balanced
python3 plugins/kol-tools/scripts/kol_distill.py TJ_Research --vault /Users/saberrao/vault/kol --mode apply --pack-id <pack-id>
python3 plugins/kol-tools/scripts/kol_distill.py TJ_Research --vault /Users/saberrao/vault/kol --mode validate --pack-id <pack-id>
python3 plugins/kol-tools/scripts/kol_distill.py TJ_Research --vault /Users/saberrao/vault/kol --mode commit --pack-id <pack-id>
python3 plugins/kol-tools/scripts/kol_ask.py TJ_Research --vault /Users/saberrao/vault/kol --question "怎么看 NVDA 和 AI capex?" --mode context-pack
python3 plugins/kol-tools/scripts/kol_debate.py --vault /Users/saberrao/vault/kol --kols TJ_Research,LinQingV --question "AI capex 是泡沫吗？" --rounds 2 --mode prompt-pack
```

`kol_distill.py --mode prompt-pack` writes only a review workspace under:

```text
/Users/saberrao/vault/kol/<handle>/wiki/.distill_prompt_packs/
```

`prompt-pack` does not modify durable wiki pages or advance `.ingest_meta.json`.

The generated `manifest.json` and `risk_assessment.json` classify the run:

- `auto_eligible`: low-risk source/index-log updates; user review is not required after validators pass.
- `agent_review_required`: medium-risk existing method/position updates or larger deltas; an agent should review, but the user is not interrupted unless validation fails.
- `user_review_required`: high-risk changes such as timeline/soul updates, new methods, new positions, or large deltas.
- `blocked`: private/subscriber evidence, schema mismatch, or missing required evidence fields; do not apply or commit.

`kol_distill.py --mode apply` applies only `auto_eligible` packs by default. It
backs up changed files, appends source evidence with tweet ids, and writes
`apply_result.json`. For reviewed non-auto packs, pass `--force`; blocked packs
still refuse.

`kol_distill.py --mode validate` checks durable wiki coverage for every delta id
and writes `validation_result.json`. `--mode commit` advances the ingest
watermark only after validation marks the pack safe.

`kol_ask.py --mode context-pack` writes only a question-specific context
workspace under:

```text
/Users/saberrao/vault/kol/<handle>/wiki/.ask_context_packs/
```

It does not call a model; use the generated `prompt.md` with the runner of choice.

`kol_debate.py --mode prompt-pack` writes a multi-KOL debate workspace under:

```text
/Users/saberrao/vault/kol/_cross/debates/
```

It creates participant contexts, Round 1/2 prompts, and a synthesizer prompt, but
does not execute the model or generate a final verdict.

## Privacy

Raw tweets and subscriber-only content remain private. Do not publish generated twin output as if it were written by the KOL.
