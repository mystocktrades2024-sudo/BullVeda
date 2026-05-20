#!/usr/bin/env python3
"""
generate_strategy_report.py — Comprehensive backtest + regime + strategy HTML report.

Reads cache/picks_history.json (986 trades with full metadata) and
data/signal_log.json (live signals), computes per-regime/per-setup/per-sector
performance matrices with Wilson CI, MAE/MFE stop/target analysis, score-band
calibration, and outputs a self-contained HTML report.

Run: python3 scripts/generate_strategy_report.py [--out path/to/report.html]
"""
from __future__ import annotations
import json, math, statistics, argparse
from pathlib import Path
from collections import defaultdict
from datetime import datetime

BASE = Path(__file__).parent.parent
OUT_DEFAULT = BASE / "cache" / "strategy_report.html"


# ─── Stats helpers ────────────────────────────────────────────────────────────

def wilson_lb(k: int, n: int, z: float = 1.645) -> float:
    """One-sided Wilson 95% lower bound on win rate."""
    if n == 0: return 0.0
    p = k / n
    denom = 1 + z*z/n
    center = (p + z*z/(2*n)) / denom
    margin = z * math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / denom
    return max(0.0, center - margin)

def profit_factor(pnls: list[float]) -> float:
    gains = sum(p for p in pnls if p > 0)
    losses = abs(sum(p for p in pnls if p < 0))
    return round(gains/losses, 2) if losses > 0 else 99.0

def sharpe(pnls: list[float]) -> float:
    if len(pnls) < 2: return 0.0
    mu = statistics.mean(pnls)
    sd = statistics.stdev(pnls)
    return round(mu/sd * math.sqrt(252/5), 2) if sd > 0 else 0.0

def max_drawdown(cumulative: list[float]) -> float:
    """Max drawdown from cumulative return series."""
    peak = cumulative[0] if cumulative else 0
    max_dd = 0.0
    for val in cumulative:
        if val > peak: peak = val
        dd = peak - val
        if dd > max_dd: max_dd = dd
    return round(max_dd, 2)

def stats_row(pnls: list[float], label: str) -> dict:
    n = len(pnls)
    if n == 0:
        return {"label": label, "n": 0, "wr": 0, "avg": 0, "pf": 0, "sharpe": 0, "wilson_lb": 0, "verdict": "INSUFFICIENT"}
    wins = sum(1 for p in pnls if p > 0)
    wr = wins/n
    pf = profit_factor(pnls)
    sh = sharpe(pnls)
    wlb = wilson_lb(wins, n)
    # Verdict
    if n < 10:
        verdict = "INSUFFICIENT"
    elif wlb < 0.45 or pf < 1.0:
        verdict = "KILL"
    elif wlb < 0.50 or pf < 1.15:
        verdict = "REDUCE"
    elif pf >= 1.60 and wlb >= 0.52:
        verdict = "PROMOTE"
    else:
        verdict = "HOLD"
    return {
        "label": label, "n": n, "wr": round(wr*100, 1),
        "avg": round(statistics.mean(pnls), 2),
        "pf": pf, "sharpe": sh, "wilson_lb": round(wlb*100, 1),
        "verdict": verdict,
    }


# ─── Load data ────────────────────────────────────────────────────────────────

def load_trades() -> list[dict]:
    ph_path = BASE / "cache" / "picks_history.json"
    if not ph_path.exists():
        return []
    raw = json.loads(ph_path.read_text())
    return raw.get("trades", [])

def load_signal_log() -> list[dict]:
    sl_path = BASE / "data" / "signal_log.json"
    if not sl_path.exists():
        return []
    sl = json.loads(sl_path.read_text())
    return [s for s in sl if s.get("status") == "CLOSED" and s.get("actual_pnl_pct") is not None]


# ─── Analysis computations ────────────────────────────────────────────────────

def compute_all(trades: list[dict]) -> dict:
    pnls_all = [t["pct_chg"] for t in trades if t.get("pct_chg") is not None]
    n = len(trades)
    wins = sum(1 for t in trades if t.get("win"))

    # Equity curve (cumulative sum per exit_date)
    by_date: dict[str, list] = defaultdict(list)
    for t in trades:
        d = t.get("exit_date") or t.get("run_date") or ""
        if d:
            by_date[d].append(t.get("pct_chg", 0))
    dates = sorted(by_date.keys())
    cumulative = []
    running = 0.0
    for d in dates:
        daily = statistics.mean(by_date[d])
        running += daily
        cumulative.append({"date": d, "cum": round(running, 2), "daily": round(daily, 2), "n": len(by_date[d])})

    # Regime breakdown
    regime_stats = {}
    for regime in ["risk_on_trending", "risk_on_choppy", "bull", "unknown"]:
        rp = [t["pct_chg"] for t in trades if (t.get("regime4") or t.get("regime","unknown")) == regime]
        regime_stats[regime] = stats_row(rp, regime)

    # Setup family breakdown
    setup_families = set(t.get("setup_family") or "unknown" for t in trades)
    setup_stats = {}
    for sf in setup_families:
        sp = [t["pct_chg"] for t in trades if (t.get("setup_family") or "unknown") == sf]
        setup_stats[sf] = stats_row(sp, sf)

    # Regime × Setup matrix
    matrix = {}
    all_regimes = ["risk_on_trending", "risk_on_choppy", "bull"]
    all_setups = ["Trend Continuation", "Breakout Expansion", "Impulse Catalyst", "Insider Cluster"]
    for r in all_regimes:
        for sf in all_setups:
            key = f"{r}|{sf}"
            rp = [t["pct_chg"] for t in trades
                  if (t.get("regime4") or t.get("regime","unknown")) == r
                  and (t.get("setup_family") or "unknown") == sf]
            matrix[key] = stats_row(rp, key)

    # Score band analysis (10-pt bands)
    score_bands = {}
    for floor in range(20, 110, 10):
        band = f"{floor}-{floor+9}"
        bp = [t["pct_chg"] for t in trades if floor <= (t.get("score") or 0) < floor+10]
        score_bands[band] = stats_row(bp, band)

    # Sector analysis
    sectors = set(t.get("sector") or "Unknown" for t in trades)
    sector_stats = {}
    for sec in sectors:
        sp = [t["pct_chg"] for t in trades if (t.get("sector") or "Unknown") == sec]
        sector_stats[sec] = stats_row(sp, sec)

    # Entry quality
    qualities = set(t.get("entry_quality") or "unknown" for t in trades)
    eq_stats = {}
    for q in qualities:
        qp = [t["pct_chg"] for t in trades if (t.get("entry_quality") or "unknown") == q]
        eq_stats[q] = stats_row(qp, q)

    # Catalyst tier
    cat_stats = {}
    for tier in [1, 2, 3]:
        tp = [t["pct_chg"] for t in trades if t.get("catalyst_tier") == tier]
        cat_stats[f"Tier {tier}"] = stats_row(tp, f"Catalyst Tier {tier}")

    # MAE/MFE distributions
    wins_t = [t for t in trades if t.get("win")]
    loss_t = [t for t in trades if not t.get("win")]
    mae_winners = [t["mae"] for t in wins_t if t.get("mae") is not None]
    mae_losers = [t["mae"] for t in loss_t if t.get("mae") is not None]
    mfe_winners = [t["mfe"] for t in wins_t if t.get("mfe") is not None]
    mfe_losers = [t["mfe"] for t in loss_t if t.get("mfe") is not None]

    # Stop analysis: how many winners had MAE worse than -5%?
    stop_1_5_pct = sum(1 for m in mae_winners if m < -1.5)
    stop_3_pct = sum(1 for m in mae_winners if m < -3.0)
    stop_5_pct = sum(1 for m in mae_winners if m < -5.0)

    # Generate improvement recommendations
    recommendations = _generate_recommendations(
        sector_stats, eq_stats, setup_stats, regime_stats, matrix,
        score_bands, mae_winners, mfe_winners, pnls_all
    )

    dd_series = [c["cum"] for c in cumulative]
    mdd = max_drawdown(dd_series) if dd_series else 0

    return {
        "overview": {
            "total_trades": n, "wins": wins, "losses": n-wins,
            "wr": round(wins/n*100, 1) if n else 0,
            "avg_pnl": round(statistics.mean(pnls_all), 2) if pnls_all else 0,
            "pf": profit_factor(pnls_all),
            "sharpe": sharpe(pnls_all),
            "wilson_lb": round(wilson_lb(wins, n)*100, 1) if n else 0,
            "max_drawdown": mdd,
            "date_start": dates[0] if dates else "—",
            "date_end": dates[-1] if dates else "—",
        },
        "cumulative": cumulative,
        "regime_stats": regime_stats,
        "setup_stats": setup_stats,
        "matrix": matrix,
        "matrix_regimes": all_regimes,
        "matrix_setups": all_setups,
        "score_bands": score_bands,
        "sector_stats": sector_stats,
        "eq_stats": eq_stats,
        "cat_stats": cat_stats,
        "mae_winners": mae_winners,
        "mae_losers": mae_losers,
        "mfe_winners": mfe_winners,
        "mfe_losers": mfe_losers,
        "stop_analysis": {
            "winners_stopped_at_1_5": stop_1_5_pct,
            "winners_stopped_at_3": stop_3_pct,
            "winners_stopped_at_5": stop_5_pct,
            "total_winners": len(wins_t),
            "pct_unnecessarily_stopped_at_3": round(stop_3_pct/len(wins_t)*100, 1) if wins_t else 0,
        },
        "recommendations": recommendations,
    }


def _generate_recommendations(sector_stats, eq_stats, setup_stats, regime_stats,
                               matrix, score_bands, mae_winners, mfe_winners, pnls_all) -> list:
    recs = []

    # Sector: kill bad sectors
    for sec, s in sorted(sector_stats.items(), key=lambda x: x[1]["avg"]):
        if s["n"] >= 20 and s["pf"] < 0.85:
            recs.append({
                "priority": "P0", "category": "Sector Filter",
                "action": f"BLOCK sector '{sec}' — PF {s['pf']:.2f}, WR {s['wr']:.1f}%, avg {s['avg']:.2f}% (n={s['n']})",
                "expected_lift": f"Remove {s['n']} losing trades. Avg drag per trade: {s['avg']:.2f}%",
                "config_key": f"sector_blocklist.add('{sec}')"
            })
        elif s["n"] >= 20 and s["avg"] >= 1.5 and s["wr"] >= 60:
            recs.append({
                "priority": "P1", "category": "Sector Tilt",
                "action": f"BOOST size 1.2× in sector '{sec}' — WR {s['wr']:.1f}%, avg +{s['avg']:.2f}% (n={s['n']})",
                "expected_lift": f"Sector shows consistent edge. Wilson LB {s['wilson_lb']:.1f}%",
                "config_key": f"sector_size_tilt.{sec} = 1.2"
            })

    # Entry quality: FRESH is worst
    fresh = eq_stats.get("FRESH") or eq_stats.get("fresh")
    if fresh and fresh["n"] >= 10 and fresh["avg"] < -1.0:
        recs.append({
            "priority": "P0", "category": "Entry Quality Gate",
            "action": f"INVESTIGATE FRESH entry — WR {fresh['wr']:.1f}%, avg {fresh['avg']:.2f}% (n={fresh['n']}). "
                      "Counter-intuitive: entries AT support are underperforming. "
                      "Hypothesis: buying support = buying into distribution.",
            "expected_lift": "Removing FRESH entries could improve avg by ~0.5-1.0% per trade",
            "config_key": "entry_quality_gate: block FRESH OR require catalyst_tier <= 1"
        })

    # Score bands: 60-69 beats 70-79
    b6069 = score_bands.get("60-69")
    b7079 = score_bands.get("70-79")
    b8089 = score_bands.get("80-89")
    if b6069 and b7079 and b6069["pf"] > b7079["pf"] + 0.3:
        recs.append({
            "priority": "P1", "category": "Score Calibration",
            "action": f"Score 60-69 (PF {b6069['pf']}, WR {b6069['wr']:.1f}%) OUTPERFORMS 70-79 (PF {b7079['pf']}, WR {b7079['wr']:.1f}%). "
                      "Raising the score floor is hurting, not helping. "
                      "Recommendation: revert buy_min_score to 65 (from 80) and apply per-regime floors instead.",
            "expected_lift": f"Restoring score floor to 65 adds back n={b6069['n']} high-quality trades",
            "config_key": "regime4_thresholds.risk_on_trending.buy_min_score = 65"
        })

    # Regime × setup: kill combinations with PF < 1.0
    for key, s in matrix.items():
        regime, setup = key.split("|")
        if s["n"] >= 20 and s["pf"] < 1.0:
            recs.append({
                "priority": "P0", "category": "Regime×Setup Kill",
                "action": f"KILL {setup} in {regime} — PF {s['pf']:.2f}, WR {s['wr']:.1f}%, avg {s['avg']:.2f}% (n={s['n']})",
                "expected_lift": f"Blocking this combination removes {s['n']} losing trades",
                "config_key": f"regime_setup_blocklist.{regime}.{setup.replace(' ','_')} = blocked"
            })

    # Stop analysis: if winners are getting stopped
    if mfe_winners:
        mfe_mean = statistics.mean(mfe_winners)
        if mfe_mean > 5.0:
            recs.append({
                "priority": "P1", "category": "Target Optimization",
                "action": f"Winners reach avg MFE {mfe_mean:.1f}% but T1 targets may be too conservative. "
                          "Consider extending T1 to +5% and using trailing stop after T1 hit.",
                "expected_lift": "Letting winners run +1-2% longer could improve avg by 0.3-0.5% per trade",
                "config_key": "canonical_trade_plan: extend T1 = entry × 1.05"
            })

    if mae_winners:
        mae_mean = abs(statistics.mean(mae_winners))
        if mae_mean < 2.5:
            recs.append({
                "priority": "P2", "category": "Stop Tightening",
                "action": f"Winners only drawdown avg {mae_mean:.1f}% MAE before going positive. "
                          "Current 1.5×ATR stop may be too wide. Test 1.25×ATR for trending stocks.",
                "expected_lift": "Tighter stop on winners = better R:R. Small risk of early exits.",
                "config_key": "scoring.stop_atr_multiple = 1.25 (trending only)"
            })

    # Sort by priority
    pri_order = {"P0": 0, "P1": 1, "P2": 2}
    recs.sort(key=lambda r: pri_order.get(r["priority"], 3))
    return recs


# ─── HTML generation ──────────────────────────────────────────────────────────

VERDICT_COLOR = {
    "PROMOTE": "#22c55e", "HOLD": "#3b82f6", "REDUCE": "#f59e0b",
    "KILL": "#ef4444", "INSUFFICIENT": "#6b7280"
}
PF_GRADIENT = [  # (threshold, bg, text)
    (1.60, "#14532d", "#86efac"),
    (1.30, "#1a3a1a", "#4ade80"),
    (1.10, "#1c1a06", "#fde047"),
    (1.00, "#2a1515", "#fca5a5"),
    (0.00, "#3b0a0a", "#f87171"),
]

def pf_style(pf: float) -> str:
    for threshold, bg, text in PF_GRADIENT:
        if pf >= threshold:
            return f"background:{bg};color:{text}"
    return "background:#1a0000;color:#f87171"

def wr_bar(wr: float) -> str:
    color = "#22c55e" if wr >= 55 else "#f59e0b" if wr >= 45 else "#ef4444"
    return f'<div style="background:#1e293b;border-radius:3px;height:6px;width:100%;margin-top:3px"><div style="background:{color};width:{min(wr,100):.0f}%;height:6px;border-radius:3px"></div></div>'

def verdict_badge(v: str) -> str:
    c = VERDICT_COLOR.get(v, "#6b7280")
    return f'<span style="background:{c}22;color:{c};border:1px solid {c}44;border-radius:4px;padding:1px 7px;font-size:10px;font-weight:700;letter-spacing:0.5px">{v}</span>'


def html_stats_table(rows: list[dict], title: str, subtitle: str = "") -> str:
    rows_sorted = sorted(rows, key=lambda r: -r.get("pf", 0))
    html = f"""
    <div class="card">
      <div class="card-header">
        <h3>{title}</h3>
        {f'<p class="subtitle">{subtitle}</p>' if subtitle else ''}
      </div>
      <div class="table-wrap">
      <table>
        <thead><tr>
          <th>Strategy</th><th>n</th><th>WR%</th><th>Avg%</th><th>PF</th><th>Sharpe</th><th>Wilson LB</th><th>Verdict</th>
        </tr></thead>
        <tbody>
    """
    for r in rows_sorted:
        if r["n"] == 0: continue
        pf_s = pf_style(r["pf"])
        html += f"""<tr>
          <td><strong>{r['label']}</strong></td>
          <td style="color:#94a3b8">{r['n']}</td>
          <td>{r['wr']:.1f}% {wr_bar(r['wr'])}</td>
          <td style="color:{'#22c55e' if r['avg']>0 else '#ef4444'};font-weight:600">{r['avg']:+.2f}%</td>
          <td style="{pf_s};padding:3px 8px;border-radius:4px;font-weight:700">{r['pf']:.2f}</td>
          <td style="color:#94a3b8">{r['sharpe']:.2f}</td>
          <td style="color:{'#22c55e' if r['wilson_lb']>=52 else '#f59e0b' if r['wilson_lb']>=45 else '#ef4444'}">{r['wilson_lb']:.1f}%</td>
          <td>{verdict_badge(r['verdict'])}</td>
        </tr>"""
    html += "</tbody></table></div></div>"
    return html


def build_html(data: dict, generated_at: str) -> str:
    ov = data["overview"]
    cum = data["cumulative"]
    recs = data["recommendations"]

    # Chart data
    dates_js = json.dumps([c["date"] for c in cum])
    cum_js = json.dumps([c["cum"] for c in cum])
    daily_js = json.dumps([c["daily"] for c in cum])

    # MAE histogram buckets
    def hist_buckets(vals, lo, hi, n_buckets=20):
        if not vals: return [], []
        step = (hi-lo)/n_buckets
        labels = [f"{lo+i*step:.1f}" for i in range(n_buckets)]
        counts = [0]*n_buckets
        for v in vals:
            idx = int((v-lo)/step)
            idx = max(0, min(n_buckets-1, idx))
            counts[idx] += 1
        return labels, counts

    mae_lbls, mae_w = hist_buckets(data["mae_winners"], -15, 5, 20)
    _, mae_l = hist_buckets(data["mae_losers"], -15, 5, 20)
    mfe_lbls, mfe_w = hist_buckets(data["mfe_winners"], -5, 40, 20)
    _, mfe_l = hist_buckets(data["mfe_losers"], -5, 40, 20)

    # Score band chart data
    sb_labels = json.dumps([k for k in sorted(data["score_bands"].keys()) if data["score_bands"][k]["n"] > 0])
    sb_wr = json.dumps([data["score_bands"][k]["wr"] for k in sorted(data["score_bands"].keys()) if data["score_bands"][k]["n"] > 0])
    sb_pf = json.dumps([data["score_bands"][k]["pf"] for k in sorted(data["score_bands"].keys()) if data["score_bands"][k]["n"] > 0])
    sb_n = json.dumps([data["score_bands"][k]["n"] for k in sorted(data["score_bands"].keys()) if data["score_bands"][k]["n"] > 0])

    # Regime × Setup matrix
    matrix_html = _build_matrix_html(data)

    # Recommendations
    rec_html = _build_rec_html(recs)

    # Stat tables
    regime_rows = list(data["regime_stats"].values())
    setup_rows = list(data["setup_stats"].values())
    sector_rows = sorted(data["sector_stats"].values(), key=lambda r: -r["n"])[:12]
    eq_rows = list(data["eq_stats"].values())
    cat_rows = list(data["cat_stats"].values())

    # Stop analysis
    sa = data["stop_analysis"]

    # System verdict
    pf_total = ov["pf"]
    wr_total = ov["wr"]
    wlb = ov["wilson_lb"]
    if pf_total >= 1.5 and wlb >= 52 and ov["sharpe"] >= 0.5:
        sys_verdict = "EDGE CONFIRMED"
        sys_color = "#22c55e"
        sys_icon = "✓"
    elif pf_total >= 1.20 and wlb >= 48:
        sys_verdict = "MARGINAL EDGE"
        sys_color = "#f59e0b"
        sys_icon = "~"
    else:
        sys_verdict = "NO EDGE"
        sys_color = "#ef4444"
        sys_icon = "✗"

    p0_count = sum(1 for r in recs if r["priority"] == "P0")
    p1_count = sum(1 for r in recs if r["priority"] == "P1")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SwingTrade — Strategy Report {generated_at[:10]}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  :root {{
    --bg: #0a0d12; --surface: #0f1318; --surface2: #141820; --border: #1e2530;
    --text: #e2e8f0; --muted: #64748b; --accent: #3b82f6; --green: #22c55e;
    --yellow: #f59e0b; --red: #ef4444; --purple: #a855f7;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font-family: 'Inter',system-ui,sans-serif; font-size: 13px; line-height: 1.5; }}
  a {{ color: var(--accent); text-decoration: none; }}
  h1 {{ font-size: 22px; font-weight: 700; letter-spacing: -0.5px; }}
  h2 {{ font-size: 16px; font-weight: 600; color: var(--text); border-left: 3px solid var(--accent); padding-left: 10px; margin-bottom: 16px; }}
  h3 {{ font-size: 13px; font-weight: 600; color: var(--text); margin-bottom: 4px; }}
  .subtitle {{ color: var(--muted); font-size: 11px; margin-top: 2px; }}
  .header {{ background: var(--surface); border-bottom: 1px solid var(--border); padding: 16px 24px; display: flex; align-items: center; justify-content: space-between; position: sticky; top: 0; z-index: 100; }}
  .header-left {{ display: flex; align-items: center; gap: 12px; }}
  .verdict-badge {{ background: {sys_color}22; color: {sys_color}; border: 1px solid {sys_color}; border-radius: 6px; padding: 4px 12px; font-size: 11px; font-weight: 700; letter-spacing: 1px; }}
  .main {{ max-width: 1400px; margin: 0 auto; padding: 24px; }}
  .section {{ margin-bottom: 32px; }}
  .grid2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
  .grid3 {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; }}
  .grid4 {{ display: grid; grid-template-columns: repeat(4,1fr); gap: 12px; }}
  .card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }}
  .card-header {{ padding: 14px 16px; border-bottom: 1px solid var(--border); }}
  .table-wrap {{ overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  th {{ background: var(--surface2); color: var(--muted); font-weight: 600; font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; padding: 8px 12px; text-align: left; border-bottom: 1px solid var(--border); }}
  td {{ padding: 8px 12px; border-bottom: 1px solid #0d1117; }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover td {{ background: var(--surface2); }}
  .kpi-grid {{ display: grid; grid-template-columns: repeat(8,1fr); gap: 1px; background: var(--border); border-radius: 8px; overflow: hidden; margin-bottom: 20px; }}
  .kpi {{ background: var(--surface); padding: 14px 12px; text-align: center; }}
  .kpi-val {{ font-size: 22px; font-weight: 700; line-height: 1.1; }}
  .kpi-lbl {{ font-size: 10px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; margin-top: 3px; }}
  .chart-wrap {{ padding: 16px; height: 260px; position: relative; }}
  .rec-list {{ padding: 12px 16px; display: flex; flex-direction: column; gap: 10px; }}
  .rec {{ background: var(--surface2); border: 1px solid var(--border); border-radius: 6px; padding: 12px 14px; }}
  .rec-header {{ display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }}
  .p0 {{ color: #ef4444; background: #ef444422; border: 1px solid #ef444444; border-radius: 4px; padding: 1px 7px; font-size: 10px; font-weight: 700; }}
  .p1 {{ color: #f59e0b; background: #f59e0b22; border: 1px solid #f59e0b44; border-radius: 4px; padding: 1px 7px; font-size: 10px; font-weight: 700; }}
  .p2 {{ color: #3b82f6; background: #3b82f622; border: 1px solid #3b82f644; border-radius: 4px; padding: 1px 7px; font-size: 10px; font-weight: 700; }}
  .rec-cat {{ color: var(--muted); font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; }}
  .rec-action {{ font-size: 12px; font-weight: 500; color: var(--text); margin-bottom: 4px; }}
  .rec-lift {{ font-size: 11px; color: #22c55e; }}
  .rec-config {{ font-size: 10px; color: var(--muted); font-family: monospace; margin-top: 4px; }}
  .matrix-table td {{ font-size: 11px; padding: 6px 8px; }}
  .matrix-table th {{ font-size: 10px; }}
  .stop-stat {{ display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid var(--border); }}
  .stop-stat:last-child {{ border-bottom: none; }}
  .nav {{ display: flex; gap: 2px; background: var(--surface2); padding: 4px; border-radius: 6px; margin-bottom: 20px; flex-wrap: wrap; }}
  .nav a {{ padding: 5px 12px; border-radius: 4px; font-size: 11px; font-weight: 500; color: var(--muted); transition: all 0.15s; }}
  .nav a:hover {{ background: var(--surface); color: var(--text); }}
  @media (max-width: 900px) {{ .grid4 {{ grid-template-columns: repeat(2,1fr); }} .kpi-grid {{ grid-template-columns: repeat(4,1fr); }} .grid2 {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<div class="header">
  <div class="header-left">
    <div>
      <h1>SwingTrade — Strategy Report</h1>
      <div style="color:var(--muted);font-size:11px">{ov['date_start']} → {ov['date_end']} · {ov['total_trades']} trades · Generated {generated_at}</div>
    </div>
  </div>
  <div style="display:flex;align-items:center;gap:12px">
    <div style="color:var(--muted);font-size:11px;text-align:right">{p0_count} P0 issues · {p1_count} P1 improvements</div>
    <div class="verdict-badge">{sys_icon} {sys_verdict}</div>
  </div>
</div>

<div class="main">

<nav class="nav">
  <a href="#overview">Overview</a>
  <a href="#equity">Equity Curve</a>
  <a href="#regime">Regime Analysis</a>
  <a href="#matrix">Regime×Setup Matrix</a>
  <a href="#setups">Setup Families</a>
  <a href="#scores">Score Calibration</a>
  <a href="#sectors">Sectors</a>
  <a href="#entry">Entry Quality</a>
  <a href="#maemfe">MAE/MFE</a>
  <a href="#recommendations">Recommendations</a>
</nav>

<!-- ── OVERVIEW KPIs ── -->
<div class="section" id="overview">
<h2>System Performance Overview</h2>
<div class="kpi-grid">
  <div class="kpi"><div class="kpi-val" style="color:{sys_color}">{ov['wr']:.1f}%</div><div class="kpi-lbl">Win Rate</div></div>
  <div class="kpi"><div class="kpi-val" style="color:{'#22c55e' if ov['pf']>=1.3 else '#f59e0b' if ov['pf']>=1.0 else '#ef4444'}">{ov['pf']:.2f}</div><div class="kpi-lbl">Profit Factor</div></div>
  <div class="kpi"><div class="kpi-val" style="color:{'#22c55e' if ov['sharpe']>=0.5 else '#f59e0b' if ov['sharpe']>=0 else '#ef4444'}">{ov['sharpe']:.2f}</div><div class="kpi-lbl">Sharpe</div></div>
  <div class="kpi"><div class="kpi-val">{ov['avg_pnl']:+.2f}%</div><div class="kpi-lbl">Avg Trade</div></div>
  <div class="kpi"><div class="kpi-val" style="color:var(--muted)">{ov['total_trades']}</div><div class="kpi-lbl">Total Trades</div></div>
  <div class="kpi"><div class="kpi-val" style="color:#22c55e">{ov['wins']}</div><div class="kpi-lbl">Winners</div></div>
  <div class="kpi"><div class="kpi-val" style="color:#ef4444">{ov['losses']}</div><div class="kpi-lbl">Losers</div></div>
  <div class="kpi"><div class="kpi-val" style="color:var(--yellow)">{ov['wilson_lb']:.1f}%</div><div class="kpi-lbl">Wilson LB</div></div>
</div>
<div class="grid3">
  <div class="card">
    <div class="card-header"><h3>System Verdict</h3></div>
    <div style="padding:20px;text-align:center">
      <div style="font-size:48px;font-weight:900;color:{sys_color};letter-spacing:-2px">{sys_icon}</div>
      <div style="font-size:18px;font-weight:700;color:{sys_color};margin:8px 0">{sys_verdict}</div>
      <div style="color:var(--muted);font-size:11px;max-width:220px;margin:0 auto">
        Wilson LB {wlb:.1f}% | PF {pf_total:.2f} | Sharpe {ov['sharpe']:.2f}<br>
        {'Edge statistically supported (Wilson LB &gt; 50%)' if wlb > 50 else 'Edge marginal — needs more data or tuning' if wlb > 45 else 'No statistically supported edge — system needs tuning'}
      </div>
    </div>
  </div>
  <div class="card">
    <div class="card-header"><h3>Risk Profile</h3></div>
    <div style="padding:14px 16px">
      <div class="stop-stat"><span style="color:var(--muted)">Max Drawdown</span><span style="color:#ef4444;font-weight:600">-{ov['max_drawdown']:.1f}%</span></div>
      <div class="stop-stat"><span style="color:var(--muted)">Avg Winner MFE</span><span style="color:#22c55e">{statistics.mean(data['mfe_winners']):.1f}% max</span></div>
      <div class="stop-stat"><span style="color:var(--muted)">Avg Loser MAE</span><span style="color:#ef4444">{statistics.mean(data['mae_losers']):.1f}% min</span></div>
      <div class="stop-stat"><span style="color:var(--muted)">Avg Winner MAE</span><span style="color:#f59e0b">{statistics.mean(data['mae_winners']):.1f}% drawdown</span></div>
      <div class="stop-stat"><span style="color:var(--muted)">Hold Period</span><span>5 days (fixed)</span></div>
    </div>
  </div>
  <div class="card">
    <div class="card-header"><h3>Stop Effectiveness</h3></div>
    <div style="padding:14px 16px">
      <div class="stop-stat"><span style="color:var(--muted)">Total winners</span><span>{sa['total_winners']}</span></div>
      <div class="stop-stat"><span style="color:var(--muted)">Winners w/ MAE &lt; -1.5%</span><span style="color:#f59e0b">{sa['winners_stopped_at_1_5']} ({sa['winners_stopped_at_1_5']/sa['total_winners']*100:.0f}%)</span></div>
      <div class="stop-stat"><span style="color:var(--muted)">Winners w/ MAE &lt; -3%</span><span style="color:#f59e0b">{sa['winners_stopped_at_3']} ({sa['pct_unnecessarily_stopped_at_3']:.0f}%)</span></div>
      <div class="stop-stat"><span style="color:var(--muted)">Winners w/ MAE &lt; -5%</span><span style="color:#ef4444">{sa['winners_stopped_at_5']} ({sa['winners_stopped_at_5']/sa['total_winners']*100:.0f}%)</span></div>
      <div style="color:var(--muted);font-size:11px;margin-top:8px">
        {sa['pct_unnecessarily_stopped_at_3']:.0f}% of eventual winners dropped past -3% first —
        {'tight stops may be cutting winners early' if sa['pct_unnecessarily_stopped_at_3'] > 20 else 'stop placement looks appropriate'}
      </div>
    </div>
  </div>
</div>
</div>

<!-- ── EQUITY CURVE ── -->
<div class="section" id="equity">
<h2>Equity Curve &amp; Daily Performance</h2>
<div class="grid2">
  <div class="card">
    <div class="card-header"><h3>Cumulative Return</h3><p class="subtitle">Average daily return per exit-date cohort</p></div>
    <div class="chart-wrap"><canvas id="equityChart"></canvas></div>
  </div>
  <div class="card">
    <div class="card-header"><h3>Daily P&amp;L Distribution</h3><p class="subtitle">Per-day avg return, color-coded by sign</p></div>
    <div class="chart-wrap"><canvas id="dailyChart"></canvas></div>
  </div>
</div>
</div>

<!-- ── REGIME ── -->
<div class="section" id="regime">
<h2>Regime Performance</h2>
{html_stats_table(regime_rows, "Per-Regime Statistics", "How does the system perform in each of the 4 market regimes?")}
<div style="margin-top:12px;padding:12px;background:var(--surface);border:1px solid var(--border);border-radius:8px;font-size:11px;color:var(--muted)">
  <strong style="color:var(--text)">Interpretation:</strong>
  The bulk of trades ({data['regime_stats'].get('risk_on_choppy',{}).get('n',0)} of {ov['total_trades']}) occurred in <em>risk_on_choppy</em>.
  Edge in <em>risk_on_trending</em> is higher WR but fewer opportunities.
  Regime classification is the most critical system component — a misclassified regime degrades every downstream decision.
</div>
</div>

<!-- ── MATRIX ── -->
<div class="section" id="matrix">
<h2>Regime × Setup Matrix</h2>
{matrix_html}
</div>

<!-- ── SETUPS ── -->
<div class="section" id="setups">
<h2>Setup Family Performance</h2>
{html_stats_table(setup_rows, "Per-Setup Family", "Wilson LB is the key metric — anything below 45% with n≥30 is a kill candidate")}
{html_stats_table(cat_rows, "Catalyst Tier Breakdown", "Catalyst tier 1 = PEAD/UOA/VCP, Tier 2 = squeeze/EMA pullback, Tier 3 = analyst headlines")}
</div>

<!-- ── SCORE CALIBRATION ── -->
<div class="section" id="scores">
<h2>Score Band Calibration</h2>
<div class="card">
  <div class="card-header">
    <h3>Win Rate &amp; Profit Factor by Score Band</h3>
    <p class="subtitle">⚠️ Higher score does NOT always mean better performance — score 60-69 outperforms 70-79</p>
  </div>
  <div class="chart-wrap" style="height:300px"><canvas id="scoreChart"></canvas></div>
</div>
<div class="card" style="margin-top:12px">
  <div class="card-header"><h3>Score Band Table</h3></div>
  <div class="table-wrap">
  <table>
    <thead><tr><th>Score Band</th><th>n</th><th>WR%</th><th>Avg%</th><th>PF</th><th>Sharpe</th><th>Wilson LB</th><th>Verdict</th></tr></thead>
    <tbody>
"""
    for band, s in sorted(data["score_bands"].items()):
        if s["n"] == 0: continue
        html += f"""<tr>
          <td><strong>{s['label']}</strong></td>
          <td style="color:#94a3b8">{s['n']}</td>
          <td>{s['wr']:.1f}% {wr_bar(s['wr'])}</td>
          <td style="color:{'#22c55e' if s['avg']>0 else '#ef4444'};font-weight:600">{s['avg']:+.2f}%</td>
          <td style="{pf_style(s['pf'])};padding:3px 8px;border-radius:4px;font-weight:700">{s['pf']:.2f}</td>
          <td style="color:#94a3b8">{s['sharpe']:.2f}</td>
          <td style="color:{'#22c55e' if s['wilson_lb']>=52 else '#f59e0b' if s['wilson_lb']>=45 else '#ef4444'}">{s['wilson_lb']:.1f}%</td>
          <td>{verdict_badge(s['verdict'])}</td>
        </tr>"""
    html += f"""    </tbody>
  </table>
  </div>
</div>
</div>

<!-- ── SECTORS ── -->
<div class="section" id="sectors">
<h2>Sector Performance</h2>
{html_stats_table(sector_rows, "Per-Sector Statistics (top 12 by volume)", "Technology and Consumer Defensive show edge; Energy and Consumer Cyclical are drags")}
</div>

<!-- ── ENTRY QUALITY ── -->
<div class="section" id="entry">
<h2>Entry Quality Analysis</h2>
{html_stats_table(eq_rows, "Entry Quality Breakdown", "⚠️ FRESH entries (at support) are underperforming — buy-at-support may be buying into distribution")}
<div style="margin-top:12px;padding:12px;background:#1c1205;border:1px solid #92400e;border-radius:8px;font-size:12px">
  <strong style="color:#fcd34d">⚠️ Counter-intuitive finding:</strong>
  FRESH entry quality (buying precisely at support) has WR 36.8% and avg -2.69% — the WORST category.
  MISSED entries (already moved, chasing slightly) outperform at WR 60.2%, avg +1.35%.
  Hypothesis: FRESH = buying into supply from weak holders at support; MISSED = confirmation of break above supply.
  <strong>Action: Demote FRESH to WATCH-only, require VALID/MISSED for BUY.</strong>
</div>
</div>

<!-- ── MAE/MFE ── -->
<div class="section" id="maemfe">
<h2>MAE / MFE Analysis — Stop &amp; Target Optimization</h2>
<div class="grid2">
  <div class="card">
    <div class="card-header"><h3>MAE Distribution (Max Adverse Excursion)</h3><p class="subtitle">How far trades went against us before resolving — green=winners, red=losers</p></div>
    <div class="chart-wrap"><canvas id="maeChart"></canvas></div>
  </div>
  <div class="card">
    <div class="card-header"><h3>MFE Distribution (Max Favorable Excursion)</h3><p class="subtitle">How far trades went in our favor — green=winners, red=losers</p></div>
    <div class="chart-wrap"><canvas id="mfeChart"></canvas></div>
  </div>
</div>
<div class="grid2" style="margin-top:12px">
  <div class="card">
    <div class="card-header"><h3>Stop Optimization Insight</h3></div>
    <div style="padding:14px 16px;font-size:12px">
      <p style="margin-bottom:8px;color:var(--muted)">Winners' MAE tells you where stops can be set without cutting them:</p>
      <ul style="margin-left:16px;color:var(--text);line-height:2">
        <li>Winners avg MAE: <strong style="color:#f59e0b">{statistics.mean(data['mae_winners']):.1f}%</strong> (they briefly go against you this much)</li>
        <li>Losers avg MAE: <strong style="color:#ef4444">{statistics.mean(data['mae_losers']):.1f}%</strong> (losers go much further against)</li>
        <li>Stop suggestion: <strong style="color:#22c55e">-{abs(statistics.mean(data['mae_winners']))*1.5:.1f}%</strong> from entry (1.5× winner MAE) as floor</li>
        <li>{sa['pct_unnecessarily_stopped_at_3']:.0f}% of winners dipped below -3% before recovering</li>
      </ul>
    </div>
  </div>
  <div class="card">
    <div class="card-header"><h3>Target Optimization Insight</h3></div>
    <div style="padding:14px 16px;font-size:12px">
      <p style="margin-bottom:8px;color:var(--muted)">Winners' MFE tells you where to set T1/T2 targets:</p>
      <ul style="margin-left:16px;color:var(--text);line-height:2">
        <li>Winners avg MFE: <strong style="color:#22c55e">{statistics.mean(data['mfe_winners']):.1f}%</strong> max favorable</li>
        <li>Losers avg MFE: <strong style="color:#ef4444">{statistics.mean(data['mfe_losers']):.1f}%</strong> (barely move up)</li>
        <li>T1 suggestion: <strong style="color:#22c55e">+{statistics.mean(data['mfe_winners'])*0.6:.1f}%</strong> (60% of avg winner MFE)</li>
        <li>T2 suggestion: <strong style="color:#22c55e">+{statistics.mean(data['mfe_winners'])*0.9:.1f}%</strong> (90% of avg winner MFE)</li>
        <li>MFE &gt; 2% is a strong winner signal — if MFE &lt; 1.5% by day 2, consider early exit</li>
      </ul>
    </div>
  </div>
</div>
</div>

<!-- ── RECOMMENDATIONS ── -->
<div class="section" id="recommendations">
<h2>Improvement Recommendations ({len(recs)} items)</h2>
{rec_html}
</div>

</div><!-- /main -->

<script>
const DATES = {dates_js};
const CUM = {cum_js};
const DAILY = {daily_js};
const SB_LABELS = {sb_labels};
const SB_WR = {sb_wr};
const SB_PF = {sb_pf};
const SB_N = {sb_n};
const MAE_LBLS = {json.dumps(mae_lbls)};
const MAE_W = {json.dumps(mae_w)};
const MAE_L = {json.dumps(mae_l)};
const MFE_LBLS = {json.dumps(mfe_lbls)};
const MFE_W = {json.dumps(mfe_w)};
const MFE_L = {json.dumps(mfe_l)};

Chart.defaults.color = '#64748b';
Chart.defaults.borderColor = '#1e2530';
Chart.defaults.font.family = 'Inter,system-ui,sans-serif';
Chart.defaults.font.size = 11;

// Equity curve
new Chart(document.getElementById('equityChart'), {{
  type: 'line',
  data: {{
    labels: DATES,
    datasets: [{{
      label: 'Cumulative Return',
      data: CUM,
      borderColor: '#3b82f6',
      backgroundColor: 'rgba(59,130,246,0.1)',
      fill: true,
      tension: 0.3,
      pointRadius: 2,
      pointHoverRadius: 5,
    }}]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ display: false }}, tooltip: {{ callbacks: {{ label: c => c.parsed.y.toFixed(2) + '%' }} }} }},
    scales: {{
      x: {{ ticks: {{ maxRotation: 45, maxTicksLimit: 8 }} }},
      y: {{ ticks: {{ callback: v => v.toFixed(1)+'%' }} }}
    }}
  }}
}});

// Daily P&L
new Chart(document.getElementById('dailyChart'), {{
  type: 'bar',
  data: {{
    labels: DATES,
    datasets: [{{
      label: 'Daily Avg',
      data: DAILY,
      backgroundColor: DAILY.map(v => v >= 0 ? 'rgba(34,197,94,0.7)' : 'rgba(239,68,68,0.7)'),
      borderWidth: 0,
    }}]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ display: false }}, tooltip: {{ callbacks: {{ label: c => c.parsed.y.toFixed(2) + '%' }} }} }},
    scales: {{
      x: {{ ticks: {{ maxRotation: 45, maxTicksLimit: 8 }} }},
      y: {{ ticks: {{ callback: v => v.toFixed(1)+'%' }} }}
    }}
  }}
}});

// Score band chart
new Chart(document.getElementById('scoreChart'), {{
  type: 'bar',
  data: {{
    labels: SB_LABELS,
    datasets: [
      {{ label: 'Win Rate %', data: SB_WR, backgroundColor: 'rgba(59,130,246,0.7)', yAxisID: 'y' }},
      {{ label: 'Profit Factor', data: SB_PF, type: 'line', borderColor: '#22c55e', backgroundColor: 'transparent', pointRadius: 4, yAxisID: 'y2' }},
    ]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ tooltip: {{ callbacks: {{ label: c => c.dataset.label + ': ' + c.parsed.y.toFixed(2) }} }} }},
    scales: {{
      y: {{ title: {{ display: true, text: 'Win Rate %' }}, min: 30, max: 80 }},
      y2: {{ position: 'right', title: {{ display: true, text: 'Profit Factor' }}, grid: {{ drawOnChartArea: false }}, min: 0, max: 3 }}
    }}
  }}
}});

// MAE chart
new Chart(document.getElementById('maeChart'), {{
  type: 'bar',
  data: {{
    labels: MAE_LBLS,
    datasets: [
      {{ label: 'Winners', data: MAE_W, backgroundColor: 'rgba(34,197,94,0.6)', barPercentage: 0.9 }},
      {{ label: 'Losers', data: MAE_L, backgroundColor: 'rgba(239,68,68,0.6)', barPercentage: 0.9 }},
    ]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ tooltip: {{}} }},
    scales: {{ x: {{ ticks: {{ maxTicksLimit: 10 }} }}, y: {{ title: {{ display: true, text: 'Count' }} }} }}
  }}
}});

// MFE chart
new Chart(document.getElementById('mfeChart'), {{
  type: 'bar',
  data: {{
    labels: MFE_LBLS,
    datasets: [
      {{ label: 'Winners', data: MFE_W, backgroundColor: 'rgba(34,197,94,0.6)', barPercentage: 0.9 }},
      {{ label: 'Losers', data: MFE_L, backgroundColor: 'rgba(239,68,68,0.6)', barPercentage: 0.9 }},
    ]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ tooltip: {{}} }},
    scales: {{ x: {{ ticks: {{ maxTicksLimit: 10 }} }}, y: {{ title: {{ display: true, text: 'Count' }} }} }}
  }}
}});
</script>
</body>
</html>"""
    return html


def _build_matrix_html(data: dict) -> str:
    regimes = data["matrix_regimes"]
    setups = data["matrix_setups"]
    matrix = data["matrix"]

    html = """<div class="card"><div class="card-header"><h3>Regime × Setup Performance Matrix</h3>
    <p class="subtitle">PF color: green ≥ 1.60 · yellow 1.10-1.60 · red &lt; 1.10 | Only cells with n≥5 shown</p></div>
    <div class="table-wrap"><table class="matrix-table">
    <thead><tr><th>Setup Family</th>"""
    for r in regimes:
        label = r.replace("risk_on_", "").replace("_", " ").title()
        html += f"<th colspan='3' style='text-align:center'>{label}</th>"
    html += "</tr><tr><th></th>"
    for _ in regimes:
        html += "<th>n</th><th>WR%</th><th>PF</th>"
    html += "</tr></thead><tbody>"

    for sf in setups:
        html += f"<tr><td><strong>{sf}</strong></td>"
        for r in regimes:
            key = f"{r}|{sf}"
            s = matrix.get(key, {})
            n = s.get("n", 0)
            if n < 5:
                html += "<td colspan='3' style='color:#1e2530;text-align:center'>—</td>"
            else:
                pf = s.get("pf", 0)
                wr = s.get("wr", 0)
                pf_s = pf_style(pf)
                wr_color = "#22c55e" if wr >= 55 else "#f59e0b" if wr >= 45 else "#ef4444"
                html += f"<td style='color:#64748b'>{n}</td>"
                html += f"<td style='color:{wr_color}'>{wr:.0f}%</td>"
                html += f"<td style='{pf_s};border-radius:3px;text-align:center'>{pf:.2f}</td>"
        html += "</tr>"

    html += "</tbody></table></div></div>"
    return html


def _build_rec_html(recs: list) -> str:
    if not recs:
        return "<div style='padding:20px;color:#64748b;text-align:center'>No recommendations generated</div>"
    html = '<div class="rec-list">'
    for r in recs:
        pri = r["priority"]
        html += f"""
        <div class="rec">
          <div class="rec-header">
            <span class="{pri.lower()}">{pri}</span>
            <span class="rec-cat">{r['category']}</span>
          </div>
          <div class="rec-action">{r['action']}</div>
          <div class="rec-lift">Expected lift: {r['expected_lift']}</div>
          <div class="rec-config">Config: {r['config_key']}</div>
        </div>"""
    html += "</div>"
    return html


# ─── Entry point ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(OUT_DEFAULT), help="Output HTML path")
    args = parser.parse_args()

    print("Loading trades...")
    trades = load_trades()
    if not trades:
        print("ERROR: No trades found in cache/picks_history.json")
        return

    print(f"Loaded {len(trades)} trades. Computing stats...")
    data = compute_all(trades)
    ov = data["overview"]
    print(f"  WR={ov['wr']:.1f}%, PF={ov['pf']:.2f}, Sharpe={ov['sharpe']:.2f}, n={ov['total_trades']}")
    print(f"  Recommendations: {len(data['recommendations'])} ({sum(1 for r in data['recommendations'] if r['priority']=='P0')} P0)")

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M PT")
    html = build_html(data, generated_at)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"\nReport written → {out}")
    print(f"Open: http://localhost:7432/cache/{out.name}")


if __name__ == "__main__":
    main()
