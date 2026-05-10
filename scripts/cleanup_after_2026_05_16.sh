#!/bin/bash
# Run after 2026-05-16 if dashboard has been stable for a week.
# Removes pre-modular rollback snapshots.
cd "$(dirname "$0")/.."
rm -f infra/prototype/dashboard.html.snap-pre-modular-2026-05-09
rm -f infra/prototype/elite-detail.html.snap-pre-modular-2026-05-09
rm -f infra/prototype/dashboard.html.bak
rm -f infra/prototype/dashboard.html.broken-2026-05-09
rm -f data/roles.json.bak-2026-05-09
echo "Pre-modular snapshots cleaned."
