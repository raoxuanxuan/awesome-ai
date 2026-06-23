---
name: kol-ask
description: Answer a question through one private KOL digital twin using the KOL archive, selected source pages, and optional invest wiki context. Use for "问问 <KOL>", "KOL 会怎么看", or single-KOL decision-support questions.
---

# KOL Ask

Use this skill for single-KOL digital twin Q&A.

## Boundary

- Reads KOL wiki pages.
- May read the local invest wiki when the question is investment-related.
- `context-pack` mode writes only a review workspace under `wiki/.ask_context_packs/`.
- Does not fetch X/Twitter.
- Does not update raw files, indexes, or distilled wiki pages.
- Does not impersonate the KOL as the real person.
- Does not call a model or save a final transcript unless a later runner explicitly does that.

## Runtime Rules

- Say this is a decision-support twin based on archived public/private notes, not the KOL本人.
- Do not claim real-time speech or new opinions from the KOL.
- Do not make time-and-price point predictions.
- If the archive does not cover the question, say it is out of coverage.
- Cite KOL wiki links and include a metadata block.

## Script

Generate a context pack:

```bash
python3 plugins/kol-tools/scripts/kol_ask.py TJ_Research \
  --vault /Users/saberrao/vault/kol \
  --question "怎么看 NVDA 和 AI capex?" \
  --mode context-pack
```

Then review `context.md` and use `prompt.md` with the model/runtime of choice.

See `references/runtime.md`.
