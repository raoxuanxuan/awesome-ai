---
name: qmx-lyric-log-diagnosis
description: Diagnose QMX/Vemus third-party lyric cleanup problems for /v1/qmx_user_song/get_third_song_info. Use when the user provides a Vemus song share text, t.tencentmusic.com short link, mixsongid, traceID, or asks why third-party lyrics were not cleaned, were over-cleaned, followed the wrong LrcToTxt/ClearLyricHeader path, or differ between online logs and current qmx_user_asset code.
---

# QMX Lyric Log Diagnosis

## Overview

Diagnose QMX/Vemus third-party lyric cleanup by connecting four evidence sources:

1. User input, including share text, short links, direct `mixsongid`, or `traceID`.
2. Online RMS/CLS logs through `aik-mtp-delivery-kit:zhiyu-bff-rms`.
3. Live `qmx_user_asset` code, especially current log statements and lyric cleanup functions.
4. Current-code reproduction using the raw LRC from online logs.

Cached log keywords are an acceleration path, not the source of truth. If cached queries miss, evidence is incomplete, or the conclusion depends on implementation behavior, inspect live code and derive query terms from current log statements.

## Required Workflow

1. Resolve the song identity.
   - If the user gives `traceID`, use it directly.
   - If the user gives `mixsongid`, use it directly.
   - If the user gives share text or a `t.tencentmusic.com` URL, follow [input-resolution.md](references/input-resolution.md) and use `scripts/resolve_song_input.py`.
   - If only song name or artist is provided, ask for a time range plus share link or `mixsongid`.

2. Build the first online log query.
   - Use `scripts/build_log_query.py` for the fast path.
   - Defaults: `rmsId=11367`, project `qmx_user_asset`, region `ap-guangzhou`.
   - Default to text search for `mixsongid`, for example `"861782805" AND (...)`, because CLS `mixsongid` fields may be unindexed. Use field search only after live evidence confirms the field is indexed.
   - Use cached lyric log keywords first:
     - `KMR歌词起唱点信息`
     - `开始清洗第三方歌词`
     - `媒资没有返回起唱点`
     - `lrc内容`
     - `第三方歌词清洗结果`

3. Fetch online logs with `zhiyu-bff-rms`.
   - Use `aik-mtp-delivery-kit:zhiyu-bff-rms`; load that skill when making the query.
   - Use `aik-mtp-delivery-kit:zhiyu-bff-jwt` if JWT is missing.
   - Follow [log-fetch-bridge.md](references/log-fetch-bridge.md).
   - Do not print JWTs or credentials.

4. If the fast query misses or is incomplete, discover log terms from live code.
   - Read [live-code-log-discovery.md](references/live-code-log-discovery.md).
   - Inspect current `qmx_user_asset` files and extract the log messages actually emitted around `GetThirdSongInfo`, LRC fetching, and lyric cleanup.
   - Re-query logs with the live-code-derived messages.

5. Extract the lyric case from logs.
   - If the user provides a time window, first aggregate `第三方歌词清洗结果` by `clean_mode`, `lyric_start_time`, `clean_lyric_len`, and `has_clean_lyric`, then choose a representative trace for full extraction.
   - Capture raw LRC from `lrc内容` or equivalent current log fields.
   - For `/v1/qmx_user_song/get_third_song_info`, prefer `service/qmx_user_song_service.go` `lrc内容` logs over similarly named logs from other flows such as `service/song_activity_service.go`.
   - Capture `lyric_start_time`, clean mode, online clean result, trace metadata, and whether the service logged a missing start time.
   - Extract a short raw LRC evidence window around the first expected real lyric and any suspicious retained/removed non-lyric lines. Include enough surrounding lines to show why the output is wrong or right; do not rely only on byte counts or abstract labels.
   - Use `scripts/classify_lyric_issue.py` for a first-pass report, but do not treat heuristics as final code truth.

6. Compare the online lyric with current code.
   - This step is required before giving a root-cause conclusion about lyric cleanup behavior.
   - Follow [code-comparison-workflow.md](references/code-comparison-workflow.md).
   - Use `scripts/run_current_code_lyric_clean.py` when possible to run the current `common.LrcToTxt` or `common.ClearLyricHeader` against the raw LRC from logs without modifying the business repo.
   - Compare the raw LRC evidence window with the online/current-code cleaned first lines. Identify the first wrong retained line or first wrong removed line whenever a mismatch exists.

7. Diagnose using the comparison.
   - Online fails and current code fails: current implementation still has a rule gap.
   - Online fails and current code passes: suspect deployment version, gray release coverage, stale instance, or Apollo config drift.
   - Online passes and current code passes: fixed; treat as regression verification.
   - Raw LRC is missing or malformed: suspect upstream KMR/media/third-party data.
   - Log path differs from code expectation: inspect `lyric_start_time` source and media start-point logs.

## Output Template

Always start the final diagnosis with a concise manager-ready summary paragraph, then give the engineering evidence.

Manager-ready summary rules:

- Put it before all detailed sections.
- Do not add a heading for this summary; write the 2-4 sentences directly at the top.
- Use 2-4 sentences, precise and direct enough to forward to a manager.
- Include whether the problem exists, the exact failure class, the user-visible impact, and the recommended fix direction.
- Name the decisive evidence such as `lyric_start_time`, `clean_mode`, and the first wrong retained or removed lyric line when relevant.
- Do not start with raw log lists, long command output, or broad background.
- When the issue is a lyric content mismatch, include concrete LRC evidence: raw LRC key snippet, actual cleaned snippet, expected cleaned snippet, and the first wrong retained/removed line. Do not leave the diagnosis at "header not cleaned", `txt_byte_len`, or `clean_mode` only.

Use this shape for the final diagnosis:

````md
<2-4 句精确结论：问题是否存在、属于哪类原因、影响、修复方向。>

**结论**
这次属于：<问题类型 / 已修复验证 / 线上代码差异 / 上游数据问题>。

**输入解析**
- 输入类型: 分享文案 / 短链 / mixsongid / traceID
- mixsongid: xxx
- 短链: xxx

**日志搜索依据**
- rmsId: 11367
- region: ap-guangzhou
- queryStr: ...
- 日志关键词来源: cached fast path / live code discovery
- 代码日志点: file:line "message" ...

**线上证据**
- traceID/spanID: ...
- lyric_start_time: ...
- raw_lrc_len / has_raw_lrc: ...
- clean_mode: ...
- aggregate clean result: ...
- online clean result: ...

**LRC差异证据**
- raw LRC key snippet:
```text
<包含首个预期正文前后的 5-15 行，保留时间戳>
```
- actual cleaned snippet:
```text
<线上或当前代码实际清洗后的开头/结尾关键行>
```
- expected cleaned snippet:
```text
<预期清洗后的开头/结尾关键行>
```
- first wrong retained line: <如果有，写具体行；没有则写 none>
- first wrong removed line: <如果有，写具体行；没有则写 none>

**当前代码确认**
- repo: /Users/saberrao/work/vemus/qmx_user_asset
- branch/commit: ...
- cleanup function: common.LrcToTxt / common.ClearLyricHeader
- current-code output: txt_byte_len / first_lines / full output when needed
- online vs current-code: 一致 / 不一致

**根因**
...

**建议**
...
````

## References

- [input-resolution.md](references/input-resolution.md): resolve share text, short links, and direct IDs.
- [log-fetch-bridge.md](references/log-fetch-bridge.md): use verified `zhiyu-bff-rms` online log access.
- [live-code-log-discovery.md](references/live-code-log-discovery.md): derive search keywords from current code when needed.
- [code-comparison-workflow.md](references/code-comparison-workflow.md): run online raw LRC through current code.
- [lyric-cleanup-rules.md](references/lyric-cleanup-rules.md): cleanup path and boundary rules.
- [known-cases.md](references/known-cases.md): fixed historical regression cases and edge boundaries.

## Scripts

- `scripts/resolve_song_input.py`: parse share text, short links, direct `mixsongid`, and `traceID`.
- `scripts/build_log_query.py`: build RMS/CLS query parameters using fast-path or supplied log terms.
- `scripts/classify_lyric_issue.py`: extract LRC clues and produce a heuristic first-pass diagnosis.
- `scripts/run_current_code_lyric_clean.py`: run current `qmx_user_asset` cleanup code against a raw LRC file from logs and report `txt_byte_len` plus `first_lines`.
