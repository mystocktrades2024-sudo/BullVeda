#!/bin/zsh
# Cloudflare tunnel healthcheck — pings trade.mystockholding.com every 5 min.
# Alerts Slack on failure, with debouncing so we don't spam during outages.
#
# Expected healthy responses: 200 (logged in), 401 (Basic auth challenge — origin reachable).
# Failure responses: 530 (origin down), 1033 (tunnel not registered), 502/503/504 (gateway), 0 (timeout).

set -u
DOMAIN="https://trade.mystockholding.com/"
STATE_FILE="/tmp/tunnel-healthcheck.state"
LOG_FILE="/tmp/tunnel-healthcheck.log"
ALERT_COOLDOWN_SECONDS=3600   # don't re-alert more than once per hour
DEBOUNCE_FAILURES=2           # require N consecutive failures before alerting

SLACK_WEBHOOK=$(grep '^SLACK_WEBHOOK_URL' "/Volumes/MyMacDisk/Claude Skills/SwingTrade/.env" 2>/dev/null | cut -d= -f2-)

now=$(date +%s)
ts=$(date "+%Y-%m-%d %H:%M:%S %Z")

# Probe the domain — short timeout, just need the status code.
code=$(curl -sS -o /dev/null -w "%{http_code}" --max-time 8 "$DOMAIN" 2>/dev/null || echo "000")

# 200 or 401 = origin reachable. Anything else = problem.
if [[ "$code" == "200" || "$code" == "401" ]]; then
  echo "$ts  OK  ($code)" >> "$LOG_FILE"
  # Reset failure count on success; if we were in alert state, send recovery message.
  if [[ -f "$STATE_FILE" ]]; then
    last_state=$(grep '^state=' "$STATE_FILE" 2>/dev/null | cut -d= -f2)
    if [[ "$last_state" == "alerted" && -n "$SLACK_WEBHOOK" ]]; then
      curl -s -X POST "$SLACK_WEBHOOK" -H "Content-Type: application/json" \
        -d "{\"text\":\"✅ trade.mystockholding.com recovered — HTTP $code at $ts\"}" >> "$LOG_FILE" 2>&1
    fi
  fi
  printf 'state=ok\nfailures=0\nlast_alert=0\n' > "$STATE_FILE"
  exit 0
fi

# Failure path
echo "$ts  FAIL  ($code)" >> "$LOG_FILE"

# ── Self-heal: force-restart the origin server BEFORE alerting. KeepAlive only
#    restarts a DEAD process; this also catches a HUNG server (alive but not
#    answering → 530/timeout/gateway). No sudo — com.swingtrade.server is a user
#    LaunchAgent. Skipped for 1033 (pure cloudflared/tunnel issue — KeepAlive on the
#    system daemon handles a crash; a hang there needs sudo, see docs/tunnel-recovery.md).
case "$code" in
  530|000|502|503|504)
    if launchctl kickstart -k "gui/$(id -u)/com.swingtrade.server" 2>>"$LOG_FILE"; then
      echo "$ts  RECOVER  kickstarted com.swingtrade.server (was $code)" >> "$LOG_FILE"
    fi ;;
esac

# Read prior state
failures=0
last_alert=0
if [[ -f "$STATE_FILE" ]]; then
  failures=$(grep '^failures=' "$STATE_FILE" 2>/dev/null | cut -d= -f2 || echo 0)
  last_alert=$(grep '^last_alert=' "$STATE_FILE" 2>/dev/null | cut -d= -f2 || echo 0)
  failures=${failures:-0}
  last_alert=${last_alert:-0}
fi
failures=$((failures + 1))

# Decide whether to alert
should_alert=0
if (( failures >= DEBOUNCE_FAILURES )); then
  if (( now - last_alert >= ALERT_COOLDOWN_SECONDS )); then
    should_alert=1
  fi
fi

if (( should_alert == 1 )) && [[ -n "$SLACK_WEBHOOK" ]]; then
  case "$code" in
    1033) reason="Cloudflare tunnel not registered (cloudflared daemon down or misconfigured)" ;;
    530)  reason="Origin error (FastAPI server on :7432 not reachable from cloudflared)" ;;
    502|503|504) reason="Cloudflare gateway error" ;;
    000)  reason="Request timed out / network unreachable" ;;
    *)    reason="Unexpected status code" ;;
  esac
  curl -s -X POST "$SLACK_WEBHOOK" -H "Content-Type: application/json" \
    -d "{\"text\":\":rotating_light: trade.mystockholding.com STILL DOWN after auto-heal — HTTP $code\\n${reason}\\nFailed ${failures}× in a row at $ts\\nThe watchdog already force-restarted the server and it did NOT recover — needs a human. Recovery: docs/tunnel-recovery.md (cloudflared restart needs sudo).\"}" \
    >> "$LOG_FILE" 2>&1
  printf 'state=alerted\nfailures=%d\nlast_alert=%d\n' "$failures" "$now" > "$STATE_FILE"
else
  state="failing"
  (( failures >= DEBOUNCE_FAILURES )) && state="alerted"
  printf 'state=%s\nfailures=%d\nlast_alert=%d\n' "$state" "$failures" "$last_alert" > "$STATE_FILE"
fi

exit 1
