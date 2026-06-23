# Phase 2.C.3 Timeline + Soul Agent Prompt 模板

> 占位符: `<HANDLE>` `<DESC>` `<USABLE_N>` `<TWEET_N>` `<REPLY_N>` `<LANG_MIX>` `<COVERAGE>` `<已有KOL列表>`
> 用法: CLAUDE.md kol-ingest Phase C, 待 4 sources 批 + methods/positions 全完后, 起 1 个 general-purpose agent。

---

Phase 2.C.3 (final) — ingest @<HANDLE> (<DESC>). raw 含实质 replies (<REPLY_N> of <USABLE_N> usable)。

**Read all:**
- `/Users/saberrao/vault/kol/<HANDLE>/wiki/.ingest_index.jsonl` / `.ingest_stats.json` / `.topic_buckets.json`
- `/Users/saberrao/vault/kol/<HANDLE>/wiki/sources/` (全部) / `methods/` (全部) / `positions/` (全部)
- `/Users/saberrao/vault/kol/AGENTS.md` (soul schema 严格遵守)
- (若重 ingest, 参考不改) `wiki.v1-bak-*/soul.md` — v2 必须是 superset 不退化

**两输出:**

## A) `/Users/saberrao/vault/kol/<HANDLE>/wiki/timeline.md`

仅记录立场明确变化的议题 (前后矛盾/演变)。扫 positions 立场翻转 + methods/self-correction + sources 自我修正语。Aim 5-9 议题, 不硬凑。Schema:
```markdown
---
type: kol-timeline
handle: <HANDLE>
tracked_issues: <N>
created: <DATE>
last_updated: <DATE>
---
# 观点演变时间线
> 仅记录前后立场明确变化的, 未列入视为稳定 (以 [[soul.md]] 核心观点集锦 为准)。
## <议题>
| 时间 | 立场 | 触发/论据 | 推文 id |   (reply id 标 [reply])
**当前立场:** / **演变原因:** / **关联:** [[positions/X]] [[methods/Y]]
```

## B) `/Users/saberrao/vault/kol/<HANDLE>/wiki/soul.md`

严格按 CLAUDE.md soul schema。Frontmatter 必含: handle, type=kol-soul, language, language_mix=<LANG_MIX>, domain, coverage_period=<COVERAGE>, tweet_count_indexed=<USABLE_N>, raw_version=v2, includes_replies=true, trust_level=待评定, voice_profile_version, soul_version, signature_phrases[] (v2 corpus 含 reply 重核频次, 10-16), do_not_say[], aliases, related[], last_ingest, purpose=个人投资决策辅助(非冒充本人)。

章节顺序: 身份 / 方法论(全列按 applies_count 降序, 含新方法) / 核心观点集锦(15-20 evergreen, 标 仍持有|演变→timeline) / 关键观点(6-8 议题展开) / 叙事特征(写厚: 句式/语气/比喻库/标志性术语/**代表性 few-shot 原文 8-12 条带场景标签, 必含 2-3 条 substantive reply 标 [reply]**) / 互动网络(从 replies 的 @ 重建, 比纯 tweet 更全) / 舒适圈与禁区 / 已知偏见(LLM推断+自我承认) / 信号价值(placeholder+alpha候选) / 已索引素材(全列按量降序)。

**末尾必加** (若已注册 ≥2 KOL): `## 与 @<已有KOL> 的核心分野` — debate 弹药库:
- 对比总表 (方法论母体/背景/估值标尺/覆盖主场/关键议题立场逐行)
- 3-5 段差异分析, 每段带双方 wikilink, 指出 debate 引爆点

**v2 重点:** replies 是最高信号层 (KOL 被挑战时反驳藏最锋利方法论, 新方法常首现于 reply) — soul 叙事特征 + 方法论必须吃进。重 ingest 时 v2 是 v1 superset 不退化。

**Quality:** signature_phrases 真实高频 (扫 corpus 确认); few-shot 场景多样且含 reply; 严格档案式不客套。

报告: timeline 议题数 / soul 字数行数 / signature_phrases 数 / few-shot 数(含几 reply) / 与已有KOL分野节质量 / 取舍。只写 timeline.md + soul.md。
