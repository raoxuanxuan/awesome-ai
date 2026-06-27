# Code Comparison Workflow

Use the raw LRC from online logs to run the current cleanup implementation. Do this before claiming a root cause about lyric cleanup rules.

## Determine The Function

Use online evidence:

- `lyric_start_time > 0`: run `common.ClearLyricHeader(ctx, lrc, lyricStartTime)`.
- `lyric_start_time <= 0`, missing, or logs show `媒资没有返回起唱点`: run `common.LrcToTxt(ctx, lrc)`.

If code has changed, follow the current branch's logic rather than this cached rule.

## Non-Mutating Reproduction

Prefer `scripts/run_current_code_lyric_clean.py`. It creates a temporary Go module outside the business repo and imports the current repo via `replace`.

Example:

```bash
python3 ~/.codex/skills/qmx-lyric-log-diagnosis/scripts/run_current_code_lyric_clean.py \
  --repo /Users/saberrao/work/vemus/qmx_user_asset \
  --lrc-file /tmp/raw.lrc \
  --lyric-start-time 0
```

The script outputs JSON with:

```text
repo
module
function
lyric_start_time
ok
txt
txt_byte_len
first_lines
```

## Visible Mismatch Evidence

Do not diagnose lyric cleanup mismatches from `clean_mode`, `txt_byte_len`, or category labels alone. When raw LRC and current-code output are available, the final answer must show the content difference:

1. Raw LRC key snippet: 5-15 timed lines around the boundary where cleanup should start or stop. Keep timestamps so repeated same-time credit lines are visible.
2. Actual cleaned snippet: the first 5-12 lines from online output when logged, or from `first_lines` in `run_current_code_lyric_clean.py` when online only logs length.
3. Expected cleaned snippet: the first few lines that should remain after cleanup. If the expectation is inferred, say it is inferred from the first real lyric boundary.
4. First wrong retained/removed line: name the exact line that proves the mismatch.

For header cleanup cases, prefer this shape:

````md
**LRC差异证据**
- raw LRC key snippet:
```text
[00:02.49]制作字段...
[00:02.49]第一句真实歌词
```
- actual cleaned snippet:
```text
制作字段...
第一句真实歌词
```
- expected cleaned snippet:
```text
第一句真实歌词
```
- first wrong retained line: `制作字段...`
- first wrong removed line: none
````

If the case is over-cleaning, invert the evidence: show the raw line that was a real lyric, the actual output where it is missing, and set `first wrong removed line` to that exact lyric line.

## If The Script Fails

If Go dependencies or internal network block the script:

1. Report that current-code execution was blocked.
2. Still read the implementation and tests.
3. Do not present a code/result comparison as verified.
4. Give the best source-level diagnosis with the verification gap clearly stated.

## Comparison Outcomes

- Online clean result equals current-code output: current code matches online behavior.
- Online bad but current code good: suspect deployment version, gray release, stale instance, or Apollo config drift.
- Online bad and current code bad: current implementation still has a rule gap.
- Online good and current code good: fixed or regression verification passed.
- Raw LRC missing: upstream KMR/media/third-party data issue.

## Apollo Configuration

Check current code for Apollo keys used by lyric filtering. Known keys include:

```text
qmx_user_asset.lyric.non_lyric_lead.prefix_keywords
qmx_user_asset.lyric.non_lyric_lead.contains_keywords
```

If current-code output differs from online and the difference depends on dynamic keyword lists, inspect live Apollo config or state that Apollo drift is a remaining possibility.
