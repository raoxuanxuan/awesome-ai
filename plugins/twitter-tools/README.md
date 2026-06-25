# Twitter Tools

Twitter Tools 是一个同时面向 Codex 和 Claude Code 的 agent plugin。目前包含四个 skill：

- `twitter-fetch`：只负责读取和规范化 X/Twitter 数据，输出 JSON 或 JSONL。
- `tweet-pool`：把 `twitter-fetch` 的 normalized item 按 tweet ID 缓存起来，让多个上层 workflow 复用抓取结果，但不共享业务状态。
- `twitter-media-fetch`：读取 `twitter-fetch` JSON 中引用的媒体 URL，下载到调用方指定目录，并输出 manifest JSON。
- `twitter-monitor`：状态化监控编排器，定时检查配置用户的新内容，过滤、补全、写入 `tweet-pool`，并把最小审阅通知交给 `notification-center`。

它适合给上层工作流当 Twitter/X 能力基座，例如保存到 Obsidian、监控用户、翻译推文、生成摘要、飞书审阅通知等。但抓取、缓存、媒体下载、监控、通知、写入仍然分层。

## 能做什么

`twitter-fetch` 当前支持：

| 场景 | 能力 |
| --- | --- |
| 单条推文 | 读取一条公开 tweet / X Article，quote tweet 会随 provider 返回一起带上 |
| 单条 + thread | 读取一条推文，并尝试展开同作者 thread 上下文 |
| thread | 以 thread 结果包的形式返回一组同主题推文 |
| timeline | 读取某个用户最近公开 timeline |
| history | 用登录态读取某个用户更深的 tweets/replies 历史 |

`twitter-media-fetch` 当前支持：

| 场景 | 能力 |
| --- | --- |
| 从 JSON 下载媒体 | 从 `twitter-fetch` envelope 中提取 tweet、article、thread、quote 里的媒体 URL |
| 从 URL 下载媒体 | 直接传入一个或多个媒体 URL 下载 |
| 输出 manifest | 输出本地路径、文件名、字节数、sha256、失败项 |

`tweet-pool` 当前支持：

| 场景 | 能力 |
| --- | --- |
| 统一缓存 | 将 `twitter-fetch` envelope / JSONL 写入 `.tweet-pool/tweets/<tweet_id>.json` |
| 稳定导出 | 按 tweet ID、作者、since_id 导出 canonical tweets，供 KOL、监控、归档等上层复用 |
| 作者缓存 | 从 tweet item 中沉淀 `authors/<username>.json`，可保存头像 URL |
| 观察记录 | 为 timeline/history 追加 `timelines/<username>.jsonl` 和 `fetch_state/<username>.json` |
| 窗口快照 | 为 user + closed time window 写入 `windows/<username>/...json`，空窗口也能复用 |
| 消费状态 | 为 `twitter-monitor`、`kol-twin` 等 consumer 独立维护 `consumers/<consumer>.json` |

`twitter-monitor` 当前支持：

| 场景 | 能力 |
| --- | --- |
| 用户监控 | 按 `/Users/saberrao/ai-workspace/content-creation/.twitter-monitor/config.yaml` 扫描配置用户的时间窗口内新内容 |
| Runner | `twitter-monitor run` 读取配置、去重、过滤、补全候选推文并更新 monitor state |
| 窗口快照复用 | 先读 `tweet-pool window get`，finalized/空窗口不再重复请求 X |
| 推文池缓存 | cache miss 时抓到的 timeline payload 会写入 `tweet-pool`，供其他 workflow 复用 |
| 标准输出 | `fetch_timeline.py` 直接输出 `twitter-fetch` 标准 envelope，不再输出旧版 `username/tweets/tweet_count` |
| 时间窗口 | 每轮检查上一个已关闭 interval，`window_grace_minutes` 控制整点后延迟确认 |
| 新内容过滤 | 根据 state 去重，过滤低价值短推和纯转推 |
| 内容补全 | 对候选内容调用 `twitter-fetch single --include-thread` |
| 通知中心 | 对候选内容构造最小 review event，并通过 `notification-center/append.py --stdin` 写入本地通知队列 |
| 飞书展示 | 通知卡片只展示作者、正文摘要、推文链接；长内容可调用 LLM 摘要，失败时本地截断兜底 |
| Obsidian 归档 | 当前不自动写入；runner 只标记 `fetched`，不会标记 `saved` |

它不会做：

- `twitter-fetch` / `twitter-media-fetch` 不写 Obsidian / vault / Markdown 文件。
- `twitter-fetch` / `twitter-media-fetch` 不更新 `.state.json`、`.backfill_state.json` 或任何监控状态。
- `tweet-pool` 不做统一业务队列，不做全局低质量过滤，不把一个 consumer 的 skip/save/ingest 状态共享给另一个 consumer。
- `twitter-monitor` 写入 `tweet-pool` 只是 best-effort fetch cache；pool 不可用时 monitor 仍继续输出。
- `twitter-monitor` 不再维护旧版 timeline JSON 输出；`--json` 参数只是 deprecated no-op。
- `twitter-monitor run` 当前完成 timeline 抓取、过滤、single 补全、tweet-pool 缓存和 notification-center append；不自动写 Obsidian。
- `twitter-monitor` 不写 GitHub Pages，不做 KOL raw history backfill。
- `twitter-monitor` 不直接请求飞书 webhook；飞书签名、安静时间、去重和实际发送属于 `notification-center`。
- `twitter-fetch` 不下载图片；需要下载媒体时使用 `twitter-media-fetch`。
- 不保存非 Twitter 平台数据。

## 目录结构

这个 plugin 放在仓库里时大致是这样：

```text
plugins/twitter-tools/
├── .codex-plugin/plugin.json
├── .claude-plugin/plugin.json
├── README.md
└── skills/
    ├── twitter-fetch/
    │   ├── SKILL.md
    │   ├── bin/twitter-fetch
    │   ├── scripts/
    │   └── references/
    ├── tweet-pool/
    │   ├── SKILL.md
    │   ├── bin/tweet-pool
    │   ├── scripts/
    │   └── references/
    ├── twitter-media-fetch/
        ├── SKILL.md
        ├── bin/twitter-media-fetch
        ├── scripts/
        └── references/
    └── twitter-monitor/
        ├── SKILL.md
        ├── bin/twitter-monitor
        ├── config.yaml.example
        └── scripts/
            └── summarize_tweet.py
```

其中：

- `README.md`：给人看的安装和使用说明，也就是这篇文档。
- `SKILL.md`：给 Codex / Claude Code 这类 agent 看的触发和执行说明。
- `references/usage.md`：给 agent 和维护者看的详细命令手册。
- `references/schema.md`：输出 JSON 字段说明。

## 安装

### Codex

如果你已经 clone 了这个仓库，在仓库根目录执行：

```bash
codex plugin marketplace add .
codex plugin add twitter-tools@awesome-ai
```

如果直接从 GitHub 安装：

```bash
codex plugin marketplace add raoxuanxuan/awesome-ai --sparse .agents/plugins --sparse plugins/twitter-tools
codex plugin add twitter-tools@awesome-ai
```

### Claude Code

如果你已经 clone 了这个仓库，在仓库根目录执行：

```bash
claude plugin marketplace add ./
claude plugin install twitter-tools@awesome-ai
```

如果直接从 GitHub 安装：

```bash
claude plugin marketplace add raoxuanxuan/awesome-ai --sparse .claude-plugin plugins/twitter-tools
claude plugin install twitter-tools@awesome-ai
```

## 首次使用会发生什么

第一次运行 `twitter-fetch` 时，runner 会自动准备本机 runtime：

```text
~/.twitter-fetch/
├── .cookies.example.json
├── cache/
├── logs/
├── tmp/
└── venv/
```

说明：

- `cache/`、`logs/`、`tmp/` 会自动创建。
- `.cookies.example.json` 会自动创建，只是模板，不是可用登录态。
- `venv/` 是 uv 使用的 Python 虚拟环境，默认放在 runtime 目录里，避免污染 plugin 源码目录。
- `.cookies.json` 不会自动创建，因为它包含真实 X/Twitter 登录凭据。

第一次使用 `twitter-monitor` 时，需要准备 monitor runtime：

```text
/Users/saberrao/ai-workspace/content-creation/.twitter-monitor/
├── config.yaml
├── .state.json
├── logs/
└── tmp/
```

如果 `config.yaml` 不存在，agent 应从已安装 skill 的 `config.yaml.example` 创建一份，再让用户确认监控账号和 sink 配置。历史 convenience path 应 symlink 回这个权威 runtime，当前机器上的 `~/.twitter-monitor` 就是 symlink。monitor 的 X/Twitter cookie 仍然使用 `~/.twitter-fetch/.cookies.json`。当前 runner 不自动写 Obsidian，因此运行 monitor 不需要 Obsidian vault 配置。

`twitter-monitor` 的通知 sink 默认写入 Notification Center，而不是直接调用飞书：

```text
/Users/saberrao/vault/.notification-center/
├── YYYY-MM-DD.jsonl
├── .delivered/
└── .digest/
```

飞书 webhook 和签名 secret 属于 Notification Center 本机配置，不属于这个 plugin，也不应提交到 git：

```text
/Users/saberrao/.codex/skills/notification-center/feishu.json
```

默认 cookie 路径：

```text
~/.twitter-fetch/.cookies.json
```

如果你需要换路径，可以设置：

```bash
export TWITTER_FETCH_RUNTIME=/path/to/runtime
export TWITTER_FETCH_COOKIES=/path/to/.cookies.json
export TWITTER_FETCH_VENV=/path/to/venv
```

第一次使用 `tweet-pool` 时，需要准备推文池 runtime：

```text
/Users/saberrao/ai-workspace/content-creation/.tweet-pool/
├── tweets/
├── authors/
├── media/
├── timelines/
├── windows/
├── fetch_state/
└── consumers/
```

初始化命令：

```bash
plugins/twitter-tools/skills/tweet-pool/bin/tweet-pool ensure --pretty
```

如果只是测试，可以设置：

```bash
export TWEET_POOL_RUNTIME=/tmp/.tweet-pool
```

## Python 和 uv

`twitter-fetch` 使用 `uv` 管理 Python 依赖。`twitter-media-fetch` 只依赖系统 `python3` 标准库，不需要额外安装 Python 包。

正常情况下你直接运行 `twitter-fetch`：

```bash
plugins/twitter-tools/skills/twitter-fetch/bin/twitter-fetch single --url "https://x.com/user/status/123" --pretty
```

如果本机没有 `uv`，命令会提示安装方式并退出，不会偷偷替你安装。你可以显式执行：

```bash
plugins/twitter-tools/skills/twitter-fetch/scripts/bootstrap.sh --install-uv
```

也可以只检查环境和初始化 runtime：

```bash
plugins/twitter-tools/skills/twitter-fetch/scripts/bootstrap.sh --check --init-runtime
```

如果想提前同步依赖：

```bash
plugins/twitter-tools/skills/twitter-fetch/scripts/bootstrap.sh --check --init-runtime --sync
```

## Cookie 怎么处理

不是所有命令都需要 Twitter cookie。

通常：

- `single`：多数公开推文不需要 cookie。
- `timeline`：读取公开 timeline，通常不需要 cookie。
- `thread`：依赖公开 timeline 窗口，通常不需要 cookie。
- `history`：需要登录态 cookie，因为它走 X/Twitter GraphQL。

cookie 文件只需要两个字段：

```json
{
  "auth_token": "...",
  "ct0": "..."
}
```

安全规则：

- 不要把 `auth_token`、`ct0` 或完整 Cookie header 发到聊天窗口。
- 不要把 `.cookies.json` 提交到 git。
- cookie 文件应只保存在本机 runtime，例如 `~/.twitter-fetch/.cookies.json`。
- 保存脚本会把文件权限设成 `0600`。

推荐获取流程：

1. 先让 agent 请求你的同意。
2. 如果有 BrowserOS MCP，优先让 agent 打开 `https://x.com/home`，你在浏览器登录后，由 BrowserOS 读取 cookie 并写入本机文件。
3. 如果没有 BrowserOS，但有 Chrome 控制能力，只用它帮助你打开和登录页面；如果当前 Chrome 策略不允许读取 cookie，就不要强行读取。
4. 最后 fallback 到手动隐藏输入：

```bash
cd plugins/twitter-tools/skills/twitter-fetch
python3 scripts/save_cookies.py --prompt
```

这个命令会用隐藏输入读取 `auth_token` 和 `ct0`，不会把值打印出来。

## 常用命令

下面命令都可以从仓库根目录执行。

### 读取单条推文

```bash
plugins/twitter-tools/skills/twitter-fetch/bin/twitter-fetch single \
  --url "https://x.com/user/status/123" \
  --pretty
```

### 读取单条推文，并尝试展开 thread

```bash
plugins/twitter-tools/skills/twitter-fetch/bin/twitter-fetch single \
  --url "https://x.com/user/status/123" \
  --include-thread \
  --pretty
```

### 只读取 thread 结果

```bash
plugins/twitter-tools/skills/twitter-fetch/bin/twitter-fetch thread \
  --url "https://x.com/user/status/123" \
  --pretty
```

`single --include-thread` 和 `thread` 的区别：

- `single --include-thread`：主结果仍然是一条 tweet，只是把 thread 上下文挂在这条 tweet 下面。
- `thread`：主结果就是 thread envelope，更适合只关心整组 thread 的上层程序。

### 读取用户最近 timeline

```bash
plugins/twitter-tools/skills/twitter-fetch/bin/twitter-fetch timeline \
  --user tig88411109 \
  --limit 10 \
  --pretty
```

### 读取更深历史 tweets/replies

```bash
plugins/twitter-tools/skills/twitter-fetch/bin/twitter-fetch history \
  --user tig88411109 \
  --max-pages 1 \
  --pretty
```

适合给上层 backfill 程序使用 JSONL：

```bash
plugins/twitter-tools/skills/twitter-fetch/bin/twitter-fetch history \
  --user tig88411109 \
  --max-pages 2 \
  --jsonl
```

增量或断点续跑由调用方管理：

```bash
plugins/twitter-tools/skills/twitter-fetch/bin/twitter-fetch history \
  --user tig88411109 \
  --since-id 123456789 \
  --jsonl

plugins/twitter-tools/skills/twitter-fetch/bin/twitter-fetch history \
  --user tig88411109 \
  --cursor "<cursor>" \
  --jsonl
```

### 下载推文媒体

先读取推文 JSON：

```bash
plugins/twitter-tools/skills/twitter-fetch/bin/twitter-fetch single \
  --url "https://x.com/user/status/123" \
  --include-thread \
  --pretty > tweet.json
```

再下载其中引用的媒体：

```bash
plugins/twitter-tools/skills/twitter-media-fetch/bin/twitter-media-fetch download \
  --input tweet.json \
  --output-dir /path/to/assets \
  --prefix my-slug \
  --pretty
```

输出 manifest 示例：

```json
{
  "ok": true,
  "downloaded": [
    {
      "source_url": "https://pbs.twimg.com/media/...",
      "filename": "my-slug-cover.jpg",
      "path": "/path/to/assets/my-slug-cover.jpg",
      "media_type": "image",
      "bytes": 12345,
      "sha256": "..."
    }
  ],
  "failed": [],
  "count": 1
}
```

注意：`history` 只读取数据，不读写 `.backfill_state.json`。

### 运行 Twitter Monitor

`twitter-monitor` 会检查上一个已关闭时间窗口。以 `interval_minutes: 60`、`window_grace_minutes: 10` 为例，12:11 运行会检查 `[11:00, 12:00)`：

```bash
plugins/twitter-tools/skills/twitter-monitor/bin/twitter-monitor run --pretty
```

运行逻辑：

```text
twitter-monitor
  -> tweet-pool window get
  -> twitter-fetch timeline on cache miss
  -> tweet-pool window put
  -> twitter-fetch single --include-thread
  -> tweet-pool ingest
  -> notification-center append
```

如果 `sinks.notification.enabled: true`，候选推文会写入 Notification Center 本地队列。Notification Center 的 dispatcher 再把通知发送到飞书：

```bash
python3 /Users/saberrao/.codex/skills/notification-center/dispatch.py --dry-run
python3 /Users/saberrao/.codex/skills/notification-center/dispatch.py
```

如果用户属于 `topics` 中的某个 topic，monitor 会把 topic 写入通知事件：

```json
{
  "meta": {
    "username": "karpathy",
    "topic": "AI"
  },
  "targets": ["feishu"]
}
```

topic 到 webhook 的路由由 Notification Center 的 `feishu.json` 控制。一个飞书 bot 可以接多个 topic，例如：

```json
{
  "default": {
    "webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/default",
    "secret": "SEC..."
  },
  "bots": {
    "tech": {
      "webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/tech",
      "secret": "SEC...",
      "topics": ["AI", "ClaudeCode"]
    },
    "invest": {
      "webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/invest",
      "secret": "SEC...",
      "topics": ["invest"]
    }
  }
}
```

飞书 webhook 和 secret 是本机私密配置，不属于 `twitter-tools` plugin，也不要提交到 git。

卡片展示保持最小：

```text
Andrej Karpathy
这里是推文正文或摘要……
https://x.com/karpathy/status/123
```

短内容直接展示；超过 `sinks.notification.direct_chars` 时，会调用 `sinks.notification.summary_command`。内置摘要脚本读取环境变量里的 API key，不把 key 写入 config：

```text
TWITTER_MONITOR_LLM_API_KEY
DEEPSEEK_API_KEY
OPENAI_API_KEY
```

## 输出格式

默认输出是 JSON envelope：

```json
{
  "ok": true,
  "mode": "single",
  "source": "fxtwitter",
  "fetched_at": "2026-06-22T00:00:00Z",
  "input": {
    "url": "https://x.com/user/status/123"
  },
  "items": [],
  "error": null
}
```

使用 `--jsonl` 时，每一行是一条规范化后的 tweet 对象，适合给上层批处理程序消费。

常见错误：

| 错误码 | 含义 |
| --- | --- |
| `missing_cookies` | 需要 cookie，但找不到 `.cookies.json` |
| `invalid_cookies` | cookie 文件格式不对，或缺少 `auth_token` / `ct0` |
| `bad_url` | URL 不是可解析的 X/Twitter status URL |
| `network_error` | 网络或 provider 请求失败 |
| `provider_error` | provider 返回了无法处理的结果 |
| `not_implemented` | 预留能力还没有完整实现 |

更详细字段见：

```text
skills/twitter-fetch/references/schema.md
```

## 给 agent 使用时怎么说

安装后，你可以直接对 Codex 或 Claude Code 说：

```text
读取这条推文：https://x.com/user/status/123
```

```text
读取 @tig88411109 最近 10 条推文
```

```text
读取 @tig88411109 更深的历史推文和回复，输出 JSONL
```

```text
帮我配置 twitter-fetch 的 cookie，优先用 BrowserOS
```

agent 应该自己选择 `single`、`timeline`、`thread` 或 `history`，而不是要求你记住所有底层命令。

## 注意事项

- X/Twitter 页面和接口可能变化，抓取失败时优先看返回的 `error.code` 和 `error.message`。
- `thread` 发现依赖最近公开 timeline 窗口，较老或隐藏的 thread 可能不完整。
- `history` 依赖登录态，cookie 过期后需要重新配置。
- 如果账号触发风控、2FA、CAPTCHA，需要你在浏览器里手动处理。
- `twitter-fetch` 是只读数据层；`twitter-media-fetch` 只写调用方指定的媒体目录。写 vault、写 raw markdown、更新 backfill state 应该放在上层 skill 或脚本里。
- `tweet-pool` 是 normalized fetch cache，不是统一业务队列；不要把一个 consumer 的处理状态当成另一个 consumer 的状态。
- `twitter-monitor` 不直接发飞书；它只写 Notification Center 队列。飞书 webhook、secret、安静时间、去重和 delivered sidecar 都属于 Notification Center。
- `twitter-monitor` 当前不会自动写 Obsidian；如果某条通知值得沉淀，应由人工或后续 workflow 再调用 Obsidian 写入能力。

## 维护者参考

- agent 入口：`skills/twitter-fetch/SKILL.md`
- 推文池入口：`skills/tweet-pool/SKILL.md`
- 媒体下载入口：`skills/twitter-media-fetch/SKILL.md`
- 监控入口：`skills/twitter-monitor/SKILL.md`
- 命令手册：`skills/twitter-fetch/references/usage.md`
- 输出 schema：`skills/twitter-fetch/references/schema.md`
- 媒体 manifest schema：`skills/twitter-media-fetch/references/schema.md`
- bootstrap：`skills/twitter-fetch/scripts/bootstrap.sh`
- cookie 保存：`skills/twitter-fetch/scripts/save_cookies.py`
