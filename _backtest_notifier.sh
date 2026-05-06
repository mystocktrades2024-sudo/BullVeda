#!/bin/bash
# Watches cache/walk_forward/*.log files for growth; notifies Slack on stall or completion.
set -e
cd "/Volumes/MyMacDisk/Claude Skills/SwingTrade"

PID=${1:-6334}
STALL_THRESHOLD=600  # seconds of no log growth before alerting

post_slack() {
  python3 -c "
from secrets_loader import get_secret
import urllib.request, json
url = get_secret('SLACK_WEBHOOK_URL', default='')
if url:
    data = json.dumps({'text': '''$1'''}).encode()
    req = urllib.request.Request(url, data=data, headers={'Content-Type':'application/json'})
    try: urllib.request.urlopen(req, timeout=10)
    except: pass
"
}

post_slack ":mag: *Backtest monitor v2 active* (log-file mtime watching, not CPU)\nPID $PID · stall threshold ${STALL_THRESHOLD}s"

last_sizes=""
while kill -0 "$PID" 2>/dev/null; do
  sleep 900  # 15-min heartbeat
  sizes=""
  progress=""
  for fold in 1yr_trailing 2yr_trailing 3yr_trailing; do
    if [ -f "cache/walk_forward/${fold}.log" ]; then
      sz=$(wc -l < "cache/walk_forward/${fold}.log" 2>/dev/null || echo 0)
      last_line=$(tail -1 "cache/walk_forward/${fold}.log" 2>/dev/null | head -c 120)
      sizes="${sizes}${fold}=${sz}l "
      progress="${progress}• ${fold}: ${last_line}\n"
    fi
  done
  if [ "$sizes" != "$last_sizes" ]; then
    post_slack ":chart_with_upwards_trend: *Progress*\n${progress}"
    last_sizes="$sizes"
  else
    post_slack ":warning: *No log growth in last 15min* — check for stall\nPID $PID\n${progress}"
  fi
done

# Process done
FINAL=$(tail -60 cache/backtest_run.log | head -c 3000)
SUMMARY_FILE=cache/walk_forward/summary.json
if [ -f "$SUMMARY_FILE" ]; then
  AGG=$(python3 -c "
import json
s = json.load(open('$SUMMARY_FILE'))
a = s.get('aggregated') or {}
r = s.get('results', [])
lines = [f\"WR mean={a.get('wr_mean','?')}% | PF mean={a.get('pf_mean','?')} | Return mean={a.get('return_mean','?')}%\"]
for fold in r:
    lines.append(f\"{fold.get('tag')}: WR={fold.get('win_rate','?')}% PF={fold.get('profit_factor','?')} Return={fold.get('total_return_pct','?')}% N={fold.get('total_trades','?')}\")
print('\\n'.join(lines))
")
else
  AGG="(summary file not found)"
fi
post_slack ":white_check_mark: *Backtest complete* (PID $PID)\n\`\`\`${AGG}\`\`\`"
echo "BACKTEST_DONE" > cache/_backtest_done.flag
