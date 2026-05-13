#!/usr/bin/env python3
"""
regime_sharpe_decomp.py — mine picks_history.json + signal_log.json for the
per-regime × per-setup Sharpe-like decomposition.

This is the cheap "is our strategy regime-consistent?" check. Doesn't need a
fresh backtest. Uses already-closed trades that the live system logged with
regime4 + setup_family + entry_quality + pnl_pct labels.

What it answers:
  - Per regime (risk_on_trending / risk_on_choppy / risk_off / panic): n, WR,
    Wilson LB, avg return, stdev, Sharpe-approx, max-single-loss.
  - Per (regime × setup_family): same stats — find which combo carries which
    regime + which combo drags it down.
  - Per regime × entry_quality: confirms or refutes the entry-quality
    stratification we already analyzed earlier.

Calls out:
  - Buckets with n<30 (CLAUDE.md principle 1 floor — flagged as noisy).
  - Outliers filtered: |pnl_pct| > 100 (CTRA-class data bugs already
    purged from picks_history but defensive).

Output: console table + cache/regime_sharpe_decomp_<DATE>.json for diff.
"""
from __future__ import annotations
import json
import math
import statistics
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _wilson_lb(wins: int, n: int, z: float = 1.96) -> float:
    if n == 0:
        return 0.0
    p = wins / n
    denom = 1 + (z * z) / n
    num = p + (z * z) / (2 * n) - z * math.sqrt((p * (1 - p) + (z * z) / (4 * n)) / n)
    return num / denom


def _load_trades() -> list[dict]:
    """Combine picks_history.trades + signal_log closed signals.
    Normalize fields so a single row schema is used downstream."""
    rows: list[dict] = []

    # picks_history.json — has regime4, setup_family, entry_quality, pct_chg
    ph_path = REPO / "cache" / "picks_history.json"
    if ph_path.exists():
        ph = json.loads(ph_path.read_text())
        for t in ph.get("trades") or []:
            if t.get("pct_chg") is None:
                continue
            pnl = float(t["pct_chg"])
            if abs(pnl) > 100:  # CTRA-class outlier defensive
                continue
            rows.append({
                "source": "picks_history",
                "ticker": t.get("ticker"),
                "regime4": t.get("regime4") or t.get("regime") or "unknown",
                "setup_family": t.get("setup_family") or "unknown",
                "entry_quality": t.get("entry_quality") or "unknown",
                "score": t.get("score"),
                "pnl_pct": pnl,
                "hold_days": t.get("hold_days"),
                "entry_date": t.get("entry_date"),
                "exit_date": t.get("exit_date"),
                "win": pnl > 0,
            })

    # signal_log.json — has regime4, setup_family, entry_quality, actual_pnl_pct
    sl_path = REPO / "data" / "signal_log.json"
    if sl_path.exists():
        sl = json.loads(sl_path.read_text())
        for s in sl:
            if s.get("status") != "CLOSED":
                continue
            pnl = s.get("actual_pnl_pct")
            if pnl is None:
                continue
            pnl = float(pnl)
            if abs(pnl) > 100:
                continue
            # signal_log has BUY+WATCH+SHORT — filter to BUY/SHORT only
            # (WATCH outcomes are sim-only, never traded)
            verdict = (s.get("verdict") or "").upper()
            if verdict not in ("BUY", "SHORT"):
                continue
            rows.append({
                "source": "signal_log",
                "ticker": s.get("ticker"),
                "regime4": s.get("regime4") or s.get("regime_name") or "unknown",
                "setup_family": s.get("setup_family") or s.get("strategy") or "unknown",
                "entry_quality": s.get("entry_quality") or "unknown",
                "score": s.get("score"),
                "pnl_pct": pnl,
                "hold_days": s.get("days_to_first_target_hit") or 5,
                "entry_date": s.get("date"),
                "exit_date": None,
                "win": pnl > 0,
            })

    return rows


def _stats(grp: list[dict]) -> dict:
    """Per-bucket stats."""
    n = len(grp)
    if n == 0:
        return {"n": 0}
    wins = sum(1 for t in grp if t["win"])
    pnl = [t["pnl_pct"] for t in grp]
    avg = statistics.mean(pnl)
    stdev = statistics.stdev(pnl) if n >= 2 else 0
    # Approx Sharpe (per-trade, not annualized — direction is what matters)
    sharpe = avg / stdev if stdev > 0 else 0
    win_pnls = [p for p in pnl if p > 0]
    loss_pnls = [p for p in pnl if p <= 0]
    pf_w = sum(win_pnls)
    pf_l = abs(sum(loss_pnls)) or 1
    return {
        "n": n,
        "wr": wins / n,
        "wilson_lb": _wilson_lb(wins, n),
        "avg_pnl": round(avg, 3),
        "stdev": round(stdev, 3),
        "sharpe_per_trade": round(sharpe, 3),
        "pf": round(pf_w / pf_l, 3),
        "max_loss": round(min(pnl), 2),
        "max_win": round(max(pnl), 2),
        "low_sample": n < 30,
    }


def _fmt_row(label: str, s: dict, indent: int = 0) -> str:
    pad = "  " * indent
    flag = " ⚠️ n<30" if s.get("low_sample") else ""
    return (
        f"{pad}{label:<45s} n={s['n']:>4d}  WR={s['wr']*100:>5.1f}%  "
        f"WLB={s['wilson_lb']*100:>5.1f}%  avg={s['avg_pnl']:>+6.2f}%  "
        f"σ={s['stdev']:>5.2f}  Sharpe/trade={s['sharpe_per_trade']:>+5.2f}  "
        f"PF={s['pf']:>5.2f}  maxL={s['max_loss']:>+6.1f}%{flag}"
    )


def main():
    rows = _load_trades()
    if not rows:
        print("ERROR: no closed trades found in picks_history.json or signal_log.json")
        sys.exit(1)

    # Source breakdown
    from collections import Counter
    src = Counter(t["source"] for t in rows)
    print(f"Loaded {len(rows)} closed trades  (picks_history: {src['picks_history']}, signal_log: {src['signal_log']})")
    print()

    # ─── L1: aggregate ───
    overall = _stats(rows)
    print("=" * 110)
    print("AGGREGATE (all closed trades)")
    print("=" * 110)
    print(_fmt_row("ALL", overall))
    print()

    # ─── L2: by regime ───
    print("=" * 110)
    print("BY REGIME (the main question — is Sharpe consistent across regimes?)")
    print("=" * 110)
    by_regime: dict[str, list[dict]] = defaultdict(list)
    for t in rows:
        by_regime[t["regime4"]].append(t)
    # Sort regimes by canonical order
    reg_order = ["risk_on_trending", "risk_on_choppy", "risk_off_trending", "panic", "unknown"]
    out_by_regime = {}
    for reg in reg_order:
        if reg not in by_regime:
            continue
        s = _stats(by_regime[reg])
        out_by_regime[reg] = s
        print(_fmt_row(reg, s))
    # Any other regime labels?
    for reg, grp in by_regime.items():
        if reg in reg_order:
            continue
        s = _stats(grp)
        out_by_regime[reg] = s
        print(_fmt_row(reg, s))
    print()

    # ─── L3: by setup family ───
    print("=" * 110)
    print("BY SETUP FAMILY (which setup carries / drags Sharpe)")
    print("=" * 110)
    by_setup: dict[str, list[dict]] = defaultdict(list)
    for t in rows:
        by_setup[t["setup_family"]].append(t)
    out_by_setup = {}
    for setup, grp in sorted(by_setup.items(), key=lambda kv: -_stats(kv[1])["n"]):
        s = _stats(grp)
        out_by_setup[setup] = s
        print(_fmt_row(setup, s))
    print()

    # ─── L4: by entry_quality ───
    print("=" * 110)
    print("BY ENTRY_QUALITY (when to take vs wait)")
    print("=" * 110)
    by_eq: dict[str, list[dict]] = defaultdict(list)
    for t in rows:
        by_eq[t["entry_quality"]].append(t)
    out_by_eq = {}
    eq_order = ["FRESH", "PULLBACK", "VALID", "EXTENDED", "MISSED", "unknown"]
    for eq in eq_order:
        if eq not in by_eq:
            continue
        s = _stats(by_eq[eq])
        out_by_eq[eq] = s
        print(_fmt_row(eq, s))
    print()

    # ─── L5: regime × setup_family cross ───
    print("=" * 110)
    print("REGIME × SETUP_FAMILY — where the actual decision matrix lives")
    print("=" * 110)
    cross: dict[tuple, list[dict]] = defaultdict(list)
    for t in rows:
        cross[(t["regime4"], t["setup_family"])].append(t)
    out_cross = {}
    # Group by regime, sorted by setup-n within regime
    for reg in reg_order:
        if reg not in by_regime:
            continue
        print(f"\n  Within {reg.upper()}:")
        regime_keys = [(r, s) for (r, s) in cross.keys() if r == reg]
        regime_keys.sort(key=lambda k: -_stats(cross[k])["n"])
        for (r, setup) in regime_keys[:6]:  # top 6 per regime
            grp = cross[(r, setup)]
            s = _stats(grp)
            out_cross[f"{r}|{setup}"] = s
            print(_fmt_row(setup, s, indent=2))

    # ─── persist ───
    out = {
        "generated_at": date.today().isoformat(),
        "n_trades_total": len(rows),
        "source_breakdown": dict(src),
        "aggregate": overall,
        "by_regime": out_by_regime,
        "by_setup_family": out_by_setup,
        "by_entry_quality": out_by_eq,
        "regime_x_setup": out_cross,
    }
    out_p = REPO / "cache" / f"regime_sharpe_decomp_{date.today().isoformat()}.json"
    out_p.write_text(json.dumps(out, indent=2, default=str))
    print()
    print(f"Saved: {out_p}")


if __name__ == "__main__":
    main()
