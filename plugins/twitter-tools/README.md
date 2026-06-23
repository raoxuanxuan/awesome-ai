# Twitter Tools

Twitter Tools 是一个同时面向 Codex 和 Claude Code 的 agent plugin。目前只包含一个 skill：

- `twitter-fetch`：只负责读取和规范化 X/Twitter 数据，输出 JSON 或 JSONL。

它适合给上层工作流当底层数据源，例如保存到 Obsidian、监控 KOL、翻译推文、生成摘要等。但这些上层动作不在 `twitter-fetch` 里做。

## 能做什么

`twitter-fetch` 当前支持：

| 场景 | 能力 |
| --- | --- |
| 单条推文 | 读取一条公开 tweet / X Article，quote tweet 会随 provider 返回一起带上 |
| 单条 + thread | 读取一条推文，并尝试展开同作者 thread 上下文 |
| thread | 以 thread 结果包的形式返回一组同主题推文 |
| timeline | 读取某个用户最近公开 timeline |
| history | 用登录态读取某个用户更深的 tweets/replies 历史 |

它不会做：

- 不写 Obsidian / vault / GitHub Pages / markdown 文件。
- 不更新 `.state.json`、`.backfill_state.json` 或任何监控状态。
- 不做分类、摘要、翻译、下载图片、推送通知。
- 不保存非 Twitter 平台数据。

## 目录结构

这个 plugin 放在仓库里时大致是这样：

```text
plugins/twitter-tools/
├── .codex-plugin/plugin.json
├── .claude-plugin/plugin.json
├── README.md
└── skills/
    └── twitter-fetch/
        ├── SKILL.md
        ├── bin/twitter-fetch
        ├── scripts/
        └── references/
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

## Python 和 uv

这个 skill 使用 `uv` 管理 Python 依赖。

正常情况下你直接运行：

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

注意：`history` 只读取数据，不读写 `.backfill_state.json`。

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
- 这个 skill 是只读数据层。写 vault、写 raw markdown、更新 backfill state 应该放在上层 skill 或脚本里。

## 维护者参考

- agent 入口：`skills/twitter-fetch/SKILL.md`
- 命令手册：`skills/twitter-fetch/references/usage.md`
- 输出 schema：`skills/twitter-fetch/references/schema.md`
- bootstrap：`skills/twitter-fetch/scripts/bootstrap.sh`
- cookie 保存：`skills/twitter-fetch/scripts/save_cookies.py`
