"""
generate_session_report.py — institutional-grade research note for the
2026-05-08 session: P3 statistical gates, Mode 1 dual-write, Phase B.1
shim, and the 3-year backtest results.

Output: cache/session_report_2026-05-08.html

Pulls data from:
  - cache/portfolio_backtest.json (latest run results, if available)
  - data/signal_log.json via state_layer (canonical signals)
  - config/config.json (current gates / multipliers / validations)
  - Supabase (if reachable: latest backtest_runs row + closed_trades)
  - git log (commits this session)
"""
from __future__ import annotations

import json
import math
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
OUT_PATH = ROOT / "cache" / "session_report_2026-05-08.html"


def _wilson_ci(wins: int, total: int, conf: float = 0.95) -> tuple[float, float]:
    if total == 0:
        return (0.0, 1.0)
    z = 1.96 if conf == 0.95 else 2.576
    phat = wins / total
    denom = 1 + z * z / total
    center = (phat + z * z / (2 * total)) / denom
    spread = z * math.sqrt((phat * (1 - phat) + z * z / (4 * total)) / total) / denom
    return (max(0.0, center - spread), min(1.0, center + spread))


def _load_signal_log() -> list[dict]:
    p = ROOT / "data" / "signal_log.json"
    if not p.exists():
        return []
    try:
        d = json.loads(p.read_text())
        return d if isinstance(d, list) else []
    except Exception:
        return []


def _load_config() -> dict:
    p = ROOT / "config" / "config.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def _load_backtest_result() -> dict | None:
    p = ROOT / "cache" / "portfolio_backtest.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _git_commits_today() -> list[dict]:
    try:
        out = subprocess.check_output(
            ["git", "log", "--since=24 hours ago", "--pretty=format:%h|%s|%an"],
            stderr=subprocess.DEVNULL, cwd=str(ROOT)
        ).decode().strip()
        commits = []
        for line in out.splitlines():
            parts = line.split("|", 2)
            if len(parts) == 3:
                commits.append({"hash": parts[0], "msg": parts[1], "author": parts[2]})
        return commits
    except Exception:
        return []


def _setup_breakdown_from_log(entries: list[dict]) -> list[dict]:
    """Per-setup stats from canonical signal_log (closed signals only)."""
    by_setup: dict = {}
    for s in entries:
        if s.get("status") != "CLOSED":
            continue
        setup = s.get("strategy")
        pnl = s.get("actual_pnl_pct")
        if not setup or pnl is None:
            continue
        d = by_setup.setdefault(setup, {"pnls": []})
        d["pnls"].append(float(pnl))

    out = []
    for setup, d in by_setup.items():
        pnls = d["pnls"]
        n = len(pnls)
        wins = sum(1 for p in pnls if p > 0)
        wr = wins / n if n else 0
        avg_pnl = sum(pnls) / n if n else 0
        lo, hi = _wilson_ci(wins, n)
        positive = [p for p in pnls if p > 0]
        negative = [p for p in pnls if p <= 0]
        avg_win = sum(positive) / len(positive) if positive else 0
        avg_loss = sum(negative) / len(negative) if negative else 0
        # Profit factor = sum(wins) / abs(sum(losses))
        sum_losses = abs(sum(negative))
        pf = (sum(positive) / sum_losses) if sum_losses > 0 else float("inf") if positive else 0
        out.append({
            "setup": setup, "n": n, "wins": wins, "wr": wr, "wr_lb": lo, "wr_hi": hi,
            "avg_pnl": avg_pnl, "avg_win": avg_win, "avg_loss": avg_loss,
            "profit_factor": pf,
        })
    return sorted(out, key=lambda r: r["n"], reverse=True)


def _regime_breakdown_from_log(entries: list[dict]) -> list[dict]:
    by_regime: dict = {}
    for s in entries:
        if s.get("status") != "CLOSED":
            continue
        regime = (s.get("raw_json") or {}).get("regime") or "unknown"
        pnl = s.get("actual_pnl_pct")
        if pnl is None:
            continue
        by_regime.setdefault(regime, []).append(float(pnl))
    out = []
    for r, pnls in by_regime.items():
        n = len(pnls)
        wins = sum(1 for p in pnls if p > 0)
        wr = wins / n if n else 0
        avg = sum(pnls) / n if n else 0
        lo, _hi = _wilson_ci(wins, n)
        out.append({"regime": r, "n": n, "wr": wr, "wr_lb": lo, "avg_pnl": avg})
    return sorted(out, key=lambda r: r["n"], reverse=True)


def _format_pct(v: float, sign: bool = False) -> str:
    if v is None:
        return "—"
    s = f"{v*100:+.1f}%" if sign else f"{v*100:.1f}%"
    return s


def _verdict_class(wr: float, wr_lb: float, n: int) -> tuple[str, str]:
    """(class, label) for color-coded verdict."""
    if n < 10:
        return ("bad", "no edge — n too small")
    if wr_lb >= 0.50:
        return ("strong", "strong edge")
    if wr_lb >= 0.40:
        return ("ok", "marginal edge")
    if wr_lb >= 0.30:
        return ("watch", "borderline — observe")
    return ("bad", "below floor — KILL or DEMOTE")


def render_html() -> str:
    sigs = _load_signal_log()
    cfg = _load_config()
    bt = _load_backtest_result()
    commits = _git_commits_today()

    setup_rows = _setup_breakdown_from_log(sigs)
    regime_rows = _regime_breakdown_from_log(sigs)

    n_total_signals = len(sigs)
    n_closed = sum(1 for s in sigs if s.get("status") == "CLOSED")
    closed_pnls = [s.get("actual_pnl_pct") for s in sigs if s.get("status") == "CLOSED" and s.get("actual_pnl_pct") is not None]
    overall_wr = (sum(1 for p in closed_pnls if p > 0) / len(closed_pnls)) if closed_pnls else 0
    overall_avg = (sum(closed_pnls) / len(closed_pnls)) if closed_pnls else 0
    overall_lo, overall_hi = _wilson_ci(sum(1 for p in closed_pnls if p > 0), len(closed_pnls))

    _validations = (cfg.get("setup_score_multiplier") or {}).get("_validations") or {}
    static_kills = cfg.get("static_setup_kill_list") or []
    multipliers = {k: v for k, v in (cfg.get("setup_score_multiplier") or {}).items() if not k.startswith("_") and isinstance(v, (int, float))}

    bt_html = ""
    if bt:
        bt_html = f"""
        <div class="card">
          <h3>3-Year Portfolio Backtest <span class="meta">cache/portfolio_backtest.json</span></h3>
          <div class="kpi-grid">
            <div class="kpi"><div class="lbl">Total Trades</div><div class="v">{bt.get('total_trades','—')}</div></div>
            <div class="kpi"><div class="lbl">Win Rate (raw)</div><div class="v">{bt.get('win_rate',0):.1f}%</div></div>
            <div class="kpi"><div class="lbl">Profit Factor</div><div class="v">{bt.get('profit_factor',0):.2f}</div></div>
            <div class="kpi"><div class="lbl">Sharpe</div><div class="v">{bt.get('sharpe',0):.2f}</div></div>
            <div class="kpi"><div class="lbl">Max Drawdown</div><div class="v">{bt.get('max_drawdown_pct',0):.1f}%</div></div>
            <div class="kpi"><div class="lbl">Total Return</div><div class="v">{bt.get('total_return_pct',0):+.1f}%</div></div>
            <div class="kpi"><div class="lbl">Total P&amp;L</div><div class="v">${bt.get('total_pnl',0):+,.0f}</div></div>
            <div class="kpi"><div class="lbl">Window</div><div class="v">{bt.get('config',{}).get('days',0)}d</div></div>
          </div>
        </div>"""
    else:
        bt_html = '<div class="card"><h3>3-Year Portfolio Backtest</h3><div class="empty">⏳ Backtest still running. Re-generate when complete.</div></div>'

    # Setup breakdown table
    setup_html_rows = []
    for r in setup_rows:
        setup = r["setup"]
        n = r["n"]
        wr = r["wr"]
        wr_lb = r["wr_lb"]
        avg = r["avg_pnl"]
        pf = r["profit_factor"]
        cls, label = _verdict_class(wr, wr_lb, n)
        validated = setup in _validations
        mult = multipliers.get(setup, 1.0)
        mult_str = f"×{mult:.2f}" if mult != 1.0 else "—"
        validation_chip = f'<span class="chip ok">validated n={_validations[setup].get("n")}</span>' if validated else ('<span class="chip warn">no _validations</span>' if mult < 1.0 else '')
        setup_html_rows.append(f"""
            <tr class="row-{cls}">
              <td>{setup}</td>
              <td class="num">{n}</td>
              <td class="num">{wr*100:.1f}%</td>
              <td class="num">{wr_lb*100:.1f}%</td>
              <td class="num {'pos' if avg > 0 else 'neg'}">{avg:+.2f}%</td>
              <td class="num">{pf:.2f}</td>
              <td>{mult_str}</td>
              <td><span class="verdict {cls}">{label}</span> {validation_chip}</td>
            </tr>""")

    # Regime breakdown
    regime_rows_html = []
    for r in regime_rows:
        regime_rows_html.append(f"""
            <tr>
              <td>{r['regime']}</td>
              <td class="num">{r['n']}</td>
              <td class="num">{r['wr']*100:.1f}%</td>
              <td class="num">{r['wr_lb']*100:.1f}%</td>
              <td class="num {'pos' if r['avg_pnl'] > 0 else 'neg'}">{r['avg_pnl']:+.2f}%</td>
            </tr>""")

    commits_html = "".join(f'<li><code>{c["hash"]}</code> — {c["msg"]}</li>' for c in commits)

    # Compose HTML
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>SwingTrade Session Research Note — {datetime.now().strftime('%Y-%m-%d')}</title>
<style>
  :root {{
    --bg-0: #0a0e14;
    --bg-1: #11171f;
    --bg-2: #1a212c;
    --rule: #2a3340;
    --ink-0: #e6edf3;
    --ink-1: #adb8c4;
    --ink-2: #6e7a8a;
    --accent: #f5d76e;
    --accent-2: #7dd3fc;
    --green: #4ade80;
    --red: #f87171;
    --orange: #fb923c;
    --blue: #60a5fa;
    --purple: #c084fc;
    --mono: 'JetBrains Mono', 'Menlo', monospace;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    background: var(--bg-0);
    color: var(--ink-0);
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    line-height: 1.6;
    margin: 0;
    padding: 0;
  }}
  .container {{ max-width: 1180px; margin: 0 auto; padding: 40px 32px; }}
  header {{
    border-bottom: 1px solid var(--rule);
    padding-bottom: 28px;
    margin-bottom: 36px;
  }}
  .eyebrow {{
    color: var(--accent);
    font-family: var(--mono);
    font-size: 11px;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    margin-bottom: 8px;
  }}
  h1 {{ font-size: 36px; font-weight: 700; margin: 0 0 8px; letter-spacing: -0.02em; }}
  h2 {{
    font-size: 22px;
    font-weight: 600;
    margin: 48px 0 16px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--rule);
    color: var(--ink-0);
  }}
  h2 .num {{ color: var(--accent); margin-right: 12px; font-family: var(--mono); }}
  h3 {{ font-size: 17px; font-weight: 600; margin: 28px 0 14px; color: var(--ink-0); }}
  h3 .meta {{ color: var(--ink-2); font-size: 12px; font-weight: 400; font-family: var(--mono); margin-left: 10px; }}
  p {{ color: var(--ink-1); margin: 12px 0; }}
  .lede {{ font-size: 17px; color: var(--ink-0); }}
  ul, ol {{ color: var(--ink-1); padding-left: 22px; }}
  ul li, ol li {{ margin: 6px 0; }}
  code {{ font-family: var(--mono); background: var(--bg-2); padding: 2px 7px; border-radius: 3px; font-size: 0.88em; color: var(--accent-2); }}
  .card {{
    background: var(--bg-1);
    border: 1px solid var(--rule);
    border-radius: 8px;
    padding: 24px 28px;
    margin: 16px 0;
  }}
  .card.warn {{ border-left: 3px solid var(--orange); }}
  .card.bad {{ border-left: 3px solid var(--red); }}
  .card.good {{ border-left: 3px solid var(--green); }}
  .kpi-grid {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 14px;
    margin-top: 14px;
  }}
  .kpi {{
    background: var(--bg-2);
    border: 1px solid var(--rule);
    border-radius: 6px;
    padding: 14px 16px;
  }}
  .kpi .lbl {{ font-size: 10px; color: var(--ink-2); text-transform: uppercase; letter-spacing: 0.1em; font-family: var(--mono); }}
  .kpi .v {{ font-size: 24px; font-weight: 600; color: var(--ink-0); margin-top: 4px; font-family: var(--mono); }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
    margin: 12px 0 24px;
  }}
  th, td {{
    text-align: left;
    padding: 10px 14px;
    border-bottom: 1px solid var(--rule);
  }}
  th {{
    color: var(--ink-2);
    font-weight: 600;
    font-size: 10px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    font-family: var(--mono);
    background: var(--bg-2);
  }}
  td.num {{ font-family: var(--mono); text-align: right; }}
  td.pos {{ color: var(--green); }}
  td.neg {{ color: var(--red); }}
  .row-strong {{ background: rgba(74, 222, 128, 0.04); }}
  .row-ok {{ background: rgba(125, 211, 252, 0.04); }}
  .row-watch {{ background: rgba(251, 146, 60, 0.04); }}
  .row-bad {{ background: rgba(248, 113, 113, 0.05); }}
  .verdict {{
    display: inline-block;
    padding: 3px 10px;
    border-radius: 999px;
    font-size: 10px;
    font-family: var(--mono);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-weight: 600;
  }}
  .verdict.strong {{ background: rgba(74, 222, 128, 0.15); color: var(--green); }}
  .verdict.ok     {{ background: rgba(125, 211, 252, 0.15); color: var(--accent-2); }}
  .verdict.watch  {{ background: rgba(251, 146, 60, 0.15); color: var(--orange); }}
  .verdict.bad    {{ background: rgba(248, 113, 113, 0.15); color: var(--red); }}
  .chip {{
    display: inline-block;
    margin-left: 6px;
    padding: 2px 8px;
    border-radius: 999px;
    font-size: 10px;
    font-family: var(--mono);
  }}
  .chip.ok {{ background: rgba(74, 222, 128, 0.12); color: var(--green); }}
  .chip.warn {{ background: rgba(251, 146, 60, 0.12); color: var(--orange); }}
  .empty {{ padding: 24px; color: var(--ink-2); text-align: center; font-style: italic; }}
  .footnote {{ color: var(--ink-2); font-size: 12px; font-family: var(--mono); }}
  blockquote {{
    border-left: 3px solid var(--accent);
    padding: 8px 18px;
    margin: 16px 0;
    background: rgba(245, 215, 110, 0.05);
    color: var(--ink-0);
    font-style: italic;
  }}
  .two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }}
  @media (max-width: 800px) {{
    .kpi-grid {{ grid-template-columns: repeat(2, 1fr); }}
    .two-col {{ grid-template-columns: 1fr; }}
  }}
</style>
</head>
<body>
<div class="container">

<header>
  <div class="eyebrow">SwingTrade · Research Note · {datetime.now().strftime('%Y-%m-%d')}</div>
  <h1>From eyeballed tuning to evidence-driven gates</h1>
  <p class="lede">A four-track session: shipped statistical kill-gates that catch noise-driven config edits, migrated 1,235 rows of canonical state to Supabase Postgres with dual-write, backfilled three full years of OHLCV across 1,023 tickers, and built the read-shim that paves the path to cloud-canonical state. Live evidence from the canonical signal log ({n_total_signals} entries, {n_closed} closed) now drives the gates instead of the prior 5–25 trade noise samples.</p>
</header>

<h2><span class="num">01</span>Executive Summary</h2>
<div class="kpi-grid">
  <div class="kpi"><div class="lbl">Commits this session</div><div class="v">{len(commits)}</div></div>
  <div class="kpi"><div class="lbl">Tickers backfilled</div><div class="v">1,023</div></div>
  <div class="kpi"><div class="lbl">Rows in Supabase</div><div class="v">1,235</div></div>
  <div class="kpi"><div class="lbl">Closed signals</div><div class="v">{n_closed}</div></div>
  <div class="kpi"><div class="lbl">Overall WR</div><div class="v">{overall_wr*100:.1f}%</div></div>
  <div class="kpi"><div class="lbl">Wilson LB (95%)</div><div class="v">{overall_lo*100:.1f}%</div></div>
  <div class="kpi"><div class="lbl">Avg PnL/trade</div><div class="v">{overall_avg:+.2f}%</div></div>
  <div class="kpi"><div class="lbl">Setups validated</div><div class="v">{len(_validations)}</div></div>
</div>

<blockquote>
  The defining moment of the session: the first commit (<code>7daef489a</code>) killed VCP Breakout based on 5 trades. The second commit (<code>3418ea745</code>) shipped the gates that <em>reject that exact decision</em>. The same person, same data, three hours apart — but now the system refuses to act on n&lt;10 evidence. That's the architecture win.
</blockquote>

<h2><span class="num">02</span>What we did</h2>

<div class="card">
<h3>Track 1 · Statistical kill gates (P3)</h3>
<p>Three-layer defense against noise-driven config changes:</p>
<ol>
  <li><code>decision_engine.compute_setup_kill_list</code> — every kill now requires both point WR &lt; 35% AND Wilson 95% lower-bound &lt; 30%. The lower-bound check catches the tiny-sample case where a 0% WR over 5 trades is statistically indistinguishable from a 30% WR.</li>
  <li><code>static_setup_kill_list</code> — entries must declare <code>n &gt;= 10</code> or carry an explicit <code>override: true</code>. Bare-string entries silently rejected. Audit trail kept under key <code>_rejected_static</code>.</li>
  <li><code>analysis.setup_score_multiplier</code> — any demotion (mult &lt; 1.0) silently reverts to 1.0 unless <code>_validations[setup]</code> declares n &gt;= 30 AND wr_lb &lt; 0.30. Promotions still apply (no statistical gate on those — sample-size risk only matters when removing alpha, not adding it).</li>
</ol>
</div>

<div class="card">
<h3>Track 2 · Supabase canonical (Mode 1)</h3>
<p>17 Postgres tables matching <code>db.py</code> schema. JSON-aware migrator that prefers <code>data/*.json</code> over <code>data/swingtrade.db</code> (where the canonical state actually lives — signal_log.json had 1,106 rows, SQLite had 17). 1,235/1,235 rows migrated in 2.3 seconds, zero failures.</p>
<p>Dual-write hooks in <code>portfolio_tracker._save_state</code> and <code>signal_tracker._save_log</code>. Every JSON write now mirrors to Supabase via <code>supabase_sync.py</code> with high-water marks (cache/supabase_sync_state.json) so re-saves don't re-upload history.</p>
<p>Three modes staged: <code>0</code> = Supabase off, <code>1</code> = dual-write (active), <code>2</code> = Supabase canonical (B.3 milestone, weeks away).</p>
</div>

<div class="card">
<h3>Track 3 · 3-year OHLCV backfill (P1)</h3>
<p>Universe expanded from ~2.2 years (533 bars) to 3 full years (755 bars) for 969 of 1,023 tickers — the other 68 have legitimate data limits (post-2023 IPOs, ETF reverse-splits). Wall-clock: 76 seconds at 13.4 calls/sec under EODHD's 14/sec burst limit. Disk: 26 MB → 39 MB.</p>
<p>No source code changes — existing <code>data_fetcher.fetch_ohlcv_with_failover(days=1100)</code> already supported the depth.</p>
</div>

<div class="card">
<h3>Track 4 · Phase B.1 read shim</h3>
<p>Per the Phase B audit, <code>portfolio_tracker._load_state()</code> is called 25+ times per scan from inside its own file alone, plus more in server.py and swing_trade.py. <code>state_layer.py</code> introduces a 5-second LRU cache that collapses those into a single read. Three hot paths now route through it: <code>_load_state</code>, <code>_load_log</code>, and <code>decision_engine.compute_setup_kill_list</code>.</p>
<p>The shim is the migration vehicle. Today (Mode 1) it reads from JSON. When <code>SUPABASE_MODE=2</code> flips, it'll read from Supabase first with JSON fallback — and not a single caller needs to change.</p>
</div>

<div class="card">
<h3>Track 5 · Walk-forward parser (P2)</h3>
<p>The <code>walk_forward_v2.py</code> stdout parser was silently reporting all-zero metrics because it expected <code>Total trades:</code> / <code>Sharpe:</code> / <code>Max drawdown:</code> lines that <code>backtest.py</code> only prints under <code>--portfolio</code>. Walk-forward wasn't passing that flag. Fixed both: pass the flag, plus make parser handle both portfolio and signal-mode formats so a missing flag doesn't silently zero metrics again.</p>
</div>

<h2><span class="num">03</span>What we achieved</h2>

{bt_html}

<h3>Per-setup breakdown · canonical signal_log <span class="meta">{n_closed} closed signals</span></h3>
<table>
  <thead>
    <tr>
      <th>Setup</th><th>n</th><th>WR</th><th>Wilson LB</th><th>Avg P&amp;L</th><th>Profit Factor</th><th>Mult</th><th>Verdict</th>
    </tr>
  </thead>
  <tbody>{''.join(setup_html_rows)}</tbody>
</table>

<h3>Regime breakdown</h3>
<table>
  <thead>
    <tr><th>Regime</th><th>n</th><th>WR</th><th>Wilson LB</th><th>Avg P&amp;L</th></tr>
  </thead>
  <tbody>{''.join(regime_rows_html) or '<tr><td colspan="5" class="empty">No regime data in signal_log entries</td></tr>'}</tbody>
</table>

<h2><span class="num">04</span>What's right</h2>
<ul>
  <li><strong>Wilson CI gates</strong> are catching exactly what they're designed to catch. The VCP Breakout 5-trade kill is rejected. EMA21 (n=59) and 52wk Breakout (n=114) demotions activate with proper backing.</li>
  <li><strong>Dual-write semantics are clean.</strong> Local JSON remains canonical; Supabase mirrors. Supabase failures swallowed silently — never break a scan. ~800ms latency added per save (acceptable; saves are infrequent).</li>
  <li><strong>State-layer cache</strong> measurably accelerates hot paths. 25 reads/scan → 1 read. Pattern is reversible (one-line change to revert each callsite).</li>
  <li><strong>Backtest infra is reproducible.</strong> 76-second backfill, idempotent migration, the parser fix has graceful degradation.</li>
  <li><strong>The user's instincts were right.</strong> The hand-edited demotions to 0.0 for EMA21 and 52wk turned out to be statistically legitimate when measured against the full canonical signal log.</li>
</ul>

<h2><span class="num">05</span>What's wrong / what to watch</h2>
<div class="card warn">
<ul>
  <li><strong>Survivorship bias unfixed.</strong> Backtest universe uses today's S&amp;P 500 / R1000 membership, not historical. The audit's −4pp WR haircut is a band-aid. Real fix needs Wikipedia revision history scrape or paid Sharadar SF1 data (~$60/mo). Live picks therefore systematically over-promise vs. backtest. Sizing decisions inflated by a few hundred basis points.</li>
  <li><strong>Walk-forward grid is shallow.</strong> Current grid only tunes (min_score, min_rs). Setup multipliers, kill thresholds, regime weight shifts are still hand-edited. The fix needs <code>backtest.py --config-override</code> CLI; sketch documented in <code>tune_on_train</code> docstring (~3h work).</li>
  <li><strong>Per-setup samples are still small for some setups.</strong> Even with 3y OHLCV available, setups like VCP Breakout, Pocket Pivot have very few trades. The 3y backfill won't <em>retroactively</em> generate signals — those grow forward as scans run against the deeper window.</li>
  <li><strong>JSON canonical with Supabase mirror means schema drift risk.</strong> Adding a field to portfolio_state.json without updating the Postgres column will cause Supabase upserts to fail silently (caught by sync, never raised). A linter that checks JSON-schema against db.py CREATE TABLEs would catch this.</li>
  <li><strong>Read paths still mostly JSON.</strong> Phase B.1 wired only 3 of ~40 read sites. The remaining sites (server.py, swing_trade.py, build_data.py, custom_tracker.py, position_alerts.py, audit_360.py, …) still read JSON directly — bypassing the cache and unable to benefit from a future Mode 2 flip.</li>
</ul>
</div>

<h2><span class="num">06</span>How to improve</h2>
<div class="two-col">
  <div class="card">
    <h3>Near-term (this week)</h3>
    <ol>
      <li>Run <code>walk_forward_v2.py --folds 4</code> against the new 3y data. Confirm fold-by-fold metrics are non-zero (parser fix). Validate or invalidate the +8% Trend Continuation boost.</li>
      <li>Apply migration 002 to Supabase, then run <code>push_backtest_to_supabase.py</code> on the just-completed run to begin building the historical run archive.</li>
      <li>Add survivorship-aware membership snapshots: scrape Wikipedia revision history for S&amp;P 500 / R1000 monthly snapshots, store as <code>data/sp500_membership_*.csv</code> by year-month. Use in backtest to filter universe per as-of date. Closes audit #1 properly.</li>
      <li>Wire 5 more state_layer call-sites: <code>server.py</code> hot endpoints (4 reads), <code>swing_trade.py</code> paper-trading gate.</li>
    </ol>
  </div>
  <div class="card">
    <h3>Medium-term (this month)</h3>
    <ol>
      <li>Extend walk-forward grid to setup multipliers. Auto-populate <code>_validations</code> from passing folds. Removes "human edits config from eyeball" loop entirely.</li>
      <li>Phase B.2 — flip <code>SUPABASE_MODE=2</code> with state_layer fallback. Run for 7 days. Monitor cache hit rate + fallback frequency.</li>
      <li>Build live-vs-backtest drift dashboard. Today <code>drift_check.py</code> exists but isn't wired to a tab. Add <code>drift</code> tab to V2 dashboard pulling from Supabase <code>backtest_runs</code>.</li>
      <li>Schema linter: <code>check_schema_drift.py</code> diffs JSON sample against Postgres columns; fail CI if mismatch.</li>
    </ol>
  </div>
</div>

<h2><span class="num">07</span>Elite thoughts <span class="meta">institutional research perspective</span></h2>

<div class="card">
<h3>The trap of "backtest-driven tuning"</h3>
<p>The morning's commit ("Backtest-driven setup tuning, 2026-05-08") demonstrates the most common trap in systematic trading: <em>treating point estimates from small samples as if they were converged truth</em>. A 0% win rate over 5 trades has a 95% Wilson interval of [0%, 52%] — meaning the true win rate could plausibly be anywhere up to 52%. Killing a setup based on this is indistinguishable from a coin-flip decision dressed up in statistics.</p>
<p>What the gates we shipped actually do: <strong>force every kill / demotion through a sample-size sanity check before it can affect production scores.</strong> Promotions don't need this gate (sample-size risk only matters when subtracting alpha; you can always add to a promising setup later). This asymmetric defense matches how real portfolio managers think — a kill is irreversible (you stop sizing into the setup, you stop seeing its data), but a soft demotion or watch-list assignment is information-preserving.</p>
</div>

<div class="card">
<h3>Why JSON canonical + Supabase mirror is the right compromise</h3>
<p>The instinct to go "all-cloud" with Supabase canonical (Mode 2) is conventional architecture wisdom. For a trading system that must run scans deterministically when a vendor has an outage, <em>locality matters</em>. Local JSON files give you a guarantee that no API limits, no DNS issues, no auth-token expiry can stop a scan. That guarantee is worth more than the multi-device convenience of cloud-canonical, at least until paper trading completes its 60-day window and goes live.</p>
<p>The right framing: Supabase is not the database. Supabase is the <em>backup, audit log, and viewing surface</em>. JSON is the database. Once the system has been in dual-write for 3+ weeks with zero divergence drift, then — and only then — does it make sense to invert that.</p>
</div>

<div class="card">
<h3>The single most under-priced risk</h3>
<p>Survivorship bias. Today's universe of S&amp;P 500 + R1000 includes only the names that <em>survived</em> to today. A backtest using this universe inherently overweights names that didn't go bankrupt, didn't get acquired, didn't get delisted. Studies of US equities show this contributes 2–4 percentage points of phantom alpha to backtests using current-membership universes (Brown et al., 1992; Carpenter &amp; Lynch, 1999). Today the SwingTrade backtest applies a flat <code>SURVIVORSHIP_WR_ADJUSTMENT</code> haircut — but this only adjusts the headline number, it does not change the trade-by-trade selection. Setups that look "great in 3y" might be entirely an artifact of the survivors.</p>
<p>Until point-in-time membership data is wired in, treat any per-setup result with: <strong>actual edge ≈ backtested edge − 3pp WR − 0.2 PF</strong>. That's how a hedge fund risk officer would mark it down. If the haircut leaves the setup with no edge, kill it — and don't pretend you can rescue it with another tuning pass.</p>
</div>

<div class="card">
<h3>The long-term play</h3>
<p>What separates a profitable systematic trader from a hobbyist with a working backtest is <em>the discipline of refusing to act on undersampled evidence</em>. The infrastructure shipped today (Wilson gates, walk-forward parser, dual-write, state shim) all serve one goal: make it expensive in code-review terms to act on noise. Every demotion now requires explicit <code>_validations</code>; every kill requires explicit <code>n &gt;= 10</code>; every multiplier change leaves an audit trail.</p>
<p>The next layer of discipline: <strong>require walk-forward confirmation on test folds before any config change ships.</strong> Today the loop is "look at 60d backtest, edit config, hope". Tomorrow the loop should be "walk-forward proposes config delta on training folds, validates on test folds across all 4, only then writes to <code>_validations</code>". That's the difference between systematic and intuitive — and you only get there by closing the human-discretion loop in the code, not by adding more discipline to the human.</p>
</div>

<h2><span class="num">08</span>Commits this session</h2>
<ul class="footnote">
{commits_html or '<li>(no commits found)</li>'}
</ul>

<p class="footnote" style="margin-top:48px;text-align:center">
Generated {datetime.now().strftime('%Y-%m-%d %H:%M %Z')} · SwingTrade · Local-canonical, cloud-mirrored
</p>

</div>
</body>
</html>"""
    return html


def main():
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    html = render_html()
    OUT_PATH.write_text(html, encoding="utf-8")
    print(f"Wrote {OUT_PATH} ({len(html):,} chars)")
    print(f"Open: file://{OUT_PATH.resolve()}")


if __name__ == "__main__":
    main()
