# Twitter Fetch Usage

Use this reference when a user asks how to use `twitter-fetch`, which command to choose, what output to expect, or how cookie setup works.

## Quick Choice

| User intent | Command |
| --- | --- |
| Fetch one public tweet or X Article | `bin/twitter-fetch single --url "<url>" --pretty` |
| Fetch one tweet and attach discovered same-thread context | `bin/twitter-fetch single --url "<url>" --include-thread --pretty` |
| Fetch only a thread envelope | `bin/twitter-fetch thread --url "<url>" --pretty` |
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

`--context full` currently expands thread context. Replies are still a reserved placeholder.

### Thread

Use this when the caller wants the thread as its own result envelope instead of a single tweet with `items[0].thread`.

```bash
bin/twitter-fetch thread --url "https://x.com/user/status/123" --pretty
```

Thread discovery depends on the recent public timeline window and may miss older or hidden thread items.

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
