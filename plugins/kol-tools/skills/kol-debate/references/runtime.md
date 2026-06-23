# KOL Debate Runtime

Current runner modes:

- `prompt-pack`: implemented. Writes all participant and synthesizer prompts to a debate workspace.
- `claude`: not implemented in `kol-tools`; old local `kol-twin` hard-coded `claude --print`, but the plugin does not.
- `codex`: not implemented; add only after a stable Codex CLI execution path is available.

Command:

```bash
python3 plugins/kol-tools/scripts/kol_debate.py \
  --vault /Users/saberrao/vault/kol \
  --kols TJ_Research,LinQingV \
  --question "AI capex 是泡沫吗？" \
  --rounds 2 \
  --mode prompt-pack
```

Workspace:

```text
<vault>/_cross/debates/<timestamp>/
├── question.md
├── manifest.json
├── README.md
├── contexts/
│   ├── <handle>.md
│   └── ...
├── prompts/
│   ├── r1-<handle>.md
│   ├── r2-<handle>.md
│   └── synthesize.md
├── turns/
│   ├── r1-<handle>.md
│   └── r2-<handle>.md
├── verdict.json
└── verdict.md
```

Every participant prompt must include the KOL twin safety boundary:

- not the real KOL
- no real-time impersonation
- no price/time point forecast
- say out of coverage when needed

`prompt-pack` creates `turns/` as an empty output directory. A later runner or
manual process should save generated turns there, then run `prompts/synthesize.md`.
