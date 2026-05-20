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

    # ── Backfill earnings prediction outcomes ────────────────────────────
    # Joins prediction_log → outcomes on (ticker, report_date) and writes
    # realized_outcome + realized_surprise_pct. Idempotent, <1s.
    echo "── Backfill earnings outcomes ──" >> "$LOG_FILE"
    set +e
    "$PYTHON" scripts/backfill_earnings_outcomes.py >> "$LOG_FILE" 2>&1
    set -e

    # ── Run ML Edge inference (3-headed forecast: dir/mag/hit-net) ──────
    # Cheap (~3s for 449 tickers). Writes cache/ml_edge_predictions.json +
    # infra/prototype/ml_edge_predictions.json. Re-training runs only on the
    # morning scan since closed-trade labels accumulate slowly.
    echo "── Run ML Edge inference ──" >> "$LOG_FILE"
    set +e
    # Morning scan: refresh historical backfill + retrain all 9 models.
    # Other intra-day scans: just re-run inference (uses prior models + cache).
    if [ "$HOUR" -lt 7 ]; then
        echo "Morning scan: refreshing historical_backfill.json (EODHD bulk EOD)" >> "$LOG_FILE"
        "$PYTHON" -m ml.historical_backfill >> "$LOG_FILE" 2>&1 || echo "⚠ ml.historical_backfill failed (using prior backfill)" >> "$LOG_FILE"
        echo "Morning scan: retraining all 9 ML Edge models (swing/position/invest × dir/mag/hit)" >> "$LOG_FILE"
        "$PYTHON" -m ml.train_historical >> "$LOG_FILE" 2>&1 || echo "⚠ ml.train_historical failed (using prior model artifacts)" >> "$LOG_FILE"
    fi
    "$PYTHON" -m ml.run_ml_edge >> "$LOG_FILE" 2>&1
    ML_EXIT=$?
    # Build setup_stats.json — Wilson CI per (setup × regime) for Technicals §6/§8
    "$PYTHON" scripts/build_setup_stats.py >> "$LOG_FILE" 2>&1 || \
        echo "⚠ build_setup_stats failed (Technicals tab will show stale per-setup stats)" >> "$LOG_FILE"
    set -e
    if [ $ML_EXIT -ne 0 ]; then
        echo "⚠ ml.run_ml_edge exited $ML_EXIT (ML Edge sub-tab will show stale predictions)" >> "$LOG_FILE"
    fi

    # ── ML A/B framework: pair every rules signal with ML prediction + backfill outcomes ──
    # Captures cache/ml_ab_pairs.jsonl — used by /api/diagnostics/ml-ab to test
    # whether ML filtering of rules signals adds Sharpe lift. Idempotent per (ticker, date).
    echo "── ML A/B capture ──" >> "$LOG_FILE"
    set +e
    "$PYTHON" scripts/ml_ab_capture.py >> "$LOG_FILE" 2>&1
    set -e

    # ── Rebuild audit ledger (per-signal D1-D5/W1-W5/M1-M6 grid) ─────────
    # Runs EVERY scan so new signals get appended and prior days' D-cells
    # populate as time passes. Builder is idempotent and incremental — it
    # reuses cached horizon data, so re-running on each scan is cheap.
    # Without this, audit_ledger.json froze in time (last write 2026-05-11).
    echo "── Rebuild audit_ledger.json ──" >> "$LOG_FILE"
    set +e
    "$PYTHON" infra/prototype/build_audit_ledger.py >> "$LOG_FILE" 2>&1
    LEDGER_EXIT=$?
    set -e
    if [ $LEDGER_EXIT -ne 0 ]; then
        echo "⚠ build_audit_ledger exited $LEDGER_EXIT (audit tab will show stale ledger until next run)" >> "$LOG_FILE"
    fi

    # ── Regenerate strategy report (backtest + regime + MAE/MFE HTML) ────────
    # Morning-scan only — data doesn't change intra-day. Serves at /reports/strategy.
    if [ "$HOUR" -lt 7 ]; then
        echo "── Regenerate strategy_report.html ──" >> "$LOG_FILE"
        set +e
        "$PYTHON" scripts/generate_strategy_report.py >> "$LOG_FILE" 2>&1
        set -e
    fi
else
    echo "Scan FAILED with exit code $EXIT_CODE." >> "$LOG_FILE"
    # Show a macOS notification on failure
    osascript -e 'display notification "Check '"$LOG_FILE"'" with title "SwingTrade scan failed"' 2>/dev/null || true
fi

# Keep only the last 30 log files
ls -t "$LOG_DIR"/scan_*.log 2>/dev/null | tail -n +31 | xargs rm -f 2>/dev/null || true

echo "Done — $(date)" >> "$LOG_FILE"
