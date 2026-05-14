#!/bin/bash
# weekly_diagnostics.sh — runs every Sunday evening via launchd
# (com.swingtrade.weekly-diagnostics.plist)
#
# Refreshes the 3 weekly diagnostic snapshots and (if SLACK_WEBHOOK_URL
# is configured) sends a regression alert when:
#   - aggregate Sharpe drops > 0.10 vs prior week
#   - rolling-20-BUY Sharpe falls below -0.5 (kill threshold)
#
# All outputs land in cache/ as dated JSON for trend analysis.

set -e
cd "/Volumes/MyMacDisk/Claude Skills/SwingTrade"
DATE=$(date +%Y-%m-%d)
LOG=/tmp/weekly-diagnostics.log
echo "==== weekly diagnostics $DATE ====" >> "$LOG"

# 1. Refresh signal_log backfill (alpha_vs_spy / exit_reason / regime4)
python3 -c "
import logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
import signal_tracker
n = signal_tracker.update_outcomes()
print(f'signal_tracker: {n} updates')
" 2>&1 | grep -v "supabase\|httpx\|httpcore\|hpack\|h2\|HTTP\|h11\|failover\|delisted" >> "$LOG"

# 2. Run regime_sharpe_decomp — snapshot per-regime stats
python3 scripts/regime_sharpe_decomp.py 2>&1 | tail -50 >> "$LOG"

# 3. Run loss_streak_investigation — snapshot recent-20 BUY pattern
python3 scripts/loss_streak_investigation.py 2>&1 | tail -50 >> "$LOG"

# 4. Refresh sharpe_screen
python3 scripts/sharpe_screener.py 2>&1 | tail -10 >> "$LOG"
python3 scripts/sharpe_screener_html.py 2>&1 | tail -3 >> "$LOG"

# 5. Per-stock Sharpe by regime (item #3)
python3 scripts/sharpe_per_regime.py 2>&1 | tail -30 >> "$LOG"

# 6. Per-setup Sharpe trend (edge-erosion radar, item #4)
python3 scripts/sharpe_setup_trend.py 2>&1 | tail -40 >> "$LOG"

# 7. Portfolio Sharpe KPI vs target + per-trade attribution (items #6, #11)
python3 scripts/sharpe_kpi.py 2>&1 | tail -40 >> "$LOG"

# 8. Sharpe alerts (Slack push for watchlist threshold crossings, item #10)
python3 scripts/sharpe_alert.py 2>&1 | tail -10 >> "$LOG"

# 9. Compare to prior week — alert if Sharpe regressed
python3 scripts/_weekly_diag_compare.py 2>&1 >> "$LOG"

echo "==== done $DATE ====" >> "$LOG"
