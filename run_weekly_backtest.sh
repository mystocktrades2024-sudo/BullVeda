#!/usr/bin/env bash
# AI-22: Weekly auto-regen backtest
# Invoked by launchd: ~/Library/LaunchAgents/com.swingtrade.weekly-backtest.plist
# Runs Saturday 2am PT — market closed, no contention with scheduled scans.

set -euo pipefail

SCRIPT_DIR="/Volumes/MyMacDisk/Claude Skills/SwingTrade"
PYTHON="/Applications/Xcode.app/Contents/Developer/Library/Frameworks/Python3.framework/Versions/3.9/bin/python3"
LOG_DIR="$SCRIPT_DIR/cache/logs"
LOG_FILE="$LOG_DIR/backtest_$(date +%Y-%m-%d).log"

mkdir -p "$LOG_DIR"

echo "======================================" >> "$LOG_FILE"
echo "Weekly Backtest — $(date)" >> "$LOG_FILE"
echo "======================================" >> "$LOG_FILE"

cd "$SCRIPT_DIR"
"$PYTHON" backtest.py --portfolio --days 252 --hold 7 --min-score 55 \
    --min-rs 65 --top-n 5 --equity 5000 --positions 5 --size-pct 0.25 \
    >> "$LOG_FILE" 2>&1
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "Backtest OK — updating _meta.last_backtested" >> "$LOG_FILE"
    # Update config._meta.last_backtested via in-place Python edit
    "$PYTHON" - << 'PYEOF' >> "$LOG_FILE" 2>&1 || true
import json
from datetime import date
from pathlib import Path
p = Path("config/config.json")
cfg = json.loads(p.read_text())
meta = cfg.setdefault("_meta", {})
meta["last_backtested"] = date.today().isoformat()
meta["last_modified"] = date.today().isoformat()
p.write_text(json.dumps(cfg, indent=2))
print(f"  Updated _meta.last_backtested → {date.today().isoformat()}")
PYEOF
    # Optional Slack ping
    "$PYTHON" - << 'PYEOF' 2>/dev/null || true
import sys, os, json
sys.path.insert(0, "/Volumes/MyMacDisk/Claude Skills/SwingTrade")
try:
    from secrets_loader import get_secret
    url = get_secret("SLACK_WEBHOOK_URL", default="")
    if url:
        import urllib.request
        msg = {"text": "✓ SwingTrade weekly backtest completed — check cache/logs/"}
        urllib.request.urlopen(urllib.request.Request(
            url, data=json.dumps(msg).encode(),
            headers={"Content-Type": "application/json"}), timeout=8)
except Exception:
    pass
PYEOF
else
    echo "Backtest FAILED (exit $EXIT_CODE)" >> "$LOG_FILE"
    osascript -e 'display notification "Check cache/logs/" with title "SwingTrade weekly backtest FAILED"' 2>/dev/null || true
fi

# Keep only last 12 weekly backtest logs
ls -t "$LOG_DIR"/backtest_*.log 2>/dev/null | tail -n +13 | xargs rm -f 2>/dev/null || true
echo "Done — $(date)" >> "$LOG_FILE"
