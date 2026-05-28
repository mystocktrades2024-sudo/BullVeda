#!/usr/bin/env bash
# Invoked by launchd at 6:35am PT (9:35am ET) Mon-Fri.
# 2026-05-28: upgraded from BUY-only executor to the FULL paper automation loop
# (auto_engine.py --auto): EXITS (real protective stops · earnings-blackout ·
# regime-flip / Sharpe-kill flatten · T1 partial+trail) → BUY entries → gated
# SHORTS. PAPER ONLY. Respects the kill-switch (cache/AUTOMATION_HALT).
set -euo pipefail
SCRIPT_DIR="/Volumes/MyMacDisk/Claude Skills/SwingTrade"
PYTHON="/Applications/Xcode.app/Contents/Developer/Library/Frameworks/Python3.framework/Versions/3.9/bin/python3"
LOG_DIR="$SCRIPT_DIR/cache/logs"
LOG_FILE="$LOG_DIR/executor_$(date +%Y-%m-%d).log"
mkdir -p "$LOG_DIR"
echo "======== Auto-Engine run — $(date) ========" >> "$LOG_FILE"
cd "$SCRIPT_DIR"
"$PYTHON" auto_engine.py --auto --submit >> "$LOG_FILE" 2>&1 || true
echo "Done — $(date)" >> "$LOG_FILE"
