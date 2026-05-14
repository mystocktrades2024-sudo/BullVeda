#!/usr/bin/env python3
"""sharpe_kpi.py — portfolio-level rolling Sharpe vs target KPI.

Computes annualized portfolio Sharpe over the last N closed trades and reports
target / actual / gap. Surfaces the article's "Sharpe ≥ 1.5 across regimes" bar
as an explicit goal.

Inputs:
  cache/picks_history.json (canonical trades)
  data/portfolio_state.json (real positions + equity history if present)
  config/config.json :: portfolio.sharpe_kpi_target

Outputs:
  console KPI dashboard
  cache/sharpe_kpi_<DATE>.json
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def _load_recent_trades(n_recent: int) -> list[dict]:
    ph = REPO / "cache" / "picks_history.json"
    if not ph.exists():
        return []
    d = json.loads(ph.read_text())
    rows = []
    for t in d.get("trades") or []:
        if t.get("pct_chg") is None:
            continue
        pnl = float(t["pct_chg"])
        if abs(pnl) > 100:
            continue
        rows.append({
            "ticker": t.get("ticker"),
            "pnl_pct": pnl,
            "win": pnl > 0,
            "regime4": t.get("regime4") or t.get("regime") or "unknown",
            "setup_family": t.get("setup_family") or "unknown",
            "entry_date": t.get("entry_date"),
            "exit_date": t.get("exit_date"),
            "hold_days": t.get("hold_days") or 5,
        })
    rows.sort(key=lambda r: r.get("entry_date") or "")
    if n_recent and n_recent < len(rows):
        return rows[-n_recent:]
    return rows


def _annualize_per_trade_sharpe(per_trade_sharpe: float, avg_hold_days: float) -> float:
    """Convert per-trade Sharpe to annualized Sharpe.

    If avg trade lasts H trading days, ~252/H trades per year.
    annualized_sharpe = per_trade_sharpe × sqrt(252/H)
    """
    if avg_hold_days <= 0:
        return per_trade_sharpe
    trades_per_year = 252 / avg_hold_days
    return round(per_trade_sharpe * math.sqrt(trades_per_year), 3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-recent", type=int, default=60,
                    help="Number of most recent trades to use (default 60)")
    args = ap.parse_args()

    cfg = json.loads((REPO / "config" / "config.json").read_text())
    kpi_cfg = (cfg.get("portfolio", {}) or {}).get("sharpe_kpi_target") or {}
    target = float(kpi_cfg.get("target_sharpe_annualized", 1.5))
    floor = float(kpi_cfg.get("min_acceptable_sharpe_annualized", 0.5))
    enabled = kpi_cfg.get("_enabled", True)

    trades = _load_recent_trades(args.n_recent)
    if not trades:
        print("ERROR: no trades in picks_history.json", file=sys.stderr)
        sys.exit(1)

    from lib.sharpe_utils import per_trade_sharpe, per_trade_sortino, attribution_contribution
    pnls = [t["pnl_pct"] for t in trades]
    avg_hold = sum(t["hold_days"] for t in trades) / len(trades)

    sh, mean, std = per_trade_sharpe(pnls)
    so, dd = per_trade_sortino(pnls)
    ann_sh = _annualize_per_trade_sharpe(sh or 0, avg_hold) if sh is not None else None
    ann_so = _annualize_per_trade_sharpe(so or 0, avg_hold) if so is not None else None

    wins = sum(1 for t in trades if t["win"])
    win_pnls = [p for p in pnls if p > 0]
    loss_pnls = [p for p in pnls if p <= 0]
    pf = round(sum(win_pnls) / max(abs(sum(loss_pnls)), 1), 3)

    # Verdict
    if ann_sh is None:
        verdict = "INSUFFICIENT"
        v_color = "—"
    elif ann_sh >= target:
        verdict = "ON TARGET"
        v_color = "✅"
    elif ann_sh >= floor:
        verdict = "BELOW TARGET (above floor)"
        v_color = "⚠️"
    else:
        verdict = "BELOW FLOOR — CAPITAL PRESERVATION"
        v_color = "🔴"

    # Output
    print("=" * 70)
    print(f"PORTFOLIO SHARPE KPI  —  enabled={enabled}")
    print("=" * 70)
    print(f"  Sample:           last {len(trades)} closed trades  ({trades[0].get('entry_date')} → {trades[-1].get('entry_date')})")
    print(f"  Avg hold:         {avg_hold:.1f} trading days  ⇒  ~{252/avg_hold:.0f} trades/year")
    print()
    print(f"  Target Sharpe (annualized):    {target:+.2f}")
    print(f"  Floor Sharpe (annualized):     {floor:+.2f}")
    print(f"  ACTUAL Sharpe (annualized):    {ann_sh if ann_sh is not None else 'N/A'}")
    print(f"  ACTUAL Sortino (annualized):   {ann_so if ann_so is not None else 'N/A'}")
    print(f"  Per-trade Sharpe:              {sh if sh is not None else 'N/A'}")
    print(f"  Per-trade Sortino:             {so if so is not None else 'N/A'}")
    print()
    print(f"  Win rate:        {wins/len(trades)*100:.1f}%   PF: {pf:.2f}   avg PnL: {mean:+.2f}%   σ: {std:.2f}")
    print()
    print(f"  Gap to target:   {(ann_sh - target):+.2f}" if ann_sh is not None else "  Gap: N/A")
    print(f"  VERDICT:         {v_color}  {verdict}")
    print()

    # ─── Per-trade attribution to portfolio Sharpe (item #11) ───
    print("=" * 70)
    print("ATTRIBUTION — top contributors / detractors")
    print("=" * 70)
    indexed = [(i, t) for i, t in enumerate(trades)]
    by_pnl = sorted(indexed, key=lambda x: -x[1]["pnl_pct"])
    print("\n  TOP 10 contributors:")
    print(f"  {'#':>3} {'TICKER':<7} {'DATE':<11} {'SETUP':<22} {'REGIME':<20} {'PNL%':>7}  {'SHARE%':>7}")
    for i, (idx, t) in enumerate(by_pnl[:10], 1):
        sub_sum, share = attribution_contribution(pnls, [idx])
        ed = (t.get("entry_date") or "?")[:10]
        sf = (t.get("setup_family") or "?")[:22]
        rg = (t.get("regime4") or "?")[:20]
        print(f"  {i:>3} {t['ticker']:<7} {ed:<11} {sf:<22} {rg:<20} {t['pnl_pct']:>+6.2f}%  {share:>+6.2f}%")
    print("\n  TOP 10 detractors:")
    print(f"  {'#':>3} {'TICKER':<7} {'DATE':<11} {'SETUP':<22} {'REGIME':<20} {'PNL%':>7}  {'SHARE%':>7}")
    for i, (idx, t) in enumerate(by_pnl[-10:][::-1], 1):
        sub_sum, share = attribution_contribution(pnls, [idx])
        ed = (t.get("entry_date") or "?")[:10]
        sf = (t.get("setup_family") or "?")[:22]
        rg = (t.get("regime4") or "?")[:20]
        print(f"  {i:>3} {t['ticker']:<7} {ed:<11} {sf:<22} {rg:<20} {t['pnl_pct']:>+6.2f}%  {share:>+6.2f}%")

    # ─── Per-setup contribution ───
    print()
    print("=" * 70)
    print("CONTRIBUTION BY SETUP_FAMILY")
    print("=" * 70)
    by_setup: dict[str, list[int]] = {}
    for i, t in enumerate(trades):
        by_setup.setdefault(t["setup_family"], []).append(i)
    setup_rows = []
    for setup, idxs in by_setup.items():
        sub_sum, share = attribution_contribution(pnls, idxs)
        setup_rows.append((setup, len(idxs), sub_sum, share))
    setup_rows.sort(key=lambda r: -r[2])
    print(f"  {'SETUP':<28} {'n':>4} {'TOTAL_PNL':>10} {'SHARE%':>7}")
    for setup, n, sub_sum, share in setup_rows:
        print(f"  {setup:<28} {n:>4} {sub_sum:>+9.2f}% {share:>+6.2f}%")

    # ─── Per-regime contribution ───
    print()
    print("=" * 70)
    print("CONTRIBUTION BY REGIME")
    print("=" * 70)
    by_reg: dict[str, list[int]] = {}
    for i, t in enumerate(trades):
        by_reg.setdefault(t["regime4"], []).append(i)
    reg_rows = []
    for reg, idxs in by_reg.items():
        sub_sum, share = attribution_contribution(pnls, idxs)
        reg_rows.append((reg, len(idxs), sub_sum, share))
    reg_rows.sort(key=lambda r: -r[2])
    print(f"  {'REGIME':<24} {'n':>4} {'TOTAL_PNL':>10} {'SHARE%':>7}")
    for reg, n, sub_sum, share in reg_rows:
        print(f"  {reg:<24} {n:>4} {sub_sum:>+9.2f}% {share:>+6.2f}%")

    # Persist
    out = {
        "generated_at": date.today().isoformat(),
        "n_trades": len(trades),
        "first_entry": trades[0].get("entry_date"),
        "last_entry": trades[-1].get("entry_date"),
        "avg_hold_days": round(avg_hold, 2),
        "target_sharpe_ann": target,
        "floor_sharpe_ann": floor,
        "per_trade_sharpe": sh,
        "per_trade_sortino": so,
        "annualized_sharpe": ann_sh,
        "annualized_sortino": ann_so,
        "win_rate_pct": round(wins / len(trades) * 100, 2),
        "profit_factor": pf,
        "verdict": verdict,
        "by_setup_attribution": [
            {"setup": s, "n": n, "total_pnl_pct": round(p, 3), "share_pct": share}
            for s, n, p, share in setup_rows
        ],
        "by_regime_attribution": [
            {"regime": r, "n": n, "total_pnl_pct": round(p, 3), "share_pct": share}
            for r, n, p, share in reg_rows
        ],
        "top_contributors": [
            {"ticker": t["ticker"], "entry_date": t.get("entry_date"),
             "setup": t.get("setup_family"), "pnl_pct": t["pnl_pct"]}
            for _, t in by_pnl[:10]
        ],
        "top_detractors": [
            {"ticker": t["ticker"], "entry_date": t.get("entry_date"),
             "setup": t.get("setup_family"), "pnl_pct": t["pnl_pct"]}
            for _, t in by_pnl[-10:][::-1]
        ],
    }
    out_p = REPO / "cache" / f"sharpe_kpi_{date.today().isoformat()}.json"
    out_p.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved: {out_p}")

    # Exit code: non-zero if below floor (for cron/Slack alerting)
    if ann_sh is not None and ann_sh < floor:
        sys.exit(2)


if __name__ == "__main__":
    main()
