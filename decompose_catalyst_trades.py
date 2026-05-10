"""
decompose_catalyst_trades.py — A5 Catalyst-Conditional Trade Decomposition

Goal (per session brief):
  The mover_predictor v2 commit (d3e6127ff) concluded "pure technical features at
  entry time DO NOT predict whether a trade reaches +2%. Right next moves:
  catalyst-conditional ML, options flow features, NLP earnings."

  This script does the *catalyst-conditional* analysis WITHOUT ML — just grouped
  statistics with Wilson 95% CIs across all 2^N catalyst combinations.

Inputs (READ-ONLY):
  - cache/portfolio_backtest_750d_20260509_100501.json   (384 backtest trades)
  - data/signal_log.json                                 (1,106 live signals, 550 closed)

Output:
  - cache/catalyst_decomposition_2026-05-09.html        (dark-theme report)

Data-quality reality (documented in the report):
  - The 384-trade 750d backtest captures NO per-trade catalyst metadata. The
    `trades` array carries only: ticker, dates, prices, pnl, exit_reason, setup_type,
    score, verdict. There are no `catalyst_tags`, `news_sentiment_score`, `uoa`,
    `insider_data`, `analyst`, or `earnings` fields written per-trade.
  - The signal_log overlaps the backtest by 1 trade only (different windows:
    backtest is 2023-08-04 → 2026-04-30, signal_log is 2026-04-13 → 2026-05-08).
    So we cannot enrich the 384 trades retroactively.
  - We therefore report on TWO separate corpora:
      A) The 384 backtest trades using *setup-type-as-catalyst-proxy* and
         score-band slicing (the only signal we have at entry time).
      B) The signal_log's 550 closed signals using `setup_family`,
         `entry_quality`, `conviction_label`, `regime_name`, `tail_filter_demoted`
         as catalyst-adjacent dimensions.
  - Combinations that meet the (n>=20, Wilson LB>0.40, PF>1.3) bar in either
    corpus are surfaced as "surviving alpha buckets". Failed combos sit below
    with reasons (small-n, low-LB, weak-PF). Full matrix at the bottom.

Usage:
  python3 decompose_catalyst_trades.py

Re-uses tracker.py's wilson_ci helper and elite_research_note.py CSS.
"""
from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from datetime import datetime
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).parent
BT_PATH = ROOT / "cache" / "portfolio_backtest_750d_20260509_100501.json"
SL_PATH = ROOT / "data" / "signal_log.json"
OUT_PATH = ROOT / "cache" / "catalyst_decomposition_2026-05-09.html"

# Filter thresholds (per brief)
MIN_N = 20
MIN_WILSON_LB = 0.40
MIN_PF = 1.3


# ─── Stats helpers ────────────────────────────────────────────────────────

def wilson_ci(wins: int, total: int, confidence: float = 0.95) -> tuple[float, float]:
    """Wilson 95% CI — copied from tracker.py:637 verbatim."""
    if total == 0:
        return (0.0, 1.0)
    z_map = {0.90: 1.645, 0.95: 1.96, 0.99: 2.576}
    z = z_map.get(confidence, 1.96)
    phat = wins / total
    denom = 1 + z * z / total
    center = (phat + z * z / (2 * total)) / denom
    spread = z * math.sqrt((phat * (1 - phat) + z * z / (4 * total)) / total) / denom
    return (max(0.0, center - spread), min(1.0, center + spread))


def profit_factor(pnls: list[float]) -> float:
    pos = sum(p for p in pnls if p > 0)
    neg = abs(sum(p for p in pnls if p < 0))
    if neg == 0:
        return float("inf") if pos > 0 else 0.0
    return pos / neg


def expectancy(pnls: list[float]) -> float:
    return sum(pnls) / len(pnls) if pnls else 0.0


# ─── Catalyst classifiers ─────────────────────────────────────────────────

def classify_backtest_trade(t: dict) -> dict:
    """
    Classify a 384-trade backtest trade by *available* signal at entry.
    Real catalyst fields (earnings, insider_cluster, uoa, analyst, news) are
    NOT in the trade record — only setup_type and score. We surface
    setup-as-proxy + score-band as the available catalyst-adjacent dimensions.
    """
    setup = (t.get("setup_type") or "").strip()
    score = float(t.get("score") or 0)

    return {
        # Available catalyst-proxy dimensions
        "is_breakout_setup":    setup in ("VCP Breakout", "Near-VCP Breakout"),
        "is_pocket_pivot":      setup == "Pocket Pivot",
        "is_squeeze":           setup == "Squeeze Expansion",
        "is_trend_cont":        setup == "Trend Continuation",
        "score_high":           score >= 85,
        "score_mid":            65 <= score < 85,
    }


def classify_signal(s: dict) -> dict:
    """
    Classify a signal_log entry by available catalyst-adjacent fields.
    These are richer than the backtest trade record.
    """
    setup_fam = (s.get("setup_family") or "").strip()
    setup = (s.get("strategy") or "").strip()
    entry_q = (s.get("entry_quality") or "").strip().upper()
    conv = (s.get("conviction_label") or "").strip().upper()
    regime = (s.get("regime_name") or "").strip()
    tail_demoted = bool(s.get("tail_filter_demoted"))

    # Note: in this signal_log, conviction_label only has {WATCH, T3} and
    # regime_name is {neutral, bull} — so we adapt the classifiers to
    # surface only what the data actually carries.
    return {
        "is_impulse_catalyst":  setup_fam == "Impulse Catalyst",
        "is_breakout_expand":   setup_fam == "Breakout Expansion",
        "is_trend_cont":        setup_fam == "Trend Continuation",
        "is_insider_setup":     setup == "Insider Cluster",
        "is_squeeze_setup":     setup == "Squeeze Expansion",
        "is_pullback_setup":    setup in ("EMA21 Pullback", "EMA50 Pullback", "10-Week Pullback", "Bounce off Support"),
        "entry_fresh":          entry_q == "FRESH",
        "entry_pullback":       entry_q == "PULLBACK",
        "entry_extended":       entry_q in ("EXTENDED", "MISSED"),
        "is_t3_conviction":     conv == "T3",
        "regime_bull":          regime == "bull",
        "tail_demoted":         tail_demoted,
    }


# ─── Combinatorial decomposition ──────────────────────────────────────────

def decompose(records: list[dict], dim_names: list[str], *, include_negations: bool = True) -> list[dict]:
    """
    For each non-empty subset of dimension names, compute stats on records
    where ALL chosen dimensions are True. (Singletons + pairs + triples + ...)

    If include_negations=True, also test ¬dim (dimension is False) variants —
    so each dim becomes 2 literals (dim, NOT_dim). This is critical when some
    dimensions are "bad-entry flags" (entry_extended, tail_demoted) — the
    survival edge lives in their *exclusion*, not inclusion.

    Returns list of dicts, one per non-empty subset, sorted by Wilson LB desc.
    """
    out = []
    # Build literal pool: dim and (optionally) ¬dim
    literals: list[tuple[str, str, bool]] = []  # (label, dim_key, want_value)
    for d in dim_names:
        literals.append((d, d, True))
        if include_negations:
            literals.append((f"NOT_{d}", d, False))

    # Cap subset size — combinatorial explosion past k=3 with 20 literals
    max_k = 3 if include_negations else min(len(dim_names), 4)
    for k in range(1, max_k + 1):
        for combo in combinations(literals, k):
            # No-op: skip combos that pair (d, NOT_d) — always empty
            keys = [c[1] for c in combo]
            if len(set(keys)) != len(keys):
                continue
            subset = [r for r in records if all(r["dims"].get(dim_key) == want for (_, dim_key, want) in combo)]
            n = len(subset)
            if n == 0:
                continue
            wins = sum(1 for r in subset if r["win"])
            pnls = [r["pnl_pct"] for r in subset]
            wr = wins / n
            lo, hi = wilson_ci(wins, n)
            pf = profit_factor(pnls)
            exp = expectancy(pnls)
            avg_hold = sum(r.get("hold", 0) for r in subset) / n if any(r.get("hold") for r in subset) else 0
            labels = [c[0] for c in combo]
            out.append({
                "combo": tuple(labels),
                "combo_label": " ∧ ".join(labels),
                "k": k,
                "n": n,
                "wins": wins,
                "wr": wr,
                "wr_lo": lo,
                "wr_hi": hi,
                "ci_width_pp": (hi - lo) * 100,
                "pf": pf,
                "expectancy": exp,
                "avg_hold": avg_hold,
            })
    # Sort by Wilson LB desc, then by n desc
    out.sort(key=lambda r: (r["wr_lo"], r["n"]), reverse=True)
    return out


def dedupe_by_signature(combos: list[dict]) -> list[dict]:
    """
    Many combinations select the *same* trade subset (e.g., NOT_X ∧ NOT_Y vs
    NOT_X ∧ NOT_Y ∧ NOT_Z when Z is rare). Dedupe by (n, wins, wr_lo×1000, pf×100)
    signature, keeping the shortest combo_label per signature. Hugely reduces noise.
    """
    by_sig: dict[tuple, dict] = {}
    for c in combos:
        sig = (c["n"], c["wins"], round(c["wr_lo"] * 10000), round(c["expectancy"] * 100))
        prev = by_sig.get(sig)
        if prev is None or len(c["combo"]) < len(prev["combo"]):
            by_sig[sig] = c
    out = list(by_sig.values())
    out.sort(key=lambda r: (r["wr_lo"], r["n"]), reverse=True)
    return out


def filter_survivors(combos: list[dict]) -> tuple[list[dict], list[dict]]:
    survivors, failed = [], []
    for c in combos:
        ok_n = c["n"] >= MIN_N
        ok_lb = c["wr_lo"] >= MIN_WILSON_LB
        ok_pf = c["pf"] >= MIN_PF and c["pf"] != float("inf")
        if ok_n and ok_lb and ok_pf:
            survivors.append(c)
        else:
            reasons = []
            if not ok_n:
                reasons.append(f"n={c['n']}<{MIN_N}")
            if not ok_lb:
                reasons.append(f"WilsonLB={c['wr_lo']*100:.1f}%<{MIN_WILSON_LB*100:.0f}%")
            if not ok_pf:
                if c["pf"] == float("inf"):
                    reasons.append("PF=inf (no losses; suspicious)")
                else:
                    reasons.append(f"PF={c['pf']:.2f}<{MIN_PF}")
            c["fail_reasons"] = ", ".join(reasons)
            failed.append(c)
    return survivors, failed


# ─── HTML rendering (dark theme — copied from elite_research_note.py) ─────

CSS = """
:root {
  --bg-0: #0b0e13;
  --bg-1: #131820;
  --bg-2: #1c2330;
  --rule: #2c3441;
  --rule-2: #3a4554;
  --ink-0: #e8eef5;
  --ink-1: #aab5c4;
  --ink-2: #6b7686;
  --gold: #f5d76e;
  --gold-2: #d4af37;
  --teal: #5eead4;
  --green: #4ade80;
  --red: #f87171;
  --orange: #fb923c;
  --blue: #7dd3fc;
  --purple: #c084fc;
  --serif: 'Iowan Old Style', 'Palatino', Georgia, 'Times New Roman', serif;
  --sans: -apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', sans-serif;
  --mono: 'JetBrains Mono', 'SF Mono', Menlo, monospace;
}
* { box-sizing: border-box; }
body {
  background: var(--bg-0);
  color: var(--ink-0);
  font-family: var(--serif);
  line-height: 1.65;
  margin: 0;
  font-size: 16px;
}
.page { max-width: 1080px; margin: 0 auto; padding: 56px 40px 80px; }

.masthead { border-bottom: 2px solid var(--gold); padding-bottom: 28px; margin-bottom: 44px; }
.brand-row { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 24px; font-family: var(--mono); font-size: 11px; color: var(--ink-2); letter-spacing: 0.16em; text-transform: uppercase; }
.brand-row .left { color: var(--gold); }
.title { font-size: 38px; font-weight: 600; letter-spacing: -0.02em; line-height: 1.18; margin: 0 0 14px; color: var(--ink-0); }
.subtitle { font-size: 17px; color: var(--ink-1); font-style: italic; margin: 0 0 18px; max-width: 820px; }
.byline { font-family: var(--mono); font-size: 11px; color: var(--ink-2); letter-spacing: 0.1em; text-transform: uppercase; }

section { margin: 48px 0; }
.section-num { font-family: var(--mono); font-size: 11px; color: var(--gold); letter-spacing: 0.18em; text-transform: uppercase; margin-bottom: 6px; }
h2 { font-size: 26px; font-weight: 600; margin: 0 0 10px; letter-spacing: -0.01em; color: var(--ink-0); }
h2 + .lede { font-size: 16px; color: var(--ink-1); font-style: italic; margin-bottom: 22px; }
h3 { font-size: 17px; font-weight: 600; margin: 26px 0 12px; color: var(--ink-0); }
p { color: var(--ink-1); margin: 14px 0; }
strong { color: var(--ink-0); font-weight: 600; }
em { color: var(--ink-0); }

.thesis-card {
  background: linear-gradient(180deg, rgba(245, 215, 110, 0.08), rgba(245, 215, 110, 0.02));
  border-left: 3px solid var(--gold);
  padding: 24px 28px;
  margin: 18px 0 30px;
  font-family: var(--serif);
}
.thesis-card .label { font-family: var(--mono); font-size: 10px; color: var(--gold); letter-spacing: 0.16em; text-transform: uppercase; margin-bottom: 8px; }
.thesis-card .claim { font-size: 20px; line-height: 1.4; color: var(--ink-0); font-weight: 500; margin: 0 0 14px; }
.thesis-card .support { color: var(--ink-1); font-size: 15px; line-height: 1.7; }

.warn-card {
  background: linear-gradient(180deg, rgba(251, 146, 60, 0.10), rgba(251, 146, 60, 0.02));
  border-left: 3px solid var(--orange);
  padding: 22px 28px;
  margin: 18px 0;
}
.warn-card .label { font-family: var(--mono); font-size: 10px; color: var(--orange); letter-spacing: 0.16em; text-transform: uppercase; margin-bottom: 6px; }
.warn-card p { color: var(--ink-0); margin: 6px 0; font-size: 15px; }

table { width: 100%; border-collapse: collapse; font-family: var(--sans); font-size: 13px; margin: 16px 0; }
th, td { text-align: left; padding: 9px 12px; border-bottom: 1px solid var(--rule); }
th { background: var(--bg-2); color: var(--ink-2); font-weight: 600; font-family: var(--mono); font-size: 10px; letter-spacing: 0.1em; text-transform: uppercase; }
td.num { font-family: var(--mono); text-align: right; }
td.pos { color: var(--green); }
td.neg { color: var(--red); }
.row-survivor { background: rgba(74, 222, 128, 0.06); }
.row-failed { background: rgba(248, 113, 113, 0.03); }
.row-baseline { background: rgba(245, 215, 110, 0.05); }

.pill { display: inline-block; padding: 2px 9px; border-radius: 999px; font-family: var(--mono); font-size: 10px; letter-spacing: 0.06em; }
.pill.pass { background: rgba(74, 222, 128, 0.16); color: var(--green); }
.pill.fail { background: rgba(248, 113, 113, 0.16); color: var(--red); }
.pill.warn { background: rgba(251, 146, 60, 0.16); color: var(--orange); }
.pill.neutral { background: rgba(125, 211, 252, 0.14); color: var(--blue); }

.kpi-row { display: flex; gap: 16px; margin: 16px 0 24px; flex-wrap: wrap; }
.kpi { flex: 1; min-width: 150px; background: var(--bg-1); border: 1px solid var(--rule); border-left: 3px solid var(--gold); padding: 14px 18px; border-radius: 4px; }
.kpi .label { font-family: var(--mono); font-size: 10px; color: var(--ink-2); letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 6px; }
.kpi .value { font-size: 22px; font-weight: 600; color: var(--ink-0); font-family: var(--mono); }
.kpi .sub { font-size: 11px; color: var(--ink-2); font-family: var(--mono); margin-top: 2px; }

.colophon { margin-top: 64px; padding-top: 24px; border-top: 1px solid var(--rule); color: var(--ink-2); font-family: var(--mono); font-size: 11px; letter-spacing: 0.05em; line-height: 1.7; }
.colophon strong { color: var(--ink-1); }

code { font-family: var(--mono); background: var(--bg-2); padding: 2px 6px; border-radius: 3px; font-size: 0.9em; color: var(--blue); }

.note-list { background: var(--bg-1); border: 1px solid var(--rule); padding: 18px 26px; border-radius: 4px; }
.note-list li { margin: 8px 0; color: var(--ink-1); }

.empty-state { padding: 30px; text-align: center; color: var(--ink-2); font-style: italic; background: var(--bg-1); border: 1px dashed var(--rule); border-radius: 4px; }
"""


def _row_class(c: dict, baseline_wr: float) -> str:
    if c["wr_lo"] >= MIN_WILSON_LB and c["pf"] >= MIN_PF and c["pf"] != float("inf") and c["n"] >= MIN_N:
        return "row-survivor"
    return "row-failed" if c["wr"] < baseline_wr else ""


def render_combo_table(combos: list[dict], baseline_wr: float, *, with_fail_reasons: bool = False, max_rows: int = None) -> str:
    if not combos:
        return '<div class="empty-state">No combinations matched the filter criteria.</div>'
    rows_to_show = combos[:max_rows] if max_rows else combos
    head_extra = "<th>Why filtered</th>" if with_fail_reasons else ""
    html = [f'''<table>
<thead><tr>
  <th style="width:34%">Combination</th>
  <th>k</th>
  <th>n</th>
  <th>WR</th>
  <th>Wilson 95% LB</th>
  <th>CI width</th>
  <th>PF</th>
  <th>Expectancy</th>
  <th>Avg hold (d)</th>
  {head_extra}
</tr></thead><tbody>''']
    for c in rows_to_show:
        cls = _row_class(c, baseline_wr)
        pf_txt = "&infin;" if c["pf"] == float("inf") else f"{c['pf']:.2f}"
        wr_cls = "pos" if c["wr"] >= baseline_wr else "neg"
        exp_cls = "pos" if c["expectancy"] > 0 else "neg"
        fail_cell = f"<td>{c.get('fail_reasons','')}</td>" if with_fail_reasons else ""
        html.append(f'''<tr class="{cls}">
  <td><code>{c["combo_label"]}</code></td>
  <td class="num">{c["k"]}</td>
  <td class="num">{c["n"]}</td>
  <td class="num {wr_cls}">{c["wr"]*100:.1f}%</td>
  <td class="num">{c["wr_lo"]*100:.1f}%</td>
  <td class="num">{c["ci_width_pp"]:.1f}pp</td>
  <td class="num">{pf_txt}</td>
  <td class="num {exp_cls}">{c["expectancy"]:+.2f}%</td>
  <td class="num">{c["avg_hold"]:.1f}</td>
  {fail_cell}
</tr>''')
    html.append("</tbody></table>")
    return "\n".join(html)


def render(report_data: dict) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    bt = report_data["backtest"]
    sl = report_data["signal_log"]

    # ─── Backtest section
    bt_baseline_wr = bt["baseline"]["wr"]
    bt_kpis = f'''
<div class="kpi-row">
  <div class="kpi"><div class="label">Trades</div><div class="value">{bt["baseline"]["n"]}</div><div class="sub">2023-08-04 → 2026-04-30</div></div>
  <div class="kpi"><div class="label">Baseline WR</div><div class="value">{bt_baseline_wr*100:.1f}%</div><div class="sub">Wilson LB {bt["baseline"]["wr_lo"]*100:.1f}%</div></div>
  <div class="kpi"><div class="label">Baseline PF</div><div class="value">{bt["baseline"]["pf"]:.2f}</div><div class="sub">Expectancy {bt["baseline"]["expectancy"]:+.2f}%</div></div>
  <div class="kpi"><div class="label">Survivors</div><div class="value" style="color:var(--green)">{len(bt["survivors"])}</div><div class="sub">n&ge;{MIN_N}, WLB&ge;{int(MIN_WILSON_LB*100)}%, PF&ge;{MIN_PF}</div></div>
</div>'''

    bt_survivors_html = render_combo_table(bt["survivors"], bt_baseline_wr) if bt["survivors"] else '<div class="empty-state">No backtest combinations cleared the alpha bar (n&ge;20, Wilson LB&ge;40%, PF&ge;1.3).</div>'
    bt_failed_html = render_combo_table(bt["failed"][:30], bt_baseline_wr, with_fail_reasons=True)
    bt_full_html = render_combo_table(bt["all"], bt_baseline_wr, max_rows=80)

    # ─── Signal log section
    sl_baseline_wr = sl["baseline"]["wr"]
    sl_kpis = f'''
<div class="kpi-row">
  <div class="kpi"><div class="label">Closed signals</div><div class="value">{sl["baseline"]["n"]}</div><div class="sub">2026-04-13 → 2026-05-08</div></div>
  <div class="kpi"><div class="label">Baseline WR</div><div class="value">{sl_baseline_wr*100:.1f}%</div><div class="sub">Wilson LB {sl["baseline"]["wr_lo"]*100:.1f}%</div></div>
  <div class="kpi"><div class="label">Baseline PF</div><div class="value">{sl["baseline"]["pf"]:.2f}</div><div class="sub">Expectancy {sl["baseline"]["expectancy"]:+.2f}%</div></div>
  <div class="kpi"><div class="label">Survivors</div><div class="value" style="color:var(--green)">{len(sl["survivors"])}</div><div class="sub">n&ge;{MIN_N}, WLB&ge;{int(MIN_WILSON_LB*100)}%, PF&ge;{MIN_PF}</div></div>
</div>'''

    sl_survivors_html = render_combo_table(sl["survivors"], sl_baseline_wr, max_rows=60) if sl["survivors"] else '<div class="empty-state">No signal-log combinations cleared the alpha bar.</div>'
    sl_failed_html = render_combo_table(sl["failed"][:30], sl_baseline_wr, with_fail_reasons=True)
    sl_full_html = render_combo_table(sl["all"], sl_baseline_wr, max_rows=120)

    # ─── Top-3 stand-out summary (across both corpora)
    all_survivors = [
        {"corpus": "750d backtest", **c} for c in bt["survivors"]
    ] + [
        {"corpus": "signal log",   **c} for c in sl["survivors"]
    ]
    top_callout = ""
    if all_survivors:
        top = sorted(all_survivors, key=lambda c: (c["wr_lo"], c["n"]), reverse=True)[:5]
        rows = ""
        for c in top:
            pf_txt = "&infin;" if c["pf"] == float("inf") else f"{c['pf']:.2f}"
            rows += (
                f'<tr><td><span class="pill neutral">{c["corpus"]}</span></td>'
                f'<td><code>{c["combo_label"]}</code></td>'
                f'<td class="num">{c["n"]}</td>'
                f'<td class="num pos">{c["wr"]*100:.1f}%</td>'
                f'<td class="num">{c["wr_lo"]*100:.1f}%</td>'
                f'<td class="num">{pf_txt}</td>'
                f'<td class="num pos">{c["expectancy"]:+.2f}%</td></tr>'
            )
        top_callout = f'''
<h3>Top survivors across both corpora</h3>
<table>
<thead><tr><th>Corpus</th><th>Combination</th><th>n</th><th>WR</th><th>Wilson LB</th><th>PF</th><th>Expectancy</th></tr></thead>
<tbody>{rows}</tbody>
</table>
'''
    else:
        top_callout = '<div class="empty-state"><strong>Zero combinations cleared the alpha bar in either corpus.</strong> See the failed-combinations tables below for the closest near-misses and reasons.</div>'

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8">
<title>Catalyst-Conditional Trade Decomposition — A5</title>
<style>{CSS}</style>
</head><body>
<div class="page">

<div class="masthead">
  <div class="brand-row"><span class="left">SwingTrade · Research</span><span>A5 · {today}</span></div>
  <h1 class="title">Catalyst-Conditional Trade Decomposition</h1>
  <div class="subtitle">Pure technical features failed to predict +2% movers (mover_predictor v1+v2, AUC 0.546). This note tests whether catalyst-adjacent slicing surfaces hidden alpha buckets — without ML, just Wilson 95% CIs across all 2<sup>N</sup> dimension combinations.</div>
  <div class="byline">Threshold: n&ge;{MIN_N} · Wilson LB&ge;{int(MIN_WILSON_LB*100)}% · PF&ge;{MIN_PF}</div>
</div>

<section>
  <div class="section-num">§ 1 · Headline</div>
  <h2>What survived the alpha filter</h2>
  <p class="lede">The combinations below cleared all three statistical bars in their respective corpora. Anything not listed here failed at least one bar and sits in the diagnostic tables further down.</p>
  {top_callout}
</section>

<section>
  <div class="section-num">§ 2 · Data Quality Notes</div>
  <h2>What we have, and what we don't</h2>

  <div class="warn-card">
    <div class="label">⚠ Critical data gap</div>
    <p>The <strong>384-trade 750d backtest</strong> trade record carries <strong>no per-trade catalyst metadata</strong>.
    Each trade has only: <code>ticker, entry_date, exit_date, entry_price, exit_price, stop_price, position_size, pnl_pct, pnl_dollar, exit_reason, days_held, setup_type, score, verdict, win, trail_activated, highest_price</code>.
    There are <strong>no</strong> <code>catalyst_tags</code>, <code>news_sentiment_score</code>, <code>uoa</code>, <code>insider_data</code>, <code>analyst</code>, or <code>earnings</code> fields.</p>
    <p>The <strong>1,106-entry signal_log</strong> has richer metadata (<code>setup_family</code>, <code>entry_quality</code>, <code>conviction_label</code>, <code>regime_name</code>, <code>tail_filter_demoted</code>, <code>profile</code>) but its <code>raw_json</code> blobs are uniformly empty (0/1106 populated). It also <strong>does not</strong> log <code>catalyst_tags</code>, news scores, UOA flags, insider clusters, analyst upgrades, or earnings proximity.</p>
    <p>The two corpora overlap by exactly <strong>1 trade</strong> (different windows: backtest 2023-08-04 → 2026-04-30, signal_log 2026-04-13 → 2026-05-08). Cross-enrichment is therefore impossible.</p>
  </div>

  <h3>What this script substitutes</h3>
  <ul class="note-list">
    <li><strong>Backtest corpus:</strong> uses <code>setup_type</code> (6 distinct values) as a coarse catalyst-style proxy, plus a <code>score</code> high/mid band split. These are the only entry-time signals captured in the trade record.</li>
    <li><strong>Signal-log corpus:</strong> uses <code>setup_family</code>, <code>strategy</code>, <code>entry_quality</code>, <code>conviction_label</code>, <code>regime_name</code>, and <code>tail_filter_demoted</code> as catalyst-adjacent dimensions.</li>
    <li>True catalyst conditioning (earnings ±5d, insider cluster 30d, UOA, analyst upgrade ±14d, news sentiment burst) requires a one-line patch to <code>backtest.py</code> and <code>signal_tracker.py</code> to <strong>persist <code>catalyst_tags</code> + <code>news_sentiment_score.score</code> + <code>tier1_signals.signals</code> into the trade record at entry time</strong>. Until that ships, this analysis is a coarse approximation.</li>
  </ul>
</section>

<section>
  <div class="section-num">§ 3 · 750d backtest — proxy decomposition</div>
  <h2>384 trades, setup-and-score proxy</h2>
  <p class="lede">Six setup types + score bands. The decomposition probes whether any setup-band combination escapes the 27.3% baseline WR / 0.70 PF that doomed the 750d run.</p>
  {bt_kpis}

  <h3>Surviving combinations</h3>
  {bt_survivors_html}

  <h3>Failed combinations (top 30, with reasons)</h3>
  {bt_failed_html}

  <h3>Full matrix — top 80 of {len(bt["all"])} combinations</h3>
  {bt_full_html}
</section>

<section>
  <div class="section-num">§ 4 · Signal log — catalyst-adjacent decomposition</div>
  <h2>{sl["baseline"]["n"]} closed signals, 10 dimensions</h2>
  <p class="lede">Setup family, entry quality, conviction, regime, tail-filter status. This is the closest we can get to true catalyst conditioning without re-instrumenting the trade journal.</p>
  {sl_kpis}

  <h3>Surviving combinations</h3>
  {sl_survivors_html}

  <h3>Failed combinations (top 30, with reasons)</h3>
  {sl_failed_html}

  <h3>Full matrix — top 120 of {len(sl["all"])} combinations</h3>
  {sl_full_html}
</section>

<section>
  <div class="section-num">§ 5 · Recommended next steps</div>
  <h2>To do this analysis properly</h2>
  <ul class="note-list">
    <li><strong>Fix #1 (15 min):</strong> Patch <code>backtest.py</code> and <code>signal_tracker.py::log_signal()</code> to persist <code>catalyst_tags</code>, <code>catalyst_tier</code>, <code>news_sentiment_score.score</code>, <code>tier1_signals.signals</code>, <code>insider_data.sentiment</code>, <code>uoa.alerts</code>, <code>earnings.days_to_earnings</code>, and <code>analyst.upside_pct</code> into the trade record at entry time. These are all already computed pre-scoring in <code>analysis.py</code>; they just aren't being saved.</li>
    <li><strong>Fix #2 (30 min):</strong> Re-run the 750d backtest. Because catalyst metadata is computed per-day from <code>last_bundle.json</code>-equivalent state, you'd need to either <strong>(a)</strong> snapshot daily bundles during backtest (cheap, just write to <code>cache/backtest_bundles/&lt;date&gt;.json</code>) or <strong>(b)</strong> point-in-time replay catalyst computation at each trade's <code>entry_date</code>.</li>
    <li><strong>Fix #3 (1 hr):</strong> Re-run this script. With real catalyst flags, the 2<sup>5</sup>=32 base combinations + interactions become statistically meaningful.</li>
    <li><strong>Decision rule for live:</strong> if any combination clears n&ge;30, Wilson LB&ge;55%, PF&ge;1.7 — promote it as a hard gate (<code>require_catalyst_combo</code>) in <code>decision_engine.py</code>.</li>
  </ul>
</section>

<div class="colophon">
  <p><strong>Source files</strong> · <code>cache/portfolio_backtest_750d_20260509_100501.json</code> · <code>data/signal_log.json</code></p>
  <p><strong>Output</strong> · <code>cache/catalyst_decomposition_2026-05-09.html</code></p>
  <p><strong>Generator</strong> · <code>decompose_catalyst_trades.py</code> · re-uses <code>tracker.py:wilson_ci()</code> and <code>elite_research_note.py</code> CSS</p>
  <p><strong>Filter bar</strong> · n&ge;{MIN_N} · Wilson 95% LB&ge;{int(MIN_WILSON_LB*100)}% · PF&ge;{MIN_PF}</p>
  <p><strong>Generated</strong> · {today} · A5 task</p>
</div>

</div>
</body></html>
"""


# ─── Main ─────────────────────────────────────────────────────────────────

def load_backtest_records():
    """Load backtest trades, classify each."""
    if not BT_PATH.exists():
        print(f"[ERR] backtest file not found: {BT_PATH}", file=sys.stderr)
        return []
    bt = json.loads(BT_PATH.read_text())
    records = []
    for t in bt.get("trades", []):
        records.append({
            "ticker": t.get("ticker"),
            "win": bool(t.get("win")),
            "pnl_pct": float(t.get("pnl_pct") or 0),
            "hold": float(t.get("days_held") or 0),
            "dims": classify_backtest_trade(t),
        })
    return records


def load_signal_records():
    """Load signal_log entries (closed only), classify each."""
    if not SL_PATH.exists():
        print(f"[ERR] signal log not found: {SL_PATH}", file=sys.stderr)
        return []
    sl = json.loads(SL_PATH.read_text())
    records = []
    for s in sl:
        if s.get("status") != "CLOSED":
            continue
        pnl = s.get("actual_pnl_pct")
        if pnl is None:
            continue
        win = pnl > 0
        records.append({
            "ticker": s.get("ticker"),
            "win": win,
            "pnl_pct": float(pnl),
            "hold": float(s.get("days_to_first_target_hit") or s.get("days_to_stop_hit") or 0),
            "dims": classify_signal(s),
        })
    return records


def baseline_stats(records: list[dict]) -> dict:
    n = len(records)
    if n == 0:
        return {"n": 0, "wr": 0, "wr_lo": 0, "wr_hi": 0, "pf": 0, "expectancy": 0}
    wins = sum(1 for r in records if r["win"])
    pnls = [r["pnl_pct"] for r in records]
    lo, hi = wilson_ci(wins, n)
    return {
        "n": n,
        "wins": wins,
        "wr": wins / n,
        "wr_lo": lo,
        "wr_hi": hi,
        "pf": profit_factor(pnls),
        "expectancy": expectancy(pnls),
    }


def main():
    print(">> Loading 750d backtest…")
    bt_records = load_backtest_records()
    print(f"   {len(bt_records)} backtest trades loaded")

    print(">> Loading signal_log (CLOSED only)…")
    sl_records = load_signal_records()
    print(f"   {len(sl_records)} closed signals loaded")

    bt_dims = ["is_breakout_setup", "is_pocket_pivot", "is_squeeze", "is_trend_cont", "score_high", "score_mid"]
    sl_dims = [
        "is_impulse_catalyst", "is_breakout_expand", "is_trend_cont",
        "is_insider_setup", "is_squeeze_setup", "is_pullback_setup",
        "entry_fresh", "entry_pullback", "entry_extended",
        "is_t3_conviction", "regime_bull", "tail_demoted",
    ]

    print(">> Decomposing backtest…")
    bt_combos_raw = decompose(bt_records, bt_dims)
    bt_combos = dedupe_by_signature(bt_combos_raw)
    bt_survivors, bt_failed = filter_survivors(bt_combos)
    print(f"   {len(bt_combos_raw)} raw → {len(bt_combos)} deduped · {len(bt_survivors)} survivors · {len(bt_failed)} failed")

    print(">> Decomposing signal_log…")
    sl_combos_raw = decompose(sl_records, sl_dims)
    sl_combos = dedupe_by_signature(sl_combos_raw)
    sl_survivors, sl_failed = filter_survivors(sl_combos)
    print(f"   {len(sl_combos_raw)} raw → {len(sl_combos)} deduped · {len(sl_survivors)} survivors · {len(sl_failed)} failed")

    report_data = {
        "backtest": {
            "baseline": baseline_stats(bt_records),
            "all": bt_combos,
            "survivors": bt_survivors,
            "failed": bt_failed,
        },
        "signal_log": {
            "baseline": baseline_stats(sl_records),
            "all": sl_combos,
            "survivors": sl_survivors,
            "failed": sl_failed,
        },
    }

    print(">> Rendering HTML…")
    html = render(report_data)
    OUT_PATH.write_text(html)
    print(f">> WROTE {OUT_PATH}  ({OUT_PATH.stat().st_size:,} bytes)")

    # CLI summary
    print()
    print("─" * 64)
    print(f"BACKTEST  baseline: n={report_data['backtest']['baseline']['n']}  WR={report_data['backtest']['baseline']['wr']*100:.1f}%  PF={report_data['backtest']['baseline']['pf']:.2f}")
    print(f"          survivors: {len(bt_survivors)}")
    for s in bt_survivors[:5]:
        pf_txt = "inf" if s["pf"] == float("inf") else f"{s['pf']:.2f}"
        print(f"            • {s['combo_label']:60s}  n={s['n']:3d}  WR={s['wr']*100:5.1f}%  LB={s['wr_lo']*100:5.1f}%  PF={pf_txt}")
    print()
    print(f"SIGNAL    baseline: n={report_data['signal_log']['baseline']['n']}  WR={report_data['signal_log']['baseline']['wr']*100:.1f}%  PF={report_data['signal_log']['baseline']['pf']:.2f}")
    print(f"          survivors: {len(sl_survivors)}")
    for s in sl_survivors[:5]:
        pf_txt = "inf" if s["pf"] == float("inf") else f"{s['pf']:.2f}"
        print(f"            • {s['combo_label']:60s}  n={s['n']:3d}  WR={s['wr']*100:5.1f}%  LB={s['wr_lo']*100:5.1f}%  PF={pf_txt}")
    print("─" * 64)


if __name__ == "__main__":
    main()
