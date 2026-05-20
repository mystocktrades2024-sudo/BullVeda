#!/bin/bash
# Captures daily Paper Shadow snapshot (stage 3 of validation cascade).
# Compares ACTUAL BUYs from today's scan vs WHAT IDEAL CONFIG WOULD HAVE DONE.
# Appends to data/shadow_paper_log.jsonl. Idempotent — won't duplicate same date.
# Called automatically from run_daily_scan.sh post-scan. Safe to manual-run anytime.

set -u  # error on undefined vars; do NOT set -e (graceful fail if server down)

cd "$(dirname "$0")/.."

# Pull credentials from .env
if [ -f .env ]; then
  USER=$(grep '^DASHBOARD_USER=' .env | cut -d= -f2)
  PASS=$(grep '^DASHBOARD_PASS=' .env | cut -d= -f2)
fi
USER="${USER:-gari}"
PASS="${PASS:-Swing2026}"
PORT="${PORT:-7432}"

# IDEAL config — keep aligned with what-if simulator
PAYLOAD='{
  "min_score": 70,
  "sector_cap_under": 3,
  "setup_mults": {
    "EMA21 Pullback": 0,
    "52wk Breakout": 0,
    "Pocket Pivot": 0,
    "Squeeze Expansion": 0.7,
    "Trend Continuation": 1.0,
    "VCP Breakout": 1.3,
    "10-Week Pullback": 1.5,
    "Near-VCP Breakout": 1.0
  }
}'

RESPONSE=$(curl -s --max-time 10 -u "$USER:$PASS" \
  -X POST -H 'Content-Type: application/json' \
  -d "$PAYLOAD" \
  "http://localhost:$PORT/api/shadow-paper/snapshot" 2>&1)

if [ -z "$RESPONSE" ] || [[ "$RESPONSE" == *"curl:"* ]]; then
  echo "⚠ shadow-paper snapshot: server unreachable on port $PORT — skipping (will retry tomorrow)"
  exit 0
fi

# Parse + echo summary
STATUS=$(echo "$RESPONSE" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('status','?'))" 2>/dev/null)
case "$STATUS" in
  captured)
    SUMMARY=$(echo "$RESPONSE" | python3 -c "import json,sys; e=json.load(sys.stdin).get('entry',{}); print(f\"actual={e.get('actual_buy_count',0)} shadow={e.get('shadow_buy_count',0)} shadow_only={len(e.get('shadow_only',[]))} actual_only={len(e.get('actual_only',[]))}\")" 2>/dev/null)
    echo "✓ shadow-paper snapshot captured · $SUMMARY"
    ;;
  already_captured)
    echo "○ shadow-paper snapshot already exists for today (skipped)"
    ;;
  *)
    echo "⚠ shadow-paper snapshot returned: $STATUS"
    echo "$RESPONSE" | head -c 300
    ;;
esac
