# Lyric Cleanup Rules

Use this as domain context, but verify against live code before final conclusions.

## Main Paths

Historically, `GetThirdSongInfo` cleans third-party lyrics as follows:

- `lyricStartTime > 0`: `common.ClearLyricHeader`.
- Otherwise: `common.LrcToTxt`.

Live code can change this. Always confirm the current branch.

## Important Helpers

Relevant helpers have included:

```text
LrcToTxt
ClearLyricHeader
isObviousNonLyricLeadLine
hasNonLyricLeadKeywordBeforeColon
isProbableSongInfoLeadLine
isProbableMetadataEmptyTitleLeadLine
isPerformerMarkerLine
trimTrailingNonLyricLines
```

## Boundary Rules

- Do not classify all colon lines as non-lyric.
- Single Chinese credit keys such as `词` and `曲` must be exact matches, not broad substring matches.
- Short English keys such as `OP` and `SP` should match as tokens; do not let `OP` match `STOP`.
- A Live performer marker should be an empty-suffix colon line where tokens before the colon match artist tokens from `[ar:]`.
- Tail copyright removal should use a strong pattern such as `未经` plus `许可/授权` plus `翻唱/翻录/使用`.

## Common Categories

```text
empty_metadata_title_lead
no_start_time_lrc_to_txt
start_time_clear_header
missing_credit_keyword
live_performer_marker
trailing_credit_residue
colon_false_positive_risk
online_version_or_config_drift
upstream_lrc_missing_or_malformed
fixed_regression_verification
```
