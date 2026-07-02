# Twitter Fetch Usage

Use this reference when a user asks how to use `twitter-fetch`, which command to choose, what output to expect, or how cookie setup works.

## Quick Choice

| User intent | Command |
| --- | --- |
| Fetch one public tweet or X Article | `bin/twitter-fetch single --url "<url>" --pretty` |
| Fetch one tweet and attach discovered same-thread context | `bin/twitter-fetch single --url "<url>" --include-thread --pretty` |
| Fetch only a thread envelope | `bin/twitter-fetch thread --url "<url>" --pretty` |
| Fetch visible replies best-effort | `bin/twitter-fetch replies --url "<url>" --provider auto --pretty` |
| Search X/Twitter by keyword or claim | `bin/twitter-fetch search --query "NVDA priced in" --limit 50 --mode live --pretty` |
| Fetch a user's recent public timeline | `bin/twitter-fetch timeline --user <handle> --limit 10 --pretty` |
| Fetch deeper user tweets/replies history | `bin/twitter-fetch history --user <handle> --max-pages 1 --jsonl` |
| Initialize runtime/check dependencies | `scripts/bootstrap.sh --check --init-runtime` |
| Save cookies through hidden prompt | `python3 scripts/save_cookies.py --prompt` |

## Command Details

Run commands from the `skills/twitter-fetch` directory when invoking the script directly.

### Single

Fetch exactly the linked tweet or X Article. Quote tweets are included when the provider returns them.

```bash
bin/twitter-fetch single --url "https://x.com/user/status/123" --pretty
```

Use thread context when the caller wants the linked tweet plus same-author thread items:

```bash
bin/twitter-fetch single --url "https://x.com/user/status/123" --include-thread --pretty
```

`--context full` currently expands thread context. Fetch replies separately with `replies`.

### Thread

Use this when the caller wants the thread as its own result envelope instead of a single tweet with `items[0].thread`.

```bash
bin/twitter-fetch thread --url "https://x.com/user/status/123" --pretty
```

Thread discovery depends on the recent public timeline window and may miss older or hidden thread items.

### Replies

Use this when the caller wants visible replies as a standard JSON envelope:

```bash
bin/twitter-fetch replies --url "https://x.com/user/status/123" --pretty
```

Default replies use a provider chain:

```text
graphql -> browseros -> camofox_nitter -> direct_nitter
```

GraphQL uses the explicit `--cookie-file` path, defaulting to `~/.twitter-fetch/.cookies.json`. It never reads browser cookies by itself. BrowserOS talks to the local BrowserOS MCP endpoint, defaulting to `http://127.0.0.1:9000/mcp`, and depends on what the X web UI renders. The Nitter providers do not use cookies; `camofox_nitter` needs local Camofox on `--port`, while `direct_nitter` is a low-confidence direct HTTP fallback.

Debug one provider at a time:

```bash
bin/twitter-fetch replies --url "https://x.com/user/status/123" --provider graphql --cookie-file ~/.twitter-fetch/.cookies.json --pretty
bin/twitter-fetch replies --url "https://x.com/user/status/123" --provider browseros --pretty
bin/twitter-fetch replies --url "https://x.com/user/status/123" --provider camofox_nitter --pretty
bin/twitter-fetch replies --url "https://x.com/user/status/123" --provider direct_nitter --pretty
```

### Search

Use this when a caller needs active expansion from a keyword, ticker, product
name, event phrase, or claim discovered elsewhere:

```bash
bin/twitter-fetch search --query "NVDA priced in" --limit 50 --mode live --pretty
```

`search` uses authenticated X GraphQL `SearchTimeline` and defaults to
`--mode live`, which maps to X Latest results. `--mode top` maps to X Top
ranking. It requires the explicit `--cookie-file` path, defaulting to
`~/.twitter-fetch/.cookies.json`; it never reads browser cookies by itself and
must not print `auth_token`, `ct0`, or full Cookie headers.

MVP filters append X search operators to the raw query:

```bash
bin/twitter-fetch search --query "OpenAI o3" --lang en --exclude-replies --pretty
bin/twitter-fetch search --query "TSLA robotaxi" --since-time 1782864000 --until-time 1782950400 --pretty
```

Search results use the same normalized tweet item schema as `timeline`,
`history`, and `replies`, so callers can pipe the envelope into `tweet-pool
ingest`. BrowserOS or Chrome live search can be used for manual debugging, but
the web UI snapshot/DOM path is a fallback research option rather than the
stable provider contract.

### Timeline

Use this for recent public posts from a user.

```bash
bin/twitter-fetch timeline --user tig88411109 --limit 10 --pretty
```

Timeline is not a deep backfill interface. Use `history` for deeper pagination and replies.

### History

Use this for deeper user tweets/replies history and caller-managed backfills.

```bash
bin/twitter-fetch history --user tig88411109 --max-pages 1 --pretty
bin/twitter-fetch history --user tig88411109 --max-pages 2 --jsonl
bin/twitter-fetch history --user tig88411109 --since-id 123456789 --jsonl
bin/twitter-fetch history --user tig88411109 --cursor "<cursor>" --jsonl
```

`history` reads cookies from `~/.twitter-fetch/.cookies.json` by default. It does not read or write `.backfill_state.json`; callers must pass `--since-id` and `--cursor` themselves when they need incremental behavior.

## Runtime

The runner automatically creates:

```text
~/.twitter-fetch/
├── .cookies.example.json
├── cache/
├── logs/
├── tmp/
└── venv/
```

Default cookies path:

```text
~/.twitter-fetch/.cookies.json
```

Override paths:

```bash
export TWITTER_FETCH_RUNTIME=/path/to/runtime
export TWITTER_FETCH_COOKIES=/path/to/.cookies.json
export TWITTER_FETCH_VENV=/path/to/venv
```

## Cookie Setup

Only commands that need authenticated X/Twitter GraphQL access require cookies. `history` requires cookies; `single` usually does not.

Preferred setup order:

1. Ask for user consent before reading or saving browser login cookies.
2. Use BrowserOS if available:
   - Open `https://x.com/home`.
   - Ask the user to log in if needed.
   - Prefer CDP `Storage.getCookies`.
   - Fall back to `Network.getCookies` for `https://x.com/`, `https://x.com/home`, and `https://twitter.com/`.
   - Write only `auth_token` and `ct0` to `~/.twitter-fetch/.cookies.json`.
3. Use Chrome only to help the user reach the logged-in page when the active Chrome control policy forbids cookie/session inspection.
4. Fall back to hidden manual input:

```bash
python3 scripts/save_cookies.py --prompt
```

If automation already has the values, pipe JSON to the saver without printing values:

```bash
python3 scripts/save_cookies.py --stdin-json
```

Do not print `auth_token`, `ct0`, or full cookie headers in chat, logs, or final answers.

## Output Contract

All commands emit a standard JSON envelope unless `--jsonl` is used:

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

When `--jsonl` is used, emit one normalized tweet object per line.

Common error codes:

| Code | Meaning |
| --- | --- |
| `missing_cookies` | Command requires cookies and the expected cookies file is missing. |
| `invalid_cookies` | Cookies file exists but is malformed or missing `auth_token` / `ct0`. |
| `bad_url` | URL cannot be parsed as an X/Twitter status URL. |
| `network_error` | Provider request failed and may be retryable. |
| `provider_error` | Provider returned an unexpected failure. |
| `not_implemented` | Reserved mode exists but rich provider migration is not complete. |

## Boundaries

- Do not write Obsidian, vault, GitHub Pages, or markdown files.
- Do not update monitor state, `.state.json`, or `.backfill_state.json`.
- Do not classify, summarize, translate, or download media.
- Do not put non-Twitter platforms here.
- Return structured errors instead of raising raw provider exceptions to callers.
