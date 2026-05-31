#!/bin/bash
# ml_accuracy_cron.sh — scheduled ML accuracy snapshot.
# Runs ml_accuracy_report.py, prints to the rolling log, and appends a compact
# timestamped JSON line to cache/ml/accuracy_history.jsonl so the realized-accuracy
# trend accumulates over time (the [3] REALIZED section only matures with live trades).
set -uo pipefail
ROOT="/Volumes/MyMacDisk/Claude Skills/SwingTrade"
cd "$ROOT" || exit 1
mkdir -p "$ROOT/cache/logs" "$ROOT/cache/ml"
LOG="$ROOT/cache/logs/ml_accuracy.log"
echo "==== ml accuracy snapshot — $(date) ====" >> "$LOG"

# Full human-readable report → rolling log
/usr/bin/python3 "$ROOT/scripts/ml_accuracy_report.py" >> "$LOG" 2>&1

# Compact trend line → accuracy_history.jsonl (champion + holdout + realized)
/usr/bin/python3 - <<'PY' >> "$LOG" 2>&1
import json, os, datetime
from pathlib import Path
ML = Path("/Volumes/MyMacDisk/Claude Skills/SwingTrade/cache/ml")
def load(n):
    p = ML / n
    try: return json.loads(p.read_text()) if p.exists() else {}
    except Exception: return {}
cm = load("champion_metrics.json"); cr = load("calibration_report.json"); cl = load("close_loop_report.json")
modes = cm.get("modes", {})
row = {
  "asof": datetime.datetime.now().isoformat(),
  "champion_updated": cm.get("updated_at"),
  "holdout": {m: {"dir_acc": round(v.get("direction_accuracy", 0), 4),
                  "hit_auc": round(v.get("hit_net_auc", 0), 4),
                  "brier": round(v.get("brier", 0), 4)} for m, v in modes.items()},
  "realized_n": cl.get("n") or cl.get("n_labeled"),
  "realized_hit_rate": cl.get("realized_hit_rate"),
}
hist = ML / "accuracy_history.jsonl"
with open(hist, "a") as f:
    f.write(json.dumps(row) + "\n")
print(f"[accuracy-cron] appended trend line · realized_n={row['realized_n']}")
PY
# Weekly Slack digest — Sundays only (day-of-week 7), to avoid daily noise.
# The daily run still logs + appends the trend line above every day.
if [ "$(date +%u)" -eq 7 ]; then
    /usr/bin/python3 "$ROOT/scripts/ml_accuracy_report.py" --slack >> "$LOG" 2>&1
    echo "[$(date)] ml accuracy Slack digest posted (weekly)" >> "$LOG"
fi
echo "[$(date)] ml accuracy snapshot done" >> "$LOG"
