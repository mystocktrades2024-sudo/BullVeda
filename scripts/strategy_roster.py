#!/usr/bin/env python3
"""strategy_roster.py — generate shareable HTML page of all strategies by regime.

Output:
  cache/strategy_roster.html (file)
  DB html_snapshots kind='strategy-roster' (archive)
  https://trade.mystockholding.com/reports/latest/strategy-roster (web)

Usage:
  python3 scripts/strategy_roster.py
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def _load_bundle() -> dict:
    p = REPO / "cache" / "last_bundle.json"
    return json.loads(p.read_text()) if p.exists() else {}


STRATEGY_SPECS = [
    {
        "name": "Pullback to Value",
        "icon": "⭐",
        "type": "core",
        "mechanism": "Buy retracement to EMA/support · 3:1 R:R minimum",
        "regimes": ["risk_on_trending", "risk_on_choppy"],
        "primary_regime": "risk_on_choppy",
        "evidence": "Live · backtested PF 1.41",
        "status": "LIVE",
        "status_color": "#00d68f",
        "academic_ref": "Default scoring engine",
        "config_key": None,
        "produces_families": ["Trend Continuation", "Breakout Expansion", "Impulse Catalyst", "Special Situation"],
    },
    {
        "name": "Momentum Continuation",
        "icon": "🚀",
        "type": "sleeve",
        "mechanism": "Buy strength · ADX≥25 · Sharpe≥1.5 · EMA stack · 5d return ≥+3%",
        "regimes": ["risk_on_trending", "bull"],
        "primary_regime": "risk_on_trending",
        "evidence": "Backtested PF 1.53 (n=2,553) ✓",
        "status": "ENABLED",
        "status_color": "#00d68f",
        "academic_ref": "Trend persistence + breakout literature",
        "config_key": "momentum_sleeve",
        "produces_families": ["Momentum Continuation"],
    },
    {
        "name": "Defensive Rotation",
        "icon": "🛡️",
        "type": "sleeve",
        "mechanism": "Long XLU + GLD when SPY < 50EMA · flight-to-safety bid",
        "regimes": ["risk_off_trending", "panic", "risk_on_choppy"],
        "primary_regime": "risk_off_trending",
        "evidence": "Backtested PF 1.03 (marginal)",
        "status": "ENABLED",
        "status_color": "#ffb800",
        "academic_ref": "Federal Reserve flow data, CRSP returns",
        "config_key": "defensive_rotation_sleeve",
        "produces_families": ["Defensive Rotation"],
    },
    {
        "name": "Mean Reversion",
        "icon": "🔄",
        "type": "sleeve",
        "mechanism": "RSI<30 + price>EMA200 + recent low w/in 5d + RVOL≥1.0",
        "regimes": ["risk_on_choppy", "bull"],
        "primary_regime": "risk_on_choppy",
        "evidence": "Backtested PF 1.21 (borderline)",
        "status": "ENABLED",
        "status_color": "#ffb800",
        "academic_ref": "Jegadeesh 1990, Lehmann 1990, Conrad-Kaul 1989",
        "config_key": "mean_reversion_sleeve",
        "produces_families": ["Mean Reversion"],
    },
    {
        "name": "PEAD",
        "icon": "🎯",
        "type": "sleeve",
        "mechanism": "1-3d post-earnings + EPS surprise ≥10% + gap 3-8%",
        "regimes": ["risk_on_trending", "risk_on_choppy", "risk_off_trending", "panic"],
        "primary_regime": "ALL (catalyst-driven)",
        "evidence": "Backtested PF 2.04 (tightened thresholds) ✓",
        "status": "ENABLED",
        "status_color": "#00d68f",
        "academic_ref": "Bernard-Thomas 1989, Ball-Brown 1968",
        "config_key": "pead_sleeve",
        "produces_families": ["PEAD"],
    },
    {
        "name": "Insider Cluster",
        "icon": "👥",
        "type": "sleeve",
        "mechanism": "≥3 insider buys + ≥$200K total OR CEO/CFO buy + price>EMA50",
        "regimes": ["risk_on_trending", "risk_on_choppy", "risk_off_trending", "panic"],
        "primary_regime": "ALL (info edge)",
        "evidence": "Dollar-evidence gate added 2026-05-14 (fixed 165 false-positive overflow)",
        "status": "ENABLED",
        "status_color": "#ffb800",
        "academic_ref": "Bettis-Coles-Lemmon 2000, Cohen-Malloy-Pomorski 2012",
        "config_key": "insider_cluster_sleeve",
        "produces_families": ["Insider Cluster"],
    },
    {
        "name": "ESP Play",
        "icon": "📊",
        "type": "sleeve",
        "mechanism": "Zacks ESP>0 + Rank≤3 + earnings 4-14d away · pre-earnings drift",
        "regimes": ["risk_on_trending", "risk_on_choppy", "risk_off_trending", "panic"],
        "primary_regime": "ALL (catalyst)",
        "evidence": "Zacks: ~70% beat rate · 25y · 100K reports",
        "status": "ENABLED",
        "status_color": "#ffb800",
        "academic_ref": "Zacks Earnings ESP Filter (proprietary)",
        "config_key": "esp_play_sleeve",
        "produces_families": ["ESP Play"],
    },
    {
        "name": "Pre-FOMC Drift",
        "icon": "🔸",
        "type": "overlay",
        "mechanism": "Multiply long sizing 1.25× on T-1 to scheduled FOMC (Lucca-Moench)",
        "regimes": ["risk_on_trending", "risk_on_choppy", "risk_off_trending", "panic"],
        "primary_regime": "Calendar event",
        "evidence": "Pre-2008: ~80% of equity premium pre-FOMC · Post-2008 reduced (~50%)",
        "status": "ARMED",
        "status_color": "#00d4ff",
        "academic_ref": "Lucca-Moench 2015 (Journal of Finance)",
        "config_key": "prefomc_drift_overlay",
        "produces_families": ["overlay — multiplies existing sleeve sizing"],
    },
]


REGIMES = [
    {"key": "risk_on_trending", "label": "Risk-On Trending", "emoji": "🟢",
     "desc": "SPY > 50/200 EMA · VIX < 18 · Breadth > 65%",
     "color": "#00d68f", "bg": "rgba(0, 214, 143, 0.08)"},
    {"key": "risk_on_choppy", "label": "Risk-On Choppy", "emoji": "🟡",
     "desc": "SPY > 50EMA · VIX 18-25 · Breadth 40-65%",
     "color": "#ffb800", "bg": "rgba(255, 184, 0, 0.08)"},
    {"key": "risk_off_trending", "label": "Risk-Off Trending", "emoji": "🟠",
     "desc": "SPY < 50EMA · VIX 25-35 · Breadth 20-40%",
     "color": "#ff7a00", "bg": "rgba(255, 122, 0, 0.10)"},
    {"key": "panic", "label": "Panic", "emoji": "🔴",
     "desc": "VIX > 35 OR Breadth < 20%",
     "color": "#ff4d4f", "bg": "rgba(255, 77, 79, 0.10)"},
]


def _strat_eligible(strat: dict, regime_key: str) -> tuple[bool, str]:
    """Returns (active, label). label is 'primary', 'fires', 'conditional', or 'dormant'."""
    if strat["type"] == "core":
        if regime_key in strat["regimes"]:
            return True, "primary" if regime_key == strat["primary_regime"] else "fires"
        return False, "dormant"
    if strat["type"] == "overlay":
        return False, "calendar"  # only on T-1 FOMC
    if regime_key in strat["regimes"]:
        if regime_key == strat["primary_regime"] or strat["primary_regime"].startswith("ALL"):
            return True, "primary"
        return True, "fires"
    return False, "dormant"


def _render_matrix_cell(strat: dict, regime_key: str) -> str:
    active, label = _strat_eligible(strat, regime_key)
    if label == "primary":
        return '<td class="cell active primary">🟢 PRIMARY</td>'
    if label == "fires":
        return '<td class="cell active">🟢 fires</td>'
    if label == "calendar":
        return '<td class="cell calendar">⏰ on FOMC</td>'
    return '<td class="cell dormant">⚪ dormant</td>'


def _render_strategy_card(strat: dict) -> str:
    regime_chips = ""
    for r in REGIMES:
        active, label = _strat_eligible(strat, r["key"])
        if active:
            regime_chips += f'<span class="chip chip-active" style="background:{r["bg"]};color:{r["color"]};border-color:{r["color"]}">{r["emoji"]} {r["label"]}</span>'
    families_str = " · ".join(strat["produces_families"])
    type_icon = {"core": "⭐ CORE ENGINE", "sleeve": "🔹 SLEEVE", "overlay": "🔸 OVERLAY"}[strat["type"]]
    return f"""
    <div class="strat-card">
      <div class="strat-head">
        <div class="strat-name">
          <span class="strat-icon">{strat['icon']}</span>
          <span class="strat-title">{strat['name']}</span>
        </div>
        <div class="strat-meta">
          <span class="type-tag">{type_icon}</span>
          <span class="status-tag" style="color:{strat['status_color']};border-color:{strat['status_color']}">{strat['status']}</span>
        </div>
      </div>
      <div class="strat-body">
        <div class="strat-mech"><b>Mechanism:</b> {strat['mechanism']}</div>
        <div class="strat-row">
          <div class="strat-cell">
            <div class="cell-label">Active in regime</div>
            <div class="chip-row">{regime_chips}</div>
          </div>
        </div>
        <div class="strat-row two-col">
          <div class="strat-cell">
            <div class="cell-label">Evidence</div>
            <div class="cell-val">{strat['evidence']}</div>
          </div>
          <div class="strat-cell">
            <div class="cell-label">Academic Reference</div>
            <div class="cell-val">{strat['academic_ref']}</div>
          </div>
        </div>
        <div class="strat-row">
          <div class="strat-cell">
            <div class="cell-label">Produces signal type</div>
            <div class="cell-val mono">{families_str}</div>
          </div>
        </div>
      </div>
    </div>"""


def render_html(current_regime: str = None) -> str:
    today_str = date.today().strftime("%A · %B %-d, %Y").upper()
    time_str = datetime.now().strftime("%-I:%M %p PT")

    # Build matrix
    matrix_header_cells = "".join(
        f'<th class="regime-col" style="background:{r["bg"]};color:{r["color"]}">'
        f'<div class="regime-emoji">{r["emoji"]}</div>'
        f'<div class="regime-label">{r["label"]}</div>'
        f'<div class="regime-desc">{r["desc"]}</div>'
        f'</th>'
        for r in REGIMES
    )
    matrix_rows = ""
    for strat in STRATEGY_SPECS:
        cells = "".join(_render_matrix_cell(strat, r["key"]) for r in REGIMES)
        type_emo = {"core": "⭐", "sleeve": "🔹", "overlay": "🔸"}[strat["type"]]
        matrix_rows += f"""
        <tr>
          <td class="strat-label">
            <span class="strat-icon-sm">{strat['icon']}</span>
            <span class="strat-name-sm">{strat['name']}</span>
            <span class="strat-type-sm">{type_emo} {strat['type']}</span>
          </td>
          {cells}
        </tr>"""

    # Build cards
    cards_html = "".join(_render_strategy_card(s) for s in STRATEGY_SPECS)

    # Today's regime highlight
    today_banner = ""
    if current_regime:
        cr = next((r for r in REGIMES if r["key"] == current_regime), None)
        if cr:
            today_banner = f"""
            <div class="today-banner" style="background:{cr['bg']};border-left:4px solid {cr['color']}">
              <div class="today-label">CURRENT REGIME</div>
              <div class="today-name">{cr['emoji']} {cr['label']}</div>
              <div class="today-desc">{cr['desc']}</div>
            </div>"""

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>SwingTrade · Strategy Roster by Regime</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  * {{ box-sizing:border-box; }}
  body {{ background:#000; color:#e8e8e8; margin:0;
         font-family:'Inter',-apple-system,BlinkMacSystemFont,Helvetica,sans-serif;
         font-feature-settings:'tnum' 1, 'ss01' 1; line-height:1.5; }}
  .frame {{ max-width:1100px; margin:0 auto; padding:0 16px 60px; }}

  /* Masthead */
  .masthead {{ padding:32px 0 20px; border-bottom:2px solid #ff7a00; margin-bottom:24px; }}
  .masthead-row {{ display:flex; align-items:baseline; gap:16px; }}
  .brand {{ font-size:28px; font-weight:800; letter-spacing:-0.5px;
           color:#fff; line-height:1; }}
  .brand-bar {{ display:inline-block; width:4px; height:24px;
               background:#ff7a00; margin-right:10px; vertical-align:middle; }}
  .edition {{ font-size:11px; color:#888; letter-spacing:2px; text-transform:uppercase;
             font-weight:600; margin-top:6px; }}
  .date-bar {{ font-size:11px; color:#888; font-weight:500; letter-spacing:1px;
              margin-left:auto; text-align:right; }}
  .date-day {{ color:#ff7a00; font-weight:700; }}

  h1 {{ font-size:24px; color:#fff; margin:24px 0 8px; font-weight:700;
       letter-spacing:-0.5px; }}
  h2 {{ font-size:12px; color:#ff7a00; letter-spacing:2px; text-transform:uppercase;
       font-weight:700; margin:32px 0 14px; padding-bottom:8px;
       border-bottom:1px solid #222; }}
  .subhead {{ color:#888; font-size:14px; margin-bottom:16px; }}

  /* Today banner */
  .today-banner {{ padding:14px 18px; margin:20px 0 28px;
                  border-radius:4px; }}
  .today-label {{ font-size:10px; color:#888; letter-spacing:2px;
                 text-transform:uppercase; font-weight:600; }}
  .today-name {{ font-size:20px; font-weight:700; color:#fff; margin-top:4px; }}
  .today-desc {{ font-size:13px; color:#bbb; margin-top:2px;
                font-family:'JetBrains Mono',monospace; }}

  /* Regime descriptions block */
  .regime-grid {{ display:grid; grid-template-columns:repeat(4, 1fr);
                 gap:1px; background:#222; padding:1px; border:1px solid #222; }}
  .regime-grid > div {{ background:#0a0a0a; padding:14px; }}
  .regime-card-emoji {{ font-size:24px; }}
  .regime-card-name {{ font-size:13px; font-weight:600; color:#fff; margin:6px 0 4px; }}
  .regime-card-desc {{ font-size:11px; color:#888;
                      font-family:'JetBrains Mono',monospace; line-height:1.4; }}

  /* Matrix */
  .matrix {{ width:100%; border-collapse:separate; border-spacing:1px;
            background:#222; margin-top:8px; }}
  .matrix th, .matrix td {{ background:#0a0a0a; padding:10px 12px;
                            font-size:12px; text-align:left; vertical-align:middle; }}
  .matrix th {{ font-weight:600; }}
  .strat-col-head {{ width:240px; background:#161616 !important;
                    font-size:10px; color:#888; letter-spacing:1.5px;
                    text-transform:uppercase; }}
  .regime-col {{ text-align:center !important; vertical-align:top !important;
                font-weight:600; padding:14px 8px !important; }}
  .regime-emoji {{ font-size:18px; }}
  .regime-label {{ font-size:11px; letter-spacing:0.5px; margin-top:2px; }}
  .regime-desc {{ font-size:9px; color:#888; margin-top:3px;
                 font-family:'JetBrains Mono',monospace; font-weight:400;
                 letter-spacing:0; line-height:1.3; }}
  .strat-label {{ font-size:13px; color:#fff; padding:14px 12px !important; }}
  .strat-icon-sm {{ margin-right:6px; }}
  .strat-name-sm {{ font-weight:600; }}
  .strat-type-sm {{ display:block; font-size:10px; color:#666; margin-top:2px;
                   font-weight:400; }}
  .cell {{ text-align:center !important; font-size:11px;
          font-family:'JetBrains Mono',monospace; }}
  .cell.active {{ color:#00d68f; font-weight:600; }}
  .cell.active.primary {{ color:#00d4ff; font-weight:700; }}
  .cell.calendar {{ color:#ffb800; }}
  .cell.dormant {{ color:#444; }}

  /* Strategy cards */
  .strat-card {{ background:#0a0a0a; border:1px solid #222;
                border-radius:6px; padding:18px 20px; margin-bottom:14px; }}
  .strat-card:hover {{ border-color:#333; }}
  .strat-head {{ display:flex; align-items:center; gap:12px;
                margin-bottom:14px; padding-bottom:10px;
                border-bottom:1px solid #1a1a1a; }}
  .strat-name {{ flex:1; display:flex; align-items:baseline; gap:10px; }}
  .strat-icon {{ font-size:20px; }}
  .strat-title {{ font-size:18px; font-weight:700; color:#fff;
                 letter-spacing:-0.3px; }}
  .strat-meta {{ display:flex; gap:8px; align-items:center; }}
  .type-tag {{ font-size:10px; color:#888; letter-spacing:1px;
              text-transform:uppercase; }}
  .status-tag {{ font-size:10px; letter-spacing:1.5px; text-transform:uppercase;
                font-weight:700; padding:3px 8px; border:1px solid;
                border-radius:2px; }}
  .strat-mech {{ font-size:13px; color:#ddd; margin-bottom:14px;
                line-height:1.5; }}
  .strat-mech b {{ color:#888; font-weight:500; font-size:11px;
                  text-transform:uppercase; letter-spacing:1px;
                  margin-right:6px; }}
  .strat-row {{ margin-bottom:12px; }}
  .strat-row.two-col {{ display:grid; grid-template-columns:1fr 1fr; gap:14px; }}
  .strat-cell {{ font-size:12px; }}
  .cell-label {{ font-size:10px; color:#666; letter-spacing:1px;
                text-transform:uppercase; font-weight:600;
                margin-bottom:5px; }}
  .cell-val {{ font-size:13px; color:#ccc; }}
  .cell-val.mono {{ font-family:'JetBrains Mono',monospace; font-size:11px;
                   color:#aaa; }}
  .chip-row {{ display:flex; flex-wrap:wrap; gap:6px; }}
  .chip {{ display:inline-block; padding:3px 10px; border-radius:12px;
          font-size:11px; font-weight:500; border:1px solid #333; }}
  .chip-active {{ font-weight:600; }}

  /* Footer */
  footer {{ margin-top:40px; padding-top:20px; border-top:1px solid #222;
           text-align:center; font-size:11px; color:#666; }}
  footer a {{ color:#ff7a00; text-decoration:none; margin:0 14px;
             font-weight:500; letter-spacing:0.5px; }}
  footer a:hover {{ color:#fff; }}
  .disclaimer {{ margin-top:14px; color:#444; font-size:10px;
                line-height:1.5; }}
</style></head>
<body>
<div class="frame">

<div class="masthead">
  <div class="masthead-row">
    <div>
      <div class="brand"><span class="brand-bar"></span>SwingTrade</div>
      <div class="edition">Strategy Roster · By Regime</div>
    </div>
    <div class="date-bar">
      <div class="date-day">{today_str}</div>
      <div style="margin-top:4px">{time_str}</div>
    </div>
  </div>
</div>

<h1>7 Sleeves + 1 Overlay · Active in All 4 Regimes</h1>
<div class="subhead">Every strategy is regime-gated. The matrix below shows which strategies are active in each market regime — by design.</div>

{today_banner}

<h2>4-Regime Classification Model</h2>
<div class="regime-grid">
  {''.join(f'<div><div class="regime-card-emoji">{r["emoji"]}</div><div class="regime-card-name">{r["label"]}</div><div class="regime-card-desc">{r["desc"]}</div></div>' for r in REGIMES)}
</div>

<h2>Strategy × Regime Matrix</h2>
<div class="subhead">🟢 PRIMARY = the regime this strategy is designed for · 🟢 fires = active · ⚪ dormant = correctly off · ⏰ calendar = event-driven</div>
<table class="matrix">
  <thead>
    <tr>
      <th class="strat-col-head">Strategy</th>
      {matrix_header_cells}
    </tr>
  </thead>
  <tbody>{matrix_rows}</tbody>
</table>

<h2>Strategy Detail Cards</h2>
<div class="subhead">Mechanism · Active regimes · Backtest evidence · Academic reference</div>
{cards_html}

<h2>Coverage Summary</h2>
<table class="matrix">
  <thead><tr>
    <th class="strat-col-head">Regime</th>
    <th style="text-align:center">Active Strategies</th>
    <th style="text-align:center">Count</th>
    <th>Expected Daily Volume</th>
  </tr></thead>
  <tbody>
    <tr><td class="strat-label">🟢 risk_on_trending</td><td class="cell">Pullback · Momentum · PEAD · Insider · ESP</td><td class="cell active">5</td><td>High</td></tr>
    <tr><td class="strat-label">🟡 risk_on_choppy</td><td class="cell">Pullback · Mean Rev · PEAD · Insider · ESP</td><td class="cell active">5</td><td>Moderate</td></tr>
    <tr><td class="strat-label">🟠 risk_off_trending</td><td class="cell">Defensive · PEAD · Insider · ESP</td><td class="cell active">4</td><td>Lower (defensive focus)</td></tr>
    <tr><td class="strat-label">🔴 panic</td><td class="cell">Defensive (50% cap) · PEAD (25%) · Insider · ESP</td><td class="cell active">4</td><td>Lowest</td></tr>
  </tbody>
</table>

<h2>CLAUDE.md Principle Alignment</h2>
<table class="matrix">
  <thead><tr><th class="strat-col-head">Principle</th><th>How it shows in this roster</th></tr></thead>
  <tbody>
    <tr><td class="strat-label">1. Statistical rigor</td><td>Each sleeve has Wilson LB + Phase 1 pass floor</td></tr>
    <tr><td class="strat-label">2. Mechanism over correlation</td><td>Each strategy has 1-sentence mechanism + academic ref</td></tr>
    <tr><td class="strat-label">5. Regime conditioning</td><td>This matrix IS principle 5 made explicit</td></tr>
    <tr><td class="strat-label">9. Drawdown asymmetry</td><td>Defensive Rotation closes the bear-regime gap</td></tr>
    <tr><td class="strat-label">14. Catalyst-driven priority</td><td>3 of 7 sleeves are catalyst-led (PEAD, Insider, ESP)</td></tr>
    <tr><td class="strat-label">18. Regime detection IS strategy</td><td>This matrix only works if regime is classified correctly</td></tr>
  </tbody>
</table>

<footer>
  <a href="https://trade.mystockholding.com/kairos.html">Live Dashboard</a>
  <a href="https://trade.mystockholding.com/reports">Report Archive</a>
  <a href="https://trade.mystockholding.com/reports/latest/morning-newsletter">Morning Brief</a>
  <a href="https://trade.mystockholding.com/reports/latest/dashboard">Latest Snapshot</a>
  <div class="disclaimer">
    SwingTrade · 7-strategy systematic engine + 1 calendar overlay · Paper observation phase ·
    Calibration overlay (docs/claude_md_calibration.md) ·
    Educational use only — not investment advice
  </div>
</footer>

</div></body></html>"""
    return html


def main():
    bundle = _load_bundle()
    current_regime = (bundle.get("regime") or {}).get("regime4")
    html = render_html(current_regime=current_regime)

    out_p = REPO / "cache" / "strategy_roster.html"
    out_p.write_text(html)
    print(f"Wrote {out_p}")

    try:
        import db
        snap_id = db.save_html_snapshot(
            kind="strategy-roster",
            html_content=html,
            label=f"Strategy Roster {date.today().isoformat()}",
            meta={"current_regime": current_regime, "n_strategies": len(STRATEGY_SPECS)},
        )
        print(f"Saved to DB: snapshot id={snap_id}")
        print(f"View at: https://trade.mystockholding.com/reports/latest/strategy-roster")
    except Exception as e:
        print(f"DB save failed: {e}")


if __name__ == "__main__":
    main()
