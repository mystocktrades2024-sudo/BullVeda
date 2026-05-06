#!/bin/zsh
# SwingTrade auto-scan — runs every 4 hours via system cron
# Auto-retries once on failure. Logs to SwingTrade/cache/logs/

LOG_DIR="/Volumes/MyMacDisk/Claude Skills/SwingTrade/cache/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/scan_$(date +%Y%m%d_%H%M).log"
PYTHON="/Applications/Xcode.app/Contents/Developer/Library/Frameworks/Python3.framework/Versions/3.9/bin/python3"
SCAN_DIR="/Volumes/MyMacDisk/Claude Skills/SwingTrade"

# Keep only last 30 log files
ls -t "$LOG_DIR"/scan_*.log 2>/dev/null | tail -n +31 | xargs rm -f 2>/dev/null

echo "=== SwingTrade Scan: $(date) ===" >> "$LOG"
cd "$SCAN_DIR" && $PYTHON swing_trade.py >> "$LOG" 2>&1
EXIT_CODE=$?

# Auto-retry once on failure (with --fresh flag to force re-fetch)
if [ $EXIT_CODE -ne 0 ]; then
  echo "=== RETRY: First run failed (exit $EXIT_CODE), retrying with --fresh: $(date) ===" >> "$LOG"
  sleep 30
  cd "$SCAN_DIR" && $PYTHON swing_trade.py --fresh >> "$LOG" 2>&1
  EXIT_CODE=$?
  if [ $EXIT_CODE -ne 0 ]; then
    echo "=== FAILED: Both attempts failed (exit $EXIT_CODE): $(date) ===" >> "$LOG"
  fi
fi

echo "=== Done (exit $EXIT_CODE): $(date) ===" >> "$LOG"
