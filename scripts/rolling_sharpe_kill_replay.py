#!/usr/bin/env python3
"""Counterfactual replay of rolling-Sharpe kill modes.

For each CLOSED BUY in signal_log.json, computes (using only PRIOR closed BUYs):
  - aggregate rolling Sharpe → would aggregate mode have killed it?
  - per-sleeve rolling Sharpe → would per-sleeve mode have killed it?
  - per-sleeve + catalyst bypass → would the combined mode have killed it?

Reports:
  - Trades let through under each mode (count + PnL sum)
  - Trades killed under each mode (count + PnL sum)
  - Net PnL delta vs aggregate (baseline)
  - Wilson 95% LB on win-rate improvement

Honest read: this is COUNTERFACTUAL on REALIZED outcomes — it does not account
for the meta-effect of being demoted to WATCH (trade never happens, capital
freed for next setup). Treat it as a directional signal, not a P&L prediction.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SIGNAL_LOG = ROOT / "data" / "signal_log.json"

CATALYST_SLEEVES = {"PEAD", "Insider Cluster", "Defensive Rotation",
                    "Momentum Continuation", "Mean Reversion", "ESP Play"}


def _wilson_lb(wins: int, total: int, z: float = 1.96) -> float:
    if total == 0:
        return 0.0
    p = wins / total
    den = 1 + z * z / total
    num = p + z * z / (2 * total) - z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total))
    return max(0.0, num / den)


def _load_closed_buys() -> list[dict]:
    signals = json.loads(SIGNAL_LOG.read_text())
    rows = []
    for s in signals:
        if not isinstance(s, dict):
            continue
        if s.get("status") != "CLOSED":
            continue
        if (s.get("verdict") or "").upper() != "BUY":
            continue
        pnl = s.get("actual_pnl_pct")
        if pnl is None:
            continue
        try:
            pnl = float(pnl)
        except (TypeError, ValueError):
            continue
        if abs(pnl) > 100:
            continue
        sleeve = (s.get("setup_family") or s.get("setup_type") or s.get("strategy") or "Unknown")
        rows.append({
            "date": s.get("date") or "",
            "pnl": pnl,
            "sleeve": sleeve,
            "ticker": s.get("ticker"),
        })
    rows.sort(key=lambda r: r["date"])
    return rows


def _sharpe(samples: list[float]) -> float | None:
    if len(samples) < 2:
        return None
    avg = statistics.mean(samples)
    std = statistics.stdev(samples)
    return (avg / std) if std > 0 else 0.0


def replay(lookback_n: int = 20, min_sample_n: int = 10, threshold: float = -0.5) -> dict:
    rows = _load_closed_buys()
    n_total = len(rows)
    if n_total < min_sample_n:
        return {"error": f"not enough data ({n_total} < {min_sample_n})"}

    # For each trade i, compute "would each mode have killed it" using only trades [0..i-1].
    by_sleeve: dict[str, list[float]] = defaultdict(list)
    aggregate_history: list[float] = []

    results = {
        "aggregate":           {"killed": [], "let_through": []},
        "per_sleeve":          {"killed": [], "let_through": []},
        "per_sleeve_bypass":   {"killed": [], "let_through": []},  # A + B
        "none":                {"let_through": rows[:]},           # baseline: no kill
    }

    for i, r in enumerate(rows):
        sleeve = r["sleeve"]
        is_catalyst = sleeve in CATALYST_SLEEVES

        # AGGREGATE: rolling Sharpe across last N closed BUYs (any sleeve).
        agg_recent = aggregate_history[-lookback_n:]
        agg_active = False
        if len(agg_recent) >= min_sample_n:
            s_agg = _sharpe(agg_recent)
            agg_active = (s_agg is not None) and (s_agg < threshold)

        # PER-SLEEVE: rolling Sharpe of THIS sleeve's last N closed BUYs.
        sleeve_recent = by_sleeve[sleeve][-lookback_n:]
        sleeve_active = False
        if len(sleeve_recent) >= min_sample_n:
            s_sl = _sharpe(sleeve_recent)
            sleeve_active = (s_sl is not None) and (s_sl < threshold)

        # Apply modes.
        if agg_active:
            results["aggregate"]["killed"].append(r)
        else:
            results["aggregate"]["let_through"].append(r)

        if sleeve_active:
            results["per_sleeve"]["killed"].append(r)
        else:
            results["per_sleeve"]["let_through"].append(r)

        # per_sleeve + catalyst bypass: same as per_sleeve EXCEPT catalyst sleeves never get killed
        if sleeve_active and not is_catalyst:
            results["per_sleeve_bypass"]["killed"].append(r)
        else:
            results["per_sleeve_bypass"]["let_through"].append(r)

        # Append AFTER decision (rolling state evolves causally).
        aggregate_history.append(r["pnl"])
        by_sleeve[sleeve].append(r["pnl"])

    # Compute statistics per mode.
    def _stats(trades: list[dict]) -> dict:
        if not trades:
            return {"n": 0, "wr": 0, "avg_pnl": 0, "total_pnl": 0, "pf": 0, "wilson_lb": 0}
        wins = [t for t in trades if t["pnl"] > 0]
        losses = [t for t in trades if t["pnl"] <= 0]
        gross_w = sum(t["pnl"] for t in wins)
        gross_l = abs(sum(t["pnl"] for t in losses))
        pf = (gross_w / gross_l) if gross_l > 0 else float("inf")
        return {
            "n": len(trades),
            "wr": round(len(wins) / len(trades) * 100, 1),
            "avg_pnl": round(sum(t["pnl"] for t in trades) / len(trades), 2),
            "total_pnl": round(sum(t["pnl"] for t in trades), 2),
            "pf": round(pf, 2) if pf != float("inf") else "inf",
            "wilson_lb": round(_wilson_lb(len(wins), len(trades)) * 100, 1),
        }

    summary = {
        "n_total": n_total,
        "config": {"lookback_n": lookback_n, "min_sample_n": min_sample_n, "threshold": threshold},
        "modes": {},
    }
    for mode, sets in results.items():
        let_through = sets.get("let_through", [])
        killed = sets.get("killed", [])
        summary["modes"][mode] = {
            "let_through": _stats(let_through),
            "killed_pnl": _stats(killed),
            "n_killed": len(killed),
        }

    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lookback", type=int, default=20)
    ap.add_argument("--min-sample", type=int, default=10)
    ap.add_argument("--threshold", type=float, default=-0.5)
    args = ap.parse_args()

    summary = replay(args.lookback, args.min_sample, args.threshold)
    print(json.dumps(summary, indent=2))

    print("\n" + "=" * 72)
    print("  ROLLING-SHARPE KILL — COUNTERFACTUAL REPLAY")
    print("=" * 72)
    cfg = summary["config"]
    print(f"  n_total: {summary['n_total']}   lookback={cfg['lookback_n']}   "
          f"min_sample={cfg['min_sample_n']}   threshold={cfg['threshold']}")
    print()
    print(f"  {'MODE':<22}{'n_let':>6}{'WR':>7}{'avg%':>7}{'PF':>6}{'Wilson':>8}{'total_pnl':>12}{'n_killed':>10}")
    print(f"  {'-'*22}{'-'*6}{'-'*7}{'-'*7}{'-'*6}{'-'*8}{'-'*12}{'-'*10}")
    for mode, st in summary["modes"].items():
        lt = st["let_through"]
        print(f"  {mode:<22}{lt['n']:>6}{lt['wr']:>7}{lt['avg_pnl']:>7}{str(lt['pf']):>6}"
              f"{lt['wilson_lb']:>8}{lt['total_pnl']:>12}{st['n_killed']:>10}")

    # Deltas vs aggregate (baseline).
    base = summary["modes"]["aggregate"]["let_through"]
    print()
    print("  DELTA vs aggregate baseline:")
    for mode in ("per_sleeve", "per_sleeve_bypass"):
        lt = summary["modes"][mode]["let_through"]
        d_n = lt["n"] - base["n"]
        d_pnl = lt["total_pnl"] - base["total_pnl"]
        d_pf = lt["pf"] - base["pf"] if isinstance(lt["pf"], (int, float)) and isinstance(base["pf"], (int, float)) else "n/a"
        d_wr = lt["wr"] - base["wr"]
        print(f"    {mode:<22}  +{d_n} trades  PnL {d_pnl:+.2f}%  PF {d_pf}  WR {d_wr:+.1f}pp")


if __name__ == "__main__":
    main()
