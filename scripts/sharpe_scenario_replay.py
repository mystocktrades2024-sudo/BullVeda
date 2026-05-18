#!/usr/bin/env python3
"""Sharpe-improvement scenario sweep — counterfactual replay over closed trades.

Loads cache/picks_history.json (912 closed trades w/ regime4 / setup_family /
entry_quality / catalyst_tier / score / pnl_pct), applies each scenario as a
filter or reweight, recomputes the full stat suite (Sharpe per-trade + annual,
Sortino, PF, max DD, Wilson LB), and reports diff-vs-baseline.

Limits (honest):
  - Counterfactual on REALIZED outcomes. Filtering a trade out doesn't account
    for the meta-effect of capital being freed for the next signal.
  - Cannot evaluate stop/target/sizing changes (need price simulation).
    Those scenarios are flagged "NEEDS-BACKTEST" and skipped here.
  - In-sample only — see sharpe_scenario_walkforward.py for OOS validation.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PICKS = ROOT / "cache" / "picks_history.json"
SIGNAL = ROOT / "data" / "signal_log.json"
TRADING_DAYS_PER_YEAR = 252


# ── Scenarios ────────────────────────────────────────────────────────────────
SCENARIOS = [
    {"id": 0, "name": "baseline",                       "kind": "filter",   "filter": lambda t: True},
    {"id": 1, "name": "Block BE in risk_on_trending",   "kind": "filter",
     "filter": lambda t: not (t.get("regime4") == "risk_on_trending" and t.get("setup_family") == "Breakout Expansion")},
    {"id": 2, "name": "Kill 10-Week Pullback sleeve",   "kind": "filter",
     "filter": lambda t: t.get("setup_family") != "10-Week Pullback"},
    {"id": 3, "name": "Kill VCP Breakout sleeve",       "kind": "filter",
     "filter": lambda t: t.get("setup_family") != "VCP Breakout"},
    {"id": 4, "name": "Score >= 75 only",               "kind": "filter",
     "filter": lambda t: (t.get("score") or 0) >= 75},
    {"id": 5, "name": "Score >= 80 only",               "kind": "filter",
     "filter": lambda t: (t.get("score") or 0) >= 80},
    {"id": 6, "name": "Catalyst tier <= 1 only",        "kind": "filter",
     "filter": lambda t: (t.get("catalyst_tier") or 99) <= 1},
    {"id": 7, "name": "Catalyst tier <= 2 only",        "kind": "filter",
     "filter": lambda t: (t.get("catalyst_tier") or 99) <= 2},
    {"id": 8, "name": "Entry-quality reweight (MISSED+, FRESH-)", "kind": "reweight",
     "weights": {"MISSED": 1.25, "EXTENDED": 1.10, "VALID": 1.00,
                 "PULLBACK": 0.85, "FRESH": 0.60, "": 1.00, None: 1.00}},
    {"id": 9, "name": "Skip FRESH + PULLBACK entries",  "kind": "filter",
     "filter": lambda t: (t.get("entry_quality") or "") not in ("FRESH", "PULLBACK")},
    {"id": 10, "name": "Tail trim — drop |pnl|>15%",    "kind": "filter",
     "filter": lambda t: abs(t.get("pnl_pct") or 0) <= 15},
    # Stacked combinations — only HIGH-confidence levers
    {"id": 11, "name": "STACKED: 1+2+6 (regime gate + 10WP kill + cat<=1)",
     "kind": "filter",
     "filter": lambda t: (
         not (t.get("regime4") == "risk_on_trending" and t.get("setup_family") == "Breakout Expansion")
         and t.get("setup_family") != "10-Week Pullback"
         and (t.get("catalyst_tier") or 99) <= 1
     )},
    {"id": 12, "name": "STACKED: 1+2+4 (regime gate + 10WP kill + score>=75)",
     "kind": "filter",
     "filter": lambda t: (
         not (t.get("regime4") == "risk_on_trending" and t.get("setup_family") == "Breakout Expansion")
         and t.get("setup_family") != "10-Week Pullback"
         and (t.get("score") or 0) >= 75
     )},
    # Deferred — need price simulation
    {"id": 13, "name": "Tighter stop 1.0x ATR",          "kind": "deferred",
     "reason": "Requires price simulation — run via walk_forward_v2.py"},
    {"id": 14, "name": "Wider stop 1.5x ATR",            "kind": "deferred",
     "reason": "Requires price simulation — run via walk_forward_v2.py"},
    {"id": 15, "name": "Regime-conditional Kelly sizing","kind": "deferred",
     "reason": "Requires portfolio-state simulation"},
]


# ── Trade loading ───────────────────────────────────────────────────────────
def _iter_trades_picks(d):
    """Recursively pull closed trade dicts from picks_history nested structure."""
    if isinstance(d, dict):
        if d.get("pnl_pct") is not None or d.get("actual_pnl_pct") is not None:
            yield d
        for v in d.values():
            yield from _iter_trades_picks(v)
    elif isinstance(d, list):
        for x in d:
            yield from _iter_trades_picks(x)


def load_trades():
    """Return list of closed trades with normalized PnL field 'pnl'."""
    trades = []
    if PICKS.exists():
        ph = json.loads(PICKS.read_text())
        for t in _iter_trades_picks(ph):
            pnl = t.get("pnl_pct") if t.get("pnl_pct") is not None else t.get("actual_pnl_pct")
            if pnl is None:
                continue
            try:
                pnl = float(pnl)
            except (TypeError, ValueError):
                continue
            if abs(pnl) > 100:
                continue
            t2 = dict(t); t2["pnl"] = pnl
            trades.append(t2)
    return trades


# ── Statistics ──────────────────────────────────────────────────────────────
def _wilson_lb(wins: int, n: int, z: float = 1.96) -> float:
    if n == 0:
        return 0.0
    p = wins / n
    den = 1 + z * z / n
    num = p + z * z / (2 * n) - z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, num / den)


def _stats(pnls: list[float], avg_hold_days: float = 5.0) -> dict:
    if not pnls:
        return {
            "n": 0, "wr": None, "wilson_lb": None, "avg_pnl": None, "stdev": None,
            "sharpe_per_trade": None, "sharpe_annualized": None,
            "sortino_per_trade": None, "sortino_annualized": None,
            "pf": None, "pf_haircut": None, "max_dd": None, "calmar": None,
        }
    n = len(pnls)
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    avg = statistics.mean(pnls)
    std = statistics.stdev(pnls) if n >= 2 else 0
    sharpe_t = (avg / std) if std > 0 else 0.0
    # Annualized (trades_per_year = 252 / avg_hold_days, conservative)
    tpy = TRADING_DAYS_PER_YEAR / max(avg_hold_days, 1)
    sharpe_ann = sharpe_t * math.sqrt(tpy) if std > 0 else 0.0
    # Sortino — downside σ only
    downside = [p for p in pnls if p < 0]
    dsd = statistics.stdev(downside) if len(downside) >= 2 else (abs(downside[0]) if downside else 0)
    sortino_t = (avg / dsd) if dsd > 0 else 0.0
    sortino_ann = sortino_t * math.sqrt(tpy) if dsd > 0 else 0.0
    gross_w = sum(wins)
    gross_l = abs(sum(losses))
    pf = (gross_w / gross_l) if gross_l > 0 else float("inf")
    pf_haircut = (pf - 0.10) if isinstance(pf, float) and pf != float("inf") else pf  # retail haircut
    # Max DD over equity curve (compounded)
    equity = 100.0
    peak = 100.0
    max_dd = 0.0
    for p in pnls:
        equity *= (1 + p / 100)
        peak = max(peak, equity)
        dd = (peak - equity) / peak * 100
        max_dd = max(max_dd, dd)
    calmar = (sharpe_ann / (max_dd / 100)) if max_dd > 0 else None
    return {
        "n": n,
        "wr": round(len(wins) / n * 100, 1),
        "wilson_lb": round(_wilson_lb(len(wins), n) * 100, 1),
        "avg_pnl": round(avg, 3),
        "stdev": round(std, 3),
        "sharpe_per_trade": round(sharpe_t, 4),
        "sharpe_annualized": round(sharpe_ann, 3),
        "sortino_per_trade": round(sortino_t, 4),
        "sortino_annualized": round(sortino_ann, 3),
        "pf": round(pf, 3) if pf != float("inf") else None,
        "pf_haircut": round(pf_haircut, 3) if isinstance(pf_haircut, float) and pf_haircut != float("inf") else None,
        "max_dd": round(max_dd, 2),
        "calmar": round(calmar, 3) if calmar else None,
    }


# ── Sharpe-improvement Wilson LB (bootstrap) ────────────────────────────────
def _bootstrap_sharpe_ci(samples: list[float], n_boot: int = 1000, seed: int = 42) -> tuple[float, float]:
    """Return (lower_5%, upper_95%) of bootstrap Sharpe distribution."""
    import random
    rng = random.Random(seed)
    if len(samples) < 10:
        return (None, None)
    sharpes = []
    for _ in range(n_boot):
        resample = [rng.choice(samples) for _ in range(len(samples))]
        if len(set(resample)) < 2:
            continue
        avg = statistics.mean(resample)
        std = statistics.stdev(resample)
        sharpes.append((avg / std) if std > 0 else 0.0)
    sharpes.sort()
    lo = sharpes[int(0.05 * len(sharpes))]
    hi = sharpes[int(0.95 * len(sharpes))]
    return (round(lo, 4), round(hi, 4))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "cache" / f"sharpe_scenarios_{date.today()}.json"))
    ap.add_argument("--no-bootstrap", action="store_true", help="skip bootstrap CI (faster)")
    args = ap.parse_args()

    trades = load_trades()
    if not trades:
        print("No closed trades found.")
        return 2

    print(f"Loaded {len(trades)} closed trades from picks_history.json")
    print()

    # Avg hold days (for Sharpe annualization)
    holds = [t.get("hold_days") for t in trades if t.get("hold_days")]
    avg_hold = statistics.mean(holds) if holds else 5.0
    print(f"Avg hold: {avg_hold:.1f} trading days  ⇒  ~{TRADING_DAYS_PER_YEAR/avg_hold:.0f} trades/year")
    print()

    results = []
    baseline_pnls = None
    for sc in SCENARIOS:
        if sc["kind"] == "deferred":
            results.append({"id": sc["id"], "name": sc["name"], "kind": "deferred",
                            "reason": sc.get("reason", "")})
            continue

        # Apply filter or reweight
        if sc["kind"] == "filter":
            kept = [t for t in trades if sc["filter"](t)]
            pnls = [t["pnl"] for t in kept]
        elif sc["kind"] == "reweight":
            weights = sc["weights"]
            kept = trades
            pnls = []
            for t in trades:
                eq = t.get("entry_quality")
                w = weights.get(eq, 1.0)
                pnls.append(t["pnl"] * w)
        else:
            continue

        st = _stats(pnls, avg_hold_days=avg_hold)

        # Bootstrap Sharpe CI
        if not args.no_bootstrap:
            lo, hi = _bootstrap_sharpe_ci(pnls, n_boot=1000)
            st["sharpe_ci_5pct"] = lo
            st["sharpe_ci_95pct"] = hi

        # Diff vs baseline
        diff = {}
        if sc["id"] == 0:
            baseline_pnls = pnls
            diff = {"vs_baseline": "BASELINE"}
        elif baseline_pnls is not None:
            base = _stats(baseline_pnls, avg_hold_days=avg_hold)
            for k in ("sharpe_per_trade", "sortino_per_trade", "pf", "wr", "wilson_lb",
                      "max_dd", "avg_pnl"):
                bv = base.get(k); cv = st.get(k)
                if bv is not None and cv is not None:
                    diff[f"d_{k}"] = round(cv - bv, 4)
            diff["d_n"] = st["n"] - base["n"]

        results.append({"id": sc["id"], "name": sc["name"], "kind": sc["kind"],
                        "stats": st, "diff": diff})

    # Save
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({
        "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "n_total_trades": len(trades),
        "avg_hold_days": round(avg_hold, 2),
        "scenarios": results,
    }, indent=2, default=str))
    print(f"Saved: {out_path}")
    print()

    # Print ranked table
    print("=" * 130)
    print(f"  {'#':>2} {'SCENARIO':<48} {'n':>5} {'WR':>5} {'WLB':>5} {'Sh/t':>8} {'Sh ann':>8} {'PF':>6} {'MaxDD':>7} {'ΔSh/t':>8}")
    print("-" * 130)
    for r in results:
        if r["kind"] == "deferred":
            print(f"  {r['id']:>2} {r['name']:<48} {'—':>5} {'—':>5} {'—':>5} {'—':>8} {'—':>8} {'—':>6} {'—':>7}  DEFERRED ({r['reason'][:30]})")
            continue
        s = r["stats"]; d = r.get("diff", {})
        dsh = d.get("d_sharpe_per_trade")
        dsh_str = f"{dsh:+.3f}" if isinstance(dsh, (int, float)) else "—"
        sh = s.get("sharpe_per_trade"); sh_ann = s.get("sharpe_annualized")
        pf = s.get("pf"); mdd = s.get("max_dd")
        print(f"  {r['id']:>2} {r['name']:<48} {s['n']:>5} {s.get('wr', 0):>5.1f} "
              f"{s.get('wilson_lb', 0):>5.1f} "
              f"{(sh if sh is not None else 0):>+8.4f} "
              f"{(sh_ann if sh_ann is not None else 0):>+8.3f} "
              f"{(pf if pf is not None else 0):>6.2f} "
              f"{(mdd if mdd is not None else 0):>6.1f}% "
              f"{dsh_str:>8}")
    print("=" * 130)
    print()
    # Surface top 5 by Sharpe improvement
    ranked = sorted(
        [r for r in results if r.get("diff", {}).get("d_sharpe_per_trade") is not None],
        key=lambda r: -r["diff"]["d_sharpe_per_trade"]
    )
    print("TOP 5 SCENARIOS BY ΔSHARPE/TRADE (in-sample upper bound):")
    for r in ranked[:5]:
        d = r["diff"]; s = r["stats"]
        print(f"  #{r['id']:<2} {r['name']:<48}  "
              f"Δsh/t {d['d_sharpe_per_trade']:+.3f}  "
              f"Δpf {d.get('d_pf', 0):+.2f}  "
              f"ΔmaxDD {d.get('d_max_dd', 0):+.2f}pp  "
              f"Δn {d.get('d_n', 0):+d}")
    print()
    print("⚠️  These are IN-SAMPLE. Top 3-4 should be walk-forward validated before shipping.")
    print("⚠️  Per CLAUDE.md principle 1: Wilson 95% LB on Sharpe gain must exceed 0 before shipping.")


if __name__ == "__main__":
    main()
