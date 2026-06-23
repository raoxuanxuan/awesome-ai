# Phase 2.C.1 Sources Agent Prompt 模板 (4 批)

> 占位符: `<HANDLE>` `<DESC>` `<BATCH_N>` (1-4) `<TOPIC_LIST>` (本批 topic, 逗号分隔)
> 用法: CLAUDE.md kol-ingest Phase C 用此模板起 **4 个并发** general-purpose agent (background),
>       按 .topic_buckets.json 桶大小贪心均分 4 批 (~均衡 tweet 总量, 单批失败只丢 1/4)。
> 分批脚本: 见 CLAUDE.md "4 批均分" 片段。

---

Phase 2.C.1 batch <BATCH_N>/4 — ingest @<HANDLE> (<DESC>). raw 含实质 replies (已去噪)。

**只写这些 topic 的 source 页:**
<TOPIC_LIST>

**Inputs:**
- `/Users/saberrao/vault/kol/<HANDLE>/wiki/.topic_buckets.json` (只用你这批 topic 的 id 列表)
- `/Users/saberrao/vault/kol/<HANDLE>/wiki/.ingest_index.jsonl` (id→text/date/fav/view/is_reply/reply_to)
- TJ 对照检查 (若非首 KOL): `ls /Users/saberrao/vault/kol/<已有KOL>/wiki/sources/` 同名 topic 加对照段

**replies 一等公民:** 桶内 is_reply=true 是 substantive (噪声已过滤)。织入立场, 引用标 `[reply]`; reply 常是 KOL 答挑战=最高推理信号。

**Output:** `/Users/saberrao/vault/kol/<HANDLE>/wiki/sources/<topic>.md` (中文文件名 OK)

Schema:
```markdown
---
topic: <name>
type: kol-source
handle: <HANDLE>
tweet_count: <N>
reply_count: <N of which replies>
date_range: YYYY-MM-DD ~ YYYY-MM-DD
total_engagement: {fav: <sum>, view: <sum>}
created: <DATE>
raw_version: v2
---

# <name>
> @<HANDLE> 在该议题核心观点。<N> 条 (含 <R> 实质回复), 覆盖 <date_range>。

## 核心立场
- **<立场>**: <一句话> + <论据 ≤2 句>
  - 代表: [<id>](https://x.com/<HANDLE>/status/<id>) ([reply] 若回复)
(3-8 条)

## 代表性原文 (3-5, 含 ≥1 实质 reply 若桶内有)
> [yyyy-mm-dd · fav N · view N · tweet|reply]
> <原文 ≤350 字, 双语保留原味不强译>
> [链接](https://x.com/<HANDLE>/status/<id>)

## 时间线 (按月计数)
| 月份 | 推文数 |

## 关联议题
`[[../sources/<other>]]` ×2-4

## 与 @<已有KOL> 对照  (仅当对方有同名 sources 页, 否则整段省略)
- 对方立场: <一句话> ([[../../<已有KOL>/wiki/sources/<topic>.md]])
- 我的差异: <差异>
```

**风格:** 保留该 KOL 真实术语 (非通用财经语); 不泛"关注X"直接给判断; 每立场 ≥1 id; 覆盖全 6 月窗。
杂感与社区互动 (fallback): 不抽投资立场, 只列 6-8 条代表性"风格碎片"作 voice-profile 原料, 标 tweet/reply。
桶 <5: 仍写但简短 + 页首标注信号薄弱。

报告: 写几页 / 每页 tweet vs reply / 含对照几页 / 桶<5 / 质量问题。只写你这批 topic 的 sources/。
