#!/bin/bash
# Walk-Forward validation overnight runner.
# Scheduled by launchd · ~5-9h runtime · results in cache/walk_forward_v2_results.json
# Called by infra/launchd/com.swingtrade.walk-forward.plist
#
# 2026-05-27: added concurrency guard + 6h hard timeout after a 37h runaway
# (May 25 23:00 → May 27 12:15) caused load avg 70 and tunnel 524s.

cd "/Volumes/MyMacDisk/Claude Skills/SwingTrade"

# Concurrency / load guard — skip cleanly if scan running or load too high.
# Exits with code 0 so launchd doesn't restart. Runs at most every 4hr if
# user reschedules; this is fine for an overnight job.
bash scripts/guard_heavy_job.sh "walk-forward-tonight" || exit 0

LOG_DIR="cache/logs"
mkdir -p "$LOG_DIR"
TS=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$LOG_DIR/walkforward_overnight_$TS.log"

PYTHON=$(which python3)
HARD_TIMEOUT_SEC=21600   # 6h hard cap — kills the orchestrator if it stalls

echo "═══ Walk-Forward Overnight Run ═══" > "$LOG_FILE"
echo "Started: $(date)" >> "$LOG_FILE"
echo "PID: $$" >> "$LOG_FILE"
echo "Hard timeout: ${HARD_TIMEOUT_SEC}s ($(($HARD_TIMEOUT_SEC / 3600))h)" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"

# 4 folds, parallel, with per-setup mult tuning (most rigorous).
# Launch in background so we can enforce a hard timeout via a watchdog.
"$PYTHON" backtest/walk_forward_v2.py \
  --folds 4 \
  --train-days 250 \
  --test-days 50 \
  --parallel \
  --tune-multipliers \
  >> "$LOG_FILE" 2>&1 &
WF_PID=$!

# Watchdog: kill the orchestrator and its subprocess tree after HARD_TIMEOUT_SEC
(
  sleep "$HARD_TIMEOUT_SEC"
  if kill -0 "$WF_PID" 2>/dev/null; then
    echo "" >> "$LOG_FILE"
    echo "═══ HARD TIMEOUT after ${HARD_TIMEOUT_SEC}s — killing PID $WF_PID and tree ═══" >> "$LOG_FILE"
    # Kill the whole process group
    pkill -9 -P "$WF_PID" 2>/dev/null
    kill -9 "$WF_PID" 2>/dev/null
    # Also nuke any straggler backtest.py processes spawned by this run
    pkill -9 -f "backtest\.py.*--portfolio.*wf_.*_override" 2>/dev/null
  fi
) &
WATCHDOG_PID=$!

# Wait for orchestrator
wait "$WF_PID"
EXIT_CODE=$?

# Cancel the watchdog if we finished before it fired
kill "$WATCHDOG_PID" 2>/dev/null
echo "" >> "$LOG_FILE"
echo "═══ Done · exit=$EXIT_CODE · $(date) ═══" >> "$LOG_FILE"

# Slack alert if results landed
if [ -f cache/walk_forward_v2_results.json ]; then
  echo "✓ Results written to cache/walk_forward_v2_results.json" >> "$LOG_FILE"
  # Send Slack notification if webhook configured
  if [ -f .env ]; then
    SLACK_URL=$(grep '^SLACK_WEBHOOK_URL=' .env | cut -d= -f2)
    if [ -n "$SLACK_URL" ]; then
      curl -s -X POST -H 'Content-Type: application/json' \
        -d "{\"text\":\":bell: *Walk-Forward Backtest Complete*\nExit: $EXIT_CODE\nLog: $LOG_FILE\nResults: cache/walk_forward_v2_results.json\nReview in dashboard: Admin Activities → Change History\"}" \
        "$SLACK_URL" >> "$LOG_FILE" 2>&1
    fi
  fi
fi

# Keep only last 10 walk-forward logs
ls -t "$LOG_DIR"/walkforward_overnight_*.log 2>/dev/null | tail -n +11 | xargs rm -f 2>/dev/null
