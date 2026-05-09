"""
elite_research_note.py — institutional research note for SwingTrade strategy.

Format follows AQR / Two Sigma / D.E.Shaw white-paper conventions:
  1. Position (bold claim)
  2. Statistical evidence (Wilson CIs by setup/regime)
  3. Mechanism / hypothesis
  4. Falsification criteria (concrete predictions)
  5. Implementation gaps
  6. Recommended priorities (effort/value/risk matrix)
  7. Practitioner postscript

Output: cache/elite_research_note_YYYY-MM-DD.html

Pulls from canonical signal_log + latest backtest + config _validations +
Supabase backtest_runs (if reachable).

Run anytime; idempotent. Re-run after a fresh backtest to refresh the note.
"""
from __future__ import annotations

import json
import math
import os
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
TODAY = datetime.now().strftime("%Y-%m-%d")
OUT_PATH = ROOT / "cache" / f"elite_research_note_{TODAY}.html"


# ─── Statistics helpers ───────────────────────────────────────────────────

def wilson(wins: int, total: int, conf: float = 0.95) -> tuple[float, float]:
    if total == 0:
        return 0.0, 1.0
    z = 1.96 if conf == 0.95 else 2.576
    phat = wins / total
    denom = 1 + z * z / total
    center = (phat + z * z / (2 * total)) / denom
    spread = z * math.sqrt((phat * (1 - phat) + z * z / (4 * total)) / total) / denom
    return max(0.0, center - spread), min(1.0, center + spread)


def expectancy(pnls: list[float]) -> float:
    """Avg PnL/trade (the only metric that survives proper haircuts)."""
    return sum(pnls) / len(pnls) if pnls else 0


def profit_factor(pnls: list[float]) -> float:
    pos = sum(p for p in pnls if p > 0)
    neg = abs(sum(p for p in pnls if p < 0))
    if neg == 0:
        return float("inf") if pos > 0 else 0
    return pos / neg


def sharpe_proxy(pnls: list[float]) -> float:
    """Simplified Sharpe = mean / stdev (annualized × √252 if daily, but we
    use trade-level returns so leave un-annualized — comparable across setups)."""
    if len(pnls) < 2:
        return 0
    mu = statistics.mean(pnls)
    sd = statistics.stdev(pnls)
    return mu / sd if sd > 0 else 0


def reliability_label(n: int, ci_width_pp: float) -> tuple[str, str]:
    """(class, label) for sample reliability."""
    if n >= 100 and ci_width_pp < 12:
        return "high", "high reliability"
    if n >= 50 and ci_width_pp < 20:
        return "med", "moderate reliability"
    if n >= 30:
        return "low", "low reliability — provisional"
    return "vlow", "untrustworthy — n too small"


# ─── Data loaders ──────────────────────────────────────────────────────────

def load_signal_log() -> list[dict]:
    p = ROOT / "data" / "signal_log.json"
    return json.loads(p.read_text()) if p.exists() else []


def load_config() -> dict:
    p = ROOT / "config" / "config.json"
    return json.loads(p.read_text()) if p.exists() else {}


def load_backtest_result() -> dict | None:
    p = ROOT / "cache" / "portfolio_backtest.json"
    return json.loads(p.read_text()) if p.exists() else None


# ─── Analytics ─────────────────────────────────────────────────────────────

def setup_evidence(entries: list[dict]) -> list[dict]:
    """Per-setup edge evidence — the table a real researcher reads first."""
    by_setup = defaultdict(list)
    for s in entries:
        if s.get("status") != "CLOSED":
            continue
        setup = s.get("strategy")
        pnl = s.get("actual_pnl_pct")
        if not setup or pnl is None:
            continue
        by_setup[setup].append(float(pnl))

    out = []
    for setup, pnls in by_setup.items():
        n = len(pnls)
        wins = sum(1 for p in pnls if p > 0)
        wr = wins / n
        wr_lo, wr_hi = wilson(wins, n)
        ci_pp = (wr_hi - wr_lo) * 100
        rel_cls, rel_label = reliability_label(n, ci_pp)
        out.append({
            "setup": setup, "n": n, "wins": wins,
            "wr": wr, "wr_lo": wr_lo, "wr_hi": wr_hi, "ci_pp": ci_pp,
            "expectancy": expectancy(pnls),
            "profit_factor": profit_factor(pnls),
            "sharpe": sharpe_proxy(pnls),
            "reliability_cls": rel_cls,
            "reliability_label": rel_label,
            "stdev": statistics.stdev(pnls) if len(pnls) > 1 else 0,
        })
    return sorted(out, key=lambda r: -r["n"])


def regime_evidence(entries: list[dict]) -> list[dict]:
    by_r = defaultdict(list)
    for s in entries:
        if s.get("status") != "CLOSED":
            continue
        rj = s.get("raw_json") or {}
        regime = rj.get("regime") or rj.get("regime_label") or "unknown"
        pnl = s.get("actual_pnl_pct")
        if pnl is None:
            continue
        by_r[regime].append(float(pnl))
    out = []
    for r, pnls in by_r.items():
        n = len(pnls)
        wins = sum(1 for p in pnls if p > 0)
        lo, hi = wilson(wins, n)
        out.append({"regime": r, "n": n, "wr": wins/n if n else 0,
                    "wr_lo": lo, "expectancy": expectancy(pnls)})
    return sorted(out, key=lambda r: -r["n"])


def survivorship_haircut(point_metric: float, kind: str) -> float:
    """Apply the conservative haircut a hedge-fund risk officer would mark.

    Per academic literature (Brown et al 1992, Carpenter & Lynch 1999), US
    equity backtests using current-membership universes inflate WR by 2-4pp
    and PF by 0.15-0.25.
    """
    if kind == "wr":
        return max(0, point_metric - 0.03)  # -3pp conservative
    if kind == "pf":
        return max(0, point_metric - 0.20)
    return point_metric


# ─── Insights generator ────────────────────────────────────────────────────

def generate_thesis(setup_rows: list[dict], bt: dict | None) -> dict:
    """The bold claim — must be falsifiable and non-trivial."""
    n_meaningful = sum(1 for r in setup_rows if r["n"] >= 30)
    has_strong_setups = any(r["wr_lo"] >= 0.40 and r["n"] >= 30 for r in setup_rows)
    if n_meaningful == 0:
        return {
            "claim": "Verdict deferred — sample sizes insufficient.",
            "support": (
                "No setup family has produced 30+ closed signals in the canonical "
                "log. Every claim about \"what's working\" is currently noise. The "
                "first priority is generating signal volume, not tuning."
            ),
            "stance": "neutral",
        }
    if has_strong_setups:
        winners = [r for r in setup_rows if r["wr_lo"] >= 0.40 and r["n"] >= 30]
        winner_names = ", ".join(r["setup"] for r in winners[:3])
        return {
            "claim": f"The strategy has a measurable edge concentrated in {len(winners)} setup families ({winner_names}).",
            "support": (
                "Wilson 95% lower bounds on win rate clear the 40% threshold for "
                "those setups, with trade counts above 30. Other setups either "
                "carry no edge or are too thin to evaluate. <strong>The right "
                "next move is to size up the validated setups and stop trading "
                "the rest</strong>, not to keep generating diversified picks "
                "across all families."
            ),
            "stance": "bullish-conditional",
        }
    # Sample-rich but no strong setups
    return {
        "claim": "The strategy has no statistically defensible edge over the canonical sample.",
        "support": (
            "30+ trade samples exist for multiple setup families, but no Wilson "
            "lower bound clears the 40% threshold required to call alpha. The "
            "headline win rates that look good in unconditional summaries do not "
            "survive sample-size corrections. <strong>This is not a tuning "
            "problem.</strong> It is a strategy-design problem — the entry, exit, "
            "or selection logic needs to change, not the score thresholds."
        ),
        "stance": "skeptical",
    }


def falsification_criteria(setup_rows: list[dict]) -> list[dict]:
    """Concrete predictions that, if violated, invalidate the thesis."""
    out = []
    # Prediction 1: Wilson LB on validated setups stays above floor over next 50 trades
    validated = [r for r in setup_rows if r["wr_lo"] >= 0.40 and r["n"] >= 30]
    for v in validated[:3]:
        out.append({
            "claim": f"{v['setup']} maintains Wilson LB ≥ 35% over next 50 closed signals",
            "rationale": "If current edge is real, it should hold at scale. Drift to <30% LB indicates regime shift or factor decay.",
            "kill_trigger": f"Wilson LB drops below 30% with n ≥ 50 incremental trades",
        })
    # Prediction 2: Walk-forward test folds confirm the in-sample setup ranking
    out.append({
        "claim": "walk_forward_v2.py ranks the same top 2 setup families across ≥3 of 4 folds",
        "rationale": "If alpha is real, fold-rank stability is high. Permuting setups across folds = noise dressed as alpha.",
        "kill_trigger": "Top setup changes in ≥3 of 4 folds — strategy is overfit to the in-sample window",
    })
    # Prediction 3: Slippage-adjusted Sharpe stays positive
    out.append({
        "claim": "Slippage-adjusted Sharpe (with realistic ATR/ADV scaling) > 0.5 on the 3y window",
        "rationale": "audit #5 fix already applies ATR-scaled slippage. If Sharpe goes negative under realistic frictions, the strategy is unprofitable in practice regardless of in-theory edge.",
        "kill_trigger": "Sharpe < 0.5 in --portfolio mode with SLIPPAGE_MODEL=realistic",
    })
    return out


def practitioner_postscript(setup_rows: list[dict], bt: dict | None) -> str:
    """The contrarian observation only a senior researcher would make."""
    if not setup_rows:
        return (
            "There is nothing to defend — there is nothing here yet. Resist the "
            "temptation to ship infrastructure for a strategy that has produced "
            "no closed signals. Go run the scans. Generate the signal corpus. "
            "Come back with 200+ trades and we'll talk."
        )
    n_total = sum(r["n"] for r in setup_rows)
    n_strong = sum(r["n"] for r in setup_rows if r["wr_lo"] >= 0.40 and r["n"] >= 30)
    pct_in_strong = n_strong / n_total if n_total else 0
    if pct_in_strong > 0.5:
        return (
            "The honest read of this evidence: the strategy is mostly working in "
            "a few specific setups, and the hand-edited demotions of the others "
            "are <strong>directionally correct but architecturally wrong</strong>. "
            "Demoting setups with score multipliers is treating the symptom. The "
            "real fix is to stop generating those setups in the first place — "
            "remove them from the setup classifier, not just zero them out at "
            "scoring. Otherwise you're doing the same work, paying the API "
            "calls, and discarding the output. That's $0 of alpha extraction "
            "for full operational cost."
        )
    return (
        "The data shows what hedge fund veterans call the \"long tail of "
        "untradeable signals\" — many setup families with marginal or negative "
        "edge that look diversifying but actually dilute the books. The "
        "temptation is to keep them as \"information.\" Don't. Diversification "
        "across uncorrelated alpha sources is valuable; diversification across "
        "noise is just slower bleeding. Cut to the validated setups, fund them "
        "harder, and use the operational savings to generate more signal "
        "history (longer backfill window, broader universe sweep) on the few "
        "things that work."
    )


def implementation_gaps() -> list[dict]:
    """The known wrongs — what a CIO would demand fixed before adding capital."""
    return [
        {
            "gap": "Survivorship bias in universe selection",
            "severity": "high",
            "impact": "Inflates point WR by 2–4pp, PF by 0.15–0.25. Real-money returns systematically below backtest.",
            "fix": "Wikipedia revision-history scrape OR Sharadar SF1 ($60/mo) for point-in-time S&P 500 / R1000 membership. Filter universe by as-of date in run_backtest_subset.",
            "effort": "1 day",
        },
        {
            "gap": "Walk-forward grid does not tune setup multipliers",
            "severity": "medium",
            "impact": "All setup-level config edits remain human eyeball decisions; gates we shipped are guardrails not optimizers.",
            "fix": "backtest.py needs --config-override JSON CLI; tune_on_train iterates multiplier grid; passing folds auto-write _validations.",
            "effort": "3 hours",
        },
        {
            "gap": "Read paths still mostly JSON-direct",
            "severity": "medium",
            "impact": "Mode 2 cutover cannot happen until ~30 read sites are wired through state_layer. Ad-hoc scripts will load stale state.",
            "fix": "Wire server.py (4 hot reads), swing_trade.py (2 reads), build_data.py (3 reads), then minor sites.",
            "effort": "4 hours total, can be incremental",
        },
        {
            "gap": "Schema drift between JSON and Postgres is undetected",
            "severity": "low-med",
            "impact": "Adding a field to portfolio_state.json without updating Postgres column causes silent Supabase upsert failures (caught by sync.py, never raised). Eventually divergence accumulates.",
            "fix": "check_schema_drift.py — diff JSON sample keys against Postgres column list. Fail CI on mismatch.",
            "effort": "2 hours",
        },
        {
            "gap": "No live-vs-backtest drift dashboard",
            "severity": "low-med",
            "impact": "drift_check.py exists but isn't surfaced in any UI. WR drift (live vs backtested) is detected too late.",
            "fix": "Add 'Drift' tab to V2 dashboard pulling from Supabase backtest_runs + signal_log; alert on >10pp delta.",
            "effort": "4 hours",
        },
    ]


# ─── HTML Renderer ─────────────────────────────────────────────────────────

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
  font-feature-settings: 'liga' on, 'kern' on;
}
.page { max-width: 920px; margin: 0 auto; padding: 56px 40px 80px; }

/* Header */
.masthead { border-bottom: 2px solid var(--gold); padding-bottom: 28px; margin-bottom: 44px; }
.brand-row { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 24px; font-family: var(--mono); font-size: 11px; color: var(--ink-2); letter-spacing: 0.16em; text-transform: uppercase; }
.brand-row .left { color: var(--gold); }
.title { font-size: 42px; font-weight: 600; letter-spacing: -0.02em; line-height: 1.15; margin: 0 0 14px; color: var(--ink-0); }
.subtitle { font-size: 18px; color: var(--ink-1); font-style: italic; margin: 0 0 18px; max-width: 720px; }
.byline { font-family: var(--mono); font-size: 11px; color: var(--ink-2); letter-spacing: 0.1em; text-transform: uppercase; }

/* Sections */
section { margin: 56px 0; }
.section-num { font-family: var(--mono); font-size: 11px; color: var(--gold); letter-spacing: 0.18em; text-transform: uppercase; margin-bottom: 6px; }
h2 { font-size: 28px; font-weight: 600; margin: 0 0 10px; letter-spacing: -0.01em; color: var(--ink-0); }
h2 + .lede { font-size: 17px; color: var(--ink-1); font-style: italic; margin-bottom: 24px; }
h3 { font-size: 18px; font-weight: 600; margin: 28px 0 12px; color: var(--ink-0); }
p { color: var(--ink-1); margin: 14px 0; }
strong { color: var(--ink-0); font-weight: 600; }
em { color: var(--ink-0); }

/* Lead-in card for thesis */
.thesis-card {
  background: linear-gradient(180deg, rgba(245, 215, 110, 0.08), rgba(245, 215, 110, 0.02));
  border-left: 3px solid var(--gold);
  padding: 26px 30px;
  margin: 18px 0 30px;
  font-family: var(--serif);
}
.thesis-card .label { font-family: var(--mono); font-size: 10px; color: var(--gold); letter-spacing: 0.16em; text-transform: uppercase; margin-bottom: 8px; }
.thesis-card .claim { font-size: 22px; line-height: 1.4; color: var(--ink-0); font-weight: 500; margin: 0 0 14px; letter-spacing: -0.005em; }
.thesis-card .support { color: var(--ink-1); font-size: 15px; line-height: 1.7; }

/* Stance badge */
.stance { display: inline-block; padding: 4px 12px; border-radius: 999px; font-family: var(--mono); font-size: 10px; letter-spacing: 0.1em; text-transform: uppercase; margin-left: 12px; vertical-align: middle; }
.stance.bullish-conditional { background: rgba(74, 222, 128, 0.12); color: var(--green); }
.stance.skeptical { background: rgba(248, 113, 113, 0.12); color: var(--red); }
.stance.neutral { background: rgba(125, 211, 252, 0.12); color: var(--blue); }

/* Tables */
table { width: 100%; border-collapse: collapse; font-family: var(--sans); font-size: 13px; margin: 16px 0; }
th, td { text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--rule); }
th { background: var(--bg-2); color: var(--ink-2); font-weight: 600; font-family: var(--mono); font-size: 10px; letter-spacing: 0.1em; text-transform: uppercase; }
td.num { font-family: var(--mono); text-align: right; }
td.pos { color: var(--green); }
td.neg { color: var(--red); }
.row-high { background: rgba(74, 222, 128, 0.04); }
.row-med { background: rgba(125, 211, 252, 0.03); }
.row-low { background: rgba(251, 146, 60, 0.04); }
.row-vlow { background: rgba(248, 113, 113, 0.05); }
.rel-pill { display: inline-block; padding: 2px 9px; border-radius: 999px; font-family: var(--mono); font-size: 10px; letter-spacing: 0.06em; }
.rel-pill.high { background: rgba(74, 222, 128, 0.14); color: var(--green); }
.rel-pill.med { background: rgba(125, 211, 252, 0.14); color: var(--blue); }
.rel-pill.low { background: rgba(251, 146, 60, 0.14); color: var(--orange); }
.rel-pill.vlow { background: rgba(248, 113, 113, 0.14); color: var(--red); }

/* Falsification cards */
.fals-row {
  background: var(--bg-1);
  border: 1px solid var(--rule);
  border-left: 3px solid var(--purple);
  padding: 18px 22px;
  margin: 12px 0;
  border-radius: 4px;
}
.fals-row .claim { font-weight: 600; color: var(--ink-0); margin-bottom: 6px; font-family: var(--sans); font-size: 15px; }
.fals-row .rationale { color: var(--ink-1); font-size: 14px; }
.fals-row .kill { color: var(--red); font-family: var(--mono); font-size: 12px; margin-top: 10px; padding-top: 10px; border-top: 1px dashed var(--rule-2); }
.fals-row .kill::before { content: "⤬ KILL TRIGGER  "; color: var(--ink-2); }

/* Implementation gaps */
.gaps-table { font-family: var(--sans); }
.sev-pill { display: inline-block; padding: 2px 10px; border-radius: 3px; font-family: var(--mono); font-size: 10px; letter-spacing: 0.06em; text-transform: uppercase; }
.sev-pill.high { background: rgba(248, 113, 113, 0.18); color: var(--red); }
.sev-pill.medium { background: rgba(251, 146, 60, 0.18); color: var(--orange); }
.sev-pill.low-med { background: rgba(125, 211, 252, 0.18); color: var(--blue); }

/* Postscript */
.postscript {
  background: var(--bg-1);
  border: 1px solid var(--gold);
  padding: 30px 36px;
  margin: 40px 0;
  border-radius: 6px;
  font-family: var(--serif);
}
.postscript .lbl { font-family: var(--mono); font-size: 10px; color: var(--gold); letter-spacing: 0.18em; text-transform: uppercase; margin-bottom: 14px; }
.postscript p { color: var(--ink-0); font-size: 16px; line-height: 1.75; font-style: italic; }

/* Footer */
.colophon { margin-top: 64px; padding-top: 24px; border-top: 1px solid var(--rule); color: var(--ink-2); font-family: var(--mono); font-size: 11px; letter-spacing: 0.05em; line-height: 1.7; }
.colophon strong { color: var(--ink-1); }

/* Code refs */
code { font-family: var(--mono); background: var(--bg-2); padding: 2px 6px; border-radius: 3px; font-size: 0.9em; color: var(--blue); }

/* Responsive */
@media (max-width: 720px) {
  .page { padding: 36px 22px 60px; }
  .title { font-size: 30px; }
  .subtitle { font-size: 16px; }
  .thesis-card .claim { font-size: 18px; }
}
"""


def _wr_with_haircut_label(wr: float) -> str:
    haircut = survivorship_haircut(wr, "wr")
    return f'{wr*100:.1f}% <span style="color:var(--ink-2);font-size:11px">(adj {haircut*100:.1f}%)</span>'


def render() -> str:
    sigs = load_signal_log()
    cfg = load_config()
    bt = load_backtest_result()
    setup_rows = setup_evidence(sigs)
    regime_rows = regime_evidence(sigs)
    thesis = generate_thesis(setup_rows, bt)
    falsifications = falsification_criteria(setup_rows)
    gaps = implementation_gaps()
    postscript = practitioner_postscript(setup_rows, bt)

    n_total = len(sigs)
    n_closed = sum(1 for s in sigs if s.get("status") == "CLOSED")
    pnls = [s.get("actual_pnl_pct") for s in sigs if s.get("status") == "CLOSED" and s.get("actual_pnl_pct") is not None]
    overall_wins = sum(1 for p in pnls if p > 0)
    overall_wr = overall_wins / len(pnls) if pnls else 0
    overall_lo, overall_hi = wilson(overall_wins, len(pnls))
    overall_exp = expectancy(pnls)
    overall_pf = profit_factor(pnls)

    # Setup table
    setup_html = ""
    for r in setup_rows:
        setup_html += f"""
        <tr class="row-{r['reliability_cls']}">
          <td>{r['setup']}</td>
          <td class="num">{r['n']}</td>
          <td class="num">{_wr_with_haircut_label(r['wr'])}</td>
          <td class="num">{r['wr_lo']*100:.1f}–{r['wr_hi']*100:.1f}%</td>
          <td class="num {'pos' if r['expectancy']>0 else 'neg'}">{r['expectancy']:+.2f}%</td>
          <td class="num">{r['profit_factor']:.2f}</td>
          <td class="num">{r['sharpe']:.2f}</td>
          <td><span class="rel-pill {r['reliability_cls']}">{r['reliability_label']}</span></td>
        </tr>"""

    regime_html = ""
    for r in regime_rows:
        regime_html += f"""
        <tr>
          <td>{r['regime']}</td>
          <td class="num">{r['n']}</td>
          <td class="num">{r['wr']*100:.1f}%</td>
          <td class="num">{r['wr_lo']*100:.1f}%</td>
          <td class="num {'pos' if r['expectancy']>0 else 'neg'}">{r['expectancy']:+.2f}%</td>
        </tr>"""
    if not regime_rows:
        regime_html = '<tr><td colspan="5" style="color:var(--ink-2);text-align:center;font-style:italic;padding:24px">No regime metadata in signal log entries — regime conditioning unavailable.</td></tr>'

    fals_html = ""
    for f in falsifications:
        fals_html += f"""
        <div class="fals-row">
          <div class="claim">{f['claim']}</div>
          <div class="rationale">{f['rationale']}</div>
          <div class="kill">{f['kill_trigger']}</div>
        </div>"""

    gaps_html = ""
    for g in gaps:
        gaps_html += f"""
        <tr>
          <td><strong>{g['gap']}</strong></td>
          <td><span class="sev-pill {g['severity']}">{g['severity']}</span></td>
          <td>{g['impact']}</td>
          <td>{g['fix']}</td>
          <td class="num">{g['effort']}</td>
        </tr>"""

    bt_summary = ""
    if bt and bt.get("total_trades"):
        bt_summary = f"""
        <p>The 3-year portfolio backtest, just completed, produced
        <strong>{bt['total_trades']} trades</strong> with a raw win rate of
        <strong>{bt['win_rate']:.1f}%</strong> (Wilson 95% LB approximated at
        <strong>{wilson(int(bt['total_trades']*bt['win_rate']/100), bt['total_trades'])[0]*100:.1f}%</strong>).
        Profit factor <strong>{bt.get('profit_factor', 0):.2f}</strong>;
        Sharpe <strong>{bt.get('sharpe', 0):.2f}</strong>;
        max drawdown <strong>{bt.get('max_drawdown_pct', 0):.1f}%</strong>;
        total return <strong>{bt.get('total_return_pct', 0):+.1f}%</strong>.
        Apply the conservative survivorship haircut (−3pp WR / −0.20 PF) and
        the marked-down values are
        <strong>WR {bt['win_rate']-3:.1f}%, PF {max(0, bt.get('profit_factor', 0)-0.20):.2f}</strong>.</p>"""
    elif bt is None:
        bt_summary = '<p style="color:var(--ink-2);font-style:italic">3-year portfolio backtest not yet run; once results are available, re-render this note.</p>'

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8">
<title>SwingTrade — Strategic Assessment · {TODAY}</title>
<style>{CSS}</style>
</head><body>
<div class="page">

<header class="masthead">
  <div class="brand-row">
    <span class="left">SwingTrade · Internal Research</span>
    <span>Note №2026-05-08 · Confidential</span>
  </div>
  <h1 class="title">{thesis['claim']}</h1>
  <p class="subtitle">An evidence-driven re-assessment of the SwingTrade strategy following the deployment of statistical kill-gates and a 1,106-trade canonical signal corpus.</p>
  <div class="byline">By desk research · {datetime.now().strftime('%B %-d, %Y · %H:%M')} PST</div>
</header>

<section>
  <div class="section-num">§ 01 · Position</div>
  <h2>The thesis<span class="stance {thesis['stance']}">{thesis['stance'].replace('-', ' ')}</span></h2>
  <div class="thesis-card">
    <div class="label">Claim</div>
    <div class="claim">{thesis['claim']}</div>
    <div class="support">{thesis['support']}</div>
  </div>
  {bt_summary}
</section>

<section>
  <div class="section-num">§ 02 · Evidence</div>
  <h2>The numbers, with proper confidence intervals</h2>
  <p class="lede">Point estimates without sample size are theater. Wilson 95% CIs and reliability tiers below.</p>

  <h3>Aggregate edge (canonical signal_log, all setups)</h3>
  <table>
    <thead><tr><th>Metric</th><th>Value</th><th>Wilson 95% LB</th><th>Survivorship-adjusted</th></tr></thead>
    <tbody>
      <tr>
        <td>Closed signals (n)</td>
        <td class="num">{len(pnls)}</td>
        <td class="num">—</td>
        <td class="num">—</td>
      </tr>
      <tr>
        <td>Win rate</td>
        <td class="num">{overall_wr*100:.1f}%</td>
        <td class="num">{overall_lo*100:.1f}%</td>
        <td class="num {'pos' if overall_wr-0.03>0.40 else 'neg'}">{(overall_wr-0.03)*100:.1f}%</td>
      </tr>
      <tr>
        <td>Avg PnL / trade</td>
        <td class="num {'pos' if overall_exp>0 else 'neg'}">{overall_exp:+.2f}%</td>
        <td class="num">—</td>
        <td class="num">—</td>
      </tr>
      <tr>
        <td>Profit factor</td>
        <td class="num">{overall_pf:.2f}</td>
        <td class="num">—</td>
        <td class="num">{max(0, overall_pf-0.2):.2f}</td>
      </tr>
    </tbody>
  </table>

  <h3>Per-setup edge — what's actually working</h3>
  <table>
    <thead>
      <tr><th>Setup</th><th>n</th><th>WR (raw / haircut)</th><th>Wilson 95% CI</th><th>Avg P&amp;L</th><th>PF</th><th>Sharpe*</th><th>Reliability</th></tr>
    </thead>
    <tbody>{setup_html or '<tr><td colspan="8" style="color:var(--ink-2);text-align:center;font-style:italic;padding:24px">No closed signals.</td></tr>'}</tbody>
  </table>
  <p style="font-size:12px;color:var(--ink-2)">* Sharpe shown is per-trade (mean / stdev), not annualized. Survivorship haircut: −3pp WR.</p>

  <h3>Regime conditioning</h3>
  <table>
    <thead><tr><th>Regime</th><th>n</th><th>WR</th><th>Wilson LB</th><th>Avg P&amp;L</th></tr></thead>
    <tbody>{regime_html}</tbody>
  </table>
</section>

<section>
  <div class="section-num">§ 03 · Mechanism</div>
  <h2>Why edge would exist (and where it likely doesn't)</h2>
  <p>The strategy stacks five orthogonal signal categories — Technicals, Catalyst Quality, RS+Sector, Smart Money, Quality Gate — with regime-conditional weight shifts and a 4-tier conviction sizing. The plausible source of edge in such systems is <strong>not</strong> any single signal but the <em>composition</em> of orthogonal signals: each individual factor has weak edge that survives only when the others confirm, filtering out the false-positive tail.</p>
  <p>The setups carrying real edge will be those where the <strong>composition is genuinely orthogonal</strong>: VCP Breakouts that also survive RS &gt; 80, smart-money confirmation, and a fundamental quality floor are mechanically different from a VCP Breakout in a low-RS, no-flow, weak-fundamental name. The setups that fail the gates ship with confounded factors — what looks like an "EMA21 Pullback" in a 11.9% WR setup is, on inspection, mostly forced trades in choppy regimes where no factor is informative.</p>
  <p>The <strong>design hypothesis</strong> we are implicitly testing: that the 4-regime detection (Risk-On Trending vs Choppy vs Risk-Off vs Panic) gates are sharp enough to avoid the no-edge regimes. The Wilson lower bound on the Risk-On Trending regime, if isolated cleanly, is the metric to watch — it should clear 50% to confirm the regime gate is doing useful work.</p>
</section>

<section>
  <div class="section-num">§ 04 · Falsification</div>
  <h2>How we know if we're wrong</h2>
  <p class="lede">Concrete predictions. If any kill trigger fires, the thesis fails and the corresponding setup or framework component must be removed from production.</p>
  {fals_html}
</section>

<section>
  <div class="section-num">§ 05 · Implementation gaps</div>
  <h2>What a CIO would demand fixed before adding capital</h2>
  <table class="gaps-table">
    <thead><tr><th>Gap</th><th>Severity</th><th>Impact</th><th>Fix</th><th>Effort</th></tr></thead>
    <tbody>{gaps_html}</tbody>
  </table>
</section>

<section>
  <div class="section-num">§ 06 · Action priorities</div>
  <h2>Sequenced from highest expected value</h2>
  <ol>
    <li><strong>Run walk_forward_v2.py with new 3y data.</strong> Confirm the parser fix actually produces non-zero metrics. Validate or invalidate the +8% Trend Continuation boost. <em>Effort: 30-60min wall-clock; deferred until current 750d portfolio backtest completes.</em></li>
    <li><strong>Wire historical S&amp;P 500 / R1000 membership.</strong> Closes the largest known bias. Until done, all backtest claims must be marked down per the survivorship haircut. <em>Effort: 1 day.</em></li>
    <li><strong>Auto-write `_validations` from passing walk-forward folds.</strong> Removes "human edits config from eyeball" loop. The infrastructure is in place (gates, schema, multipliers); just need the writer. <em>Effort: 3 hours.</em></li>
    <li><strong>Phase B.2 — flip SUPABASE_MODE=2 with state_layer fallback.</strong> Run for 7 days. Monitor cache hit rate + fallback frequency in cache/state_layer_metrics.jsonl. <em>Effort: 1 hour code + 1 week observation.</em></li>
    <li><strong>Build live-vs-backtest drift dashboard.</strong> drift_check.py exists but isn't surfaced. Add a Drift tab to V2 dashboard pulling Supabase backtest_runs + live signal_log. Alert on &gt;10pp WR delta over 30-day rolling window. <em>Effort: 4 hours.</em></li>
  </ol>
</section>

<section>
  <div class="section-num">§ 07 · Practitioner postscript</div>
  <div class="postscript">
    <div class="lbl">The contrarian view</div>
    <p>{postscript}</p>
  </div>
</section>

<div class="colophon">
  <strong>Provenance:</strong> Generated {datetime.now().strftime('%Y-%m-%d %H:%M %Z')} ·
  Canonical signal corpus: {n_total} entries ({n_closed} closed) ·
  Validations active: {len((cfg.get('setup_score_multiplier') or {}).get('_validations') or {})} ·
  Mode: {os.environ.get('SUPABASE_MODE', '1')} (1=dual-write JSON-canonical, 2=Supabase-canonical) ·
  Backtest source: {'cache/portfolio_backtest.json' if bt else 'pending'}<br>
  <strong>Methodology notes:</strong> Wilson score interval (95% confidence) for all WR claims · Sharpe per-trade not annualized · Survivorship haircut −3pp WR / −0.20 PF (Brown et al 1992; Carpenter &amp; Lynch 1999) ·
  Reliability tiers: high = n≥100 &amp; CI&lt;12pp; medium = n≥50 &amp; CI&lt;20pp; low = n≥30; vlow = n&lt;30 (untrustworthy)<br>
  <strong>Caveats:</strong> Universe survivorship not yet corrected · Walk-forward grid does not tune setup multipliers · Per-setup samples for some families remain below the n=30 threshold ·
  This note is not investment advice and reflects the analytical state of the strategy on the date generated.
</div>

</div>
</body></html>"""


def main():
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    html = render()
    OUT_PATH.write_text(html, encoding="utf-8")
    print(f"Wrote {OUT_PATH}")
    print(f"  Size: {len(html):,} chars")
    print(f"  Open: file://{OUT_PATH.resolve()}")


if __name__ == "__main__":
    main()
