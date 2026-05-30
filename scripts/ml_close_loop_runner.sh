#!/bin/bash
# ml_close_loop_runner.sh — daily close-loop + Slack alert (if anything resolved).
set -euo pipefail

cd "/Volumes/MyMacDisk/Claude Skills/SwingTrade"

LOG_DIR="cache/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/ml_close_loop_$(date +%Y%m%d).log"

{
    echo "=== ML close-loop · $(date) ==="
    /usr/bin/python3 scripts/ml_close_loop_labels.py
    echo ""
    echo "--- Slack alert (only sends if resolved > 0) ---"
    /usr/bin/python3 scripts/ml_alert_slack.py --mode close-loop
    echo "=== done $(date) ==="
} >"$LOG" 2>&1

exit $?
