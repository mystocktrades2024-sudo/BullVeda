#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  Daily signal-state alerts: WATCH→BUY flips + new Elite Picks.
#  Day-over-day diff vs data/signal_alert_snapshot.json. Runs once
#  each morning AFTER the 7:00 PT scan rewrites cache/last_bundle.json.
#  Fires LIVE to owner Slack (same engine verdicts the briefing sends).
# ─────────────────────────────────────────────────────────────
set -euo pipefail
SCRIPT_DIR="/Volumes/MyMacDisk/Claude Skills/SwingTrade"
PYTHON="/Applications/Xcode.app/Contents/Developer/Library/Frameworks/Python3.framework/Versions/3.9/bin/python3"
LOG_DIR="$SCRIPT_DIR/cache/logs"; mkdir -p "$LOG_DIR"
cd "$SCRIPT_DIR"
"$PYTHON" -c "
import sys; sys.path.insert(0,'.')
from signal_alerts import run_signal_alerts
import json
r = run_signal_alerts(dry_run=False)
if r.get('flips') or r.get('new_elite') or r.get('error'):
    from datetime import datetime
    print(f'{datetime.now().isoformat()}  {json.dumps(r)}')
" >> "$LOG_DIR/signal_alerts.log" 2>&1
