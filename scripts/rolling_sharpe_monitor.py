#!/usr/bin/env python3
"""rolling_sharpe_monitor.py — daily rolling Sharpe tracker + state-change alerts.

Tracks the rolling Sharpe kill state over time. Posts to Slack ONLY on
state changes (kill activates/clears, sharpe enters/exits edge zone), to
prevent alert fatigue. Always saves history to DB for trend analysis.

State transitions tracked:
  HEALTHY        sharpe > threshold + 0.15
  EDGE_WARNING   threshold < sharpe <= threshold + 0.15
  KILL_ACTIVE    sharpe <= threshold

Schedule: Mon-Fri 4:15pm PT (post-market close, after closed_trades land)
Plist: infra/launchd/com.swingtrade.sharpe-monitor.plist

Usage:
  python3 scripts/rolling_sharpe_monitor.py                  # full run
  python3 scripts/rolling_sharpe_monitor.py --no-slack       # no posts
  python3 scripts/rolling_sharpe_monitor.py --force-alert    # always alert
  python3 scripts/rolling_sharpe_monitor.py --history        # show history
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


STATE_FILE = REPO / "data" / "rolling_sharpe_state.json"
HISTORY_FILE = REPO / "data" / "rolling_sharpe_history.jsonl"


def _classify_state(sharpe: float, threshold: float) -> str:
    edge_buffer = 0.15
    if sharpe <= threshold:
        return "KILL_ACTIVE"
    if sharpe <= threshold + edge_buffer:
        return "EDGE_WARNING"
    return "HEALTHY"


def _state_emoji(state: str) -> str:
    return {"HEALTHY": "🟢", "EDGE_WARNING": "🟡", "KILL_ACTIVE": "🔴"}.get(state, "⚪")


def _load_prior_state() -> dict:
    if not STATE_FILE.exists():
        return {"state": "UNKNOWN", "sharpe": None, "date": None}
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {"state": "UNKNOWN", "sharpe": None, "date": None}


def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, default=str))


def _append_history(entry: dict) -> None:
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY_FILE.open("a") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def _load_history(n: int = 30) -> list[dict]:
    if not HISTORY_FILE.exists():
        return []
    lines = HISTORY_FILE.read_text().splitlines()
    out = []
    for line in lines[-n:]:
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def _current_state() -> dict:
    """Compute current rolling Sharpe state from decision_engine."""
    try:
        from decision_engine import compute_rolling_sharpe_kill_state
        cfg = json.loads((REPO / "config" / "config.json").read_text())
        return compute_rolling_sharpe_kill_state(cfg)
    except Exception as e:
        return {"error": str(e), "active": False}


def _format_alert_slack(prior_state: str, new_state: str,
                        rs: dict, history: list[dict]) -> tuple[str, list]:
    """Build Slack alert with sparkline and transition context."""
    sharpe = rs.get("sharpe", 0)
    threshold = rs.get("threshold", -0.5)
    n = rs.get("n", 0)
    avg_pnl = rs.get("avg_pnl", 0)
    today = date.today().isoformat()

    emoji = _state_emoji(new_state)
    transition_emoji = ""
    if prior_state == "HEALTHY" and new_state == "EDGE_WARNING":
        transition_emoji = "📉"
        urgency = "warning"
        msg = "Rolling Sharpe entered EDGE WARNING zone"
    elif prior_state in ("HEALTHY", "EDGE_WARNING") and new_state == "KILL_ACTIVE":
        transition_emoji = "🚨"
        urgency = "critical"
        msg = "Rolling Sharpe KILL ACTIVATED — all BUYs halted"
    elif prior_state == "KILL_ACTIVE" and new_state in ("EDGE_WARNING", "HEALTHY"):
        transition_emoji = "✅"
        urgency = "good"
        msg = "Rolling Sharpe KILL CLEARED — BUYs can resume"
    elif prior_state == "EDGE_WARNING" and new_state == "HEALTHY":
        transition_emoji = "📈"
        urgency = "good"
        msg = "Rolling Sharpe returned to HEALTHY zone"
    elif prior_state == "EDGE_WARNING" and new_state == "KILL_ACTIVE":
        transition_emoji = "🚨"
        urgency = "critical"
        msg = "Rolling Sharpe KILL ACTIVATED from edge warning"
    else:
        transition_emoji = "ℹ️"
        urgency = "info"
        msg = f"State change: {prior_state} → {new_state}"

    # Build mini sparkline from history
    sparkline = ""
    if history:
        recent = history[-10:]
        sharpes = [h.get("sharpe", 0) for h in recent if h.get("sharpe") is not None]
        if sharpes:
            lo, hi = min(sharpes + [threshold]), max(sharpes + [threshold])
            rng = hi - lo if hi > lo else 1
            blocks = "▁▂▃▄▅▆▇█"
            sparkline = "".join(blocks[min(7, int(((s - lo) / rng) * 7))] for s in sharpes)

    text = f"{transition_emoji} *{msg}*"

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": f"{emoji} Rolling Sharpe Monitor"}},
        {"type": "section", "text": {"type": "mrkdwn",
         "text": f"{transition_emoji} *{msg}*\n_State: `{prior_state}` → `{new_state}`_"}},
        {"type": "section", "text": {"type": "mrkdwn",
         "text": f"*Sharpe per-trade*: `{sharpe:+.3f}` vs threshold `{threshold:+.2f}`\n"
                 f"*Sample*: last {n} closed BUYs · avg PnL `{avg_pnl:+.2f}%`\n"
                 f"*Recent trend* (10d): `{sparkline}`" if sparkline else
                 f"*Sharpe per-trade*: `{sharpe:+.3f}` vs threshold `{threshold:+.2f}`\n"
                 f"*Sample*: last {n} closed BUYs · avg PnL `{avg_pnl:+.2f}%`"}},
    ]

    if new_state == "KILL_ACTIVE":
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn",
            "text": "🚨 *Action*: NO new BUYs until kill clears. Wait for: (1) winning trades roll into window, OR (2) older losses age out (3-7 days typical)."}]})
    elif new_state == "EDGE_WARNING":
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn",
            "text": "⚠️ *Warning*: one losing trade could trigger kill switch. Position sizing should be conservative."}]})
    elif new_state == "HEALTHY" and prior_state == "KILL_ACTIVE":
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn",
            "text": "✅ *Resume*: BUYs can resume on next scan. System safety net cleared."}]})

    blocks.append({"type": "section", "text": {"type": "mrkdwn",
        "text": "<https://trade.mystockholding.com/reports/latest/sharpe-monitor|📊 Open Monitor Report> · "
                "<https://trade.mystockholding.com/v2/dashboard.html|🔗 Live Dashboard>"}})

    return text, blocks


def _build_history_html(history: list[dict], current: dict) -> str:
    """Render a 30-day rolling Sharpe history HTML page."""
    from collections import defaultdict
    today_str = date.today().strftime("%A · %B %-d, %Y").upper()
    time_str = datetime.now().strftime("%-I:%M %p PT")

    # Build SVG line chart of last 30 days
    chart_data = [h for h in history if h.get("sharpe") is not None][-30:]
    chart_svg = ""
    if chart_data:
        w, h = 720, 200
        m = 30
        sharpes = [d["sharpe"] for d in chart_data]
        threshold = current.get("threshold", -0.5)
        all_vals = sharpes + [threshold, 0]
        lo, hi = min(all_vals) - 0.05, max(all_vals) + 0.05
        rng = hi - lo
        def xy(i, s):
            x = m + (i / max(len(sharpes) - 1, 1)) * (w - 2*m)
            y = h - m - ((s - lo) / rng) * (h - 2*m)
            return x, y
        points = " ".join(f"{x:.1f},{y:.1f}" for x, y in (xy(i, s) for i, s in enumerate(sharpes)))
        zero_y = h - m - ((0 - lo) / rng) * (h - 2*m)
        thresh_y = h - m - ((threshold - lo) / rng) * (h - 2*m)
        # Dots colored by state
        dots = ""
        for i, d in enumerate(chart_data):
            x, y = xy(i, d["sharpe"])
            color = {"HEALTHY": "#00d68f", "EDGE_WARNING": "#ffb800", "KILL_ACTIVE": "#ff4d4f"}.get(d.get("state", ""), "#888")
            dots += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{color}"/>'
        chart_svg = f"""
        <svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" style="background:#0a0a0a;border:1px solid #222">
          <line x1="{m}" y1="{zero_y:.1f}" x2="{w-m}" y2="{zero_y:.1f}" stroke="#333" stroke-dasharray="3,3"/>
          <text x="{w-m-5}" y="{zero_y-4:.1f}" fill="#666" font-size="10" text-anchor="end" font-family="JetBrains Mono">0.00</text>
          <line x1="{m}" y1="{thresh_y:.1f}" x2="{w-m}" y2="{thresh_y:.1f}" stroke="#ff4d4f" stroke-dasharray="5,3" opacity="0.6"/>
          <text x="{w-m-5}" y="{thresh_y-4:.1f}" fill="#ff4d4f" font-size="10" text-anchor="end" font-family="JetBrains Mono">{threshold} (kill)</text>
          <polyline fill="none" stroke="#00d4ff" stroke-width="1.5" points="{points}"/>
          {dots}
        </svg>"""

    # State count summary
    state_counts = defaultdict(int)
    for h in history[-30:]:
        state_counts[h.get("state", "UNKNOWN")] += 1

    # Recent transitions
    transitions = []
    prev_state = None
    for h in history:
        cur_state = h.get("state")
        if prev_state and cur_state and prev_state != cur_state:
            transitions.append({"date": h.get("date"), "from": prev_state, "to": cur_state,
                                 "sharpe": h.get("sharpe")})
        prev_state = cur_state
    transitions = transitions[-10:]

    # History table rows
    history_rows = []
    for h in reversed(history[-30:]):
        s = h.get("sharpe", 0)
        st = h.get("state", "?")
        emo = _state_emoji(st)
        n = h.get("n", 0)
        history_rows.append(f"""
        <tr>
          <td>{h.get('date', '?')}</td>
          <td style="font-family:'JetBrains Mono',monospace">{s:+.3f}</td>
          <td>{emo} {st}</td>
          <td style="font-family:'JetBrains Mono',monospace;color:#888">n={n}</td>
        </tr>""")

    current_state = current.get("state", "UNKNOWN")
    current_sharpe = current.get("sharpe", 0)
    current_emoji = _state_emoji(current_state)

    transitions_html = ""
    if transitions:
        for t in transitions:
            from_emo = _state_emoji(t["from"])
            to_emo = _state_emoji(t["to"])
            transitions_html += f"""
            <div class="trans-row">
              <span style="font-family:'JetBrains Mono',monospace;color:#888">{t['date']}</span>
              <span style="margin:0 12px">{from_emo} {t['from']} → {to_emo} {t['to']}</span>
              <span style="font-family:'JetBrains Mono',monospace;color:#aaa">sharpe {t.get('sharpe', 0):+.3f}</span>
            </div>"""

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>SwingTrade · Rolling Sharpe Monitor</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  body {{ background:#000; color:#e8e8e8; margin:0; padding:32px 16px;
         font-family:'Inter',sans-serif; line-height:1.5; }}
  .frame {{ max-width:880px; margin:0 auto; }}
  .masthead {{ padding:24px 0 16px; border-bottom:2px solid #ff7a00; margin-bottom:24px; }}
  .brand {{ font-size:26px; font-weight:800; color:#fff; }}
  .brand-bar {{ display:inline-block; width:4px; height:22px; background:#ff7a00; margin-right:10px; vertical-align:middle; }}
  .edition {{ font-size:11px; color:#888; letter-spacing:2px; text-transform:uppercase; margin-top:6px; }}
  .current-banner {{ background:linear-gradient(135deg, #1a1a1a, #0a0a0a);
                    border-left:4px solid #ff7a00; padding:20px 24px;
                    border-radius:4px; margin:0 0 24px; }}
  .banner-label {{ font-size:11px; color:#888; letter-spacing:2px; text-transform:uppercase; }}
  .banner-state {{ font-size:28px; font-weight:700; color:#fff; margin:4px 0; }}
  .banner-sharpe {{ font-size:14px; color:#aaa; font-family:'JetBrains Mono',monospace; }}
  h2 {{ font-size:12px; color:#ff7a00; letter-spacing:2px; text-transform:uppercase;
       font-weight:700; margin:28px 0 12px; padding-bottom:6px; border-bottom:1px solid #222; }}
  table {{ width:100%; border-collapse:collapse; font-size:12px; }}
  td, th {{ padding:8px 12px; border-bottom:1px solid #1a1a1a; text-align:left; }}
  th {{ color:#888; font-size:10px; letter-spacing:1px; text-transform:uppercase; font-weight:600; }}
  .summary-grid {{ display:grid; grid-template-columns:repeat(3, 1fr); gap:1px; background:#222; padding:1px; border:1px solid #222; }}
  .summary-grid > div {{ background:#0a0a0a; padding:14px; }}
  .summary-label {{ font-size:10px; color:#888; letter-spacing:1px; text-transform:uppercase; }}
  .summary-val {{ font-size:22px; font-weight:700; color:#fff; margin-top:4px; font-family:'JetBrains Mono',monospace; }}
  .trans-row {{ padding:6px 0; font-size:13px; border-bottom:1px solid #1a1a1a; }}
  footer {{ margin-top:32px; padding-top:18px; border-top:1px solid #222; text-align:center; font-size:11px; color:#666; }}
  footer a {{ color:#ff7a00; text-decoration:none; margin:0 12px; }}
</style></head>
<body>
<div class="frame">
<div class="masthead">
  <div class="brand"><span class="brand-bar"></span>SwingTrade</div>
  <div class="edition">Rolling Sharpe Monitor</div>
  <div style="font-size:11px;color:#888;margin-top:8px">{today_str} · {time_str}</div>
</div>

<div class="current-banner">
  <div class="banner-label">CURRENT STATE</div>
  <div class="banner-state">{current_emoji} {current_state}</div>
  <div class="banner-sharpe">Sharpe: {current_sharpe:+.3f} vs threshold {current.get('threshold', -0.5):+.2f} on n={current.get('n', 0)}</div>
</div>

<h2>30-Day History Chart</h2>
{chart_svg}
<div style="font-size:11px;color:#666;margin-top:8px;text-align:center">
  🟢 healthy · 🟡 edge warning · 🔴 kill active · dashed red = kill threshold · dashed gray = zero
</div>

<h2>30-Day State Distribution</h2>
<div class="summary-grid">
  <div><div class="summary-label">🟢 Healthy days</div><div class="summary-val">{state_counts.get('HEALTHY', 0)}</div></div>
  <div><div class="summary-label">🟡 Edge warning</div><div class="summary-val">{state_counts.get('EDGE_WARNING', 0)}</div></div>
  <div><div class="summary-label">🔴 Kill active</div><div class="summary-val">{state_counts.get('KILL_ACTIVE', 0)}</div></div>
</div>

<h2>Recent Transitions (last 10)</h2>
{transitions_html if transitions_html else '<div style="color:#666;font-size:12px">No state changes in tracked history.</div>'}

<h2>Daily History</h2>
<table>
  <thead><tr><th>Date</th><th>Sharpe</th><th>State</th><th>Sample</th></tr></thead>
  <tbody>{''.join(history_rows)}</tbody>
</table>

<footer>
  <a href="https://trade.mystockholding.com/reports">Report Archive</a>
  <a href="https://trade.mystockholding.com/reports/latest/morning-newsletter">Morning Brief</a>
  <a href="https://trade.mystockholding.com/reports/latest/strategy-roster">Strategy Roster</a>
  <a href="https://trade.mystockholding.com/v2/dashboard.html">Live Dashboard</a>
</footer>
</div></body></html>"""
    return html


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-slack", action="store_true")
    ap.add_argument("--force-alert", action="store_true", help="Always post to Slack (not just on state change)")
    ap.add_argument("--history", action="store_true", help="Print history and exit")
    args = ap.parse_args()

    if args.history:
        history = _load_history(60)
        for h in history:
            emoji = _state_emoji(h.get("state", ""))
            print(f"  {h.get('date'):12s} {emoji} {h.get('state','?'):14s} "
                  f"sharpe={h.get('sharpe', 0):+.3f} n={h.get('n', 0)} "
                  f"avg_pnl={h.get('avg_pnl', 0):+.2f}%")
        return

    # Compute current state
    rs = _current_state()
    if rs.get("error"):
        print(f"ERROR: {rs['error']}")
        sys.exit(1)

    sharpe = rs.get("sharpe", 0)
    threshold = rs.get("threshold", -0.5)
    n = rs.get("n", 0)
    avg_pnl = rs.get("avg_pnl", 0)
    state = _classify_state(sharpe, threshold)

    print("=" * 60)
    print(f"ROLLING SHARPE MONITOR — {date.today().isoformat()}")
    print("=" * 60)
    print(f"  State:       {_state_emoji(state)} {state}")
    print(f"  Sharpe:      {sharpe:+.3f}")
    print(f"  Threshold:   {threshold:+.2f}")
    print(f"  Sample:      n={n} closed BUYs · avg PnL {avg_pnl:+.2f}%")
    print()

    # Compare to prior state
    prior = _load_prior_state()
    prior_state = prior.get("state", "UNKNOWN")
    state_changed = (prior_state != state and prior_state != "UNKNOWN")

    print(f"  Prior state: {prior_state} (from {prior.get('date', 'first run')})")
    if state_changed:
        print(f"  CHANGE:      {prior_state} → {state}")
    else:
        print(f"  No state change.")

    # Append to history
    entry = {
        "date": date.today().isoformat(),
        "ts": datetime.now().isoformat(timespec="seconds"),
        "state": state,
        "sharpe": sharpe,
        "threshold": threshold,
        "n": n,
        "avg_pnl": avg_pnl,
    }
    _append_history(entry)
    _save_state({**entry, "prior_state": prior_state})
    print(f"\n  History appended: {HISTORY_FILE}")

    # Build + save HTML
    try:
        history = _load_history(60)
        html = _build_history_html(history, {**rs, "state": state})
        out_p = REPO / "cache" / "sharpe_monitor.html"
        out_p.write_text(html)
        import db
        snap_id = db.save_html_snapshot(
            kind="sharpe-monitor",
            html_content=html,
            label=f"Rolling Sharpe Monitor {date.today().isoformat()}",
            meta={"state": state, "sharpe": sharpe, "n": n, "transition": f"{prior_state}→{state}" if state_changed else "no change"},
        )
        print(f"  HTML report: snapshot id={snap_id}")
        print(f"  URL: https://trade.mystockholding.com/reports/latest/sharpe-monitor")
    except Exception as e:
        print(f"  HTML save failed: {e}")

    # Slack alert ONLY on state change (or --force-alert)
    if not args.no_slack and (state_changed or args.force_alert):
        try:
            from secrets_loader import get_secret as _gs
            webhook = _gs("SLACK_WEBHOOK_URL", default="")
        except Exception:
            webhook = ""
        if webhook:
            text, blocks = _format_alert_slack(prior_state, state, rs, _load_history(60))
            from alerts import _slack_post
            ok = _slack_post(webhook, text, blocks)
            print(f"\n  Slack alert: {'✓ sent' if ok else '✗ failed'}")
        else:
            print("\n  No SLACK_WEBHOOK_URL — skipped alert")
    elif not state_changed:
        print(f"\n  No state change — Slack alert suppressed (use --force-alert to override)")


if __name__ == "__main__":
    main()
