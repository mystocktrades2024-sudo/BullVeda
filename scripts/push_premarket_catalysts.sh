#!/bin/bash
# Push overnight catalysts affecting portfolio/watchlist to Slack.
# Called by run_daily_scan.sh post-scan (so it fires after fresh data lands).
# Idempotent — but Slack may dedup itself if repeated.

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

if [ -z "${SLACK_URL:-}" ]; then
  echo "○ no SLACK_WEBHOOK_URL — skipping push"
  exit 0
fi

# Pull mine-only catalysts (last 16 hours)
RESP=$(curl -s --max-time 10 -u "$USER:$PASS" \
  "http://localhost:$PORT/api/premarket-catalysts?lookback_hours=16&mine_only=true")

if [ -z "$RESP" ] || [[ "$RESP" == *"curl:"* ]]; then
  echo "⚠ premarket-catalysts: server unreachable on port $PORT — skipping"
  exit 0
fi

# Parse JSON and format Slack message
SLACK_MSG=$(echo "$RESP" | python3 -c "
import json, sys
d = json.load(sys.stdin)
cats = d.get('catalysts', [])
if not cats:
    print('')  # no message
    sys.exit(0)
sum = d.get('summary', {})
lines = []
lines.append(':newspaper: *OVERNIGHT CATALYSTS* — ' + str(sum.get('mine_count', 0)) + ' affecting your tickers')
for c in cats[:10]:
    mag = c.get('magnitude', 'low').upper()
    cat = c.get('category', '?')
    sent_raw = c.get('sentiment', '')
    sent_icon = ':chart_with_upwards_trend:' if 'pos' in sent_raw or 'bull' in sent_raw else ':chart_with_downwards_trend:' if 'neg' in sent_raw or 'bear' in sent_raw else ':grey_question:'
    mag_icon = ':rotating_light:' if mag == 'HIGH' else ':warning:' if mag == 'MEDIUM' else ':bulb:'
    head = (c.get('headline') or '')[:100]
    lines.append(f\"{mag_icon} *{c.get('ticker')}* [{cat}] {sent_icon} {head}\")
print('\\n'.join(lines))
")

if [ -z "$SLACK_MSG" ]; then
  echo "○ no portfolio/watchlist catalysts to push"
  exit 0
fi

# Send to Slack
curl -s -X POST -H 'Content-Type: application/json' \
  -d "$(python3 -c "import json,sys; print(json.dumps({'text': '''$(echo "$SLACK_MSG" | sed "s/'/\\\\'/g")'''}))")" \
  "$SLACK_URL" > /dev/null

echo "✓ pushed $(echo "$SLACK_MSG" | wc -l | tr -d ' ') line(s) to Slack"
