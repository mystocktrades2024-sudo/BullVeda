#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  SwingTrade — Daily Scan Runner
#  Invoked by macOS LaunchAgent: com.swingtrade.daily.plist
#  Runs 5×/day PT (2026-06-03): 05:15 HEAVY (pre-market full enrich),
#  07:00 / 09:30 / 11:30 / 13:30 LIGHT (after-open · 2× session · after-close).
#  SCAN_MODE chosen by clock below: <06:15 = heavy, else = light.
# ─────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="/Volumes/MyMacDisk/Claude Skills/SwingTrade"
PYTHON="/Applications/Xcode.app/Contents/Developer/Library/Frameworks/Python3.framework/Versions/3.9/bin/python3"
LOG_DIR="$SCRIPT_DIR/cache/logs"
LOG_FILE="$LOG_DIR/scan_$(date +%Y-%m-%d).log"
# Ensure log directory exists
mkdir -p "$LOG_DIR"

# Raise the file-descriptor soft limit (2026-06-04). launchd jobs inherit ~256 fds;
# the HEAVY morning scan deep-enriches 1,500 tickers with 16 concurrent workers, which
# opens far more sockets/files than that and exhausts the limit mid-enrichment. The
# symptom is getaddrinfo failures — "[Errno 8] nodename nor servname provided" / "Too
# many open files" — even though the network is fine (the process just can't open new
# sockets). This also starves build_audit_ledger.py (runs below) so it can't fetch
# forward-return horizons and writes a None-filled ledger (the 2026-06-03 15:01 wipe).
# The nightly full-enrich already does this; the daily scan was missing it.
# Raise to 200000 — well under this host's kernel per-process cap (kern.maxfilesperproc
# = 245760). Cascade down if a host rejects it. Far more headroom than any scan needs;
# eliminates fd exhaustion as a failure mode entirely.
ulimit -n 200000 2>/dev/null || ulimit -n 65536 2>/dev/null || ulimit -n 10240 2>/dev/null || ulimit -Sn 10240 2>/dev/null || true

echo "======================================" >> "$LOG_FILE"
echo "[fd limit: $(ulimit -n)]" >> "$LOG_FILE"
echo "SwingTrade Daily Scan — $(date)" >> "$LOG_FILE"
echo "======================================" >> "$LOG_FILE"

# Run the scan, capturing all output. Don't `set -e` exit on scan failure —
# we want to log and notify, not crash the wrapper.
cd "$SCRIPT_DIR"
# 2026-05-28: heavy-once / light-often. The 06:00 scan does the full deep-enrich
# (warms the 7-day fundamentals cache). The intraday scans run SCAN_MODE=light —
# re-rank ALL tickers from warm cache + OHLCV, shrink the expensive-endpoint tier.
# Keeps the full ~2,000-ticker universe ranked 6×/day without blowing the quota.
_HHMM=$((10#$(date +%H%M)))
if [ "$_HHMM" -lt 615 ]; then
    export SCAN_MODE=""        # heavy: the 06:00 morning scan
    echo "[$(date)] SCAN_MODE=heavy (full deep-enrich)" >> "$LOG_FILE"
else
    export SCAN_MODE="light"   # intraday: re-rank all, light deep-enrich
    echo "[$(date)] SCAN_MODE=light (intraday re-rank)" >> "$LOG_FILE"
fi
set +e
"$PYTHON" swing_trade.py >> "$LOG_FILE" 2>&1
EXIT_CODE=$?
set -e

if [ $EXIT_CODE -eq 0 ]; then
    echo "Scan completed successfully — V2 at http://localhost:7432/kairos.html" >> "$LOG_FILE"
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

    # ── Fetch corporate events (IPOs + splits next 30d) ───────────────────
    # Writes cache/corporate_events.json which build_data.py reads and embeds
    # in the bundle as data.corporate_events. Powers the IPO·Splits tab.
    # Cheap (~2 EODHD calls). Morning-scan only — calendar doesn't shift intraday.
    if [ "$HOUR" -lt 7 ]; then
        echo "── Fetch corporate events (IPOs + splits) ──" >> "$LOG_FILE"
        set +e
        "$PYTHON" scripts/fetch_corporate_events.py 30 >> "$LOG_FILE" 2>&1
        set -e

        # ── Build universe extras (recent IPOs + post-earnings movers) ─────
        # Fills the structural gap of names that IPO'd after the Russell
        # reconstitution + catches PEAD candidates not in any index.
        # Reads cache/corporate_events.json (just refreshed above) + the
        # local earnings_outcomes log. Writes cache/universe_extras.json
        # which the next scan_orchestrator() reads via _load_universe_extras().
        # 2-3 EODHD calls per IPO candidate (~100-300 calls total · ~2min).
        # Morning-scan only — universe doesn't shift intraday.
        echo "── Build universe extras (recent IPOs + PEAD movers) ──" >> "$LOG_FILE"
        set +e
        "$PYTHON" scripts/build_universe_extras.py >> "$LOG_FILE" 2>&1
        set -e

        # ── Build thematic universe (ETF holdings + crypto + screener) ─────
        # 22 sector/thematic ETFs × ~50 holdings each + hardcoded crypto
        # equity list + EODHD screener API momentum filter. Writes
        # cache/universe_thematic.json. ~25 EODHD calls (cheap, ~20s).
        # Morning-scan only — screener output is daily-stable enough.
        echo "── Build thematic universe (ETF holdings + crypto + screener) ──" >> "$LOG_FILE"
        set +e
        "$PYTHON" scripts/build_universe_thematic.py >> "$LOG_FILE" 2>&1
        set -e
    fi

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
    # ML inference runs only 4x/day (2026-06-03 · user) — pre-market / 2x session /
    # post-market — NOT every 30-min scan. Predictions are stable enough intraday;
    # 4 anchors keep them fresh without 16x compute. Anchors: <06:15 (pre/heavy),
    # 09:30, 11:30, 13:30 (post-close). ml_edge_predictions.json persists between.
    ML_EXIT=0
    if [ "$_HHMM" -lt 615 ] || [ "$_HHMM" -eq 930 ] || [ "$_HHMM" -eq 1130 ] || [ "$_HHMM" -eq 1330 ]; then
        "$PYTHON" -m ml.run_ml_edge >> "$LOG_FILE" 2>&1
        ML_EXIT=$?
    else
        echo "ML inference skipped — not a 4x anchor (pre/09:30/11:30/13:30)" >> "$LOG_FILE"
    fi
    # Build setup_stats.json — Wilson CI per (setup × regime) for Technicals §6/§8
    "$PYTHON" scripts/build_setup_stats.py >> "$LOG_FILE" 2>&1 || \
        echo "⚠ build_setup_stats failed (Technicals tab will show stale per-setup stats)" >> "$LOG_FILE"
    set -e
    if [ $ML_EXIT -ne 0 ]; then
        echo "⚠ ml.run_ml_edge exited $ML_EXIT (ML Edge sub-tab will show stale predictions)" >> "$LOG_FILE"
    fi

    # ── SMC / Patterns scan (server-side smc_engine confluence) ──────────────
    # Morning-scan only — SMC is computed from DAILY bars (daily-stable); intraday
    # only price-vs-zone moves (handled by the live layer). Reuses cached bars →
    # 0 EODHD. Writes cache/smc_scan.json → read by the Slack digest + dashboard.
    if [ "$HOUR" -lt 7 ]; then
        echo "── SMC / Patterns scan ──" >> "$LOG_FILE"
        set +e
        "$PYTHON" scripts/build_smc_scan.py >> "$LOG_FILE" 2>&1 || \
            echo "⚠ build_smc_scan failed (SMC Slack section will be empty)" >> "$LOG_FILE"
        # Dedicated SMC-only Slack ping (morning, after the fresh SMC scan)
        "$PYTHON" scripts/slack_smc_ping.py >> "$LOG_FILE" 2>&1 || \
            echo "⚠ slack_smc_ping failed" >> "$LOG_FILE"
        set -e
    fi

    # ── ML A/B framework: pair every rules signal with ML prediction + backfill outcomes ──
    # Captures cache/ml_ab_pairs.jsonl — used by /api/diagnostics/ml-ab to test
    # whether ML filtering of rules signals adds Sharpe lift. Idempotent per (ticker, date).
    echo "── ML A/B capture ──" >> "$LOG_FILE"
    set +e
    "$PYTHON" scripts/ml_ab_capture.py >> "$LOG_FILE" 2>&1
    set -e

    # ── Rolling Sharpe Kill transition alert ──────────────────────────────
    # Fires a Slack message when the gate transitions blocked↔clear. Writes
    # state to cache/sharpe_kill_state.json for transition detection.
    echo "── Rolling Sharpe Kill alert check ──" >> "$LOG_FILE"
    set +e
    "$PYTHON" scripts/sharpe_kill_alert.py >> "$LOG_FILE" 2>&1
    set -e

    # ── Post-scan top-picks Slack digest (Swing · Options · Momentum · ML Edge) ──
    # Sends one unified Slack message with top 5 per source after every scan.
    # Idempotent — same scan window won't re-post identical picks (hash check).
    SCAN_TAG=$(date +"%H:%M")
    echo "── Post-scan Slack digest [$SCAN_TAG] ──" >> "$LOG_FILE"
    set +e
    "$PYTHON" scripts/post_scan_slack_alert.py --scan-tag "$SCAN_TAG" >> "$LOG_FILE" 2>&1
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
