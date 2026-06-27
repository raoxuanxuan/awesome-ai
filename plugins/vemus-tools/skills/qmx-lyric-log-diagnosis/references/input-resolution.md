# Input Resolution

Resolve the user's input before querying lyric logs.

## Supported Inputs

1. Direct `traceID`.
2. Direct `mixsongid`.
3. A URL containing `mixsongid=123` or encoded `mixsongid%3D123`.
4. Vemus share text containing a `t.tencentmusic.com` short link, for example:

```text
复制打开Vemus未音，听@薛之谦创作的歌曲《违背的青春 (Live)》 https://t.tencentmusic.com/v/in9EedEsMulY ，AI音乐创作就在（@Vemus未音）
```

5. Song name or artist only. This is insufficient for log lookup; ask for a share link, `mixsongid`, `traceID`, or time range.

## Resolution Order

1. Extract `traceID` with a conservative pattern such as `traceID[:= ]+"?([A-Za-z0-9._:-]+)"?`.
2. Extract direct `mixsongid` from raw input.
3. Decode URL-encoded input and extract `mixsongid` again.
4. Extract the first URL using:

```regex
https?:\/\/[^\s，。、！？）》\]]+
```

5. If the URL is a short link, resolve it with the Vemus short-link API:

```text
POST https://vemus-asset.tmeoa.com/v1/qmx_user_song/public/get_short_link_info
body: { "short_link": "<url>" }
```

The expected field is:

```text
data.song_info.mixsongid
```

## Notes

- The Vemus admin page treats text containing `mixsongid=` as a direct long-link case.
- If there is no `mixsongid=`, it extracts the URL and sends it to `get_short_link_info`.
- The short-link API is used only to obtain `mixsongid`. Do not treat its `song_name` or `song_cover` as the authoritative song detail.
- If short-link resolution fails, tell the user to provide `mixsongid`, `traceID`, or use the admin page `https://vemus-admin.tmeoa.com/song/songLinkQuery`.

## Script

Use:

```bash
python3 ~/.codex/skills/qmx-lyric-log-diagnosis/scripts/resolve_song_input.py --text '<share text>'
```

Use `--fetch-short-link` only when it is acceptable to call `vemus-asset.tmeoa.com`.
