#!/usr/bin/env bash
# Invoked by launchd at 6:35am PT (9:35am ET) Mon-Fri.
# Submits paper bracket orders for today's BUY signals.
set -euo pipefail
SCRIPT_DIR="/Volumes/MyMacDisk/Claude Skills/SwingTrade"
PYTHON="/Applications/Xcode.app/Contents/Developer/Library/Frameworks/Python3.framework/Versions/3.9/bin/python3"
LOG_DIR="$SCRIPT_DIR/cache/logs"
LOG_FILE="$LOG_DIR/executor_$(date +%Y-%m-%d).log"
mkdir -p "$LOG_DIR"
echo "======== Executor run — $(date) ========" >> "$LOG_FILE"
cd "$SCRIPT_DIR"
"$PYTHON" executor.py --submit --filter BUY >> "$LOG_FILE" 2>&1 || true
echo "Done — $(date)" >> "$LOG_FILE"
