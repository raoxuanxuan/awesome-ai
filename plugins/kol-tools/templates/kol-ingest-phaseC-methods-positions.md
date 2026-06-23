# Phase 2.C.2 Methods + Positions Agent Prompt 模板

> 占位符: `<HANDLE>` `<DESC>` `<USABLE_N>` `<TWEET_N>` `<REPLY_N>` `<已有KOL>`
> 用法: CLAUDE.md kol-ingest Phase C 用此模板起 1 个 general-purpose agent (background), 与 4 sources 批并发。

---

Phase 2.C.2 — ingest @<HANDLE> (<DESC>). raw 含实质 replies (已去噪)。

**Input:** `/Users/saberrao/vault/kol/<HANDLE>/wiki/.ingest_index.jsonl`
- Skip is_retweet=true OR low_content=true → <USABLE_N> usable (<TWEET_N> tweet + <REPLY_N> 实质 reply)
- **replies 高信号**: KOL 被空头/质疑者挑战时的反驳藏最锋利方法论 — 重点挖

**两输出 (空目录写新):**

## A) Methods — `/Users/saberrao/vault/kol/<HANDLE>/wiki/methods/<slug>.md`

≥5 次复现的分析框架 (tweets + replies)。slug = 英文 kebab-case (跨 KOL 同方法用同名复用)。

Schema:
```markdown
---
method: <name>
type: kol-method
handle: <HANDLE>
applies_count: <N>
created: <DATE>
raw_version: v2
---
# <name>
## 本质 (一句话)
## 何时用
## 何时不用
## 步骤/公式
## 实例 (3-5, 标 tweet|reply + id 链接; 优先含 ≥1 reply 实例 — 反驳中见方法)
## 与 @<已有KOL> 同方法对比 (若复用名)
- 对方用法: <一句话> ([[../../<已有KOL>/wiki/methods/<slug>]])
- 我的差异: <差异>
## 关联
- [[../sources/<topic>]] [[<other method>]]
```

## B) Positions — `/Users/saberrao/vault/kol/<HANDLE>/wiki/positions/<ticker>.md`

≥3 条实质评论 (tweets+replies) 的 ticker/事件。

Schema:
```markdown
---
target: <ticker/event>
type: kol-position
handle: <HANDLE>
tweet_count: <N>
reply_count: <N>
first_seen: YYYY-MM-DD
last_seen: YYYY-MM-DD
created: <DATE>
raw_version: v2
---
# <target>
## 当前立场 (按最新)
<看多/看空/中立 + 信心度>
## 立场演变
| 时间 | 立场 | 触发/论据 | id (tweet|reply) |
## 关键论据
## 风险/反方 (KOL 自己提过的)
## 与 @<已有KOL> 对照 (若对方也有该 position)
- 对方立场: <一句话> ([[../../<已有KOL>/wiki/positions/<target>]])
- 我的差异: <差异>
## 关联
```

**Quality:** methods ≥5 / positions ≥3 (含 reply 计数); 覆盖全 6 月窗; KOL 真术语保留; 引用必带 id + tweet|reply 标注; 立场明确不要"复杂"; 双语 KOL 英文原文别全译。

报告: methods 数 / positions 数 / 各 max-min applies_count / 取舍 / replies 贡献了哪些新增或强化。只写 methods/ 和 positions/。
