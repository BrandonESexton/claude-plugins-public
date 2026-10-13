#!/usr/bin/env bash
# Builds one zip per plugin and one zip per skill into dist/.
#   dist/<plugin>.zip          whole plugin, .claude-plugin/ at the archive root (Claude Cowork upload)
#   dist/skill-<skill>.zip     one skill folder with SKILL.md at its top (ChatGPT or other skill uploads)
# Usage: scripts/package.sh [plugin-name ...]   (default: every plugin)
set -euo pipefail
cd "$(dirname "$0")/.."
rm -rf dist && mkdir -p dist
plugins=("$@")
[ ${#plugins[@]} -eq 0 ] && plugins=($(ls plugins))
for p in "${plugins[@]}"; do
  [ -d "plugins/$p" ] || { echo "no such plugin: $p" >&2; exit 1; }
  (cd "plugins/$p" && zip -qr "../../dist/$p.zip" . -x '*.DS_Store' '*/__pycache__/*' '*.pyc')
  echo "dist/$p.zip"
  for s in plugins/$p/skills/*/; do
    [ -f "$s/SKILL.md" ] || continue
    n=$(basename "$s")
    (cd "$s/.." && zip -qr "../../../dist/skill-$n.zip" "$n" -x '*.DS_Store')
    echo "dist/skill-$n.zip"
  done
done
