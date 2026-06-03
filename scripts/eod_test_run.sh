#!/usr/bin/env bash
# One-time EOD test scan — fires 17:03 PT, just after EODHD quota resets (00:00 UTC).
# Tests the new permanent routing: fresh quota + warm enrichment cache → the scan
# should land cheap (~1.5-3K EODHD net). SELF-REMOVES after running so it's one-shot.
set -uo pipefail
ROOT="/Volumes/MyMacDisk/Claude Skills/SwingTrade"
PY="/Applications/Xcode.app/Contents/Developer/Library/Frameworks/Python3.framework/Versions/3.9/bin/python3"
LOG="$ROOT/cache/logs/eod_test_5pm.log"
mkdir -p "$ROOT/cache/logs"
cd "$ROOT" || exit 1

echo "==================================================" >> "$LOG"
echo "EOD test scan (5pm backstop) — $(date)" >> "$LOG"

# Clear an orphaned scan lock if no live scan process holds it.
if [ -f /tmp/swing_trade_scan.lock ] && ! pgrep -f "swing_trade.py" >/dev/null 2>&1; then
  rm -f /tmp/swing_trade_scan.lock
  echo "[eod-test] cleared orphaned /tmp/swing_trade_scan.lock" >> "$LOG"
fi

# ONE scan (heavy default; warm cache → cheap). Then rebuild the v2 dashboard.
echo "[eod-test] launching swing_trade.py …" >> "$LOG"
"$PY" swing_trade.py >> "$LOG" 2>&1
echo "[eod-test] scan exit=$? — $(date)" >> "$LOG"
"$PY" infra/prototype/build_data.py >> "$LOG" 2>&1
echo "[eod-test] build_data done — $(date)" >> "$LOG"

# SELF-REMOVE — guarantees one-shot (won't fire again tomorrow).
launchctl remove com.swingtrade.eod-test-5pm 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/com.swingtrade.eod-test-5pm.plist" 2>/dev/null || true
echo "[eod-test] self-removed launchd job — done" >> "$LOG"
