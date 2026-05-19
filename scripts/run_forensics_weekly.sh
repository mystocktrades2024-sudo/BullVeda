#!/bin/bash
# run_forensics_weekly.sh — hits /api/diagnostics/forensics and pushes the top
# recommendations to Slack. Called from weekly_diagnostics.sh (Sunday 5pm PT).
#
# The recommendations are NOT auto-applied. They are surfaced for human review
# via Slack + persisted in /tmp/forensics-weekly.log for trend tracking.
# To apply, hit /api/diagnostics/apply-tune from the kairos.html BUY Pipeline tab
# or run a one-liner curl POST per recommendation.

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
LOG=/tmp/forensics-weekly.log
DATE=$(date +%Y-%m-%d)

echo "==== forensics weekly $DATE ====" >> "$LOG"

if [ -z "${SLACK_URL:-}" ]; then
  echo "○ no SLACK_WEBHOOK_URL — skipping push" >> "$LOG"
  exit 0
fi

# Pull forensics (90d window)
RESP=$(curl -s --max-time 30 -u "$USER:$PASS" "http://localhost:$PORT/api/diagnostics/forensics?days=90")

if [ -z "$RESP" ] || [[ "$RESP" == *"curl:"* ]]; then
  echo "⚠ forensics: server unreachable on port $PORT — skipping" >> "$LOG"
  exit 0
fi

# Persist raw output for trend tracking
echo "$RESP" > "cache/forensics_weekly_${DATE}.json"

# Format Slack message
SLACK_MSG=$(echo "$RESP" | python3 -c "
import json, sys
d = json.load(sys.stdin)
if d.get('error'):
    print('SKIP: ' + d['error'])
    sys.exit(0)
recs = d.get('recommendations', [])
sum = d.get('summary', {})
td = d.get('time_decay', [])
if not recs and (sum.get('mean', 0) >= 0):
    # No issues — quiet pass
    print('OK')
    sys.exit(0)
lines = [':bar_chart: *WEEKLY FORENSICS · ' + str(d.get('lookback_days')) + 'd*']
lines.append(f'BUYs analyzed: *{sum.get(\"n\")}* · WR *{sum.get(\"wr\")}%* · PF *{sum.get(\"pf\")}* · mean *{sum.get(\"mean\",0):+.2f}%* · sum *{sum.get(\"sum\",0):+.1f}pp*')
if td:
    decay_strs = [f'{t[\"month\"]}={t[\"mean\"]:+.1f}%' for t in td[-3:]]
    lines.append('Time decay: ' + ' → '.join(decay_strs))
if recs:
    lines.append('')
    lines.append(f'*{len(recs)} actionable recommendation(s)* — addressable lift *+{d.get(\"total_lift_pp\",0)}pp*')
    for r in recs[:8]:
        lift = r.get('historical_lift_pp', 0)
        emoji = ':x:' if r.get('action') == 'KILL' else ':warning:' if r.get('action') == 'REDUCE' else ':arrow_up:' if r.get('action') == 'RAISE' else ':wrench:'
        wlb = f' · wlb {r[\"wilson_lb\"]}%' if r.get('wilson_lb') is not None else ''
        lines.append(f'{emoji} *{r[\"action\"]}* {r[\"target\"]} → \`{r[\"new_value\"]}\` · +{lift}pp · n={r[\"n\"]}{wlb}')
        lines.append(f'     _{r[\"reason\"]}_')
lines.append('')
lines.append('_Apply via kairos.html → BUY Pipeline → AUTO-TUNE FORENSICS card_')
print('\n'.join(lines))
")

if [ -z "$SLACK_MSG" ] || [ "$SLACK_MSG" = "OK" ]; then
  echo "○ no actionable recommendations — quiet pass" >> "$LOG"
  exit 0
fi
if [[ "$SLACK_MSG" == SKIP:* ]]; then
  echo "$SLACK_MSG" >> "$LOG"
  exit 0
fi

# Post to Slack
PAYLOAD=$(python3 -c "import json,sys; print(json.dumps({'text': sys.argv[1]}))" "$SLACK_MSG")
RESULT=$(curl -s -X POST -H "Content-Type: application/json" -d "$PAYLOAD" "$SLACK_URL")
echo "Slack: $RESULT" >> "$LOG"
echo "$SLACK_MSG" >> "$LOG"
echo "==== done $DATE ====" >> "$LOG"
