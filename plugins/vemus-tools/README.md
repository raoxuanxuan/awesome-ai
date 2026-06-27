# Vemus Tools

Vemus Tools collects reusable QMX/Vemus business diagnostics for Codex and Claude Code. The first release packages the `qmx-lyric-log-diagnosis` skill for third-party lyric cleanup issues in `qmx_user_asset`.

## Capabilities

- Resolve Vemus share text, `t.tencentmusic.com` short links, direct `mixsongid`, or `traceID`.
- Build RMS/CLS log queries for `qmx_user_asset` lyric cleanup evidence.
- Query online logs through the existing `aik-mtp-delivery-kit` BFF/JWT workflow when available.
- Extract raw LRC from service logs and identify the relevant cleanup mode.
- Reproduce cleanup against the current local `qmx_user_asset` code without modifying the business repo.
- Report concrete raw/actual/expected LRC differences, including the first wrong retained or removed line.

## Boundaries

- This plugin does not store runtime logs, credentials, JWTs, or iOA state.
- It does not mutate `qmx_user_asset`; current-code reproduction uses a temporary Go module.
- It does not replace `aik-mtp-delivery-kit`; online RMS/CLS access still depends on that plugin's BFF/JWT skills.
- It does not create MTP tasks, operate KCD pipelines, or perform approval actions.

## Directory Structure

```text
vemus-tools/
├── .codex-plugin/plugin.json
├── .claude-plugin/plugin.json
├── README.md
└── skills/
    └── qmx-lyric-log-diagnosis/
        ├── SKILL.md
        ├── agents/openai.yaml
        ├── references/
        └── scripts/
```

## Runtime Inputs

The lyric diagnosis workflow may need:

- A Vemus share link, `mixsongid`, or `traceID`.
- A narrow time window for online CLS lookup.
- Local access to `/Users/saberrao/work/vemus/qmx_user_asset` when comparing current code.
- Local TME iOA/BFF login state when querying RMS/CLS logs.

Temporary reproduction files are created outside the business repo by the skill script and should not be committed.

## Install

From the awesome-ai repository root:

```bash
codex plugin marketplace add .
codex plugin add vemus-tools@awesome-ai
```

Claude Code:

```bash
claude plugin marketplace add ./
claude plugin install vemus-tools@awesome-ai
```

## Example Prompts

```text
查一下今天中午 11:00-12:00，这首 Vemus 歌的歌词清洗问题: <share link>
```

```text
qmx-lyric-log-diagnosis: traceID=xxx 为什么第三方歌词头部没清干净？
```

## Security

- Do not print or commit BFF JWTs, iOA tickets, cookies, or private service credentials.
- Keep online log excerpts scoped to the requested case.
- Avoid committing raw production logs or temporary reproduction artifacts.
