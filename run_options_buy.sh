#!/usr/bin/env bash
# Options auto-BUY — invoked by launchd at 6:50am PT (after the morning scan).
# Small mode: exactly 1 contract/ticker, defined-risk long calls, PAPER ONLY.
# Gated by config.options_auto_buy._enabled + market-hours guard + cache/AUTOMATION_HALT.
set -euo pipefail
SCRIPT_DIR="/Volumes/MyMacDisk/Claude Skills/SwingTrade"
PYTHON="/Applications/Xcode.app/Contents/Developer/Library/Frameworks/Python3.framework/Versions/3.9/bin/python3"
LOG_DIR="$SCRIPT_DIR/cache/logs"
LOG_FILE="$LOG_DIR/options_buy_$(date +%Y-%m-%d).log"
mkdir -p "$LOG_DIR"
cd "$SCRIPT_DIR"
echo "======== Options auto-buy — $(date) ========" >> "$LOG_FILE"
"$PYTHON" options_executor.py --submit >> "$LOG_FILE" 2>&1 || true
echo "Done — $(date)" >> "$LOG_FILE"
