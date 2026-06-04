#!/usr/bin/env bash
# weekly_full_enrich.sh — WEEKLY full heavy EODHD refresh, Saturday evening.
#
# Once per week, markets closed, full quota, no contention: deep-enrich the WHOLE
# universe — fundamentals + options/UOA/gamma + news + every per-ticker endpoint —
# so the next week's data is comprehensively warm. Replaces the old Saturday 03:00
# fundamentals-only warm (enrich-fundamentals-weekly, retired 2026-06-03).
#
# MAX_ENRICHMENT_OVERRIDE lifts the total-enrich cap; DEEP_ENRICHMENT_OVERRIDE lifts
# the deep (options/UOA/gamma/news) tier so it covers the whole universe, not top-N.
# SCAN_MODE="" = heavy path. Caffeinated so a closed-lid Saturday doesn't sleep mid-run.
#
# Cost: ~10-20K EODHD (one-time/week, Saturday evening) + Schwab options (off-budget,
# paced ~100/min). Runtime ~1-2h. Quota: Saturday daily scans spend ~8K by evening,
# +full refresh → ~25K total, well under the 95K cap.
set -uo pipefail
ROOT="/Volumes/MyMacDisk/Claude Skills/SwingTrade"
PY="/Applications/Xcode.app/Contents/Developer/Library/Frameworks/Python3.framework/Versions/3.9/bin/python3"
LOG="$ROOT/cache/logs/weekly_full_enrich.log"
mkdir -p "$ROOT/cache/logs"
cd "$ROOT" || exit 1

echo "==================================================" >> "$LOG"
echo "WEEKLY full enrich (Saturday evening) — $(date)" >> "$LOG"

# launchd inherits a ~256 fd limit; the full-universe deep enrich opens far more
# sockets/files than that and exhausts it mid-run — the symptom is getaddrinfo
# failures ("nodename nor servname" / "Too many open files") even though the
# network is fine. Match run_daily_scan.sh: raise to 200000, well under this
# host's kernel cap (kern.maxfilesperproc = 245760). Cascade down if rejected.
ulimit -n 200000 2>/dev/null || ulimit -n 65536 2>/dev/null || ulimit -n 10240 2>/dev/null || ulimit -Sn 10240 2>/dev/null || true

# Clear an orphaned scan lock if no live scan holds it.
if [ -f /tmp/swing_trade_scan.lock ] && ! pgrep -f "swing_trade.py" >/dev/null 2>&1; then
  rm -f /tmp/swing_trade_scan.lock
  echo "[weekly-full] cleared orphaned lock" >> "$LOG"
fi

# Whole-universe deep enrich (heavy path). 3500 covers the full liquid universe.
export MAX_ENRICHMENT_OVERRIDE=3500
export DEEP_ENRICHMENT_OVERRIDE=3500
export SCAN_MODE=""

echo "[weekly-full] launching full heavy enrich (caffeinated) …" >> "$LOG"
caffeinate -i "$PY" swing_trade.py >> "$LOG" 2>&1
SCAN_RC=$?
echo "[weekly-full] scan exit=$SCAN_RC — $(date)" >> "$LOG"
caffeinate -i "$PY" infra/prototype/build_data.py >> "$LOG" 2>&1
echo "[weekly-full] build_data done — $(date)" >> "$LOG"

# ── Self-report to Slack (the "Saturday check") — survives a closed laptop /
# absent Claude session, so the result lands automatically. Reads this run's
# EODHD cost + tier split + picks straight from the log. ──
"$PY" - "$LOG" "$SCAN_RC" <<'PYEOF' >> "$LOG" 2>&1 || true
import sys, re, json, urllib.request
from pathlib import Path
log_path, scan_rc = sys.argv[1], sys.argv[2]
ROOT = Path("/Volumes/MyMacDisk/Claude Skills/SwingTrade")
# pull the LAST run's lines from the log (after the last separator)
txt = Path(log_path).read_text(errors="ignore").split("=========")[-1]
def grab(pat, d="—"):
    m = re.findall(pat, txt)
    return m[-1] if m else d
calls   = grab(r"EODHD calls this scan: ([\d,]+ network[^\n]*)")
budget  = grab(r"EODHD budget: ([\d,]+/[\d,]+ \([\d]+%\))")
tier    = grab(r"(tier1=\d+[^\n]*tier2=\d+[^\n]*)")
elite   = grab(r"Elite picks: (\[[^\]]*\])")
skipped = "SKIPPING scan" in txt
status  = "🔴 SKIPPED (quota maxed)" if skipped else ("✅ completed" if scan_rc == "0" else f"⚠️ exit {scan_rc}")
msg = (f"🛡️ *Weekly Saturday full deep-enrich* — {status}\n"
       f"EODHD: {calls}\nBudget: {budget}\nTier split: {tier}\nElite: {elite}")
# load webhook from .env
wh = None
for line in (ROOT/".env").read_text().splitlines():
    if line.startswith("SLACK_WEBHOOK_URL=") and "=" in line:
        wh = line.split("=",1)[1].strip().strip('"').strip("'")
if wh:
    req = urllib.request.Request(wh, data=json.dumps({"text": msg}).encode(),
                                 headers={"Content-Type":"application/json"})
    try:
        urllib.request.urlopen(req, timeout=8); print("[weekly-full] Slack summary posted")
    except Exception as e:
        print(f"[weekly-full] Slack post failed: {e}")
else:
    print("[weekly-full] no SLACK_WEBHOOK in .env")
PYEOF
