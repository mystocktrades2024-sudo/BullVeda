#!/bin/bash
# OPS-2 (2026-05-10): SwingTrade FastAPI uptime monitor.
# Pings localhost:7432/api/health-ping. Slack alert on 2 consecutive fails.
# Recovery message when health restored. State at /tmp/swingtrade-uptime.state.

set -e

REPO="/Volumes/MyMacDisk/Claude Skills/SwingTrade"
STATE_FILE="/tmp/swingtrade-uptime.state"
LOG_FILE="${HOME}/.swingtrade/uptime.jsonl"
PING_URL="http://localhost:7432/api/health-ping"
TIMEOUT=10

mkdir -p "$(dirname "$LOG_FILE")"

ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Read previous state (default: ok=true, fails=0)
if [ -f "$STATE_FILE" ]; then
    prev_status=$(cat "$STATE_FILE" | head -1)
    prev_fails=$(cat "$STATE_FILE" | sed -n '2p')
else
    prev_status="ok"
    prev_fails=0
fi

# Ping with curl
http_code=$(curl --max-time "$TIMEOUT" -s -o /dev/null -w "%{http_code}" "$PING_URL" 2>/dev/null || echo "000")

if [ "$http_code" = "200" ]; then
    cur_status="ok"
    cur_fails=0
else
    cur_status="fail"
    cur_fails=$((prev_fails + 1))
fi

# Write state
echo "$cur_status" > "$STATE_FILE"
echo "$cur_fails" >> "$STATE_FILE"

# Append to JSONL log (newest events appended)
echo "{\"ts\":\"$ts\",\"http_code\":\"$http_code\",\"status\":\"$cur_status\",\"consecutive_fails\":$cur_fails}" >> "$LOG_FILE"

# Slack alert logic — fire only on transitions, not every check
SLACK_URL=$(grep -E "^SLACK_WEBHOOK_URL=" "$REPO/.env" 2>/dev/null | head -1 | cut -d= -f2-)

send_slack() {
    if [ -n "$SLACK_URL" ]; then
        curl --max-time 5 -s -X POST -H "Content-Type: application/json" \
            -d "{\"text\":\"$1\"}" "$SLACK_URL" >/dev/null 2>&1 || true
    fi
}

# Going-down alert: fired exactly when consecutive_fails hits 2
if [ "$cur_fails" -eq 2 ] && [ "$prev_status" != "fail" -o "$prev_fails" -lt 2 ]; then
    send_slack "🔴 SwingTrade uptime FAIL — 2 consecutive fails on $PING_URL (HTTP $http_code at $ts). Investigate server.py PID."
    echo "$ts ALERT-DOWN sent"
fi

# Recovery alert: was failing (fails >= 2), now ok
if [ "$cur_status" = "ok" ] && [ "$prev_fails" -ge 2 ]; then
    send_slack "🟢 SwingTrade uptime RECOVERED — health-ping back to 200 at $ts (was down for $prev_fails consecutive checks)."
    echo "$ts ALERT-UP sent"
fi

echo "$ts $cur_status http=$http_code fails=$cur_fails"
