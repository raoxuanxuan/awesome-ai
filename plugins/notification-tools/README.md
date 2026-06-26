# Notification Tools

Notification Tools provides a local notification boundary for agent workflows.
Producer skills append structured events into a local JSONL queue; dispatcher
scripts route those events to Feishu bots with signing, quiet-hour rules,
target-scoped delivery sidecars, and a process lock to avoid duplicate sends.

## Capabilities

- Append structured notification events.
- Route Feishu notifications by topic.
- Send one topic to multiple bots, or one bot to multiple topics.
- Hide Feishu card source, level, or footer through `meta.display`.
- Respect quiet hours for non-critical alerts.
- Keep target-scoped delivered markers for dedupe.
- Watch local files and convert changes into notification events.

## Non-Goals

- It does not fetch Twitter/X content.
- It does not write Obsidian notes.
- It does not own producer scheduling.
- It does not store real Feishu webhook URLs or secrets in the plugin.

## Directory Structure

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

## Runtime Paths

Runtime queue and delivery state:

```text
~/vault/.notification-center/
```

Preferred Feishu config path:

```text
~/.notification-center/feishu.json
```

Environment overrides:

```bash
export NOTIFICATION_CENTER_RUNTIME=/path/to/runtime
export NOTIFICATION_CENTER_FEISHU_CONFIG=/path/to/feishu.json
```

`dispatch.py` also checks the legacy local-skill path
`~/.codex/skills/notification-center/feishu.json` for compatibility.

## Feishu Setup

Copy `skills/notification-center/feishu.example.json` to a local config path,
replace placeholders, and lock down permissions:

```bash
mkdir -p ~/.notification-center
cp skills/notification-center/feishu.example.json ~/.notification-center/feishu.json
chmod 600 ~/.notification-center/feishu.json
```

Do not commit real webhook URLs or Feishu secrets.

## Commands

Append an event:

```bash
python3 skills/notification-center/append.py \
  --source twitter-monitor \
  --level alert \
  --title "Damnang2" \
  --summary "Useful content" \
  --dedupe-key "tweet:123" \
  --link "tweet=https://x.com/user/status/123" \
  --meta '{"topic":"invest"}'
```

Preview pending Feishu sends:

```bash
python3 skills/notification-center/dispatch.py --dry-run
```

Dispatch pending sends:

```bash
python3 skills/notification-center/dispatch.py
```

Run watcher checks:

```bash
python3 skills/notification-center/watcher.py --dry-run
```

## Launchd

The bundled launchd plists are templates. Install them only after confirming
their script paths match the installed plugin or local checkout path.

```bash
cp skills/notification-center/launchd/com.saber.notification-center.*.plist \
  ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.saber.notification-center.dispatch.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.saber.notification-center.watch.plist
```

## Security

- Keep real Feishu config outside git.
- Keep config permissions at `0600`.
- Do not paste Feishu webhook URLs or signing secrets into chat.
- Runtime queues, logs, sidecars, and watermarks are local mutable state and
  should not be committed.

## Install

From the repository root:

```bash
codex plugin marketplace add .
codex plugin add notification-tools@awesome-ai
```

For Claude Code:

```bash
claude plugin marketplace add ./
claude plugin install notification-tools@awesome-ai
```
