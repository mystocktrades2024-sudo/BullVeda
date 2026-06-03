#!/bin/bash
# nightly_full_enrich.sh — top-tier deep enrichment, off-hours, alternate nights.
#
# The daily 06:00/11:00 scans deep-enrich only the top ~1000 ranked tickers (fast, for
# trading decisions). This batch runs overnight, ALONE, to deep-enrich the top ~1200
# ranked names so their detail panels are pre-populated (served via /api/ticker +
# Supabase) by morning. The low-momentum tail (rank >1200) fills lazily on first click.
#
# 2026-06-02 — RIGHT-SIZED. Was MAX_ENRICHMENT_OVERRIDE=3500 (full ~3000 universe),
# the single biggest recurring EODHD consumer (~9K network calls/night ≈ 9% of the
# 100K/day quota). It pre-built ~3000 detail panels nightly but ~2950 were never opened.
# Now: top 1200 only + EVERY OTHER NIGHT. The names you actually trade are enriched by
# the daily scans anyway; fundamentals are quarterly so a 48h-stale tail panel is fine.
# Net saving ≈ 60-70% of this job's cost with near-zero UX impact (first click on a
# rarely-viewed tail name does a ~3-5s live fetch, then caches).
#
# Why this avoids the EODHD per-minute limit: it runs at ~02:30 PT (after the EDGAR batch
# at 02:00, before enrich-nightly), when no other EODHD job competes for the per-process
# 950/min budget. The shared cross-process limiter (eodhd_client) throttles rather than
# erroring, so it just takes ~10-15 min paced.
#
# MAX_ENRICHMENT_OVERRIDE is read by swing_trade.py run_daily_scan to lift the enrichment
# cap for THIS run only (the daily scans leave it unset → config default 1500).
set -uo pipefail
ROOT="/Volumes/MyMacDisk/Claude Skills/SwingTrade"
cd "$ROOT" || exit 1
LOG="$ROOT/cache/logs/nightly_full_enrich.log"
mkdir -p "$ROOT/cache/logs"

# Alternate-night schedule: launchd fires this nightly, but we only DO the work on
# even day-of-year — every other night. Fundamentals barely move overnight, so the
# tail detail panels staying ~48h fresh is an easy trade for halving the call cost.
# (10# forces base-10 so a leading-zero day like 008 isn't parsed as octal.)
_doy=$(( 10#$(date +%j) ))
if [ $(( _doy % 2 )) -ne 0 ]; then
  echo "[$(date)] skipped — alternate-night schedule (day-of-year $_doy is odd)" >> "$LOG"
  exit 0
fi

# launchd jobs inherit a low file-descriptor soft limit (~256). The full-universe
# enrich (3500 tickers) opens far more concurrent sockets/files than the daily
# top-1000 scan and exhausts it → "OSError: [Errno 24] Too many open files"
# (crashed 2026-06-01). Raise the soft limit (hard limit is unlimited on this host).
ulimit -n 10240 2>/dev/null || ulimit -Sn 10240 2>/dev/null || true

echo "==== nightly full-universe enrich — $(date) (fd limit $(ulimit -n)) ====" >> "$LOG"

# Deep-enrich the top ~1200 ranked names this run (overrides config max_enrichment_tickers).
# Right-sized 2026-06-02 from 3500 → 1200 (see header). Covers everything realistically
# viewed; the tail loads lazily on first /api/ticker click.
export MAX_ENRICHMENT_OVERRIDE=1200
# Heavy mode (full deep-enrich path), not the light intraday path.
export SCAN_MODE=""

/usr/bin/python3 "$ROOT/swing_trade.py" >> "$LOG" 2>&1
rc=$?
echo "[$(date)] nightly full enrich exit=$rc" >> "$LOG"
exit $rc
