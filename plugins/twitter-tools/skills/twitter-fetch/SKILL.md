---
name: twitter-fetch
description: Use when Codex needs to fetch, inspect, normalize, or troubleshoot X/Twitter content including single tweets, X Articles, timelines, threads, replies, or KOL tweet history before another skill saves, translates, monitors, or ingests that content.
---

# Twitter Fetch

`twitter-fetch` is a read-only Twitter/X data adapter. It fetches and normalizes single tweets, X Articles, timelines, threads, replies, keyword search results, and user history into JSON/JSONL for upper-layer skills.

It only retrieves and normalizes data. It must not write Obsidian files, GitHub Pages files, KOL vault files, monitor state, summaries, translations, downloaded media, or Feishu inbox entries.

## Runtime

Default runtime directory for new users:

```text
~/.twitter-fetch/
```

Default cookies path:

```text
~/.twitter-fetch/.cookies.json
```

Runtime layout:

```text
~/.twitter-fetch/
├── .cookies.json
├── cache/
├── logs/
└── tmp/
```

Override for any environment:

```bash
export TWITTER_FETCH_COOKIES=/path/to/.cookies.json
```

`twitter-fetch` does not use `~/.twitter-monitor` or monitor runtime paths. Upper-layer skills can read `~/.twitter-fetch/.cookies.json`, but their state belongs in their own runtime or output directories.

## Environment

Use the skill runner for normal operation:

```bash
bin/twitter-fetch single --url "https://x.com/user/status/123" --pretty
bin/twitter-fetch search --query "NVDA priced in" --limit 50 --mode live --pretty
bin/twitter-fetch history --user TJ_Research --max-pages 1 --pretty
```

The runner uses:

```bash
uv run --project <skill-dir> python <skill-dir>/scripts/twitter_fetch.py ...
```

If `uv` is missing, the runner prints installation guidance and exits. It must not install `uv` implicitly.

The runner automatically creates `~/.twitter-fetch/cache`, `logs`, `tmp`, and `.cookies.example.json` when they are missing. It cannot create a real authenticated cookies file; commands that require login cookies return a structured `missing_cookies` or `invalid_cookies` error telling the caller where to put `.cookies.json` or how to use `TWITTER_FETCH_COOKIES`.

The runner stores the uv virtual environment outside the plugin source/cache by default:

```text
~/.twitter-fetch/venv/
```

Override with `TWITTER_FETCH_VENV=/path/to/venv` when needed.

## Cookie Setup

Use this flow only when a command returns `missing_cookies` or `invalid_cookies`, or when the user explicitly asks to set up Twitter cookies.

Principles:

- Ask for user consent before reading or saving browser login cookies.
- Never print `auth_token`, `ct0`, or a full Cookie header in chat, logs, or final answers.
- Save only `auth_token` and `ct0` to `~/.twitter-fetch/.cookies.json` with mode `0600`.
- Use `scripts/save_cookies.py` for the final write so permissions and JSON shape stay consistent.

Preferred setup order:

1. BrowserOS MCP, if available.
   - Open `https://x.com/home` in BrowserOS and ask the user to log in if needed.
   - After login, prefer BrowserOS raw CDP `Storage.getCookies`; fall back to `Network.getCookies` with `https://x.com/`, `https://x.com/home`, and `https://twitter.com/` URLs if needed.
   - Write `auth_token` and `ct0` directly to `~/.twitter-fetch/.cookies.json` from the BrowserOS runtime or through `scripts/save_cookies.py --stdin-json`; do not return cookie values to chat.
   - Page JavaScript cannot read HttpOnly cookies such as `auth_token`; do not keep retrying `document.cookie` if it does not contain both `auth_token` and `ct0`.
   - If both values are available, write them locally with `scripts/save_cookies.py` and do not show the values.
2. Chrome plugin, if BrowserOS cannot provide cookies.
   - Use the user's Chrome profile only after user consent.
   - Ask the user to log in to `https://x.com/home` in Chrome if needed.
   - Do not inspect Chrome cookies or session stores when the active Chrome control policy forbids it. In that case, use Chrome only to help the user reach the logged-in page, then fall back to hidden manual entry.
3. Manual fallback.
   - Tell the user to open browser developer tools, find Cookies for `https://x.com`, copy only `auth_token` and `ct0`, and provide them through a hidden prompt:

```bash
python3 scripts/save_cookies.py --prompt
```

If an automation surface has obtained the two values as JSON, write them through stdin rather than command-line arguments:

```bash
python3 scripts/save_cookies.py --stdin-json
```

Expected stdin object:

```json
{"auth_token":"...","ct0":"..."}
```

Bootstrap checks:

```bash
scripts/bootstrap.sh --check
scripts/bootstrap.sh --init-runtime
scripts/bootstrap.sh --sync
scripts/bootstrap.sh --install-uv
```

`--install-uv` is the only mode allowed to install `uv`.
`--init-runtime` creates `~/.twitter-fetch/cache`, `logs`, `tmp`, and a `.cookies.example.json` template without overwriting `.cookies.json`.

## CLI

Run from anywhere:

```bash
bin/twitter-fetch single --url "https://x.com/user/status/123" --pretty
bin/twitter-fetch history --user TJ_Research --since-id 123456789 --jsonl
python3 scripts/twitter_fetch.py single --url "https://x.com/user/status/123" --pretty
python3 scripts/twitter_fetch.py single --url "https://x.com/user/status/123" --include-thread --pretty
python3 scripts/twitter_fetch.py single --url "https://x.com/user/status/123" --context full --pretty
python3 scripts/twitter_fetch.py timeline --user karpathy --limit 20 --pretty
python3 scripts/twitter_fetch.py thread --url "https://x.com/user/status/123" --pretty
python3 scripts/twitter_fetch.py replies --url "https://x.com/user/status/123" --pretty
python3 scripts/twitter_fetch.py search --query "NVDA priced in" --limit 50 --mode live --pretty
python3 scripts/twitter_fetch.py search --query "OpenAI o3" --lang en --exclude-replies --pretty
python3 scripts/twitter_fetch.py history --user TJ_Research --months 6 --pretty
python3 scripts/twitter_fetch.py history --user TJ_Research --since-id 123456789 --jsonl
```

Current provider status:

| Command | Provider | Status |
| --- | --- | --- |
| `single` | FxTwitter | active; quote included when provider returns it; thread context optional via `--include-thread` or `--context thread/full` |
| `timeline` | Twitter Syndication | active |
| `thread` | Twitter Syndication + normalized items | active for recent timeline window |
| `replies` | GraphQL -> BrowserOS -> Camofox/Nitter -> direct Nitter | active provider chain; GraphQL uses explicit cookies, BrowserOS uses local MCP, Nitter paths do not use cookies |
| `search` | GraphQL SearchTimeline | active; requires explicit cookies; BrowserOS/Nitter are fallback research paths, not the stable default |
| `history` | GraphQL UserTweetsAndReplies | active pure JSON/JSONL fetch; no vault/state writes |

## Output Contract

All commands emit JSON:

```json
{
  "ok": true,
  "mode": "single",
  "source": "fxtwitter",
  "fetched_at": "2026-06-22T00:00:00Z",
  "input": {"url": "https://x.com/user/status/123"},
  "items": [],
  "error": null
}
```

For field details, read `references/schema.md`.

For command selection, runtime setup, cookie setup, and usage examples, read `references/usage.md`.

## Compatibility

Existing skills should keep their user-facing workflows but delegate fetch work here:

- `x-tweet-fetcher/scripts/fetch_tweet.py` is a compatibility wrapper for `single`, `timeline`, and `replies`.
- `twitter-monitor/scripts/fetch_timeline.py` is a compatibility wrapper for `timeline`.
- `twitter-monitor/scripts/fetch_user_history.py` is the upper-layer KOL raw markdown/state writer; it calls `twitter-fetch` history and owns `raw/tweets/*.md` plus `.backfill_state.json`.

## History Mode

Use `history` when the caller needs deeper user tweets/replies than `timeline` can provide.

Real `history` runs require dependencies that may not exist in system `python3`.
Prefer the runner:

```bash
bin/twitter-fetch history --user TJ_Research --max-pages 1 --pretty
```

Inputs:

- `--user`: X/Twitter screen name.
- `--months`: rolling cutoff window for backfill.
- `--cursor`: explicit GraphQL bottom cursor for caller-managed resume.
- `--since-id`: explicit watermark for caller-managed incremental fetch.
- `--page-size`, `--max-pages`, `--sleep`: pagination controls.
- `--jsonl`: emit one normalized tweet item per line instead of the envelope.

`history` may read cookies from the authoritative runtime path, but it must not read or update `.backfill_state.json`. Callers that need incremental behavior must pass `--since-id`; callers that need resume must pass `--cursor`.

## Context Expansion

Use default `single` when the caller wants exactly the linked post plus quote data.

Use `single --include-thread` or `single --context thread` when the caller wants the linked post with discovered same-thread items attached under `items[0].thread`.

Use `single --context full` as the future full-context switch. Today it expands thread context. Use standalone `replies` when callers need a best-effort replies envelope.

`replies --provider auto` tries GraphQL first, then BrowserOS, then Camofox/Nitter, then direct Nitter HTTP. Use an explicit provider when debugging:

```bash
bin/twitter-fetch replies --url "https://x.com/user/status/123" --provider graphql --cookie-file ~/.twitter-fetch/.cookies.json --pretty
bin/twitter-fetch replies --url "https://x.com/user/status/123" --provider browseros --pretty
bin/twitter-fetch replies --url "https://x.com/user/status/123" --provider camofox_nitter --pretty
bin/twitter-fetch replies --url "https://x.com/user/status/123" --provider direct_nitter --pretty
```

Keep the standalone `thread` command for callers that want only the thread result envelope instead of a single tweet envelope.

## Boundaries

- Do not put non-Twitter platforms here. `x-tweet-fetcher/scripts/fetch_china.py` stays in `x-tweet-fetcher`.
- Do not update `.state.json` or `.backfill_state.json` from this skill.
- Do not classify, translate, summarize, download images, or write markdown from this skill.
- Return structured provider errors instead of raising raw network exceptions to callers.
