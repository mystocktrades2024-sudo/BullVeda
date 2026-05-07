#!/bin/bash
# setup_monitoring.sh — One-shot installer for daily engine health check.
#
# Adds two cron entries to your user crontab:
#   1. Daily engine health check at 7:30am Mon-Fri (right after typical scan time)
#   2. Monthly review on the 1st at 8:00am (kill list / multiplier change recs)
#
# Re-runnable: detects existing entries and skips duplicates.
# Reverse with: crontab -l | grep -v 'engine_health_check\|monthly_review' | crontab -

set -e
PROJ_DIR="/Volumes/MyMacDisk/Claude Skills/SwingTrade"
PYTHON="$(which python3)"

if [ ! -d "$PROJ_DIR" ]; then
  echo "✗ Project directory not found: $PROJ_DIR"
  exit 1
fi
if [ -z "$PYTHON" ]; then
  echo "✗ python3 not in PATH"
  exit 1
fi

HEALTH_CMD="cd \"$PROJ_DIR\" && $PYTHON engine_health_check.py --quiet"
HEALTH_CRON="30 7 * * 1-5 $HEALTH_CMD"
REVIEW_CMD="cd \"$PROJ_DIR\" && $PYTHON monthly_review.py >> \"$PROJ_DIR/cache/logs/monthly_review.log\" 2>&1"
REVIEW_CRON="0 8 1 * * $REVIEW_CMD"

# Read existing crontab (handle empty case)
EXISTING="$(crontab -l 2>/dev/null || true)"

ADDED=0
if echo "$EXISTING" | grep -q 'engine_health_check'; then
  echo "⊘ engine_health_check cron entry already exists — skipping"
else
  EXISTING="$EXISTING
$HEALTH_CRON"
  ADDED=$((ADDED+1))
  echo "✓ Adding daily engine health check (7:30am Mon-Fri)"
fi

if echo "$EXISTING" | grep -q 'monthly_review'; then
  echo "⊘ monthly_review cron entry already exists — skipping"
else
  EXISTING="$EXISTING
$REVIEW_CRON"
  ADDED=$((ADDED+1))
  echo "✓ Adding monthly review (1st of month at 8:00am)"
fi

if [ "$ADDED" -gt 0 ]; then
  echo "$EXISTING" | crontab -
  echo ""
  echo "✓ Cron updated. Current swing-trade entries:"
  crontab -l | grep -E 'engine_health_check|monthly_review' || true
else
  echo ""
  echo "Nothing to add. Current entries:"
  crontab -l | grep -E 'engine_health_check|monthly_review' || true
fi

echo ""
echo "Take a baseline snapshot for monthly_review now? [Y/n]"
read -r REPLY
if [[ ! "$REPLY" =~ ^[Nn] ]]; then
  cd "$PROJ_DIR"
  $PYTHON monthly_review.py --reset
fi

echo ""
echo "Done. Verify cron with: crontab -l"
echo "Test health check now: cd \"$PROJ_DIR\" && python3 engine_health_check.py"
