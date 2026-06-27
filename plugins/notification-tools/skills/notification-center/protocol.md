# Notification Center Protocol

## Purpose

Notification Center is a local outbox for user-facing events. Producers write structured JSONL events. Dispatchers deliver those events to user channels such as Feishu.

This boundary keeps discovery workflows separate from archival workflows. For example, Twitter Monitor should notify first; Obsidian save remains a later explicit user decision.

## Runtime

Authoritative runtime:

```text
~/vault/.notification-center/
```

Runtime files:

| File | Purpose |
| --- | --- |
| `YYYY-MM-DD.jsonl` | Append-only daily event queue |
| `.delivered/<id>` | Legacy/default delivered event sidecar |
| `.delivered/<id>__feishu-<bot>` | Routed Feishu bot delivered sidecar |
| `.digest/YYYY-MM-DD` | Daily digest delivered marker |
| `.watermarks.json` | Watcher producer watermarks |
| `.dispatch.log` | Dispatcher log |
| `.watcher.log` | Watcher log |

## Event

```json
{
  "schema_version": 1,
  "id": "16-char sha1",
  "dedupe_key": "tweet:180123",
  "ts": "2026-06-24T10:00:00+08:00",
  "source": "twitter-monitor",
  "level": "critical",
  "title": "Cookie expired",
  "summary": "Twitter fetch cannot read history.",
  "links": [{"label": "tweet", "url": "https://x.com/..."}],
  "paths": ["/absolute/local/path.json"],
  "meta": {"tweet_id": "180123", "topic": "AI", "author_tags": ["CPO", "小盘chokepoint"]},
  "targets": ["feishu"]
}
```

Required producer fields:

| Field | Rule |
| --- | --- |
| `source` | Stable producer name, for example `twitter-monitor` |
| `level` | `critical`, `alert`, or `info` |
| `title` | Single-line human title |
| `dedupe_key` | Stable semantic key; required by convention |

`id` is generated as `sha1(source|dedupe_key|YYYY-MM-DD)[:16]` unless explicitly provided.

## Levels

| Level | Use For | Dispatch |
| --- | --- | --- |
| `critical` | User action required, broken auth, failed important job | Immediate, including quiet hours |
| `alert` | Significant content or non-urgent warning | Immediate except 23:00-08:00 |
| `info` | Routine success, heartbeat, stats | Digest only |

## Links And Paths

Use `links` for user-clickable external URLs:

```json
"links": [{"label": "tweet", "url": "https://x.com/..."}]
```

Use `paths` for local artifacts:

```json
"paths": ["/Users/saberrao/vault/invest/raw/articles/example.md"]
```

Do not overload `paths` with URLs in new producers.

## Producer Contract

- Appending is best-effort and should not break the primary workflow.
- Producer state remains producer-owned. Notification Center does not own monitor `saved/skipped/failed` states.
- Use `meta` for machine-readable fields needed by later manual actions.
- Use `meta.author_tags` when the producer wants Feishu card titles to show concise author profile tags. Dispatcher renders at most three tags as `title  tag1 · tag2 · tag3`.
- Use `targets` when a notification should go to a subset of dispatchers. The default is `["feishu"]`.
- Set `meta.topic` when the event should be routed to a topic-specific Feishu bot.

## Dispatcher Contract

- Dispatcher reads only today's queue.
- Delivered default events are marked by touching `.delivered/<id>`.
- Routed Feishu events are marked per selected bot, for example `.delivered/<id>__feishu-tech`.
- Feishu sends are signed with the selected bot secret from `feishu.json`.
- One Feishu bot can serve multiple topics through `bots.<name>.topics`.
- One topic can route to multiple Feishu bots through repeated `bots.<name>.topics` membership or an explicit `topics` array mapping.
- Dispatcher does not scan vault files; `watcher.py` is a separate producer.

## Watcher Contract

Watchers turn local file changes into notification events. They are configured in `watch.json` and maintain `.watermarks.json`.

Supported modes:

| Mode | Behavior |
| --- | --- |
| `per-file` | One event per new file since source watermark |
| `per-kol-window` | Group new `vault/kol/<handle>/...` files by KOL |
| `per-author-window` | Group new article files by frontmatter or filename author |
