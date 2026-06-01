#!/bin/bash
# nightly_full_enrich.sh — full-universe deep enrichment, off-hours.
#
# The daily 06:00/11:00 scans deep-enrich only the top ~1000 ranked tickers (fast, for
# trading decisions). This batch runs ONCE overnight, ALONE, to deep-enrich the ENTIRE
# ranked universe (~3000) so EVERY ticker's detail panel is pre-populated (served via
# /api/ticker + Supabase) by morning — instead of filling lazily on click.
#
# Why this avoids the EODHD per-minute limit: it runs at ~02:30 PT (after the EDGAR batch
# at 02:00, before enrich-nightly), when no other EODHD job competes for the per-process
# 950/min budget. ~3000 x ~6 EODHD calls ~= 18K, well under the 95K/day quota, and the
# rate limiter throttles (sleeps) rather than erroring — so it just takes ~20-30 min paced.
#
# MAX_ENRICHMENT_OVERRIDE is read by swing_trade.py run_daily_scan to lift the enrichment
# cap for THIS run only (the daily scans leave it unset → config default 1000).
set -uo pipefail
ROOT="/Volumes/MyMacDisk/Claude Skills/SwingTrade"
cd "$ROOT" || exit 1
LOG="$ROOT/cache/logs/nightly_full_enrich.log"
mkdir -p "$ROOT/cache/logs"

# launchd jobs inherit a low file-descriptor soft limit (~256). The full-universe
# enrich (3500 tickers) opens far more concurrent sockets/files than the daily
# top-1000 scan and exhausts it → "OSError: [Errno 24] Too many open files"
# (crashed 2026-06-01). Raise the soft limit (hard limit is unlimited on this host).
ulimit -n 10240 2>/dev/null || ulimit -Sn 10240 2>/dev/null || true

echo "==== nightly full-universe enrich — $(date) (fd limit $(ulimit -n)) ====" >> "$LOG"

# Deep-enrich the whole ranked universe this run (overrides config max_enrichment_tickers).
export MAX_ENRICHMENT_OVERRIDE=3500
# Heavy mode (full deep-enrich path), not the light intraday path.
export SCAN_MODE=""

/usr/bin/python3 "$ROOT/swing_trade.py" >> "$LOG" 2>&1
rc=$?
echo "[$(date)] nightly full enrich exit=$rc" >> "$LOG"
exit $rc
