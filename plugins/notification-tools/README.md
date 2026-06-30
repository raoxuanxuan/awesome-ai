# Notification Tools

Notification Tools 为本地 agent workflow 提供通知边界。生产者 skill 将结构化事件写入本地 JSONL 队列；dispatcher 脚本负责按 topic 路由到飞书或企业微信机器人，并处理签名、安静时间、按目标去重的 delivered sidecar，以及进程锁，避免重复发送。

## 能做什么

- 写入结构化通知事件。
- 按 topic 路由飞书和企业微信通知。
- 支持一个 topic 推送到多个 bot，也支持一个 bot 接收多个 topic。
- 通过 `meta.display` 隐藏飞书卡片的来源、等级或底部信息。
- 通过 `meta.author_tags` 在飞书卡片标题里展示作者画像 tag，例如 `Serenity  CPO · 小盘chokepoint · 散户优先`。
- 非关键告警遵守安静时间。
- 使用按目标区分的 delivered marker 做去重。
- 监听本地文件变化，并转换成通知事件。

## 不做什么

- 不抓取 Twitter/X 内容。
- 不写入 Obsidian 笔记。
- 不负责生产者调度。
- 不在插件里保存真实飞书 webhook URL、飞书 secret 或企业微信 webhook URL。

## 目录结构

```text
notification-tools/
├── .codex-plugin/plugin.json
├── .claude-plugin/plugin.json
├── README.md
└── skills/
    └── notification-center/
        ├── SKILL.md
        ├── append.py
        ├── dispatch.py
        ├── feishu.example.json
        ├── launchd/
        ├── mark_delivered.py
        ├── protocol.md
        ├── tests/
        ├── watch.json
        └── watcher.py
```

## 运行时路径

通知队列和投递状态：

```text
~/vault/.notification-center/
```

推荐的飞书配置路径：

```text
~/.notification-center/feishu.json
```

环境变量覆盖：

```bash
export NOTIFICATION_CENTER_RUNTIME=/path/to/runtime
export NOTIFICATION_CENTER_FEISHU_CONFIG=/path/to/feishu.json
```

为了兼容历史配置，`dispatch.py` 也会检查旧本地 skill 路径：

```text
~/.codex/skills/notification-center/feishu.json
```

## 机器人配置

将 `skills/notification-center/feishu.example.json` 复制到本机配置路径，替换占位符，并收紧权限：

```bash
mkdir -p ~/.notification-center
cp skills/notification-center/feishu.example.json ~/.notification-center/feishu.json
chmod 600 ~/.notification-center/feishu.json
```

不要提交真实 webhook URL 或飞书 secret。企业微信机器人可放在同一个本地配置文件的 `wecom.bots` 下，例如按 `Codex` topic 路由到企业微信群。

## 常用命令

写入一个事件：

```bash
python3 skills/notification-center/append.py \
  --source twitter-monitor \
  --level alert \
  --title "Damnang2" \
  --summary "Useful content" \
  --dedupe-key "tweet:123" \
  --link "tweet=https://x.com/user/status/123" \
  --meta '{"topic":"invest","author_tags":["CPO","小盘chokepoint","散户优先"]}'
```

预览待发送消息：

```bash
python3 skills/notification-center/dispatch.py --dry-run
```

发送待处理消息：

```bash
python3 skills/notification-center/dispatch.py
```

运行 watcher 检查：

```bash
python3 skills/notification-center/watcher.py --dry-run
```

## Launchd

插件内置的 launchd plist 是模板。安装前需要确认其中脚本路径和当前插件安装路径或本地 checkout 路径一致。

```bash
cp skills/notification-center/launchd/com.saber.notification-center.*.plist \
  ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.saber.notification-center.dispatch.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.saber.notification-center.watch.plist
```

## 安全

- 真实机器人配置保存在 git 之外。
- 配置文件权限保持为 `0600`。
- 不要把飞书 webhook URL、飞书签名 secret 或企业微信 webhook URL 粘贴到对话里。
- 运行时队列、日志、sidecar 和 watermark 都是本地可变状态，不应提交。

## 安装

在仓库根目录执行：

```bash
codex plugin marketplace add .
codex plugin add notification-tools@awesome-ai
```

Claude Code：

```bash
claude plugin marketplace add ./
claude plugin install notification-tools@awesome-ai
```
