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
