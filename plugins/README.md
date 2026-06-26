# Awesome AI Plugins

This directory contains local agent plugins that share a few common rules:

- Plugin code lives in git.
- Runtime state, credentials, caches, logs, cookies, webhooks, and secrets stay outside git.
- Each plugin owns one coherent layer; cross-plugin workflows should pass structured files or events rather than sharing mutable business state.
- Codex manifests live in `.codex-plugin/plugin.json`; Claude Code manifests live in `.claude-plugin/plugin.json`.

## Plugins

| Plugin | Purpose | Runtime State |
| --- | --- | --- |
| `twitter-tools` | Fetch, normalize, cache, download media for, and monitor X/Twitter content. | `/Users/saberrao/ai-workspace/content-creation/.twitter-monitor/`, `/Users/saberrao/ai-workspace/content-creation/.tweet-pool/`, `~/.twitter-fetch/` |
| `notification-tools` | Queue local notification events, route them by topic, and dispatch Feishu cards. | `~/vault/.notification-center/`, `~/.notification-center/feishu.json` |
| `obsidian-tools` | Route normalized external content into configured Obsidian vaults. | Local vault configuration and target vaults |
| `kol-tools` | Refresh, clean, index, distill, ask, and debate private KOL archives. | `/Users/saberrao/vault/kol/` |

## Boundaries

- `twitter-tools` fetches and monitors external social content, but does not send Feishu messages directly.
- `notification-tools` sends notifications, but does not fetch Twitter/X content or write Obsidian notes.
- `obsidian-tools` writes knowledge artifacts only after a source-specific fetcher provides normalized content.
- `kol-tools` consumes private KOL archives and can call source fetchers, but keeps KOL vault data outside the plugin.

## Marketplace Files

Codex:

```text
.agents/plugins/marketplace.json
```

Claude Code:

```text
.claude-plugin/marketplace.json
```

From the repository root, install with:

```bash
codex plugin marketplace add .
codex plugin add <plugin-name>@awesome-ai
```

For Claude Code:

```bash
claude plugin marketplace add ./
claude plugin install <plugin-name>@awesome-ai
```
