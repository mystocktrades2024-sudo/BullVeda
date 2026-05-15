#!/bin/bash
# paper_execute_after_scan.sh — submit paper orders for today's BUYs to Alpaca.
#
# Runs Mon-Fri 9:35am PT (5 min after market open) so today's scan output is
# fresh AND market is open for limit order acceptance.
#
# Safety:
#   1. Calls executor.py --submit (paper-only — alpaca_paper=true required)
#   2. Daily cap (4 trades/day) enforced inside executor.py
#   3. Rolling Sharpe kill state respected by upstream scan
#   4. Posts every order to Slack via lib/autorun_reporter
#
# Triggered by:
#   ~/Library/LaunchAgents/com.swingtrade.paper-execute.plist

set -e
cd "/Volumes/MyMacDisk/Claude Skills/SwingTrade"

LOG=/tmp/swingtrade-paper-execute.log
DATE=$(date '+%Y-%m-%d %H:%M:%S PT')
echo "==== paper-execute $DATE ====" >> "$LOG"

# 1. Verify paper trading still active
python3 executor.py --status >> "$LOG" 2>&1

# 2. Run execution (submit real paper orders)
python3 executor.py --submit >> "$LOG" 2>&1
EXIT_CODE=$?

# 3. Slack status on completion (autorun_reporter handles per-order notifs;
#    this is the wrapper-level summary)
python3 -c "
from lib.autorun_reporter import report
import subprocess
result = subprocess.run(['python3', 'executor.py', '--status'], capture_output=True, text=True)
status_text = result.stdout[:300]
if $EXIT_CODE == 0:
    report('paper-execute', 'success',
           summary=f'Paper execution sweep complete (after market open)',
           details={'status_snapshot': status_text[:200]})
else:
    report('paper-execute', 'failed',
           summary=f'Paper execution sweep failed with exit {$EXIT_CODE}',
           details={'status_snapshot': status_text[:200]})
" >> "$LOG" 2>&1 || true

echo "==== done $DATE (exit=$EXIT_CODE) ====" >> "$LOG"
exit $EXIT_CODE
