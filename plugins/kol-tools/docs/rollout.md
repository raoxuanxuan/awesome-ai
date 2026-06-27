# KOL Twin Wiki Rollout

Start with a dry-run:

```bash
python3 plugins/kol-tools/scripts/kol_rollout.py \
  --vault /Users/saberrao/vault/kol \
  --dry-run
```

The planner classifies each handle through `kol_wiki_inventory.py`:

- `existing_mature_wiki` -> `delta`
- `partial_wiki_repair` -> `bootstrap-pack`
- `bootstrap_required` -> `bootstrap-pack`
- `not_ready` -> `blocked`

Recommended order:

1. `TJ_Research`
2. `tig88411109`
3. `aleabitoreddit`
4. `qinbafrank`
5. remaining handles by route and review cost

Never commit ingest watermarks before validation marks
`safe_to_commit_watermark: true`.

Bootstrap packs are review workspaces. They do not write durable wiki pages by
themselves and should be treated as high-risk until reviewed.
