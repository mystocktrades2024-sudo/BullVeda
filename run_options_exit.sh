#!/usr/bin/env bash
# Options auto-EXIT — invoked by launchd every 30 min. Also refreshes the
# cache/options_positions.json snapshot each run. PAPER ONLY.
# Exits gated by config.options_auto_exit._enabled + market-hours guard + AUTOMATION_HALT.
# Off-hours runs are cheap no-ops (market-hours guard refuses to submit).
set -euo pipefail
SCRIPT_DIR="/Volumes/MyMacDisk/Claude Skills/SwingTrade"
PYTHON="/Applications/Xcode.app/Contents/Developer/Library/Frameworks/Python3.framework/Versions/3.9/bin/python3"
LOG_DIR="$SCRIPT_DIR/cache/logs"
LOG_FILE="$LOG_DIR/options_exit_$(date +%Y-%m-%d).log"
mkdir -p "$LOG_DIR"
cd "$SCRIPT_DIR"
echo "---- Options exit check — $(date) ----" >> "$LOG_FILE"
"$PYTHON" options_portfolio.py --exits --submit >> "$LOG_FILE" 2>&1 || true
