#!/bin/bash
# eod_snapshots.sh — single end-of-day snapshot runner.
# (com.swingtrade.eod-snapshots.plist · Mon-Fri 4:35pm PT)
#
# Consolidates 6 formerly-separate launchd jobs (16:15-16:55) into one
# sequential runner to reduce launchd churn. WHAT each step computes is
# unchanged — only the scheduling collapsed.
#
# Order matches the old stagger: sharpe-monitor first, then the 5 snapshots.
# Each step is error-isolated — a failure in one does NOT stop the others.
# All output lands in cache/logs/eod_snapshots.log for trend analysis.

cd "/Volumes/MyMacDisk/Claude Skills/SwingTrade"
DATE=$(date +%Y-%m-%d)
LOG_DIR="cache/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/eod_snapshots.log"
echo "==== eod snapshots $DATE ====" >> "$LOG"

# 1. Rolling Sharpe monitor (kill/alert state) — was com.swingtrade.sharpe-monitor (16:15)
python3 scripts/rolling_sharpe_monitor.py >> "$LOG" 2>&1 \
  || echo "[eod_snapshots] sharpe-monitor failed" | tee -a "$LOG"

# 2. Rolling Sharpe snapshot — was com.swingtrade.snapshot-sharpe (16:35)
python3 scripts/snapshot_rolling_sharpe.py --apply >> "$LOG" 2>&1 \
  || echo "[eod_snapshots] snapshot-sharpe failed" | tee -a "$LOG"

# 3. Portfolio risk snapshot — was com.swingtrade.snapshot-risk (16:40)
python3 scripts/snapshot_portfolio_risk.py --apply >> "$LOG" 2>&1 \
  || echo "[eod_snapshots] snapshot-risk failed" | tee -a "$LOG"

# 4. Strategy attribution snapshot — was com.swingtrade.snapshot-attribution (16:45)
python3 scripts/snapshot_strategy_attribution.py --apply >> "$LOG" 2>&1 \
  || echo "[eod_snapshots] snapshot-attribution failed" | tee -a "$LOG"

# 5. Wilson CI snapshot — was com.swingtrade.snapshot-wilson (16:50)
python3 scripts/snapshot_wilson_ci.py --apply >> "$LOG" 2>&1 \
  || echo "[eod_snapshots] snapshot-wilson failed" | tee -a "$LOG"

# 6. VaR breaches snapshot — was com.swingtrade.snapshot-var (16:55)
python3 scripts/snapshot_var_breaches.py --apply >> "$LOG" 2>&1 \
  || echo "[eod_snapshots] snapshot-var failed" | tee -a "$LOG"

echo "==== done $DATE ====" >> "$LOG"
