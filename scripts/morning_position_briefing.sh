#!/bin/bash
# morning_position_briefing.sh — daily 8am PT (after morning newsletter at 7:45am).
# Hits /api/positions/active-watch and posts EXPLICIT action items to Slack for
# every open portfolio position. Closes the post-BUY gap: after the system fires
# a BUY signal and you take the trade + add to portfolio, this is the daily
# "should I still hold X?" check.

set -u
cd "$(dirname "$0")/.."

if [ -f .env ]; then
  USER=$(grep '^DASHBOARD_USER=' .env | cut -d= -f2)
  PASS=$(grep '^DASHBOARD_PASS=' .env | cut -d= -f2)
  SLACK_URL=$(grep '^SLACK_WEBHOOK_URL=' .env | cut -d= -f2)
fi
USER="${USER:-gari}"
PASS="${PASS:-Swing2026}"
PORT="${PORT:-7432}"
LOG=/tmp/morning-position-briefing.log
DATE=$(date +%Y-%m-%d)

echo "==== position briefing $DATE ====" >> "$LOG"

if [ -z "${SLACK_URL:-}" ]; then
  echo "○ no SLACK_WEBHOOK_URL — skipping push" >> "$LOG"
  exit 0
fi

RESP=$(curl -s --max-time 15 -u "$USER:$PASS" "http://localhost:$PORT/api/positions/active-watch")
if [ -z "$RESP" ] || [[ "$RESP" == *"curl:"* ]]; then
  echo "⚠ server unreachable on port $PORT — skipping" >> "$LOG"
  exit 0
fi

SLACK_MSG=$(echo "$RESP" | python3 -c "
import json, sys
d = json.load(sys.stdin)
positions = d.get('positions', [])
if not positions:
    print('')
    sys.exit(0)
summary = d.get('summary', {})
lines = [':briefcase: *MORNING POSITION BRIEFING · ' + str(len(positions)) + ' open*']
critical = summary.get('exit_stop', 0) + summary.get('target2_hit', 0)
warn = summary.get('approaching_stop', 0) + summary.get('approaching_t1', 0) + summary.get('trail_active', 0)
if critical: lines.append(f':rotating_light: *{critical} CRITICAL action(s) required*')
elif warn: lines.append(f':warning: *{warn} attention item(s)*')
else: lines.append(':white_check_mark: All positions healthy — hold.')
lines.append('')
emoji_map = {
    'EXIT_STOP':       ':rotating_light:',
    'TARGET2_HIT':     ':moneybag:',
    'TRAIL_ACTIVE':    ':chart_with_upwards_trend:',
    'APPROACHING_T1':  ':dart:',
    'APPROACHING_STOP':':warning:',
    'HOLD':            ':white_check_mark:',
    'NO_PRICE':        ':grey_question:',
}
for p in positions:
    e = emoji_map.get(p['verdict'], '·')
    pnl = f\"{p['pnl_pct']:+.2f}%\" if p['pnl_pct'] else '—'
    lines.append(f\"{e} *{p['ticker']}* {p['verdict']} · {p['shares']}sh @ \${p['entry']:.2f} → \${p['current']:.2f} ({pnl})\")
    lines.append(f\"     {p['action']}\")
print('\n'.join(lines))
")

if [ -z "$SLACK_MSG" ]; then
  echo "○ no open positions — quiet pass" >> "$LOG"
  exit 0
fi

PAYLOAD=$(python3 -c "import json,sys; print(json.dumps({'text': sys.argv[1]}))" "$SLACK_MSG")
RESULT=$(curl -s -X POST -H "Content-Type: application/json" -d "$PAYLOAD" "$SLACK_URL")
echo "Slack: $RESULT" >> "$LOG"
echo "$SLACK_MSG" >> "$LOG"
echo "==== done $DATE ====" >> "$LOG"
