# KOL Tools

KOL Tools 是一个同时面向 Codex 和 Claude Code 的私有 KOL 数字分身插件。

## 能做什么

- 维护 `/Users/saberrao/vault/kol/` 下的 KOL 原始档案。
- 写入 KOL raw Markdown 前，复用 `twitter-tools/tweet-pool` 作为规范化推文缓存。
- 清洗低信息密度推文，但不删除原始数据。
- 保留有实质信息的回复，并将其路由到方法论、立场、source、voice 或 timeline。
- 构建确定性的索引和统计信息。
- 在更新 KOL wiki 前生成带风险分级的蒸馏 prompt pack。
- 提供 KOL ask 和 debate workflow 的 prompt 与脚本。

## 不做什么

- 不在本插件内实现底层 X/Twitter 抓取或全局推文缓存；这些能力由 `twitter-tools/twitter-fetch` 和 `twitter-tools/tweet-pool` 提供。
- 不公开发布 KOL twin 输出。
- 不提交原始推文、cookies、订阅者内容或运行时状态。
- 不把数字分身输出冒充成 KOL 本人发言。

## 运行时数据

权威 KOL vault 路径：

```text
/Users/saberrao/vault/kol/
```

可用环境变量覆盖：

```bash
export KOL_TOOLS_VAULT=/path/to/kol
```

对投资相关问题，`kol_ask.py` 也可以引入本地 invest wiki 的相关页面：

```text
/Users/saberrao/vault/invest/wiki/
```

可用环境变量覆盖：

```bash
export KOL_TOOLS_INVEST_WIKI=/path/to/invest/wiki
```

KOL refresh 还会通过 `twitter-tools/tweet-pool` 写入规范化推文缓存和 consumer 状态。默认运行时路径：

```text
/Users/saberrao/ai-workspace/content-creation/.tweet-pool/
```

测试时可覆盖：

```bash
export TWEET_POOL_RUNTIME=/tmp/.tweet-pool
```

历史 raw 档案可以用 `kol_pool_backfill.py` 迁移进 tweet-pool。这是针对旧 `vault/kol/<handle>/raw/tweets/*.md` 文件的一次性兼容迁移：它会写入 canonical tweet JSON 和 `consumers/kol-tools.json`，但不会改写 raw Markdown、不会清洗或索引内容、不会更新 wiki 页面，也不会推进 `.backfill_state.json`。

## 安装

在 `awesome-ai` 仓库根目录执行：

```bash
codex plugin marketplace add .
codex plugin add kol-tools@awesome-ai
claude plugin marketplace add ./
claude plugin install kol-tools@awesome-ai
```

## 首次运行

插件可以生成 `.clean_corpus.jsonl`、`.ingest_index.jsonl`、health report 等派生文件。它不会创建凭据，也不会抓取浏览器 cookies。

## 常用命令

```bash
python3 plugins/kol-tools/skills/kol-clean/scripts/kol_clean.py TJ_Research --vault /Users/saberrao/vault/kol --dry-run
python3 plugins/kol-tools/skills/kol-clean/scripts/kol_clean.py TJ_Research --vault /Users/saberrao/vault/kol --write
python3 plugins/kol-tools/skills/kol-index/scripts/kol_index.py TJ_Research --vault /Users/saberrao/vault/kol --dry-run
python3 plugins/kol-tools/scripts/registry_health.py --vault /Users/saberrao/vault/kol
python3 plugins/kol-tools/scripts/kol_pool_backfill.py --vault /Users/saberrao/vault/kol --all --dry-run
python3 plugins/kol-tools/scripts/kol_pool_backfill.py --vault /Users/saberrao/vault/kol --all
python3 plugins/kol-tools/scripts/kol_refresh.py --vault /Users/saberrao/vault/kol --handle TJ_Research --incremental --max-pages 1 --dry-run
python3 plugins/kol-tools/scripts/kol_delta.py TJ_Research --vault /Users/saberrao/vault/kol --cap 120
python3 plugins/kol-tools/scripts/kol_distill.py TJ_Research --vault /Users/saberrao/vault/kol --mode prompt-pack --policy balanced
python3 plugins/kol-tools/scripts/kol_distill.py TJ_Research --vault /Users/saberrao/vault/kol --mode apply --pack-id <pack-id>
python3 plugins/kol-tools/scripts/kol_distill.py TJ_Research --vault /Users/saberrao/vault/kol --mode validate --pack-id <pack-id>
python3 plugins/kol-tools/scripts/kol_distill.py TJ_Research --vault /Users/saberrao/vault/kol --mode commit --pack-id <pack-id>
python3 plugins/kol-tools/scripts/kol_ask.py TJ_Research --vault /Users/saberrao/vault/kol --question "怎么看 NVDA 和 AI capex?" --mode context-pack
python3 plugins/kol-tools/scripts/kol_ask.py TJ_Research --vault /Users/saberrao/vault/kol --question "怎么看 NVDA 和 AI capex?" --mode run --pack-id <pack-id> --runner-command "<stdin-stdout-runner>"
python3 plugins/kol-tools/scripts/kol_ask.py TJ_Research --vault /Users/saberrao/vault/kol --question "怎么看 NVDA 和 AI capex?" --mode run --pack-id <pack-id> --runner-command "python3 plugins/kol-tools/scripts/kol_codex_runner.py"
python3 plugins/kol-tools/scripts/kol_debate.py --vault /Users/saberrao/vault/kol --kols TJ_Research,LinQingV --question "AI capex 是泡沫吗？" --rounds 2 --mode prompt-pack
python3 plugins/kol-tools/scripts/kol_debate.py --vault /Users/saberrao/vault/kol --kols TJ_Research,LinQingV --question "AI capex 是泡沫吗？" --rounds 2 --mode run --pack-id <pack-id> --runner-command "<stdin-stdout-runner>"
python3 plugins/kol-tools/scripts/kol_debate.py --vault /Users/saberrao/vault/kol --kols TJ_Research,LinQingV --question "AI capex 是泡沫吗？" --rounds 2 --mode run --pack-id <pack-id> --runner-command "python3 plugins/kol-tools/scripts/kol_claude_runner.py"
```

`kol_distill.py --mode prompt-pack` 只会在下面目录写入 review workspace：

```text
/Users/saberrao/vault/kol/<handle>/wiki/.distill_prompt_packs/
```

`prompt-pack` 不会修改长期 wiki 页面，也不会推进 `.ingest_meta.json`。

生成的 `manifest.json` 和 `risk_assessment.json` 会对本次运行做风险分级：

- `auto_eligible`：低风险 source / index-log 更新；validator 通过后不需要用户审阅。
- `agent_review_required`：中风险的已有方法论/立场更新，或较大 delta；应由 agent 审阅，除非校验失败，不打断用户。
- `user_review_required`：高风险变更，例如 timeline / soul 更新、新方法论、新立场或大 delta。
- `blocked`：涉及私有/订阅证据、schema 不匹配或缺失必要证据字段；不能 apply 或 commit。

`kol_distill.py --mode apply` 默认只应用 `auto_eligible` pack。它会备份被修改文件、追加带 tweet id 的来源证据，并写入 `apply_result.json`。对已审阅的非 auto pack，可传 `--force`；blocked pack 仍会拒绝执行。

`kol_distill.py --mode validate` 会检查每个 delta id 是否已覆盖到长期 wiki，并写入 `validation_result.json`。`--mode commit` 只有在 validation 标记为安全后才会推进 ingest watermark。

`kol_ask.py --mode context-pack` 只会在下面目录写入问题专属 context workspace：

```text
/Users/saberrao/vault/kol/<handle>/wiki/.ask_context_packs/
```

对投资相关问题，`context-pack` 会在可用时加入 `_index.md` 和相关 invest wiki 页面。它不会调用模型；需要把生成的 `prompt.md` 交给你选择的 runner。

`kol_ask.py --mode run` 复用同一个 workspace，通过 `--runner-command` 执行 `prompt.md`，并写入 `answer.md`。runner 必须从 stdin 读取 prompt，并向 stdout 输出回答。manifest 只记录脱敏后的 runner 元数据，不保存完整命令。

内置 runner adapter：

```bash
python3 plugins/kol-tools/scripts/kol_codex_runner.py
python3 plugins/kol-tools/scripts/kol_claude_runner.py
```

`kol_codex_runner.py` 会以只读、无需审批、临时会话模式调用 `codex exec`。`kol_claude_runner.py` 会调用禁用工具、无 session 持久化的 `claude --print`。两者都从 stdin 读取 prompt，并把模型回答写到 stdout。

`kol_debate.py --mode prompt-pack` 会在下面目录写入多 KOL debate workspace：

```text
/Users/saberrao/vault/kol/_cross/debates/
```

它会创建参与者上下文、Round 1/2 prompt 和 synthesizer prompt，但不会执行模型，也不会生成最终结论。

`kol_debate.py --mode run` 复用相同 workspace 结构，然后通过 `--runner-command` 执行每个 prompt。runner 必须从 stdin 读取 prompt，并向 stdout 输出回答。输出会保存到 `turns/`、`verdict.raw.md`、`verdict.json` 和 `verdict.md`。manifest 只保存脱敏后的 runner 元数据，不保存完整命令字符串。

## 隐私

原始推文和订阅者专属内容保持私有。不要把生成的数字分身输出发布成 KOL 本人言论。
