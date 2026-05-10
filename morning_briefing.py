"""
morning_briefing.py — wake-up summary after overnight backtest + walk-forward.

Auto-detects state of overnight runs and produces a focused HTML brief telling
the user EXACTLY what to do, in priority order:

  1. Did the 750d backtest complete? Show its KPIs + verdict.
  2. Did the walk-forward complete? Show shipped multipliers + apply suggestion.
  3. Pending issues / errors to investigate.
  4. One-click commands the user can copy-paste to act.

Output: cache/morning_briefing_YYYY-MM-DD.html

Usage:
    python3 morning_briefing.py            # generate + open in browser
    python3 morning_briefing.py --no-open  # generate only
"""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).parent
TODAY = datetime.now().strftime("%Y-%m-%d")
OUT_PATH = ROOT / "cache" / f"morning_briefing_{TODAY}.html"

# ─── Detection helpers ────────────────────────────────────────────────────

def is_process_running(pid_or_pattern: str) -> bool:
    """Check if a backtest/WF process is still running."""
    try:
        if pid_or_pattern.isdigit():
            os.kill(int(pid_or_pattern), 0)
            return True
        # Pattern match
        out = subprocess.check_output(["pgrep", "-f", pid_or_pattern],
                                       stderr=subprocess.DEVNULL).decode().strip()
        return bool(out)
    except (subprocess.CalledProcessError, ProcessLookupError, OSError, ValueError):
        return False


def file_age_minutes(p: Path) -> float | None:
    if not p.exists():
        return None
    return (datetime.now().timestamp() - p.stat().st_mtime) / 60


def load_json(p: Path) -> dict | list | None:
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


# ─── State assessments ─────────────────────────────────────────────────────

def assess_750d_backtest() -> dict:
    """750d portfolio backtest status."""
    bt_json = ROOT / "cache" / "portfolio_backtest.json"
    bt_log = sorted(ROOT.glob("cache/logs/backtest_*.log"))   # any timestamped backtest log
    age = file_age_minutes(bt_json)
    is_running = is_process_running("backtest.py --portfolio --days 750")
    result = load_json(bt_json) or {}

    return {
        "completed": age is not None and age < (24 * 60) and not is_running,
        "still_running": is_running,
        "age_min": age,
        "result": result,
        "has_recent_data": age is not None and age < 60,
    }


def assess_walk_forward() -> dict:
    """Walk-forward + multiplier proposals status."""
    proposals_json = ROOT / "cache" / "wf_multiplier_proposals.json"
    wf_results_json = ROOT / "cache" / "walk_forward_v2_results.json"
    wf_log = sorted(ROOT.glob("cache/logs/wf_run_*.log"))
    is_running = is_process_running("walk_forward_v2.py")

    proposals = load_json(proposals_json) or {}
    wf_results = load_json(wf_results_json) or {}
    age = file_age_minutes(proposals_json)

    return {
        "completed": (age is not None and not is_running) and bool(proposals.get("shipped_multipliers")),
        "still_running": is_running,
        "age_min": age,
        "proposals": proposals,
        "wf_results": wf_results,
        "log_path": str(wf_log[-1]) if wf_log else None,
    }


def assess_paper_trading() -> dict:
    """Paper trading state."""
    pt_json = ROOT / "data" / "paper_trading_start.json"
    d = load_json(pt_json) or {}
    state = "ENABLED" if d.get("enabled") else "DISABLED"
    start = d.get("start_date")
    duration = d.get("duration_days") or 60
    if start:
        try:
            day = (datetime.now().date() - datetime.fromisoformat(start).date()).days
            return {"state": state, "day": day, "duration": duration, "remaining": max(0, duration - day)}
        except Exception:
            pass
    return {"state": state, "day": None, "duration": duration}


def get_recent_commits(hours: int = 12) -> list[dict]:
    try:
        out = subprocess.check_output(
            ["git", "log", f"--since={hours} hours ago", "--pretty=format:%h|%s"],
            stderr=subprocess.DEVNULL, cwd=str(ROOT)
        ).decode().strip()
        commits = []
        for line in out.splitlines():
            parts = line.split("|", 1)
            if len(parts) == 2:
                commits.append({"hash": parts[0], "msg": parts[1]})
        return commits
    except Exception:
        return []


# ─── Action plan generator ─────────────────────────────────────────────────

def build_action_plan(bt: dict, wf: dict, pt: dict) -> list[dict]:
    """Ordered list of suggested actions with copy-paste commands."""
    actions = []

    if wf["still_running"]:
        actions.append({
            "priority": 1,
            "label": "Wait for walk-forward to finish",
            "why": f"WF is still running. Tail the log to see progress.",
            "cmd": f"tail -f {wf['log_path']}",
            "kind": "wait",
        })
    elif wf["completed"] and wf["proposals"].get("shipped_multipliers"):
        n = len(wf["proposals"].get("shipped_multipliers", {}))
        actions.append({
            "priority": 1,
            "label": f"Review WF proposals ({n} multipliers shipped 3-of-4-fold consensus)",
            "why": "Walk-forward produced validated multiplier proposals. Preview the diff before applying.",
            "cmd": "python3 apply_wf_proposals.py",
            "kind": "review",
        })
        actions.append({
            "priority": 2,
            "label": "Apply WF proposals to config.json",
            "why": "After previewing, write the shipped multipliers + _validations to config. Auto-backs up first.",
            "cmd": "python3 apply_wf_proposals.py --apply",
            "kind": "apply",
        })
    elif wf["completed"]:
        actions.append({
            "priority": 1,
            "label": "WF finished but shipped no multipliers",
            "why": "Either samples too thin per setup, or proposals didn't pass 3-of-4-fold direction consensus. Inspect log for fold-level details.",
            "cmd": f"grep -E 'SHIP|FAIL|skipping' {wf['log_path']}",
            "kind": "investigate",
        })
    else:
        actions.append({
            "priority": 1,
            "label": "WF didn't complete",
            "why": "No proposals file. Check log for errors.",
            "cmd": f"tail -50 {wf['log_path'] or 'cache/logs/wf_run_*.log'}",
            "kind": "investigate",
        })

    if bt["completed"] and bt["result"]:
        r = bt["result"]
        n_trades = r.get("total_trades", 0)
        wr = r.get("win_rate", 0)
        sharpe = r.get("sharpe", 0)
        # Apply mental haircut
        wr_adj = max(0, wr - 3)
        verdict = "STRONG" if (wr_adj > 50 and sharpe > 1.0) else (
            "DECENT" if (wr_adj > 40 and sharpe > 0.5) else "WEAK"
        )
        actions.append({
            "priority": 3,
            "label": f"Review 750d backtest verdict: {verdict}",
            "why": f"n={n_trades}, raw WR={wr:.1f}%, Sharpe={sharpe:.2f}. Survivorship-adj WR ≈ {wr_adj:.1f}%.",
            "cmd": "open cache/backtest_report_latest.html",
            "kind": "review",
        })

    if pt["state"] == "ENABLED" and pt.get("remaining", 0) < 14:
        actions.append({
            "priority": 4,
            "label": f"Paper trading window closes in {pt['remaining']} days",
            "why": "60-day paper window auto-disables. Decide before then: extend, go live, or analyze results.",
            "cmd": "python3 executor.py --status",
            "kind": "warn",
        })

    actions.append({
        "priority": 5,
        "label": "Re-generate all reports with fresh data",
        "why": "After applying WF proposals, refresh the three HTML reports.",
        "cmd": "python3 generate_session_report.py && python3 elite_research_note.py && python3 hedge_fund_report.py",
        "kind": "report",
    })

    return sorted(actions, key=lambda a: a["priority"])


# ─── HTML rendering ────────────────────────────────────────────────────────

CSS = """
:root {
  --bg-0: #0a0e14; --bg-1: #11171f; --bg-2: #1a212c;
  --rule: #2a3340; --ink-0: #e6edf3; --ink-1: #adb8c4; --ink-2: #6e7a8a;
  --gold: #f5d76e; --green: #4ade80; --red: #f87171; --orange: #fb923c;
  --blue: #7dd3fc; --purple: #c084fc;
  --mono: 'JetBrains Mono','SF Mono',Menlo,monospace;
}
* { box-sizing: border-box; }
body { background: var(--bg-0); color: var(--ink-0); font-family: -apple-system,'Inter',sans-serif; line-height: 1.6; margin: 0; }
.wrap { max-width: 980px; margin: 0 auto; padding: 36px 28px 60px; }
.eyebrow { font-family: var(--mono); font-size: 11px; color: var(--gold); letter-spacing: 0.18em; text-transform: uppercase; margin-bottom: 6px; }
h1 { font-size: 34px; font-weight: 700; margin: 0 0 8px; letter-spacing: -0.01em; }
.sub { color: var(--ink-1); font-size: 15px; margin-bottom: 28px; }

.status-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 14px; margin-bottom: 32px; }
.s-card { background: var(--bg-1); border: 1px solid var(--rule); border-radius: 6px; padding: 16px 20px; }
.s-card.live { border-left: 3px solid var(--blue); }
.s-card.done { border-left: 3px solid var(--green); }
.s-card.fail { border-left: 3px solid var(--red); }
.s-card.warn { border-left: 3px solid var(--orange); }
.s-card .lbl { font-family: var(--mono); font-size: 10px; letter-spacing: 0.1em; color: var(--ink-2); text-transform: uppercase; margin-bottom: 4px; }
.s-card .v { font-size: 22px; font-weight: 600; color: var(--ink-0); }
.s-card .meta { color: var(--ink-2); font-size: 12px; margin-top: 4px; font-family: var(--mono); }

h2 { font-size: 22px; margin: 36px 0 14px; padding-bottom: 8px; border-bottom: 1px solid var(--rule); }

.action { background: var(--bg-1); border: 1px solid var(--rule); border-radius: 6px; padding: 18px 22px; margin: 12px 0; display: grid; grid-template-columns: 28px 1fr; gap: 14px; }
.action.review { border-left: 3px solid var(--blue); }
.action.apply { border-left: 3px solid var(--green); }
.action.investigate { border-left: 3px solid var(--orange); }
.action.wait { border-left: 3px solid var(--purple); }
.action.warn { border-left: 3px solid var(--orange); }
.action.report { border-left: 3px solid var(--gold); }
.action .num { font-family: var(--mono); font-size: 18px; font-weight: 700; color: var(--gold); }
.action .body .label { font-weight: 600; font-size: 16px; color: var(--ink-0); margin-bottom: 4px; }
.action .body .why { color: var(--ink-1); font-size: 14px; margin-bottom: 8px; }
.action .body pre { background: var(--bg-2); border: 1px solid var(--rule); border-radius: 4px; padding: 10px 14px; font-family: var(--mono); font-size: 12px; color: var(--blue); overflow-x: auto; margin: 0; }

.kpi-row { display: grid; grid-template-columns: repeat(4,1fr); gap: 12px; margin: 14px 0; }
.kpi { background: var(--bg-2); border: 1px solid var(--rule); border-radius: 4px; padding: 12px; }
.kpi .lbl { font-family: var(--mono); font-size: 9px; color: var(--ink-2); letter-spacing: 0.1em; text-transform: uppercase; }
.kpi .v { font-family: var(--mono); font-size: 20px; font-weight: 600; }
.kpi .v.pos { color: var(--green); }
.kpi .v.neg { color: var(--red); }

table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { text-align: left; padding: 8px 12px; border-bottom: 1px solid var(--rule); }
th { background: var(--bg-2); color: var(--ink-2); font-family: var(--mono); font-size: 10px; text-transform: uppercase; letter-spacing: 0.1em; }

.commits { font-family: var(--mono); font-size: 12px; color: var(--ink-1); }
.commits li { margin: 4px 0; }
.commits code { color: var(--blue); }

.footer { margin-top: 48px; padding-top: 18px; border-top: 1px solid var(--rule); color: var(--ink-2); font-family: var(--mono); font-size: 11px; }

@media (max-width: 700px) {
  .status-grid { grid-template-columns: 1fr; }
  .kpi-row { grid-template-columns: repeat(2, 1fr); }
}
"""


def render_html(bt: dict, wf: dict, pt: dict, actions: list[dict], commits: list[dict]) -> str:
    bt_status_class = "live" if bt["still_running"] else ("done" if bt["completed"] else "warn")
    bt_status_text = "Running" if bt["still_running"] else ("Completed" if bt["completed"] else "Pending")

    wf_status_class = "live" if wf["still_running"] else ("done" if wf["completed"] else "fail")
    wf_status_text = "Running" if wf["still_running"] else ("Completed" if wf["completed"] else "Failed/Pending")
    wf_n_shipped = len((wf["proposals"].get("shipped_multipliers") or {})) if wf["proposals"] else 0

    pt_status_class = "done" if pt.get("state") == "ENABLED" else "warn"
    pt_status_text = pt.get("state", "UNKNOWN")
    pt_meta = f"Day {pt['day']}/{pt['duration']}" if pt.get("day") is not None else "—"

    bt_kpis_html = ""
    if bt["completed"] and bt["result"]:
        r = bt["result"]
        bt_kpis_html = f"""
        <div class="kpi-row">
          <div class="kpi"><div class="lbl">Total trades</div><div class="v">{r.get('total_trades','—')}</div></div>
          <div class="kpi"><div class="lbl">WR (raw)</div><div class="v">{r.get('win_rate', 0):.1f}%</div></div>
          <div class="kpi"><div class="lbl">Profit Factor</div><div class="v">{r.get('profit_factor', 0):.2f}</div></div>
          <div class="kpi"><div class="lbl">Sharpe</div><div class="v">{r.get('sharpe', 0):.2f}</div></div>
          <div class="kpi"><div class="lbl">Max DD</div><div class="v neg">{r.get('max_drawdown_pct', 0):.1f}%</div></div>
          <div class="kpi"><div class="lbl">Total return</div><div class="v {'pos' if r.get('total_return_pct',0)>0 else 'neg'}">{r.get('total_return_pct', 0):+.1f}%</div></div>
          <div class="kpi"><div class="lbl">Total P&amp;L</div><div class="v {'pos' if r.get('total_pnl',0)>0 else 'neg'}">${r.get('total_pnl', 0):+,.0f}</div></div>
          <div class="kpi"><div class="lbl">Window</div><div class="v">{r.get('config',{}).get('days', 0)}d</div></div>
        </div>"""

    wf_proposal_table = ""
    if wf["proposals"].get("shipped_multipliers"):
        rows = []
        for setup, mult in wf["proposals"]["shipped_multipliers"].items():
            if setup.startswith("_") or not isinstance(mult, (int, float)):
                continue
            v = (wf["proposals"]["shipped_multipliers"].get("_validations") or {}).get(setup) or {}
            rows.append(f"""
            <tr>
              <td>{setup}</td>
              <td>{mult:.3f}</td>
              <td>{v.get('n', '—')}</td>
              <td>{v.get('wr_lb', 0):.1%}</td>
              <td>{v.get('source', '—')}</td>
            </tr>""")
        if rows:
            wf_proposal_table = f"""
            <table>
              <thead><tr><th>Setup</th><th>Mult</th><th>n</th><th>Wilson LB</th><th>Source</th></tr></thead>
              <tbody>{''.join(rows)}</tbody>
            </table>"""

    actions_html = ""
    for i, a in enumerate(actions, 1):
        actions_html += f"""
        <div class="action {a['kind']}">
          <div class="num">{i}.</div>
          <div class="body">
            <div class="label">{a['label']}</div>
            <div class="why">{a['why']}</div>
            <pre>{a['cmd']}</pre>
          </div>
        </div>"""

    commits_html = "".join(f'<li><code>{c["hash"]}</code> — {c["msg"]}</li>' for c in commits)

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8">
<title>Morning Briefing · SwingTrade · {TODAY}</title>
<style>{CSS}</style>
</head><body>
<div class="wrap">

<div class="eyebrow">SwingTrade · Morning Brief · {TODAY}</div>
<h1>What happened, what to do</h1>
<p class="sub">Generated {datetime.now().strftime('%H:%M %Z')}. Auto-detected status of overnight backtest + walk-forward. Ordered action list at bottom — copy any command and run it.</p>

<div class="status-grid">
  <div class="s-card {bt_status_class}">
    <div class="lbl">3-year Backtest</div>
    <div class="v">{bt_status_text}</div>
    <div class="meta">{('age ' + format(bt['age_min'], '.0f') + ' min') if bt.get('age_min') is not None else 'no result yet'}</div>
  </div>
  <div class="s-card {wf_status_class}">
    <div class="lbl">Walk-Forward</div>
    <div class="v">{wf_status_text}</div>
    <div class="meta">{wf_n_shipped} multiplier{'s' if wf_n_shipped != 1 else ''} shipped</div>
  </div>
  <div class="s-card {pt_status_class}">
    <div class="lbl">Paper Trading</div>
    <div class="v">{pt_status_text}</div>
    <div class="meta">{pt_meta}</div>
  </div>
</div>

<h2>3-Year Backtest</h2>
{bt_kpis_html or '<p style="color:var(--ink-2)">Backtest still running or no result available yet.</p>'}

<h2>Walk-Forward Multiplier Proposals</h2>
{wf_proposal_table or '<p style="color:var(--ink-2)">No shipped multipliers yet (WF still running, or no setup passed 3-of-4-fold consensus).</p>'}

<h2>Action Plan</h2>
{actions_html}

<h2>Commits last 12 hours</h2>
<ul class="commits">
{commits_html or '<li>(none)</li>'}
</ul>

<div class="footer">
  Generated {datetime.now().strftime('%Y-%m-%d %H:%M %Z')} · Auto-detection from running processes + cache files · Re-run anytime: <code>python3 morning_briefing.py</code>
</div>

</div>
</body></html>"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-open", action="store_true", help="Generate only, don't open in browser")
    args = parser.parse_args()

    bt = assess_750d_backtest()
    wf = assess_walk_forward()
    pt = assess_paper_trading()
    actions = build_action_plan(bt, wf, pt)
    commits = get_recent_commits(12)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    html = render_html(bt, wf, pt, actions, commits)
    OUT_PATH.write_text(html, encoding="utf-8")

    print(f"Wrote {OUT_PATH}")
    print(f"  Backtest: {'running' if bt['still_running'] else ('done' if bt['completed'] else 'pending')}")
    print(f"  Walk-fwd: {'running' if wf['still_running'] else ('done' if wf['completed'] else 'pending')} ({len((wf['proposals'].get('shipped_multipliers') or {}))} mults)")
    pt_day_str = f"(day {pt['day']}/{pt['duration']})" if pt.get('day') is not None else ""
    print(f"  Paper:    {pt['state']} {pt_day_str}")
    print(f"  Actions:  {len(actions)} suggested")

    if not args.no_open:
        try:
            subprocess.Popen(["open", str(OUT_PATH)])
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
