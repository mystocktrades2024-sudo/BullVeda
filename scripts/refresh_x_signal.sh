#!/usr/bin/env bash
# refresh_x_signal.sh — wrapper for the X-chatter pipeline.
# 1) polls Nitter for tracked handles → cache/x_signal.json
# 2) re-emits infra/prototype/data_x_chatter.json sidecar (cheap, no scan re-run)
# 3) fires post_x_alert.py for any new tracked-handle hits on portfolio / top-100
#
# Wired by infra/launchd/com.swingtrade.x-signal.plist (every 4h).

set -uo pipefail
SCRIPT_DIR="/Volumes/MyMacDisk/Claude Skills/SwingTrade"
PYTHON="${PYTHON:-/usr/bin/python3}"
LOG_DIR="$SCRIPT_DIR/cache/logs"
LOG_FILE="$LOG_DIR/x_signal_$(date +%Y-%m-%d).log"
mkdir -p "$LOG_DIR"

cd "$SCRIPT_DIR"
echo "============================================" >> "$LOG_FILE"
echo "x-signal refresh — $(date)"                    >> "$LOG_FILE"

# 1) poll Nitter for every handle in config/x_handles.json
echo "[1/3] polling tracked handles via Nitter..."   >> "$LOG_FILE"
"$PYTHON" scripts/build_x_signal.py >> "$LOG_FILE" 2>&1
POLL_EXIT=$?
if [ $POLL_EXIT -ne 0 ]; then
    echo "WARN: build_x_signal exited $POLL_EXIT"    >> "$LOG_FILE"
fi

# 2) re-emit the dashboard sidecar (just the slim derived JSON, not a full
#    build_data.py rebuild — that's reserved for the daily scan)
echo "[2/3] re-emitting infra/prototype/data_x_chatter.json..." >> "$LOG_FILE"
"$PYTHON" - >> "$LOG_FILE" 2>&1 <<'PYEOF'
import json
from pathlib import Path
ROOT = Path("/Volumes/MyMacDisk/Claude Skills/SwingTrade")
xs_path = ROOT / "cache" / "x_signal.json"
out = ROOT / "infra" / "prototype" / "data_x_chatter.json"
if not xs_path.exists():
    print("  skipped — cache/x_signal.json missing")
    raise SystemExit(0)
xs = json.loads(xs_path.read_text())
slim = {
    "_meta": xs.get("_meta", {}),
    "config": xs.get("config", {}),
    "top_tickers_24h": xs.get("top_tickers_24h", [])[:20],
    "top_tickers_7d":  xs.get("top_tickers_7d",  [])[:30],
    "by_handle":       xs.get("by_handle", {}),
    "recent_posts":    xs.get("recent_posts", [])[:100],
    "by_ticker": {t["ticker"]: xs.get("by_ticker", {}).get(t["ticker"])
                  for t in (xs.get("top_tickers_7d", [])[:60])
                  if xs.get("by_ticker", {}).get(t["ticker"])},
}
out.write_text(json.dumps(slim, default=str, indent=0, allow_nan=False))
m = slim["_meta"]
print(f"  wrote {out.name} ({out.stat().st_size:,} bytes · {m.get('handles_polled','?')} handles, {m.get('unique_tickers','?')} tickers)")
PYEOF

# 3) Slack alert when a tracked handle mentions a held position or top-100 ticker
echo "[3/3] firing post_x_alert.py for cross-ref hits..." >> "$LOG_FILE"
"$PYTHON" scripts/post_x_alert.py >> "$LOG_FILE" 2>&1 || \
    echo "  (post_x_alert returned non-zero — see log)" >> "$LOG_FILE"

echo "done — $(date)"                                >> "$LOG_FILE"

# Keep only the last 30 days of x_signal logs
ls -t "$LOG_DIR"/x_signal_*.log 2>/dev/null | tail -n +31 | xargs rm -f 2>/dev/null || true
exit 0
