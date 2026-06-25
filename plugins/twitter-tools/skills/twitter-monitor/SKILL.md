---
name: twitter-monitor
description: Use when Codex needs to monitor configured X/Twitter users for new tweets, articles, or quoted posts, filter low-value items, orchestrate twitter-fetch and tweet-pool, and queue minimal review notifications through notification-center. Does not write GitHub Pages or perform KOL history backfill.
---

# Twitter Monitor

`twitter-monitor` is the stateful upper-layer monitor for X/Twitter. It detects new content from configured users, filters low-value posts, calls `twitter-fetch`, caches normalized results in `tweet-pool`, and queues minimal review notifications through `notification-center`.

It does not implement X/Twitter providers, download media internals, render Markdown, write GitHub Pages, or backfill KOL raw archives.

## Architecture

```text
twitter-monitor
  -> tweet-pool window get
  -> twitter-fetch timeline on window cache miss
  -> tweet-pool window put
  -> twitter-fetch single --include-thread
  -> tweet-pool ingest
  -> notification-center append
```

Layer ownership:

| Layer | Owns | Does Not Own |
| --- | --- | --- |
| `twitter-fetch` | X/Twitter single, timeline, thread, replies, history JSON/JSONL | Markdown, media download, state, vault writes |
| `tweet-pool` | Local normalized fetch cache keyed by tweet ID, author cache, timeline observations, timeline window snapshots | Scheduling, quality decisions, Obsidian writes, KOL ingest decisions |
| `twitter-media-fetch` | Future optional media download from `twitter-fetch` JSON into caller-provided asset dir | Tweet fetching, Markdown, state |
| `content-to-obsidian` | Future/manual vault writing after the user decides a tweet is worth saving | Twitter fetching, monitor state |
| `notification-center` | Local event queue, Feishu dispatch, quiet-hour and dedupe handling | Tweet fetching, quality filtering, archive decisions |
| `twitter-monitor` | Config, scheduling workflow, new-item detection, filtering, orchestration, monitor state, notification event production | Provider parsing, media internals, Markdown templates, GitHub Pages |

## Runtime

Authoritative runtime:

```text
/Users/saberrao/ai-workspace/content-creation/.twitter-monitor/
```

Runtime layout:

```text
/Users/saberrao/ai-workspace/content-creation/.twitter-monitor/
├── config.yaml
├── .state.json
├── logs/
└── tmp/
```

Twitter auth belongs to `twitter-fetch`:

```text
~/.twitter-fetch/.cookies.json
```

Obsidian vault config belongs to `obsidian-tools`:

```text
~/.obsidian-tools/vaults.json
```

If `config.yaml` is missing, create it from `config.yaml.example` in this skill. Historical convenience paths should symlink back to the authoritative runtime. Do not write mutable runtime state into the plugin directory.

Tweet cache belongs to `tweet-pool`:

```text
/Users/saberrao/ai-workspace/content-creation/.tweet-pool/
```

Closed timeline window snapshots also belong to `tweet-pool`:

```text
/Users/saberrao/ai-workspace/content-creation/.tweet-pool/windows/
```

The timeline wrapper writes successful `twitter-fetch timeline` payloads to
`tweet-pool` and records per-user time-window snapshots. Finalized snapshots,
including empty windows, are reused before making another X/Twitter request.
The wrapper no longer emits the old `username/tweets/tweet_count` timeline shape.

## Config

Recommended config:

```yaml
users:
  - username: "karpathy"
  - username: "Money_or_Life_X"
  - username: "Franktradinglog"
  - username: "qinbafrank"
  - username: "labubu_trader"
  - username: "omarsar0"

topics:
  - name: "ClaudeCode"
    users: ["trq212", "bcherny", "amorriscode", "OmidMogasemi", "claudeai"]
  - name: "invest"
    users: ["Money_or_Life_X", "Franktradinglog", "qinbafrank", "labubu_trader"]
  - name: "AI"
    users: ["karpathy", "omarsar0"]

settings:
  interval_minutes: 60
  window_grace_minutes: 10
  max_scan_per_user: 50
  include_replies: false
  include_retweets: false
  expand_thread: true
  download_media: true
  mark_skipped_as_seen: true

sinks:
  notification:
    enabled: true
    direct_chars: 300
    summary_chars: 300
    summary_timeout_seconds: 20
    summary_command: "python3 /Users/saberrao/.codex/plugins/cache/awesome-ai/twitter-tools/0.3.0/skills/twitter-monitor/scripts/summarize_tweet.py"
  obsidian:
    enabled: false
    prompt_prefix: "保存到 AI"
```

## Workflow

1. Load config and state.
   - Config: `/Users/saberrao/ai-workspace/content-creation/.twitter-monitor/config.yaml`.
   - State: `/Users/saberrao/ai-workspace/content-creation/.twitter-monitor/.state.json`.
   - If state is missing, initialize an empty state.
   - If state is corrupt, stop and ask before overwriting.
2. Compute the closed monitor window.
   - `interval_minutes` is both the intended run cadence and the canonical window size.
   - `window_end` is the most recent interval boundary whose grace period has passed.
   - `window_start = window_end - interval_minutes`.
   - Example: with `interval_minutes: 60` and `window_grace_minutes: 10`, a 12:11 run checks `[11:00, 12:00)`.
3. Read or create each user's timeline window snapshot.
   - First read `tweet-pool window get --user <username> --window-start <start> --window-end <end> --include-items`.
   - If the snapshot is `finalized`, reuse its tweet IDs and do not request X/Twitter.
   - On miss, call `twitter-fetch timeline --user <username> --limit <max_scan_per_user> --pretty`, then write `tweet-pool window put`.
   - Empty finalized snapshots are valid and should be reused.
   - If the scan hits `max_scan_per_user` before proving coverage of `window_start`, mark the snapshot `incomplete`.
4. Compatibility wrapper:
   - Compatibility wrapper:

```bash
python3 scripts/fetch_timeline.py --user karpathy --limit 20 --json --pretty
```

`--json` is a deprecated no-op kept only so old command lines do not fail. Output is
always the standard envelope:

```json
{
  "ok": true,
  "mode": "timeline",
  "source": "syndication",
  "fetched_at": "2026-06-23T08:00:00Z",
  "input": {"user": "karpathy", "limit": 20},
  "items": [],
  "error": null
}
```

5. Compare window tweet IDs with state.
   - Skip IDs already marked `saved` or `skipped`.
   - Preserve failed IDs for retry unless the failure is explicitly non-retryable.
6. Apply low-value filters.
   - Skip pure retweets when `include_retweets: false`.
   - Skip short non-quote posts with no URL when unlikely to carry durable value.
   - Do not skip short posts containing `http` or `t.co`; they may be X Articles or link posts.
   - If `mark_skipped_as_seen: true`, write skipped status to state with reason.
7. Fetch complete content for each candidate.
   - Use `twitter-fetch single --url <url> --include-thread --pretty`.
   - If this fails, mark retryable failure and do not write outputs.
8. Append a notification event when enabled.
   - Use `notification-center/append.py --stdin`.
   - The Feishu-facing card content is intentionally minimal:
     - author name
     - tweet summary
     - tweet link
     - content type: `thread`, `quote`, `article`, or plain `tweet`
   - The notification event includes `meta.topic` when the monitored user belongs to a configured topic.
   - Keep `targets: ["feishu"]`; topic-to-webhook routing belongs to `notification-center`, where one Feishu bot can serve multiple topics.
   - Summary policy:
     - If cleaned content length is within `sinks.notification.direct_chars`, show the content directly.
     - If content is longer, call `sinks.notification.summary_command` with JSON on stdin and use the returned summary.
     - If no command is configured or the command fails, fall back to local truncation at `sinks.notification.summary_chars`.
     - The bundled `scripts/summarize_tweet.py` uses an OpenAI-compatible chat completions API. It reads `TWITTER_MONITOR_LLM_API_KEY`, `DEEPSEEK_API_KEY`, or `OPENAI_API_KEY` from the environment and never stores keys in config.
   - Notification append is best-effort; a local notification failure should be reported but should not corrupt tweet-pool ingest state.
9. Update state only after outputs finish.
   - `saved`: future/manual state for content written to Obsidian.
   - `fetched`: content was fetched and written to `tweet-pool`; notification append result is recorded in outputs.
   - `skipped`: low-value content intentionally ignored.
   - `failed`: retryable failure, with error message.
   - Update user-level `last_success_at` only after the user run completes.
10. Print a concise run report.

Current runner:

```bash
twitter-monitor run --pretty
```

The current runner implements config loading, state loading, closed hourly
window calculation, finalized window snapshot reuse, timeline scan on cache miss,
tweet-pool ingest, state dedupe, low-value filtering, `single --include-thread`
completion, notification-center append, and state updates. Completed candidates
are marked `fetched`; notification delivery status is recorded under item
`outputs.notification`.

## State Model

Prefer state version 3:

```json
{
  "version": 3,
  "last_run": "2026-06-24T10:00:00Z",
  "users": {
    "karpathy": {
      "last_checked": "2026-06-24T10:00:00Z",
      "last_success_at": "2026-06-24T10:00:00Z",
      "window_start": "2026-06-24T09:00:00Z",
      "window_end": "2026-06-24T10:00:00Z",
      "items": {
        "123": {
          "status": "fetched",
          "source_url": "https://x.com/karpathy/status/123",
          "created_at": "2026-06-24T09:30:00Z",
          "updated_at": "2026-06-24T10:01:00Z",
          "outputs": {
            "tweet_pool": true
          },
          "error": null
        }
      }
    }
  }
}
```

Legacy state with `processed_ids` may be read during migration, but new writes should use per-item status.

Status values:

| Status | Meaning |
| --- | --- |
| `fetched` | Full candidate content has been fetched and side-cached in `tweet-pool` |
| `saved` | Future sink state: content was persisted to Obsidian |
| `skipped` | Low-value content was intentionally ignored |
| `failed` | Retryable failure, usually from single tweet fetch or sink failure |

## Explicit Non-Goals

- Do not write GitHub Pages.
- Do not depend on disabled `tweet-to-obsidian` or `x-tweet-fetcher`.
- Do not import local `~/.codex/skills/twitter-fetch`; resolve and run the installed `twitter-fetch` runner.
- Do not backfill KOL raw archives here. KOL history belongs in a future `kol-ingest` or `kol-twin` workflow.
- Current runner does not write Obsidian; it marks completed candidates as `fetched`, not `saved`.

## Runner Resolution

Monitor scripts resolve `twitter-fetch` in this order:

1. `TWITTER_FETCH_BIN=/absolute/path/to/bin/twitter-fetch`.
2. `twitter-fetch` on `PATH`.
3. Installed plugin cache under `~/.codex/plugins/cache`, `~/.claude/plugins/cache`, or `~/.agents/plugins/cache`.
4. Source checkout fallback: `~/ai-workspace/awesome-ai/plugins/twitter-tools/skills/twitter-fetch/bin/twitter-fetch`.

If none is found, fail with an error asking the user to install `twitter-tools` or set `TWITTER_FETCH_BIN`.

The timeline wrapper resolves `tweet-pool` in this order:

1. `TWEET_POOL_BIN=/absolute/path/to/bin/tweet-pool`.
2. `tweet-pool` on `PATH`.
3. Installed plugin cache under `~/.codex/plugins/cache`, `~/.claude/plugins/cache`, or `~/.agents/plugins/cache`.
4. Source checkout fallback: `~/ai-workspace/awesome-ai/plugins/twitter-tools/skills/tweet-pool/bin/tweet-pool`.

If none is found, timeline output still works but prints a best-effort warning unless
`TWITTER_MONITOR_TWEET_POOL=0` is set.

## Error Handling

| Scenario | Behavior |
| --- | --- |
| User timeline fetch fails | Record user-level error and continue other users |
| Tweet-pool ingest fails | Print warning; keep monitor output and state flow unchanged |
| Single tweet fetch fails | Mark item `failed`; retry later |
| Notification append fails | Increment `notification_failed`, keep the tweet marked `fetched`, and record the local error under outputs |
| State corrupt | Stop and ask before replacing |
