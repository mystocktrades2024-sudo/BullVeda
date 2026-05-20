#!/bin/bash
# Walk-Forward validation overnight runner.
# Scheduled by launchd · ~5-9h runtime · results in cache/walk_forward_v2_results.json
# Called by infra/launchd/com.swingtrade.walk-forward.plist

cd "/Volumes/MyMacDisk/Claude Skills/SwingTrade"

LOG_DIR="cache/logs"
mkdir -p "$LOG_DIR"
TS=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$LOG_DIR/walkforward_overnight_$TS.log"

PYTHON=$(which python3)

echo "═══ Walk-Forward Overnight Run ═══" > "$LOG_FILE"
echo "Started: $(date)" >> "$LOG_FILE"
echo "PID: $$" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"

# 4 folds, parallel, with per-setup mult tuning (most rigorous)
"$PYTHON" backtest/walk_forward_v2.py \
  --folds 4 \
  --train-days 250 \
  --test-days 50 \
  --parallel \
  --tune-multipliers \
  >> "$LOG_FILE" 2>&1

EXIT_CODE=$?
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
