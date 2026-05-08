#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  SwingTrade — Daily Scan Runner
#  Invoked by macOS LaunchAgent: com.swingtrade.daily.plist
#  Runs every weekday at 4:47 PM (after market close)
# ─────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="/Volumes/MyMacDisk/Claude Skills/SwingTrade"
PYTHON="/Applications/Xcode.app/Contents/Developer/Library/Frameworks/Python3.framework/Versions/3.9/bin/python3"
LOG_DIR="$SCRIPT_DIR/cache/logs"
LOG_FILE="$LOG_DIR/scan_$(date +%Y-%m-%d).log"
# Ensure log directory exists
mkdir -p "$LOG_DIR"

echo "======================================" >> "$LOG_FILE"
echo "SwingTrade Daily Scan — $(date)" >> "$LOG_FILE"
echo "======================================" >> "$LOG_FILE"

# Run the scan, capturing all output. Don't `set -e` exit on scan failure —
# we want to log and notify, not crash the wrapper.
cd "$SCRIPT_DIR"
set +e
"$PYTHON" swing_trade.py >> "$LOG_FILE" 2>&1
EXIT_CODE=$?
set -e

if [ $EXIT_CODE -eq 0 ]; then
    echo "Scan completed successfully — V2 at http://localhost:7432/v2/dashboard.html" >> "$LOG_FILE"
    # V2 dashboard: post-Phase-A (2026-05-08), legacy cache/dashboard.html is
    # no longer generated. Don't auto-open browser on every cron run — would
    # steal focus 14× per day. User opens V2 URL manually when needed.
else
    echo "Scan FAILED with exit code $EXIT_CODE." >> "$LOG_FILE"
    # Show a macOS notification on failure
    osascript -e 'display notification "Check '"$LOG_FILE"'" with title "SwingTrade scan failed"' 2>/dev/null || true
fi

# Keep only the last 30 log files
ls -t "$LOG_DIR"/scan_*.log 2>/dev/null | tail -n +31 | xargs rm -f 2>/dev/null || true

echo "Done — $(date)" >> "$LOG_FILE"
