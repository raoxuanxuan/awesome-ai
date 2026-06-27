# Log Fetch Bridge

Online logs are fetched through the verified `aik-mtp-delivery-kit` plugin skills.

## Verified Defaults

```text
plugin: aik-mtp-delivery-kit@assistant
log skill: aik-mtp-delivery-kit:zhiyu-bff-rms
jwt skill: aik-mtp-delivery-kit:zhiyu-bff-jwt
project: qmx_user_asset
rmsId: 11367
display name: 启明星用户资产服务
default region: ap-guangzhou
fallback region: ap-beijing
```

The fallback region may return `no CLS topic found`; treat `ap-guangzhou` as the default unless live evidence says otherwise.

## Authentication

`zhiyu-bff-jwt` obtains a BFF JWT from the local TME iOA login state:

```text
local iOA login -> iOA ticket -> /bff-skill/v1/bff_jwt/auth_by_tme_ioa_ticket -> BFF JWT
```

If JWT acquisition fails with an iOA login error, ask the user to log in to TME iOA on this Mac and then continue. Never print JWT values.

## CLS Search Parameters

Use `zhiyu-bff-rms` with:

```json
{
  "rmsId": "11367",
  "region": "ap-guangzhou",
  "queryStr": "<built query>",
  "limit": 100,
  "startTime": "YYYY-MM-DD HH:mm:ss",
  "endTime": "YYYY-MM-DD HH:mm:ss"
}
```

Prefer a narrow time window. If the user only gives a song link and no time, ask for an approximate reproduction time unless a broader query is explicitly acceptable.

## Pagination

- Start with `limit=100`.
- If `listOver=false` and evidence is incomplete, continue with `limit=500`, then `limit=1000`.
- Once using `limit=1000`, ask before continuing more pages.
- If `listOver=false` but results are empty, report that the CLS context limit may have been reached and ask for narrower filters.

## Evidence To Extract

Extract these fields when present:

```text
mixsongid
traceID
spanID
userid
lyric_start_time
raw_lrc_len
has_raw_lrc
lrc / raw LRC
clean_mode
clean_lyric_len
has_clean_lyric
online clean result
```

If the current code uses different field names, prefer the live-code field names and record where they came from.
