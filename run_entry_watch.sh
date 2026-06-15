#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  Entry-zone watcher — intraday two-tier alerts for bullish names.
#  Calls entry_watch.run_entry_watch_pass() which:
#    - reads EVERY bullish-bias name from cache/last_bundle.json (~250)
#    - computes each name's swing buy zone offline (EMA8/21/50 + ATR + S/R)
#    - one Schwab batch quote covers all (ZERO EODHD quota cost, 24/7)
#    - Tier-1 SOFT  : price pulled into the buy-zone band -> heads-up
#    - Tier-2 FIRM  : in zone + entry was sole blocker + live R:R >= floor
#    - throttled 1x/day per ticker per tier (alert_sent_log.json)
#    - self-gates to market hours (9:30-4pm ET, DST-aware) — off-hours = no-op
# ─────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="/Volumes/MyMacDisk/Claude Skills/SwingTrade"
PYTHON="/Applications/Xcode.app/Contents/Developer/Library/Frameworks/Python3.framework/Versions/3.9/bin/python3"
LOG_DIR="$SCRIPT_DIR/cache/logs"
LOG_FILE="$LOG_DIR/entry_watch.log"

mkdir -p "$LOG_DIR"
cd "$SCRIPT_DIR"
"$PYTHON" -c "
import sys
sys.path.insert(0, '.')
from entry_watch import run_entry_watch_pass
import json
r = run_entry_watch_pass()
# Only log when something fired or errored (avoid spam every cycle).
if r.get('alerts_sent') or r.get('error'):
    from datetime import datetime
    print(f'{datetime.now().isoformat()}  {json.dumps(r)}')
" >> "$LOG_FILE" 2>&1
