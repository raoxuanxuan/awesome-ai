# KOL Twin Wiki Rollout

Start with a dry-run:

```bash
python3 plugins/kol-tools/scripts/kol_rollout.py \
  --vault /Users/saberrao/vault/kol \
  --dry-run
```

The planner classifies each handle through `kol_wiki_inventory.py`:

```text
readiness: mature_wiki
next_action: process_delta

readiness: partial_wiki
next_action: create_repair_pack

readiness: no_wiki_yet
next_action: create_bootstrap_pack

readiness: clean_index_not_ready
next_action: run_clean_index_first
```

Recommended order:

1. `TJ_Research`
2. `tig88411109`
3. `aleabitoreddit`
4. `qinbafrank`
5. remaining KOLs by `readiness`, `next_action`, and review cost

Never commit ingest watermarks before validation marks
`safe_to_commit_watermark: true`.

Bootstrap packs are review workspaces. They do not write durable wiki pages by
themselves and should be treated as high-risk until reviewed.
