# KOL Twin Evaluation

Use these questions to verify that `kol-ask` loads the right KOL wiki context
and keeps answer boundaries explicit.

## TJ_Research

1. 怎么看 AI capex 是不是泡沫？
2. 怎么看 NVDA 的估值？
3. 怎么看美联储路径？
4. 哪些问题超出 TJ 的覆盖范围？

## tig88411109

1. 怎么看开源模型降价？
2. 怎么看 AI 算力需求？
3. 哪些回复体现其核心方法论？

## Expected Answer Rules

- Must include `confidence`.
- Must include `in_comfort_zone`.
- Must include wikilinks.
- Must include primary tweet ids when possible.
- Must say out of coverage instead of inventing.

## Context-Pack Checks

For Tier 1 KOLs, a context pack should include:

- `soul.md`
- relevant `methods/*.md`
- relevant `sources/*.md`
- relevant `positions/*.md` when the question contains a ticker or asset
- `timeline.md` when the question matches an evolving stance

Context packs do not execute a model by themselves. They only write
`.ask_context_packs/<pack-id>/context.md`, `prompt.md`, and `manifest.json`.
