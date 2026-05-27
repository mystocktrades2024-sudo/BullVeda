#!/bin/bash
# guard_heavy_job.sh — concurrency + load guard for CPU-heavy launchd jobs.
#
# Source this BEFORE running anything heavy (walk-forward, ml-edge, weekly-backtest,
# enrich-nightly). Aborts the caller (exit 0 — clean skip) when:
#   1. system load avg > MAX_LOAD threshold
#   2. another CPU-heavy job is already running
#   3. a daily swing scan (swing_trade.py) is in progress
#
# Outage 2026-05-27 (12:11 PT) traced to walk-forward + 11:00 scan competing
# for cores → load avg 70 → server.py starved → tunnel 524s. This guard
# prevents recurrence.
#
# Usage:
#   source "/path/to/guard_heavy_job.sh"      # or
#   bash guard_heavy_job.sh "<job-label>" || exit 0
#
# Override MAX_LOAD via env: MAX_LOAD=12 ./script.sh

MAX_LOAD="${MAX_LOAD:-8}"     # 1-min load avg ceiling; M-series Macs have 8-16 cores
JOB_LABEL="${1:-unknown-heavy-job}"
ROOT="/Volumes/MyMacDisk/Claude Skills/SwingTrade"
LOG="$ROOT/cache/logs/heavy_job_guard.log"
mkdir -p "$(dirname "$LOG")"
TS=$(date "+%Y-%m-%d %H:%M:%S %Z")

# Helper: log + exit cleanly (0, not failure — launchd shouldn't restart us)
_skip() {
  echo "[$TS] SKIP $JOB_LABEL — $1" >> "$LOG"
  exit 0
}

# 1) Load-avg check (BSD `uptime` outputs e.g. "load averages: 1.23 1.45 1.67")
load_1m=$(uptime | awk -F'load averages?:' '{print $2}' | awk '{gsub(",","",$1); print $1}')
load_1m_int=${load_1m%.*}    # integer part only
if [ -n "$load_1m_int" ] && [ "$load_1m_int" -gt "$MAX_LOAD" ]; then
  _skip "load avg $load_1m > MAX_LOAD=$MAX_LOAD (machine busy)"
fi

# 2) Is a swing scan running?
if pgrep -f "python.*swing_trade\.py" > /dev/null 2>&1; then
  _skip "swing_trade.py is running (daily scan in progress)"
fi
if pgrep -f "python.*-m ml\.train_historical" > /dev/null 2>&1; then
  _skip "ml.train_historical is running (scan's ML retrain in progress)"
fi
if pgrep -f "python.*ml\.historical_backfill" > /dev/null 2>&1; then
  _skip "ml.historical_backfill is running"
fi

# 3) Is another heavy job already running? Check by process pattern.
# NOTE: don't match ourselves — exclude $$ and our parent shell.
HEAVY_PATTERNS=(
  "backtest/walk_forward_v2\.py"
  "scripts/run_walk_forward_overnight\.sh"
  "python.*backtest\.py.*--portfolio"
  "python.*ml\.run_ml_edge"
  "scripts/run_weekly_backtest\.sh"
  "scripts/enrich_nightly\.py"
)
for pat in "${HEAVY_PATTERNS[@]}"; do
  # Strip our own PID + parent to avoid self-match
  match_pids=$(pgrep -f "$pat" 2>/dev/null | grep -v "^$$\$" | grep -v "^$PPID\$" || true)
  if [ -n "$match_pids" ]; then
    _skip "another heavy job is running: $pat (PIDs: $(echo $match_pids | tr '\n' ' '))"
  fi
done

# All checks passed — log start and continue
echo "[$TS] PROCEED $JOB_LABEL — load=$load_1m, no concurrent heavy jobs" >> "$LOG"
