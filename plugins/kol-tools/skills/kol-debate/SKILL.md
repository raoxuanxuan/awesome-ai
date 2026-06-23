---
name: kol-debate
description: Run or prepare a multi-KOL debate using private KOL twin archives. Use when several KOL perspectives should independently discuss one question and then compare disagreements.
---

# KOL Debate

Use this skill for multi-KOL discussion over the KOL wiki archive.

## Boundary

- Reads KOL wiki pages for multiple handles.
- `prompt-pack` mode writes debate workspaces under `/Users/saberrao/vault/kol/_cross/debates/`.
- Current productized mode does not call a model or generate a final verdict by itself.
- Does not fetch X/Twitter.
- Does not update raw or distilled KOL wiki pages.
- Does not hard-code one model provider as the only runtime.

## Debate Shape

1. Round 1: each KOL twin answers independently and blind.
2. Round 2: each KOL twin sees others' Round 1 and responds to real differences.
3. Synthesizer: summarizes consensus, disagreements, blind spots, and quality.

## Script

```bash
python3 plugins/kol-tools/scripts/kol_debate.py \
  --vault /Users/saberrao/vault/kol \
  --kols TJ_Research,LinQingV \
  --question "AI capex 是泡沫吗？" \
  --rounds 2 \
  --mode prompt-pack
```

Use the generated prompts with the model/runtime of choice, then save outputs into
the generated `turns/` directory.

See `references/runtime.md`.
