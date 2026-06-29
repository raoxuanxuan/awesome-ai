# Timeline Schema

Use for `wiki/timeline.md`.

## Purpose

Timeline records opinion evolution, contradictions, revisions, and trigger
events. It is not a chronological dump of every tweet.

## Required Structure

```text
# Timeline

## <Issue>

### Starting View
### Change Trigger
### Current View
### Evidence Chain
```

## Update Rules

- Add timeline entries only when the delta changes or clarifies a stance.
- Record what changed, when it changed, and which evidence caused the change.
- Include tweet ids in the evidence chain.
- Do not rewrite older stance history unless correcting an evidence error.
