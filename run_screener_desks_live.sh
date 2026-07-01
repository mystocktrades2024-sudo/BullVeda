#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  Screener-Desks live overlay — 5-min Schwab batch-quote refresh.
#  Calls run_screener_desks_live.py which:
#    - self-gates to market hours (9:30-4pm ET, DST-aware) — off-hours = no-op
#    - reads every ticker shown across the 11 desks (all horizons)
#    - one Schwab batch quote covers all (ZERO EODHD quota cost, 24/7)
#    - writes infra/prototype/screener_desks_live.json (atomic)
#    - /api/screener_desks merges it as the live price/zone overlay
# ─────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="/Volumes/MyMacDisk/Claude Skills/SwingTrade"
PYTHON="/Applications/Xcode.app/Contents/Developer/Library/Frameworks/Python3.framework/Versions/3.9/bin/python3"
LOG_DIR="$SCRIPT_DIR/cache/logs"
LOG_FILE="$LOG_DIR/screener_desks_live.log"

mkdir -p "$LOG_DIR"
cd "$SCRIPT_DIR"
"$PYTHON" run_screener_desks_live.py >> "$LOG_FILE" 2>&1
