# Awesome AI 插件

这个目录存放本地 agent 插件。所有插件遵循几条共同规则：

- 插件代码进入 git。
- 运行时状态、凭据、缓存、日志、cookies、webhook 和 secret 不进入 git。
- 每个插件只负责一个清晰层次；跨插件协作通过结构化文件或事件传递，不共享可变业务状态。
- Codex 插件声明文件放在 `.codex-plugin/plugin.json`。
- Claude Code 插件声明文件放在 `.claude-plugin/plugin.json`。

## 插件列表

| 插件 | 职责 | 运行时状态 |
| --- | --- | --- |
| `twitter-tools` | 获取、规范化、缓存、下载媒体并监控 X/Twitter 内容。 | `/Users/saberrao/ai-workspace/.twitter-monitor/`、`/Users/saberrao/ai-workspace/.tweet-pool/`、`~/.twitter-fetch/` |
| `notification-tools` | 写入本地通知事件队列，按 topic 路由，并发送飞书卡片。 | `~/vault/.notification-center/`、`~/.notification-center/feishu.json` |
| `obsidian-tools` | 将已经规范化的外部内容写入配置好的 Obsidian vault。 | 本地 vault 配置和目标 vault |
| `kol-tools` | 刷新、清洗、索引、蒸馏、问答和辩论私有 KOL 档案。 | `/Users/saberrao/vault/kol/` |

## 边界

- `twitter-tools` 负责抓取和监控外部社交内容，但不直接发送飞书消息。
- `notification-tools` 负责发送通知，但不抓取 Twitter/X 内容，也不写入 Obsidian 笔记。
- `obsidian-tools` 只在源 fetcher 已经提供规范化内容之后写入知识库。
- `kol-tools` 消费私有 KOL 档案，可以调用源 fetcher，但 KOL vault 数据保留在插件外部。

## Marketplace 文件

Codex：

```text
.agents/plugins/marketplace.json
```

Claude Code：

```text
.claude-plugin/marketplace.json
```

在仓库根目录安装 Codex 插件：

```bash
codex plugin marketplace add .
codex plugin add <plugin-name>@awesome-ai
```

安装 Claude Code 插件：

```bash
claude plugin marketplace add ./
claude plugin install <plugin-name>@awesome-ai
```

## 本地运行版本同步

本机使用的 Codex 插件以 `origin/main` 为唯一源码基线。插件修改的标准流程是：

1. 在本仓库修改插件源码。
2. 运行对应的验证命令。
3. 提交并推送到 `origin/main`。
4. 从 `origin/main` 刷新本地 Codex plugin cache。

在仓库根目录执行：

```bash
./plugins/sync-local-plugins.sh
```

这个脚本会：

- 拒绝在 dirty worktree 下运行。
- 快进本地 `main` 到 `origin/main`。
- 重新安装 `.agents/plugins/marketplace.json` 中列出的所有插件。
- 校验每个已安装 cache 目录都和 git source 完全一致。
- 将历史本地路径 `~/.codex/skills/notification-center` 改成指向已安装 `notification-tools` 插件 skill 的 symlink。

这样自然语言触发 skill、launchd 自动任务和手动命令都会使用 plugin cache 里的代码。

本地 launchd job 应调用下面目录里的脚本：

```text
~/.codex/plugins/cache/awesome-ai/<plugin>/<version>/
```

运行时配置、凭据、日志、队列、cookies 和缓存仍然保留在 git 与插件源码目录之外。
