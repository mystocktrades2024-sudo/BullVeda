#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  SwingTrade — Daily Scan Runner
#  Invoked by macOS LaunchAgent: com.swingtrade.daily.plist
#  Runs 4×/day: 06:00, 10:00, 13:00, 13:30 PT (trimmed from 17/day on 2026-05-11)
# ─────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="/Volumes/MyMacDisk/Claude Skills/SwingTrade"
PYTHON="/Applications/Xcode.app/Contents/Developer/Library/Frameworks/Python3.framework/Versions/3.9/bin/python3"
LOG_DIR="$SCRIPT_DIR/cache/logs"
LOG_FILE="$LOG_DIR/scan_$(date +%Y-%m-%d).log"
# Ensure log directory exists
mkdir -p "$LOG_DIR"

echo "======================================" >> "$LOG_FILE"
echo "SwingTrade Daily Scan — $(date)" >> "$LOG_FILE"
echo "======================================" >> "$LOG_FILE"

# Run the scan, capturing all output. Don't `set -e` exit on scan failure —
# we want to log and notify, not crash the wrapper.
cd "$SCRIPT_DIR"
set +e
"$PYTHON" swing_trade.py >> "$LOG_FILE" 2>&1
EXIT_CODE=$?
set -e

if [ $EXIT_CODE -eq 0 ]; then
    echo "Scan completed successfully — V2 at http://localhost:7432/v2/dashboard.html" >> "$LOG_FILE"
    # V2 dashboard: post-Phase-A (2026-05-08), legacy cache/dashboard.html is
    # no longer generated. Don't auto-open browser on every cron run — would
    # steal focus 14× per day. User opens V2 URL manually when needed.

    # ── Pre-compute structural-target cache (Project 2 · M2.1) ──────────
    # Runs ONLY on the 06:00 morning scan (the slowest scan of the day · adds
    # ~5-10 min). Other intra-day scans (10:00/13:00/13:30) skip this — the
    # 12h TTL cache stays valid through the trading day.
    HOUR=$(date +%H)
    if [ "$HOUR" -lt 7 ]; then
        echo "── Pre-compute target_engine cache (SP500 + R1000 + watchlist) ──" >> "$LOG_FILE"
        set +e
        "$PYTHON" scripts/precompute_targets.py >> "$LOG_FILE" 2>&1
        PRECOMP_EXIT=$?
        set -e
        if [ $PRECOMP_EXIT -ne 0 ]; then
            echo "⚠ precompute_targets exited $PRECOMP_EXIT (continuing — endpoint will fall back to on-demand)" >> "$LOG_FILE"
        fi
    else
        echo "Skipping precompute_targets — already done at 06:00 (12h cache still valid)" >> "$LOG_FILE"
    fi
else
    echo "Scan FAILED with exit code $EXIT_CODE." >> "$LOG_FILE"
    # Show a macOS notification on failure
    osascript -e 'display notification "Check '"$LOG_FILE"'" with title "SwingTrade scan failed"' 2>/dev/null || true
fi

# Keep only the last 30 log files
ls -t "$LOG_DIR"/scan_*.log 2>/dev/null | tail -n +31 | xargs rm -f 2>/dev/null || true

echo "Done — $(date)" >> "$LOG_FILE"
