#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  refresh_options_flow.py shim — runs every 30 min via launchd.
#  Script itself bails when outside Mon-Fri 6:30am-1pm PT.
# ─────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="/Volumes/MyMacDisk/Claude Skills/SwingTrade"
PYTHON="/Applications/Xcode.app/Contents/Developer/Library/Frameworks/Python3.framework/Versions/3.9/bin/python3"
LOG_DIR="$SCRIPT_DIR/cache/logs"
LOG_FILE="$LOG_DIR/options_flow_refresh.log"

mkdir -p "$LOG_DIR"
cd "$SCRIPT_DIR"
"$PYTHON" refresh_options_flow.py >> "$LOG_FILE" 2>&1
