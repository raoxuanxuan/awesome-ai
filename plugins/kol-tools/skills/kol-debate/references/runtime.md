# KOL Debate Runtime

Current runner modes:

- `prompt-pack`: implemented. Writes all participant and synthesizer prompts to a debate workspace.
- `run`: implemented. Executes prompts with a user-supplied command that reads stdin and writes stdout.
- provider-specific modes such as `claude` or `codex`: intentionally not hard-coded. Wrap those CLIs with `--runner-command` when they have a stable stdin/stdout interface.

Command:

```bash
python3 plugins/kol-tools/scripts/kol_debate.py \
  --vault /Users/saberrao/vault/kol \
  --kols TJ_Research,LinQingV \
  --question "AI capex 是泡沫吗？" \
  --rounds 2 \
  --mode prompt-pack
```

Run:

```bash
python3 plugins/kol-tools/scripts/kol_debate.py \
  --vault /Users/saberrao/vault/kol \
  --kols TJ_Research,LinQingV \
  --question "AI capex 是泡沫吗？" \
  --rounds 2 \
  --mode run \
  --pack-id <pack-id> \
  --runner-command "<stdin-stdout-runner>"
```

`--runner-command` is parsed with `shlex.split` and executed without a shell.
Avoid putting secrets directly in command arguments; use environment variables
or a wrapper script. The manifest records only the executable and argument count.

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
├── verdict.raw.md
├── verdict.json
└── verdict.md
```

Every participant prompt must include the KOL twin safety boundary:

- not the real KOL
- no real-time impersonation
- no price/time point forecast
- say out of coverage when needed

`prompt-pack` creates `turns/` as an empty output directory. `run` fills
`turns/`, runs `prompts/synthesize.md`, parses JSON from the synthesizer output,
and writes both raw and parsed verdict files.
