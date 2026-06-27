# Position Page Schema

Use for `wiki/positions/*.md`.

## Purpose

A position page records the KOL's stance on a ticker, company, asset, or event.

## Required Sections

```text
# <Position>

## Current Stance
## Stance Strength
## Reasons
## Evolution
## Relevant Methods
## Risks / Disconfirming Evidence
## Evidence
```

## Stance Rules

- Mark stance as explicit, inferred, mixed, or unknown.
- Do not infer current stance from stale evidence without saying it is stale.
- Keep stance strength separate from confidence.

## Evidence Rules

- Every stance update must cite tweet ids.
- Preserve date order for stance evolution.
- If evidence conflicts, keep the conflict visible instead of smoothing it away.
