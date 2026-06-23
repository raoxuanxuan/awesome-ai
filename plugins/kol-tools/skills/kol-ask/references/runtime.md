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

Current productized command:

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

It does not call a model. The generated `prompt.md` is the stable handoff to a
Codex/Claude/OpenAI runner or manual review.
