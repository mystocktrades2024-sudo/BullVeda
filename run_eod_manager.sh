#!/usr/bin/env bash
# Invoked by launchd at 12:55pm PT (3:55pm ET) Mon-Fri.
# Applies EOD exits / trims / stop-tighten.
set -euo pipefail
SCRIPT_DIR="/Volumes/MyMacDisk/Claude Skills/SwingTrade"
PYTHON="/Applications/Xcode.app/Contents/Developer/Library/Frameworks/Python3.framework/Versions/3.9/bin/python3"
LOG_DIR="$SCRIPT_DIR/cache/logs"
LOG_FILE="$LOG_DIR/eod_$(date +%Y-%m-%d).log"
mkdir -p "$LOG_DIR"
echo "======== EOD manager — $(date) ========" >> "$LOG_FILE"
cd "$SCRIPT_DIR"
"$PYTHON" eod_manager.py --submit --close-positions --tighten-stops >> "$LOG_FILE" 2>&1 || true
echo "Done — $(date)" >> "$LOG_FILE"
