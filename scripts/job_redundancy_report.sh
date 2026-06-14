#!/usr/bin/env bash
# job_redundancy_report.sh — evidence-based launchd job audit.
# Reads cache/logs/launchd-wrapper.log (the START/END/exit ledger for every
# wrapped job) over the last N days and surfaces:
#   1. run-count per job  (is anything firing far more than its schedule says?)
#   2. chronically-failing jobs (non-zero exit every run = dead weight or bug)
#   3. slowest jobs by duration (CPU/wall-clock hogs)
# Use to find REAL redundancy from data, not guesses. Run before + after a
# 2-day observation window and diff the output.
#
# Usage:  bash scripts/job_redundancy_report.sh [DAYS]   (default 2)
set -u
cd "$(dirname "$0")/.." || exit 1
DAYS="${1:-2}"
LOG="cache/logs/launchd-wrapper.log"
[ -f "$LOG" ] || { echo "no wrapper log at $LOG"; exit 1; }
CUT=$(date -u -v-"${DAYS}"d +%Y-%m-%d 2>/dev/null || date -u -d "${DAYS} days ago" +%Y-%m-%d)

echo "════════════════════════════════════════════════════════════"
echo " JOB REDUNDANCY REPORT — last ${DAYS} days (since ${CUT} UTC)"
echo " NOTE: only covers jobs wrapped by launchd_wrapper.sh."
echo " Directly-invoked python jobs (beatalert/earnings/etc) are NOT here."
echo "════════════════════════════════════════════════════════════"

echo ""
echo "── RUN COUNT per job (START events) ──"
awk -v cut="$CUT" '{ d=substr($1,2,10); if(d>=cut) print }' "$LOG" \
  | grep 'START' \
  | sed -E 's/.*com\.swingtrade\.([a-z0-9-]+):.*/\1/' \
  | sort | uniq -c | sort -rn

echo ""
echo "── CHRONIC FAILURES (non-zero exit) ──"
awk -v cut="$CUT" '{ d=substr($1,2,10); if(d>=cut) print }' "$LOG" \
  | grep -E 'exit=[1-9]' \
  | sed -E 's/.*com\.swingtrade\.([a-z0-9-]+):.*(exit=[0-9]+).*/\1 \2/' \
  | sort | uniq -c | sort -rn
echo "  (a job that ONLY appears here = failing every run → investigate or kill)"

echo ""
echo "── SLOWEST runs (top 12 by duration) ──"
awk -v cut="$CUT" '{ d=substr($1,2,10); if(d>=cut) print }' "$LOG" \
  | grep -oE 'com\.swingtrade\.[a-z0-9-]+:.*duration=[0-9]+s' \
  | sed -E 's/com\.swingtrade\.([a-z0-9-]+):.*duration=([0-9]+)s/\2 \1/' \
  | sort -rn | head -12 | awk '{printf "  %6ss  %s\n", $1, $2}'

echo ""
echo "── EODHD quota today (the real bottleneck) ──"
[ -f cache/eodhd_quota.json ] && python3 -c "
import json
q=json.load(open('cache/eodhd_quota.json'))
print('  ', json.dumps({k:q[k] for k in list(q)[:6]}))" 2>/dev/null || echo "  (no quota file)"
