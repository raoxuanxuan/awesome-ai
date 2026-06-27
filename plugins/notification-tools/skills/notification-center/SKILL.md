---
name: notification-center
description: Use when local automations, cron jobs, skills, or monitors need to queue user-facing notifications, route alerts to Feishu, inspect notification runtime state, or add file-change watchers.
---

# Notification Center

Notification Center is the local notification boundary for agent workflows. Producers append structured events to a local JSONL queue; dispatchers deliver pending events to Feishu with signing, quiet-hour rules, and delivered sidecars.

It is not an Obsidian writer, business queue, or content archive.

## Authoritative Paths

| Path | Purpose |
| --- | --- |
| Installed plugin skill path | Skill code, scripts, examples, and launchd templates |
| `~/vault/.notification-center/` | Runtime queue, logs, watermarks, sidecars |
| `~/vault/.notification-center/YYYY-MM-DD.jsonl` | Daily append-only event queue |
| `~/vault/.notification-center/.delivered/<id>` | Delivered sidecar for per-event dedupe |
| `~/vault/.notification-center/.dispatch.lock` | Dispatcher process lock to prevent overlapping Feishu sends |
| `~/vault/.notification-center/.digest/YYYY-MM-DD` | Daily digest delivered marker |
| `~/vault/.notification-center/.watermarks.json` | Watcher watermarks |
| `~/.notification-center/feishu.json` | Preferred Feishu webhook routing config and secrets, mode 600 |
| `feishu.example.json` | Example Feishu config; copy it locally and replace placeholders |
| `~/Library/LaunchAgents/com.saber.notification-center.dispatch.plist` | Dispatcher launchd job |
| `~/Library/LaunchAgents/com.saber.notification-center.watch.plist` | Watcher launchd job |

Environment overrides:

```bash
export NOTIFICATION_CENTER_RUNTIME=/path/to/runtime
export NOTIFICATION_CENTER_FEISHU_CONFIG=/path/to/feishu.json
```

For compatibility, `dispatch.py` also checks the legacy local-skill config path
`~/.codex/skills/notification-center/feishu.json` when the preferred config is
not present. Do not commit real Feishu webhook URLs or secrets.

## Data Flow

```text
producer skill / cron / monitor
  -> append.py
  -> ~/vault/.notification-center/YYYY-MM-DD.jsonl
  -> dispatch.py
  -> Feishu custom bot
```

`watcher.py` is only another producer. It converts file changes into notification events and does not deliver messages.

## Event Schema

```json
{
  "schema_version": 1,
  "id": "16-char sha1",
  "dedupe_key": "tweet:180123",
  "ts": "2026-06-24T10:00:00+08:00",
  "source": "twitter-monitor",
  "level": "critical|alert|info",
  "title": "New tweet @karpathy",
  "summary": "Short human-readable body",
  "links": [{"label": "tweet", "url": "https://x.com/..."}],
  "paths": ["/absolute/local/artifact.json"],
  "meta": {"tweet_id": "180123", "topic": "AI", "display": {"hide_footer": true}},
  "targets": ["feishu"]
}
```

`id` defaults to `sha1(source|dedupe_key|YYYY-MM-DD)[:16]`. Producers should set a stable `dedupe_key`, such as `tweet:<id>`, `portfolio:<ticker>:<date>`, or `watch:<path>:<mtime>`.

## Feishu Routing

`feishu.json` supports the legacy single-bot format:

```json
{
  "webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/...",
  "secret": "SEC..."
}
```

It also supports multi-bot topic routing. One bot can receive multiple topics,
and one topic can be delivered to multiple bots:

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
    "ai-archive": {
      "webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/ai-archive",
      "secret": "SEC...",
      "topics": ["AI"]
    },
    "invest": {
      "webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/invest",
      "secret": "SEC...",
      "topics": ["invest"]
    }
  }
}
```

The same routing can also be expressed with an explicit `topics` map:

```json
{
  "default": "invest",
  "bots": {
    "ai": {"webhook": "...", "secret": "..."},
    "ai-archive": {"webhook": "...", "secret": "..."},
    "invest": {"webhook": "...", "secret": "..."}
  },
  "topics": {
    "AI": ["ai", "ai-archive"],
    "ClaudeCode": ["ai"],
    "invest": ["invest"]
  }
}
```

Routing rules:

- Producers keep `targets: ["feishu"]` and set `meta.topic` when known.
- Dispatcher routes `meta.topic` through `bots.*.topics`.
- If a topic is not configured, dispatcher uses `default`.
- If a topic maps to multiple bots, dispatcher sends the same event to every configured bot.
- Delivered sidecars are target-scoped for routed bots, so one event can be delivered independently to different Feishu bots.
- Dispatcher runs hold a runtime lock. If launchd and a manual dispatch overlap, the later run exits with `locked: true` instead of sending duplicate cards.
- Feishu card display can be controlled with `meta.display`; `hide_source_prefix`, `hide_level`, and `hide_footer` are supported.
- Feishu card titles can show source-provided author tags via `meta.author_tags`.
  - Example: title `Serenity` plus `meta.author_tags: ["CPO", "小盘chokepoint", "散户优先"]` renders as `Serenity  CPO · 小盘chokepoint · 散户优先`.
  - The dispatcher renders at most three tags and does not interpret their meaning.
- Do not commit `feishu.json`; it contains webhook URLs and secrets.

## Levels

| Level | Meaning | Dispatch Rule |
| --- | --- | --- |
| `critical` | Immediate action or system failure | Delivered even during quiet hours |
| `alert` | Significant content or warning | Delivered outside 23:00-08:00 |
| `info` | Routine completion or heartbeat | Digest only |

## Commands

Append one event:

```bash
python3 ~/.codex/skills/notification-center/append.py \
  --source twitter-monitor \
  --level alert \
  --title "New tweet @karpathy" \
  --summary "..." \
  --dedupe-key "tweet:180123" \
  --link "tweet=https://x.com/karpathy/status/180123" \
  --meta '{"tweet_id":"180123","topic":"AI"}'
```

Append JSON from stdin:

```bash
echo '{"source":"twitter-monitor","level":"alert","title":"New tweet","dedupe_key":"tweet:180123"}' |
  python3 ~/.codex/skills/notification-center/append.py --stdin
```

Dispatch pending events:

```bash
python3 <installed-skill-dir>/dispatch.py
python3 <installed-skill-dir>/dispatch.py --dry-run
python3 <installed-skill-dir>/dispatch.py --test
```

Run file watchers:

```bash
python3 <installed-skill-dir>/watcher.py
python3 <installed-skill-dir>/watcher.py --dry-run
python3 <installed-skill-dir>/watcher.py --baseline
```

Manually mark delivered:

```bash
python3 <installed-skill-dir>/mark_delivered.py --id <event-id>
```

Install launchd jobs:

```bash
cp <installed-skill-dir>/launchd/com.saber.notification-center.*.plist \
  ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.saber.notification-center.dispatch.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.saber.notification-center.watch.plist
```

Operational checks:

```bash
launchctl list | grep notification-center
python3 <installed-skill-dir>/dispatch.py --dry-run
python3 <installed-skill-dir>/watcher.py --dry-run
```

## Producer Rules

- Use a stable `dedupe_key`; do not rely on title text for real dedupe.
- Keep titles short and single-line.
- Put user-actionable URLs in `links`.
- Put local artifacts in `paths`.
- Treat notification append as best-effort for primary workflows; failed notification should not corrupt producer state.

## Security

- Keep `~/.notification-center/feishu.json` local and mode 600.
- Do not commit webhook URLs or Feishu secrets.
- Dispatcher signs every Feishu request with the selected bot secret.
