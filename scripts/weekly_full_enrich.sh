#!/usr/bin/env bash
# weekly_full_enrich.sh — WEEKLY full heavy EODHD refresh, Saturday evening.
#
# Once per week, markets closed, full quota, no contention: deep-enrich the WHOLE
# universe — fundamentals + options/UOA/gamma + news + every per-ticker endpoint —
# so the next week's data is comprehensively warm. Replaces the old Saturday 03:00
# fundamentals-only warm (enrich-fundamentals-weekly, retired 2026-06-03).
#
# MAX_ENRICHMENT_OVERRIDE lifts the total-enrich cap; DEEP_ENRICHMENT_OVERRIDE lifts
# the deep (options/UOA/gamma/news) tier so it covers the whole universe, not top-N.
# SCAN_MODE="" = heavy path. Caffeinated so a closed-lid Saturday doesn't sleep mid-run.
#
# Cost: ~10-20K EODHD (one-time/week, Saturday evening) + Schwab options (off-budget,
# paced ~100/min). Runtime ~1-2h. Quota: Saturday daily scans spend ~8K by evening,
# +full refresh → ~25K total, well under the 95K cap.
set -uo pipefail
ROOT="/Volumes/MyMacDisk/Claude Skills/SwingTrade"
PY="/Applications/Xcode.app/Contents/Developer/Library/Frameworks/Python3.framework/Versions/3.9/bin/python3"
LOG="$ROOT/cache/logs/weekly_full_enrich.log"
mkdir -p "$ROOT/cache/logs"
cd "$ROOT" || exit 1

echo "==================================================" >> "$LOG"
echo "WEEKLY full enrich (Saturday evening) — $(date)" >> "$LOG"

# launchd inherits a low fd limit; the full-universe deep enrich opens many sockets.
ulimit -n 10240 2>/dev/null || ulimit -Sn 10240 2>/dev/null || true

# Clear an orphaned scan lock if no live scan holds it.
if [ -f /tmp/swing_trade_scan.lock ] && ! pgrep -f "swing_trade.py" >/dev/null 2>&1; then
  rm -f /tmp/swing_trade_scan.lock
  echo "[weekly-full] cleared orphaned lock" >> "$LOG"
fi

# Whole-universe deep enrich (heavy path). 3500 covers the full liquid universe.
export MAX_ENRICHMENT_OVERRIDE=3500
export DEEP_ENRICHMENT_OVERRIDE=3500
export SCAN_MODE=""

echo "[weekly-full] launching full heavy enrich (caffeinated) …" >> "$LOG"
caffeinate -i "$PY" swing_trade.py >> "$LOG" 2>&1
echo "[weekly-full] scan exit=$? — $(date)" >> "$LOG"
caffeinate -i "$PY" infra/prototype/build_data.py >> "$LOG" 2>&1
echo "[weekly-full] build_data done — $(date)" >> "$LOG"
