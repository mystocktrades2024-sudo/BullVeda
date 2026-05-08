#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  Position watcher — minute-resolution intraday alerts.
#  Calls position_alerts.run_alerts_pass() which:
#    - reads open positions from portfolio_state.json
#    - fetches live quote per ticker
#    - alerts Slack on stop-approach (within 1×ATR) + T1-hit
#    - throttled 1×/day per ticker per alert-type
#    - bails fast outside market hours (9:30-4pm ET, DST-aware)
# ─────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="/Volumes/MyMacDisk/Claude Skills/SwingTrade"
PYTHON="/Applications/Xcode.app/Contents/Developer/Library/Frameworks/Python3.framework/Versions/3.9/bin/python3"
LOG_DIR="$SCRIPT_DIR/cache/logs"
LOG_FILE="$LOG_DIR/position_watch.log"

mkdir -p "$LOG_DIR"
cd "$SCRIPT_DIR"
"$PYTHON" -c "
import sys
sys.path.insert(0, '.')
from position_alerts import run_alerts_pass
import json
r = run_alerts_pass()
# Only log when something actually happened (avoid log spam every minute)
if r.get('alerts_sent') or r.get('error'):
    from datetime import datetime
    print(f'{datetime.now().isoformat()}  {json.dumps(r)}')
" >> "$LOG_FILE" 2>&1
