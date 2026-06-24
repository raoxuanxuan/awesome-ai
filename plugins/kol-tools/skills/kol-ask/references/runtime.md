# KOL Ask Runtime

Context selection:

1. Resolve handle from `_cross/_registry.md`.
2. Always load `wiki/soul.md`.
3. Load relevant `wiki/methods/*.md`.
4. Load matching `wiki/positions/*.md` and `wiki/sources/*.md`.
5. Load relevant `timeline.md` sections when the question touches stance evolution.
6. Load invest wiki `_index.md` plus relevant pages only when the question is investment-related.

Required ending:

```meta
confidence: 高|中|低
in_comfort_zone: yes|no
primary_sources: [...]
wikilinks_used: [...]
caveats: ...
```

Use `plugins/kol-tools/templates/persona-system-prompt.md` as the base prompt.

Create a context pack:

```bash
python3 plugins/kol-tools/scripts/kol_ask.py <handle-or-alias> \
  --vault /Users/saberrao/vault/kol \
  --invest-wiki /Users/saberrao/vault/invest/wiki \
  --question "<question>" \
  --mode context-pack
```

It writes:

```text
vault/kol/<handle>/wiki/.ask_context_packs/<pack-id>/
├── manifest.json
├── context.md
└── prompt.md
```

`manifest.json` records both KOL wiki `selected_files` and optional
`invest_files`. The prompt requires the answer to distinguish KOL archive
evidence from invest wiki background knowledge.

Run:

```bash
python3 plugins/kol-tools/scripts/kol_ask.py <handle-or-alias> \
  --vault /Users/saberrao/vault/kol \
  --invest-wiki /Users/saberrao/vault/invest/wiki \
  --question "<question>" \
  --mode run \
  --pack-id <pack-id> \
  --runner-command "<stdin-stdout-runner>"
```

Bundled runner choices:

```bash
--runner-command "python3 plugins/kol-tools/scripts/kol_codex_runner.py"
--runner-command "python3 plugins/kol-tools/scripts/kol_claude_runner.py"
```

`kol_codex_runner.py` calls `codex exec -` with read-only sandboxing,
`--ask-for-approval never`, and `--ephemeral`. Override with:

```bash
export KOL_CODEX_BIN=/path/to/codex
export KOL_CODEX_MODEL=<model>
export KOL_CODEX_PROFILE=<profile>
```

`kol_claude_runner.py` calls `claude --print` with `--tools ""` and
`--no-session-persistence`. Override with:

```bash
export KOL_CLAUDE_BIN=/path/to/claude
export KOL_CLAUDE_MODEL=<model>
```

`--runner-command` is parsed with `shlex.split` and executed without a shell.
Avoid putting secrets directly in command arguments; use environment variables
or a wrapper script. The manifest records only the executable and argument count.

Run mode writes:

```text
vault/kol/<handle>/wiki/.ask_context_packs/<pack-id>/
├── answer.md
└── manifest.json
```
