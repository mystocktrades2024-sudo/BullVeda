#!/bin/bash
# start_server_launchd.sh — launchd-friendly wrapper around server.py.
#
# Exits 0 (success) if port 7432 is ALREADY bound (another process holds it,
# typically start-server.sh in a Terminal). Only spawns the server when the
# port is free. Prevents launchd KeepAlive=true from spamming exit-1 retries
# when the user is already running start-server.sh manually.
#
# Used by: infra/launchd/com.swingtrade.server.plist

PORT="${PORT:-7432}"
ROOT="/Volumes/MyMacDisk/Claude Skills/SwingTrade"
LOG_DIR="$ROOT/cache/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/server-launchd-wrapper.log"
ISO=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# 1. Port already bound? → exit 0
if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | grep -q LISTEN; then
  HOLDER=$(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | awk 'NR==2 {print $1"("$2")"}')
  echo "[$ISO] port $PORT already bound by $HOLDER — exiting 0 (no-op)" >> "$LOG"
  exit 0
fi

# 2. start-server.sh watchdog running? (it'll respawn server.py within 3s) → exit 0
if pgrep -f "start-server\.sh" >/dev/null 2>&1; then
  echo "[$ISO] start-server.sh watchdog is running — yielding · exit 0 (no-op)" >> "$LOG"
  exit 0
fi

# 3. server.py already running directly?
if pgrep -f "python.*server\.py" >/dev/null 2>&1; then
  echo "[$ISO] server.py already running (no watchdog) — exit 0 (no-op)" >> "$LOG"
  exit 0
fi

echo "[$ISO] port $PORT free + no watchdog + no python server — starting server.py" >> "$LOG"
cd "$ROOT" || exit 1
exec /usr/bin/python3 server.py --no-reload
