#!/bin/bash
# walk_forward_isolated.sh — run the walk-forward ALONE, then rebuild the audit
# backtest baseline. The 2026-06-21 failure was EODHD rate-limit CONTENTION (3
# concurrent backtests). This guards against that: it ABORTS if any other backtest
# is already running, so it can never be the colliding party.
#
# On success it rebuilds cache/backtest_baseline.json (the audit's backtest column)
# and posts a Slack summary. Scheduled mid-week (clear of the Fri/Sat backtest jobs)
# via com.swingtrade.wf-isolated; also runnable on demand.
set -uo pipefail
cd "/Volumes/MyMacDisk/Claude Skills/SwingTrade"

LOG_DIR="cache/logs"; mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/wf_isolated_$(date +%Y%m%d_%H%M).log"
SLACK=$(grep '^SLACK_WEBHOOK_URL' .env 2>/dev/null | cut -d= -f2-)
slack() { [ -n "$SLACK" ] && curl -s -X POST "$SLACK" -H 'Content-Type: application/json' -d "{\"text\":\"$1\"}" >/dev/null 2>&1; }

{
  echo "=== isolated walk-forward · $(date) ==="

  # ── Concurrency guard: never collide with another backtest (the 06-21 lesson) ──
  if pgrep -f "walk_forward_v2|backtest.py --portfolio" >/dev/null 2>&1; then
    echo "ABORT: another backtest/walk-forward is already running — skipping to avoid EODHD contention."
    slack ":warning: isolated walk-forward SKIPPED — another backtest was already running (contention guard)."
    exit 0
  fi
  # Weekend EODHD throttle is real; warn but proceed (data is mostly cached).
  dow=$(date +%u)  # 6=Sat 7=Sun
  [ "$dow" -ge 6 ] && echo "NOTE: weekend run — EODHD is throttled; relying on warm cache."

  echo "--- running walk_forward_v2 (4 folds, parallel) ---"
  t0=$(date +%s)
  if /usr/bin/python3 backtest/walk_forward_v2.py --folds 4 --train-days 250 --test-days 50 --parallel; then
    wf_rc=0
  else
    wf_rc=$?
  fi
  elapsed=$(( ($(date +%s) - t0) / 60 ))
  echo "--- walk-forward exit=$wf_rc · ${elapsed}m ---"

  echo "--- rebuilding audit backtest baseline ---"
  if /usr/bin/python3 scripts/build_backtest_baseline.py; then
    summary=$(/usr/bin/python3 -c "import json;d=json.load(open('cache/backtest_baseline.json'));print(', '.join(f\"{k} PF {v['pf']}\" for k,v in sorted(d.items(),key=lambda x:-(x[1]['n'] or 0))[:5]))" 2>/dev/null)
    slack ":white_check_mark: isolated walk-forward done (${elapsed}m). Baseline rebuilt → /api/audit. Top: ${summary}"
  else
    slack ":rotating_light: isolated walk-forward finished (${elapsed}m) but baseline rebuild FAILED — check $LOG"
  fi
  echo "=== done $(date) ==="
} >"$LOG" 2>&1

exit 0
