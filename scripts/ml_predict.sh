#!/usr/bin/env bash
# ml_predict.sh — standalone ML Edge predictions, DECOUPLED from the scan.
#
# Runs 3x/24h (com.swingtrade.ml-predict: ~06:45 / 11:15 / 14:00 PT) in its OWN
# process so it can never hold the scan lock or overrun the 30-min cadence (the
# 2026-06-05 incident: ML ran inside the scan and took ~3h, overrunning each scan
# to 4-5h). Inference is capped (--limit, see ML_PREDICT_LIMIT below) so the long
# tail doesn't need surfaced predictions. Morning run also retrains.
#
# 2026-06-09 (Phase 4): cap bumped 500 -> 1380 to cover the hot warm-set
# (top1000 universe ∪ track-record ∪ portfolio). ALSO fixed a silent failure:
# the flag was --max-tickers, which ml.run_ml_edge does NOT accept (its arg is
# --limit). Every prior run exited 2 ("unrecognized arguments: --max-tickers")
# so inference had been producing ZERO predictions. Now uses --limit correctly.
# Override the cap without editing this file via:  ML_PREDICT_LIMIT=NNN
ML_PREDICT_LIMIT="${ML_PREDICT_LIMIT:-1380}"
set -uo pipefail
ROOT="/Volumes/MyMacDisk/Claude Skills/SwingTrade"
PY="/Applications/Xcode.app/Contents/Developer/Library/Frameworks/Python3.framework/Versions/3.9/bin/python3"
LOG="$ROOT/cache/logs/ml_predict.log"
mkdir -p "$ROOT/cache/logs"
cd "$ROOT" || exit 1

# Match the scan's fd headroom (per-ticker feature fetch opens many sockets).
ulimit -n 200000 2>/dev/null || ulimit -n 65536 2>/dev/null || ulimit -Sn 10240 2>/dev/null || true

echo "==================================================" >> "$LOG"
echo "ML predict — $(date)" >> "$LOG"

HOUR=$(date +%H)
# Morning run only: refresh historical backfill + retrain all 9 models.
# Closed-trade labels accrue slowly, so daily retrain is enough.
if [ "$HOUR" -lt 8 ]; then
    echo "[ml-predict] morning: backfill + retrain 9 models" >> "$LOG"
    caffeinate -i "$PY" -m ml.historical_backfill >> "$LOG" 2>&1 || echo "⚠ historical_backfill failed (using prior)" >> "$LOG"
    caffeinate -i "$PY" -m ml.train_historical >> "$LOG" 2>&1 || echo "⚠ train_historical failed (using prior models)" >> "$LOG"
fi

echo "[ml-predict] inference (--limit $ML_PREDICT_LIMIT) over fresh bundle …" >> "$LOG"
caffeinate -i "$PY" -m ml.run_ml_edge --limit "$ML_PREDICT_LIMIT" >> "$LOG" 2>&1
echo "[ml-predict] exit=$? — $(date)" >> "$LOG"
