#!/bin/bash
# Removes pre-modular rollback snapshots created during the 2026-05-09 dashboard
# migration. Safe to run after 2026-05-16 once the dashboard has been stable.
#
# SAFETY (OPS-1, 2026-07): DRY-RUN BY DEFAULT. Without --execute this script
# only REPORTS what it would delete and touches nothing. Pass --execute to
# actually delete. This prevents an accidental invocation from nuking data.
#
# Usage:
#   bash scripts/cleanup_after_2026_05_16.sh            # dry-run (default) — reports only
#   bash scripts/cleanup_after_2026_05_16.sh --execute  # actually delete
set -euo pipefail
cd "$(dirname "$0")/.."

TARGETS=(
  "infra/prototype/dashboard.html.snap-pre-modular-2026-05-09"
  "infra/prototype/elite-detail.html.snap-pre-modular-2026-05-09"
  "infra/prototype/dashboard.html.bak"
  "infra/prototype/dashboard.html.broken-2026-05-09"
  "data/roles.json.bak-2026-05-09"
)

EXECUTE=0
if [ "${1:-}" = "--execute" ]; then
  EXECUTE=1
fi

if [ "$EXECUTE" -eq 0 ]; then
  echo "DRY-RUN (default) — no files will be deleted. Pass --execute to delete."
  echo "Would remove the following pre-modular snapshots (if present):"
fi

removed=0
for f in "${TARGETS[@]}"; do
  if [ -e "$f" ]; then
    if [ "$EXECUTE" -eq 1 ]; then
      rm -f "$f"
      echo "  removed: $f"
      removed=$((removed + 1))
    else
      echo "  would remove: $f"
    fi
  else
    echo "  already absent: $f"
  fi
done

if [ "$EXECUTE" -eq 1 ]; then
  echo "Pre-modular snapshots cleaned ($removed removed)."
else
  echo "Dry-run complete. Re-run with --execute to perform the deletion."
fi
