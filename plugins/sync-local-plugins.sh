#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REMOTE="${AWESOME_AI_REMOTE:-origin}"
BRANCH="${AWESOME_AI_PLUGIN_BRANCH:-main}"
MARKETPLACE="${AWESOME_AI_MARKETPLACE:-awesome-ai}"

cd "$REPO_ROOT"

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Refusing to sync plugins with a dirty worktree." >&2
  git status --short >&2
  exit 1
fi

git fetch "$REMOTE" "$BRANCH"
git switch "$BRANCH"
git pull --ff-only "$REMOTE" "$BRANCH"

PLUGINS="$(
  python3 - <<'PY'
import json
from pathlib import Path

marketplace = Path(".agents/plugins/marketplace.json")
data = json.loads(marketplace.read_text())
for plugin in data.get("plugins", []):
    name = plugin.get("name")
    if name:
        print(name)
PY
)"

for plugin in $PLUGINS; do
  selector="${plugin}@${MARKETPLACE}"
  codex plugin remove "$selector" >/dev/null 2>&1 || true
  codex plugin add "$selector"
done

for plugin in $PLUGINS; do
  version="$(
    python3 - "$plugin" <<'PY'
import json
import sys
from pathlib import Path

plugin = sys.argv[1]
manifest = Path("plugins") / plugin / ".codex-plugin" / "plugin.json"
data = json.loads(manifest.read_text())
print(data["version"])
PY
  )"
  src="plugins/${plugin}"
  cache="${HOME}/.codex/plugins/cache/${MARKETPLACE}/${plugin}/${version}"
  if [[ ! -d "$cache" ]]; then
    echo "Missing installed cache for ${plugin}: ${cache}" >&2
    exit 1
  fi
  if ! diff -qr "$src" "$cache" >/tmp/awesome-ai-plugin-sync-diff.txt; then
    echo "Installed cache differs from git source for ${plugin}." >&2
    cat /tmp/awesome-ai-plugin-sync-diff.txt >&2
    exit 1
  fi
done

notification_skill_cache="${HOME}/.codex/plugins/cache/${MARKETPLACE}/notification-tools/0.1.0/skills/notification-center"
notification_local_skill="${HOME}/.codex/skills/notification-center"
if [[ -d "$notification_skill_cache" ]]; then
  if [[ -L "$notification_local_skill" ]]; then
    rm "$notification_local_skill"
  elif [[ -e "$notification_local_skill" ]]; then
    backup="${notification_local_skill}.legacy.$(date +%Y%m%d%H%M%S)"
    mv "$notification_local_skill" "$backup"
    echo "Moved legacy notification-center skill to ${backup}."
  fi
  ln -s "$notification_skill_cache" "$notification_local_skill"
fi

plugin_pattern="$(printf '%s\n' $PLUGINS | paste -sd '|' -)"
codex plugin list | rg -n "${MARKETPLACE}|${plugin_pattern}" || true
echo "Local Codex plugin cache is synced with ${REMOTE}/${BRANCH}."
