#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  Desk signal logger + forward-outcome resolver — daily.
#  Runs scripts/desk_signal_log.py which:
#    - LOGS today's desk BUY/SHORT calls to data/desk_signal_log.jsonl
#      (the desks' OWN verdicts — self-sustained, not the old scanner)
#    - RESOLVES matured entries (≥5 trading days) from cached OHLCV
#      parquets (ZERO EODHD): stop/target/5d-close → R-multiple
#    - AGGREGATES a LIVE per-desk track record → cache/desk_track_record.json
# ─────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="/Volumes/MyMacDisk/Claude Skills/SwingTrade"
PYTHON="/Applications/Xcode.app/Contents/Developer/Library/Frameworks/Python3.framework/Versions/3.9/bin/python3"
LOG_DIR="$SCRIPT_DIR/cache/logs"
LOG_FILE="$LOG_DIR/desk_signal_log.log"

mkdir -p "$LOG_DIR"
cd "$SCRIPT_DIR"
echo "=== $(date) ===" >> "$LOG_FILE"
"$PYTHON" scripts/desk_signal_log.py >> "$LOG_FILE" 2>&1
