#!/bin/bash
# ml_weekly_retrain.sh — full weekly ML refresh pipeline.
#
# Sequence:
#   1. close-loop labels        → realized_pct on resolved picks
#   2. champion-challenger gate → wraps train_historical with promotion gate
#   3. Slack alert              → posts detailed Block Kit message
set -euo pipefail

cd "/Volumes/MyMacDisk/Claude Skills/SwingTrade"

TS=$(date +%Y%m%d_%H%M%S)
LOG_DIR="cache/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/ml_retrain_${TS}.log"
HIST="$LOG_DIR/ml_retrain_history.log"

{
    echo "=== ML weekly retrain · $(date) ==="
    echo ""
    echo "--- Step 1/3: close-loop labeling ---"
    /usr/bin/python3 scripts/ml_close_loop_labels.py
    echo ""
    echo "--- Step 2/3: train with champion-challenger gate ---"
    /usr/bin/python3 scripts/ml_train_with_gate.py
    echo ""
    echo "--- Step 3/3: post Slack alert with detail ---"
    /usr/bin/python3 scripts/ml_alert_slack.py --mode weekly-retrain
    echo ""
    echo "=== done $(date) ==="
} >"$LOG" 2>&1

RC=$?
LAST_LINE=$(tail -5 "$LOG" | tr '\n' ' | ')
echo "[$(date +%Y-%m-%d\ %H:%M:%S)] rc=$RC  log=$LOG  tail=$LAST_LINE" >>"$HIST"
exit $RC
