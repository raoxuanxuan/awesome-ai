# Known Lyric Regression Guards

These cases are historical regression guard examples, not proof that the current branch or online deployment is fixed. Do not diagnose them as current bugs or current fixes solely by `mixsongid`; use online logs and current-code comparison every time.

Each case is a regression guard:

```text
status: historical_guard_not_current_truth
purpose: regression_guard
rule: compare online logs with current code before concluding
```

## 861782805 - 人生路漫漫

Pattern:

```text
[ti:]
[ar:]
[00:00.00]白小白-人生路漫漫
[00:01.96]作词：徐重来
[00:03.93]作曲：林华勇
[00:05.89]编曲：陆泰名
[00:27.51]我漂泊的船能不能靠在你的岸
```

Historical issue: empty `ti/ar`; title-like first line was treated as the first lyric, so following credits were not filtered.

Current-status warning: this case can regress when `lyric_start_time=0` and `LrcToTxt` cannot infer the empty-metadata title line. If current-code output still starts with `白小白-人生路漫漫` or credit lines, diagnose it as a current rule gap, not a fixed verification.

## 855779725 - 人生路漫漫

Successful regression guard:

```text
[ti:人生路漫漫]
[ar:白小白]
[00:00.16]人生路漫漫 - 白小白
[00:02.09]词：徐重来
[00:03.17]曲：林华勇
[00:04.25]编曲：陆泰名
[00:15.68]未经许可，不得翻唱或使用
[00:27.80]我漂泊的船能不能靠在你的岸
```

Expected current behavior: output starts from `我漂泊的船能不能靠在你的岸`.

## 89029701 - 想你就写信 Live

Pattern:

```text
[ar:周杰伦+李硕 达布希勒图 张鑫]
[ti:想你就写信]
[00:22.01]达布希勒图：
[00:27.59]看你在摇椅上织围巾
[00:50.73]张鑫：
[00:53.63]画面像离家时的风景
[01:40.74]李硕/周杰伦：
[01:41.69]原来感觉是如此亲近
```

Historical issue: Live performer markers are not lyric lines, but colon-line removal must be narrow.

## 713148374 - 壁上观

Pattern: trailing production credits and copyright statement remained at the end.

Expected current behavior: trim continuous trailing production/copyright lines without trimming real lyric lines.

## 623433441 - 梨花香

Pattern:

```text
[ti:]
[ar:]
[00:00.00]梨花香（你看那梨花香飘满城絮）
[00:00.00]作词：卟叽卟叽顾雄
[00:00.01]作曲：弯弯顾雄
[00:00.03]艺人统筹：姜雷
[00:00.05]OP: 北京炅晟文化传媒有限公司
[00:00.06]SP: 北京炅晟文化传媒有限公司
[00:01.32]（未经授权不得翻唱翻录或使用）
[00:04.35]你看那梨花香飘满城絮
```

Historical issue: empty metadata plus title/parenthetical lead and missing keyword coverage.

## 437235478 - 月落的声音

Pattern: title/artist header plus many production fields, including `混音师`, `词曲来源`, `词协力`, `演唱指导`, `录音师`, `统筹`, and `出品`.

Historical issue: keyword list gaps caused filtering to stop early.
