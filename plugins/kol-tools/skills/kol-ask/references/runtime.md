# KOL Ask Runtime

Context selection:

1. Resolve handle from `_cross/_registry.md`.
2. Always load `wiki/soul.md`.
3. Load relevant `wiki/methods/*.md`.
4. Load matching `wiki/positions/*.md` and `wiki/sources/*.md`.
5. Load relevant `timeline.md` sections when the question touches stance evolution.
6. Load invest wiki pages only when the question is investment-related.

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

Run:

```bash
python3 plugins/kol-tools/scripts/kol_ask.py <handle-or-alias> \
  --vault /Users/saberrao/vault/kol \
  --question "<question>" \
  --mode run \
  --pack-id <pack-id> \
  --runner-command "<stdin-stdout-runner>"
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
