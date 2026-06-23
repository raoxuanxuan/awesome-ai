# Phase 2.B Topic 聚类 Agent Prompt 模板

> 占位符: `<HANDLE>` `<DESC>` (KOL 一句话画像) `<USABLE_N>` `<TWEET_N>` `<REPLY_N>`
> 用法: CLAUDE.md kol-ingest Phase B 用此模板起 1 个 general-purpose agent (background)。

---

Phase 2.B ingest for @<HANDLE> (<DESC>).

**Input:** `/Users/saberrao/vault/kol/<HANDLE>/wiki/.ingest_index.jsonl`
- Skip docs where `is_retweet=true` OR `low_content=true`.
- 留 **<USABLE_N> 可用** (~<TWEET_N> 原创 + ~<REPLY_N> 实质 reply)。
- 字段: id,date,lang,text,is_reply,reply_to,favorite_count,view_count,low_content,is_retweet。
- **replies 已去噪**: low_content=true 已标掉寒暄/一字回 reply; 剩下的 is_reply=true 是 substantive (真观点 reply, 含 $ticker/数字/看多看空 或 >20 字实质)。

**Task:** 聚类 <USABLE_N> 可用 docs, 每 doc 1-3 topic tag。

**复用 taxonomy:** 先读 `/Users/saberrao/vault/kol/_cross/topic_registry.md`。**精确复用已注册 topic 名** (跨 KOL 一致性)。仅当出现真新议题才加 topic, 加则 append 到 topic_registry.md 标 `[+<HANDLE>]`。

**Output:** `/Users/saberrao/vault/kol/<HANDLE>/wiki/.topic_buckets.json`
```json
{ "topic_name": ["tweet_id", ...], ... }
```
- topic 名精确匹配 topic_registry bold 名
- 每 doc 1-3 桶; **replies 与 tweets 同等** tag 进实质 topic (不准 dump 进杂感, 它们已通过密度过滤=带信号)

**Quality:** 桶 ≥5 (小桶并入 parent) / 杂感 fallback 可超; replies 必须分布进实质桶; 杂感应比未过滤前小。

**Report:** 总 topics / 复用 vs 新 / top5 桶 / reply-docs 进实质桶占比 / 新增 topic。

只写 `.topic_buckets.json` (+ 新 topic 则 topic_registry.md)。不碰 sources/methods/positions/soul/timeline。
