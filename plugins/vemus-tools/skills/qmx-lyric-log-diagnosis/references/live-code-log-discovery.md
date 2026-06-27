# Live Code Log Discovery

Use cached lyric log keywords as a fast path. If that fails or the diagnosis needs implementation evidence, discover log messages from the live code.

## Cached Fast-Path Keywords

```text
开始清洗第三方歌词
媒资没有返回起唱点
lrc内容
第三方歌词清洗结果
```

These are not authoritative. They only speed up the first query.

## When To Read Live Code

Read live code when any of these are true:

- Cached query returns no logs.
- Logs are missing raw LRC, clean result, or cleanup mode.
- The user asks why the behavior happened.
- Online behavior contradicts known fixed cases.
- You need to decide whether the cause is code, deployment, Apollo config, or upstream data.
- The code branch may have changed since the cached keywords were recorded.

## Repository

Default repository:

```text
/Users/saberrao/work/vemus/qmx_user_asset
```

Before mutating this repo, follow the user's branch guard. For read-only inspection, branch switching is not required.

## Required Reads

Inspect these files or their current equivalents:

```text
interfaces/qmx_user_song_interface.go
service/qmx_user_song_service.go
common/util.go
common/apollo.go
common/util_test.go
```

## Search Commands

Use `rg` first:

```bash
rg -n 'GetThirdSongInfo|lrc|lyric|歌词|起唱点|ClearLyricHeader|LrcToTxt' interfaces service common
rg -n 'log\.(Info|Warn|Error|Debug)Context|zap\.' interfaces service common
rg -n 'isObviousNonLyricLeadLine|hasNonLyricLeadKeywordBeforeColon|isProbableSongInfoLeadLine|isProbableMetadataEmptyTitleLeadLine|isPerformerMarkerLine|trimTrailingNonLyricLines|getLyricLead' common
```

Prefer messages near the `GetThirdSongInfo` call path. Record file and line numbers for every log message used in `queryStr`.

## Query Generation From Live Code

Build the query from the current log messages:

```text
mixsongid: <id> AND ("<message1>" OR "<message2>" OR "<message3>")
```

For trace search, use the trace directly:

```text
traceID: "<trace>"
```

If log fields use `mixsongId` instead of `mixsongid`, include both forms or use the exact field name shown by live logs.
