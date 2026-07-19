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
echo "=== $(date) $* ===" >> "$LOG_FILE"
# Pass-through args: no args = full (log + resolve + aggregate) for the 14:20 run;
# "--resolve" = grade + aggregate only (skip logging) for the morning grading run.
"$PYTHON" scripts/desk_signal_log.py "$@" >> "$LOG_FILE" 2>&1

# 2026-07-06: rebuild the Track-Record ledger right after logging so every desk
# pick reaches Track Record the same run (data_leaders.json is what the Track
# Record UI reads). Previously build ran on a separate schedule → desk picks
# logged at 14:20 didn't surface until the next morning's build. Guarantees
# "whatever comes in the desk lands in Track Record."
"$PYTHON" infra/prototype/build_leaders.py >> "$LOG_FILE" 2>&1 || echo "build_leaders failed (non-fatal)" >> "$LOG_FILE"
