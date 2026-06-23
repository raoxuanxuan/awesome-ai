# KOL Debate Runtime

Planned runner modes:

- `prompt-pack`: write all participant and synthesizer prompts to a debate workspace for the current agent to execute manually.
- `claude`: run through Claude Code CLI when available.
- `codex`: add only after a stable Codex CLI execution path is available.

Workspace:

```text
<vault>/_cross/debates/<timestamp>/
├── question.md
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
