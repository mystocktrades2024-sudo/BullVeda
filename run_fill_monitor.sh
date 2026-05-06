#!/usr/bin/env bash
# Invoked every 10 min during market hours.
# Cancels unfilled orders older than 10 min.
set -euo pipefail
SCRIPT_DIR="/Volumes/MyMacDisk/Claude Skills/SwingTrade"
PYTHON="/Applications/Xcode.app/Contents/Developer/Library/Frameworks/Python3.framework/Versions/3.9/bin/python3"
LOG_DIR="$SCRIPT_DIR/cache/logs"
LOG_FILE="$LOG_DIR/fill_$(date +%Y-%m-%d).log"
mkdir -p "$LOG_DIR"
cd "$SCRIPT_DIR"
"$PYTHON" fill_monitor.py --max-minutes 10 >> "$LOG_FILE" 2>&1 || true
