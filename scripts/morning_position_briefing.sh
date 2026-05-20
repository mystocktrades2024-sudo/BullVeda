#!/bin/bash
# morning_position_briefing.sh — daily 8am PT (after morning newsletter at 7:45am).
# Hits /api/positions/active-watch and posts EXPLICIT action items to Slack for
# every open portfolio position. Closes the post-BUY gap: after the system fires
# a BUY signal and you take the trade + add to portfolio, this is the daily
# "should I still hold X?" check.

set -u
cd "$(dirname "$0")/.."

if [ -f .env ]; then
  USER=$(grep '^DASHBOARD_USER=' .env | cut -d= -f2)
  PASS=$(grep '^DASHBOARD_PASS=' .env | cut -d= -f2)
  SLACK_URL=$(grep '^SLACK_WEBHOOK_URL=' .env | cut -d= -f2)
fi
USER="${USER:-gari}"
PASS="${PASS:-Swing2026}"
PORT="${PORT:-7432}"
LOG=/tmp/morning-position-briefing.log
DATE=$(date +%Y-%m-%d)

echo "==== position briefing $DATE ====" >> "$LOG"

if [ -z "${SLACK_URL:-}" ]; then
  echo "○ no SLACK_WEBHOOK_URL — skipping push" >> "$LOG"
  exit 0
fi

RESP=$(curl -s --max-time 15 -u "$USER:$PASS" "http://localhost:$PORT/api/positions/active-watch")
if [ -z "$RESP" ] || [[ "$RESP" == *"curl:"* ]]; then
  echo "⚠ server unreachable on port $PORT — skipping" >> "$LOG"
  exit 0
fi

SLACK_MSG=$(echo "$RESP" | python3 -c "
import json, sys
d = json.load(sys.stdin)
positions = d.get('positions', [])
if not positions:
    print('')
    sys.exit(0)
summary = d.get('summary', {})
lines = [':briefcase: *MORNING POSITION BRIEFING · ' + str(len(positions)) + ' open*']
critical = summary.get('exit_stop', 0) + summary.get('target2_hit', 0)
warn = summary.get('approaching_stop', 0) + summary.get('approaching_t1', 0) + summary.get('trail_active', 0)
if critical: lines.append(f':rotating_light: *{critical} CRITICAL action(s) required*')
elif warn: lines.append(f':warning: *{warn} attention item(s)*')
else: lines.append(':white_check_mark: All positions healthy — hold.')
lines.append('')
emoji_map = {
    'EXIT_STOP':       ':rotating_light:',
    'TARGET2_HIT':     ':moneybag:',
    'TRAIL_ACTIVE':    ':chart_with_upwards_trend:',
    'APPROACHING_T1':  ':dart:',
    'APPROACHING_STOP':':warning:',
    'HOLD':            ':white_check_mark:',
    'NO_PRICE':        ':grey_question:',
}
for p in positions:
    e = emoji_map.get(p['verdict'], '·')
    pnl = f\"{p['pnl_pct']:+.2f}%\" if p['pnl_pct'] else '—'
    lines.append(f\"{e} *{p['ticker']}* {p['verdict']} · {p['shares']}sh @ \${p['entry']:.2f} → \${p['current']:.2f} ({pnl})\")
    lines.append(f\"     {p['action']}\")
print('\n'.join(lines))
")

# ── System status block (rolling Sharpe kill + ML A/B) ───────────────────
SYS_STATUS=$(python3 - <<'PYEOF'
import json, sys, math, os
from pathlib import Path
from datetime import datetime

BASE = Path(os.getcwd()).resolve()  # script cd'd to project root at top

lines = []

# 1. Rolling Sharpe Kill status
state_path = BASE / "cache" / "sharpe_kill_state.json"
try:
    cfg = json.loads((BASE / "config" / "config.json").read_text())
    rsk_cfg = cfg.get("rolling_sharpe_kill", {})
    if state_path.exists():
        state = json.loads(state_path.read_text())
    else:
        sys.path.insert(0, str(BASE))
        import decision_engine as de
        state = de.compute_rolling_sharpe_kill_state(cfg)
    active = state.get("active", False)
    n = state.get("n", 0)
    sharpe = state.get("sharpe")
    threshold = state.get("threshold", -0.5)
    min_n = rsk_cfg.get("min_sample_n", 10)
    sharpe_str = f"{sharpe:+.3f}" if sharpe is not None else "n/a"
    if active:
        lines.append(f":red_circle: *Rolling Sharpe Kill ACTIVE* — BUYs paused (Sharpe={sharpe_str}, n={n})")
    elif n < min_n:
        lines.append(f":white_circle: Rolling Sharpe Kill: ACCUMULATING ({n}/{min_n} closed BUYs needed)")
    else:
        lines.append(f":green_circle: Rolling Sharpe Kill: CLEAR (Sharpe={sharpe_str}, n={n})")
except Exception as e:
    lines.append(f":grey_question: Rolling Sharpe Kill: unavailable ({e})")

# 2. ML A/B significance status
pairs_path = BASE / "cache" / "ml_ab_pairs.jsonl"
try:
    rows = [json.loads(l) for l in pairs_path.read_text().splitlines() if l.strip()] if pairs_path.exists() else []
    closed = [r for r in rows if r.get("realized_pct") is not None]
    n_total = len(rows)
    n_closed = len(closed)
    MIN_PRELIM = 30  # principle 1 floor for preliminary verdict
    if n_closed < MIN_PRELIM:
        lines.append(f":hourglass: ML A/B: ACCUMULATING ({n_closed}/{MIN_PRELIM} closed pairs for significance test)")
    else:
        # Bucket A: all closed; Bucket B: ML agrees (p_up>0.40)
        a_pnl = [r["realized_pct"] for r in closed]
        b_pnl = [r["realized_pct"] for r in closed if (r.get("ml_p_up") or 0) > 0.40]
        def sharpe_r(pnls):
            if not pnls: return None
            mu = sum(pnls) / len(pnls)
            var = sum((x - mu) ** 2 for x in pnls) / max(len(pnls) - 1, 1)
            sd = math.sqrt(var) if var > 0 else 0
            return mu / sd * math.sqrt(252) if sd > 0 else None
        sa = sharpe_r(a_pnl)
        sb = sharpe_r(b_pnl)
        sa_str = f"{sa:+.2f}" if sa is not None else "n/a"
        sb_str = f"{sb:+.2f}" if sb is not None else "n/a"
        verdict = ""
        if sb is not None and sa is not None:
            if sb > sa + 0.2:
                verdict = " :white_check_mark: ML adds Sharpe lift"
            elif sb < sa - 0.2:
                verdict = " :x: ML hurts — consider disabling filter"
            else:
                verdict = " :scales: No significant difference yet"
        lines.append(f":bar_chart: ML A/B: n_A={len(a_pnl)} Sharpe={sa_str} · n_B={len(b_pnl)} Sharpe={sb_str}{verdict}")
except Exception as e:
    lines.append(f":grey_question: ML A/B: unavailable ({e})")

print("\n".join(lines))
PYEOF
)

if [ -z "$SLACK_MSG" ] && [ -z "$SYS_STATUS" ]; then
  echo "○ no open positions, no system alerts — quiet pass" >> "$LOG"
  exit 0
fi

# Compose final message
if [ -n "$SLACK_MSG" ] && [ -n "$SYS_STATUS" ]; then
  FULL_MSG="${SLACK_MSG}

---
${SYS_STATUS}"
elif [ -n "$SLACK_MSG" ]; then
  FULL_MSG="$SLACK_MSG"
else
  # Only system status (no open positions) — still post it
  FULL_MSG=":briefcase: *MORNING SYSTEM STATUS* · no open positions

${SYS_STATUS}"
fi

PAYLOAD=$(python3 -c "import json,sys; print(json.dumps({'text': sys.argv[1]}))" "$FULL_MSG")
RESULT=$(curl -s -X POST -H "Content-Type: application/json" -d "$PAYLOAD" "$SLACK_URL")
echo "Slack: $RESULT" >> "$LOG"
echo "$FULL_MSG" >> "$LOG"
echo "==== done $DATE ====" >> "$LOG"
