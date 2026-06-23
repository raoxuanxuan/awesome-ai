---
name: twitter-monitor
description: Use when Codex needs to monitor configured X/Twitter users for new tweets, articles, or quoted posts, filter low-value items, orchestrate twitter-fetch and twitter-media-fetch, and hand normalized content to content-to-obsidian. Does not write GitHub Pages or perform KOL history backfill.
---

# Twitter Monitor

`twitter-monitor` is the stateful upper-layer monitor for X/Twitter. It detects new content from configured users, filters low-value posts, calls `twitter-fetch` and `twitter-media-fetch`, maps results to Content JSON, and delegates Obsidian writes to `content-to-obsidian`.

It does not implement X/Twitter providers, download media internals, render Markdown, write GitHub Pages, or backfill KOL raw archives.

## Architecture

```text
twitter-monitor
  -> twitter-fetch timeline
  -> twitter-fetch single --include-thread
  -> twitter-media-fetch download
  -> content-to-obsidian
```

Layer ownership:

| Layer | Owns | Does Not Own |
| --- | --- | --- |
| `twitter-fetch` | X/Twitter single, timeline, thread, replies, history JSON/JSONL | Markdown, media download, state, vault writes |
| `twitter-media-fetch` | Download media from `twitter-fetch` JSON into caller-provided asset dir | Tweet fetching, Markdown, state |
| `content-to-obsidian` | Vault config check, vault selection, Markdown rendering, Obsidian writes | Twitter fetching, monitor state |
| `twitter-monitor` | Config, scheduling workflow, new-item detection, filtering, orchestration, monitor state | Provider parsing, media internals, Markdown templates, GitHub Pages |

## Runtime

Default runtime:

```text
~/.twitter-monitor/
```

Runtime layout:

```text
~/.twitter-monitor/
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

If `~/.twitter-monitor/config.yaml` is missing, create it from `config.yaml.example` in this skill. Do not write mutable runtime state into the plugin directory.

## Config

Recommended config:

```yaml
users:
  - username: "karpathy"
    display_name: "Andrej Karpathy"
    sinks: ["obsidian"]

topics:
  - name: "ClaudeCode"
    users: ["trq212", "bcherny", "amorriscode", "OmidMogasemi", "claudeai"]

settings:
  max_tweets_per_user: 20
  include_replies: false
  include_retweets: false
  expand_thread: true
  download_media: true
  mark_skipped_as_seen: true

sinks:
  obsidian:
    enabled: true
    prompt_prefix: "保存到 AI"
```

## Workflow

1. Load config and state.
   - Config: `~/.twitter-monitor/config.yaml`.
   - State: `~/.twitter-monitor/.state.json`.
   - If state is missing, initialize an empty state.
   - If state is corrupt, stop and ask before overwriting.
2. Fetch each user's recent timeline.
   - Use `twitter-fetch timeline --user <username> --limit <N> --pretty`.
   - Compatibility wrapper:

```bash
python3 scripts/fetch_timeline.py --user karpathy --limit 20 --json --pretty
```

3. Compare timeline IDs with state.
   - Skip IDs already marked `saved` or `skipped`.
   - Preserve failed IDs for retry unless the failure is explicitly non-retryable.
4. Apply low-value filters.
   - Skip pure retweets when `include_retweets: false`.
   - Skip short non-quote posts with no URL when unlikely to carry durable value.
   - Do not skip short posts containing `http` or `t.co`; they may be X Articles or link posts.
   - If `mark_skipped_as_seen: true`, write skipped status to state with reason.
5. Fetch complete content for each candidate.
   - Use `twitter-fetch single --url <url> --include-thread --pretty`.
   - If this fails, mark retryable failure and do not write outputs.
6. Download media when enabled.
   - Use `twitter-media-fetch download --input <twitter-json> --output-dir <asset-dir> --prefix <slug> --pretty`.
   - A partial media failure should not discard text content; report failed media.
7. Map to Content JSON.
   - Follow `content-to-obsidian/references/content-json.md`.
   - Preserve URL, author, created time, text, article body, thread sections, quote tweet references, stats, and media metadata.
8. Save to Obsidian.
   - Invoke `content-to-obsidian` with Content JSON, media manifest, and a prompt such as `保存到 AI: <url>`.
   - Let `content-to-obsidian` choose the vault and enforce `~/.obsidian-tools/vaults.json`.
   - Do not render Markdown directly in monitor.
9. Update state only after outputs finish.
   - `saved`: content was written to Obsidian.
   - `skipped`: low-value content intentionally ignored.
   - `failed`: retryable failure, with error message.
10. Print a concise run report.

## State Model

Prefer state version 2:

```json
{
  "version": 2,
  "last_run": "2026-06-23T08:00:00Z",
  "users": {
    "karpathy": {
      "last_checked": "2026-06-23T08:00:00Z",
      "items": {
        "123": {
          "status": "saved",
          "source_url": "https://x.com/karpathy/status/123",
          "saved_at": "2026-06-23T08:01:00Z",
          "outputs": {
            "obsidian": "/Users/.../raw/articles/example.md"
          },
          "error": null
        }
      }
    }
  }
}
```

Legacy state with `processed_ids` may be read during migration, but new writes should use per-item status.

## Explicit Non-Goals

- Do not write GitHub Pages.
- Do not depend on disabled `tweet-to-obsidian` or `x-tweet-fetcher`.
- Do not import local `~/.codex/skills/twitter-fetch`; resolve and run the installed `twitter-fetch` runner.
- Do not backfill KOL raw archives here. KOL history belongs in a future `kol-ingest` or `kol-twin` workflow.

## Runner Resolution

Monitor scripts resolve `twitter-fetch` in this order:

1. `TWITTER_FETCH_BIN=/absolute/path/to/bin/twitter-fetch`.
2. `twitter-fetch` on `PATH`.
3. Installed plugin cache under `~/.codex/plugins/cache`, `~/.claude/plugins/cache`, or `~/.agents/plugins/cache`.
4. Source checkout fallback: `~/ai-workspace/awesome-ai/plugins/twitter-tools/skills/twitter-fetch/bin/twitter-fetch`.

If none is found, fail with an error asking the user to install `twitter-tools` or set `TWITTER_FETCH_BIN`.

## Error Handling

| Scenario | Behavior |
| --- | --- |
| User timeline fetch fails | Record user-level error and continue other users |
| Single tweet fetch fails | Mark item `failed`; retry later |
| Media download partially fails | Save text content and report failed media |
| Obsidian config missing | Stop before writing; let `content-to-obsidian` create/check config |
| Obsidian write fails | Mark item `failed`; retry later |
| State corrupt | Stop and ask before replacing |
