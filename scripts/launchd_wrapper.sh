#!/bin/bash
# launchd_wrapper.sh — runs a command and logs start/finish/exit/duration to Supabase.
#
# Usage in plist:
#   <key>ProgramArguments</key>
#   <array>
#     <string>/Volumes/MyMacDisk/Claude Skills/SwingTrade/scripts/launchd_wrapper.sh</string>
#     <string>com.swingtrade.morning-briefing</string>
#     <string>python3</string>
#     <string>/path/to/script.py</string>
#     <string>arg1</string>
#   </array>
#
# Adds telemetry without changing the script itself.

LABEL="$1"
shift
# 2026-05-28: keep args as the positional array ("$@") and run them quoted.
# CMD is a display-only string for the log. Previously `CMD="$@"; $CMD` word-split
# on the space in "/Volumes/MyMacDisk/Claude Skills/..." → broke any absolute
# script path (evening-newsletter exit=2). Run "$@" to preserve arguments.
CMD="$*"

ROOT="/Volumes/MyMacDisk/Claude Skills/SwingTrade"
LOG_DIR="$ROOT/cache/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/launchd-wrapper.log"

# 2026-05-27: CPU/concurrency guard for heavy jobs. Jobs in HEAVY_LABELS
# get skipped if load avg > 8 OR a swing scan is running OR another heavy
# job is active. Prevents recurrence of 2026-05-27 12:11 outage (walk-forward
# + scan competing → load 70 → tunnel 524). guard_heavy_job.sh `exit 0`s on
# skip, which propagates here because we `source` it (not `bash`).
HEAVY_LABELS=(
  "com.swingtrade.walk-forward-tonight"
  "com.swingtrade.ml-edge"
  "com.swingtrade.ml-edge-intraday"
  "com.swingtrade.weekly-backtest"
  "com.swingtrade.enrich-nightly"
  "com.swingtrade.precompute-prewarm"
)
for heavy in "${HEAVY_LABELS[@]}"; do
  if [ "$LABEL" = "$heavy" ]; then
    source "$ROOT/scripts/guard_heavy_job.sh" "$LABEL"
    break
  fi
done

START_EPOCH=$(date +%s)
START_ISO=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

echo "[$START_ISO] $LABEL: START · $CMD" >> "$LOG"

# Run the command, capture stdout/stderr + exit code.
# "$@" preserves arguments with spaces (e.g. the project path).
TMPOUT=$(mktemp)
"$@" > "$TMPOUT" 2>&1
EXIT_CODE=$?

END_EPOCH=$(date +%s)
END_ISO=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
DURATION=$((END_EPOCH - START_EPOCH))

# Tail of stdout (last 2000 chars)
STDOUT_TAIL=$(tail -c 2000 "$TMPOUT" 2>/dev/null | tr -d '\000' || echo "")

echo "[$END_ISO] $LABEL: END · exit=$EXIT_CODE · duration=${DURATION}s" >> "$LOG"
cat "$TMPOUT" >> "$LOG"
rm -f "$TMPOUT"

# Best-effort write to Supabase via Python (don't fail the run if this errors)
"$ROOT/scripts/launchd_log_to_supabase.py" \
  --label "$LABEL" \
  --started-at "$START_ISO" \
  --finished-at "$END_ISO" \
  --duration-s "$DURATION" \
  --exit-code "$EXIT_CODE" \
  --stdout-tail "$STDOUT_TAIL" \
  2>> "$LOG" || true

exit $EXIT_CODE
