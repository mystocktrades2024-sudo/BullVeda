#!/bin/bash
# Install SwingTrade git hooks into this clone's .git/hooks/.
# Idempotent — safe to re-run.
#
# What gets installed:
#   pre-commit  →  open-items Excel auto-rebuild + F11 schema-drift check
#
# Run once per fresh clone:
#   bash scripts/install_hooks.sh

set -e

REPO_ROOT="$(git rev-parse --show-toplevel)"
SRC="$REPO_ROOT/infra/hooks"
DST="$REPO_ROOT/.git/hooks"

if [ ! -d "$SRC" ]; then
    echo "ERROR: $SRC not found. Are you in the SwingTrade repo?" >&2
    exit 1
fi

mkdir -p "$DST"

for hook in pre-commit; do
    if [ -f "$SRC/$hook" ]; then
        cp "$SRC/$hook" "$DST/$hook"
        chmod +x "$DST/$hook"
        echo "✓ installed $hook"
    fi
done

echo ""
echo "Hooks installed. Verify with: ls -la $DST/"
echo "Bypass any hook for one commit with: git commit --no-verify"
