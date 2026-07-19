#!/usr/bin/env python3
"""backtest_mr_guard.py — signal-replay validation of the Mean-Reversion desk's
falling-knife guard (screener_desks.mr_falling_knife_guard).

Question: among oversold names (RSI<30), do the events the guard REJECTS
(bearish EMA stack OR collapsed RS) actually underperform the events it KEEPS?
If the REJECT bucket has materially worse forward returns / win-rate, the guard
adds edge. If the two buckets are indistinguishable, the guard is dead weight.

Data: data/swingtrade.db `ticker_snapshots` (captured enriched history, ~49 run-dates).
Forward returns are measured snapshot-to-snapshot (same ticker, later run_date) —
ZERO EODHD calls, zero new data. Long-only (mean-reversion buys the bounce).

Honest limitations (printed in the report, do not overclaim):
  * ~8-week window, largely one regime (risk_on_choppy) — NOT multi-year / multi-regime.
  * `above200` base condition absent from snapshots → pool = ALL oversold names
    (slightly broader than the live desk trigger, which also requires >200EMA).
  * fwd return uses the nearest scan >= D+3 trading-ish days (proxy for the 3–5d hold).
  * no slippage modeled — this is a SEPARATION test, not a PF claim.

Run: python3 scripts/backtest_mr_guard.py [--hold-days 5] [--rs-min 30]
"""
from __future__ import annotations
import argparse
import json
import math
import sqlite3
from collections import defaultdict
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DB = BASE / "data" / "swingtrade.db"


def _f(x, d=None):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def _wilson_lb(wins, n, z=1.96):
    if n == 0:
        return 0.0
    p = wins / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)
    return max(0.0, (centre - margin) / denom)


def _profit_factor(rets):
    gains = sum(r for r in rets if r > 0)
    losses = -sum(r for r in rets if r < 0)
    if losses == 0:
        return float("inf") if gains > 0 else 0.0
    return gains / losses


def _stats(label, rets):
    n = len(rets)
    if n == 0:
        return {"bucket": label, "n": 0}
    wins = sum(1 for r in rets if r > 0)
    wr = wins / n
    mean = sum(rets) / n
    return {
        "bucket": label, "n": n, "win_rate": wr, "wilson_lb": _wilson_lb(wins, n),
        "mean_fwd_ret_pct": mean * 100, "median_fwd_ret_pct": sorted(rets)[n // 2] * 100,
        "profit_factor": _profit_factor(rets),
    }


def load_snapshots():
    """Latest snapshot per (ticker, run_date) → dict[ticker] = sorted list of
    (run_date, price, rsi, rs_rank, ema_signal)."""
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT ticker, run_date, captured_at, price, rs_rank, raw_json "
        "FROM ticker_snapshots WHERE price IS NOT NULL AND raw_json IS NOT NULL "
        "ORDER BY ticker, run_date, captured_at"
    ).fetchall()
    con.close()
    latest = {}  # (ticker, run_date) -> row (last captured_at wins via ordering)
    for r in rows:
        latest[(r["ticker"], r["run_date"])] = r
    series = defaultdict(list)
    for (tk, rd), r in latest.items():
        px = _f(r["price"])
        try:
            raw = json.loads(r["raw_json"]) or {}
        except Exception:
            continue
        rsi = _f(raw.get("rsi"))
        if px is None or rsi is None or px <= 0:
            continue
        ema_sig = str(raw.get("ema_signal") or "")
        # rs_rank: prefer the column, fall back to raw_json
        rsrank = _f(r["rs_rank"], None)
        if rsrank is None:
            rsrank = _f(raw.get("rs_rank"), 50.0)
        series[tk].append((rd, px, rsi, rsrank, ema_sig))
    for tk in series:
        series[tk].sort(key=lambda x: x[0])
    return series


def _days(a, b):
    ya, ma, da = (int(x) for x in a.split("-"))
    yb, mb, db = (int(x) for x in b.split("-"))
    return (date(yb, mb, db) - date(ya, ma, da)).days


def replay(hold_days, rs_min, use_bear_stack=False, winsor=0.30):
    """Replay oversold (RSI<30) events. Guard REJECTS an event (demote BUY→WATCH) when
    rs_rank<rs_min, plus bearish EMA stack iff use_bear_stack. Returns beyond ±winsor are
    dropped as data glitches (splits / ticker reuse) — a 5d mean-reversion move that large
    is almost never a real fill."""
    series = load_snapshots()
    keep, reject, all_os = [], [], []
    reject_bear, reject_rs = [], []
    events = 0
    for tk, pts in series.items():
        for i, (rd, px, rsi, rsrank, ema_sig) in enumerate(pts):
            if rsi >= 30:                       # oversold trigger only
                continue
            # forward exit: nearest later snapshot >= hold_days calendar out (proxy),
            # capped at hold_days + 5 so we don't grab a stale month-later print.
            fwd = None
            for j in range(i + 1, len(pts)):
                gap = _days(rd, pts[j][0])
                if gap >= max(3, hold_days - 1):
                    if gap <= hold_days + 5:
                        fwd = pts[j][1]
                    break
            if fwd is None:
                continue
            ret = fwd / px - 1.0
            if abs(ret) > winsor:               # drop split / ticker-reuse glitches
                continue
            events += 1
            all_os.append(ret)
            bear_stack = use_bear_stack and ("BEAR" in ema_sig.upper())
            rs_bad = rsrank is not None and rsrank < rs_min
            if bear_stack or rs_bad:            # guard REJECTS (would demote BUY→WATCH)
                reject.append(ret)
                if bear_stack:
                    reject_bear.append(ret)
                if rs_bad:
                    reject_rs.append(ret)
            else:                               # guard KEEPS (stays BUY)
                keep.append(ret)
    return {
        "events": events,
        "all_oversold": _stats("ALL oversold (guard OFF = old BUY pool)", all_os),
        "keep": _stats("KEEP (guard ON → BUY)", keep),
        "reject": _stats("REJECT (guard ON → WATCH)", reject),
        "reject_bear_stack": _stats("  ↳ rejected: bearish EMA stack", reject_bear),
        "reject_rs_collapsed": _stats(f"  ↳ rejected: RS<{rs_min}", reject_rs),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hold-days", type=int, default=5)
    ap.add_argument("--rs-min", type=float, default=15)
    ap.add_argument("--bear-stack", action="store_true",
                    help="also reject bearish EMA stack (refuted — collinear with RSI<30)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    res = replay(args.hold_days, args.rs_min, use_bear_stack=args.bear_stack)
    if args.json:
        print(json.dumps(res, indent=2))
        return
    print("=" * 78)
    print(f"MR-desk falling-knife guard — signal replay  (hold≈{args.hold_days}d, rs_min={args.rs_min:.0f})")
    print(f"data: ticker_snapshots  |  oversold events replayed: {res['events']}")
    print("=" * 78)
    hdr = f"{'bucket':<40}{'n':>5}{'WR':>7}{'Wilson':>8}{'meanR%':>9}{'medR%':>8}{'PF':>7}"
    print(hdr); print("-" * 78)
    for key in ("all_oversold", "keep", "reject", "reject_bear_stack", "reject_rs_collapsed"):
        s = res[key]
        if s.get("n", 0) == 0:
            print(f"{s['bucket']:<40}{0:>5}{'—':>7}{'—':>8}{'—':>9}{'—':>8}{'—':>7}")
            continue
        pf = s["profit_factor"]
        pf_s = "inf" if pf == float("inf") else f"{pf:.2f}"
        print(f"{s['bucket']:<40}{s['n']:>5}{s['win_rate']*100:>6.0f}%"
              f"{s['wilson_lb']*100:>7.0f}%{s['mean_fwd_ret_pct']:>+9.2f}"
              f"{s['median_fwd_ret_pct']:>+8.2f}{pf_s:>7}")
    print("-" * 78)
    k, rj = res["keep"], res["reject"]
    if k.get("n") and rj.get("n"):
        edge = k["mean_fwd_ret_pct"] - rj["mean_fwd_ret_pct"]
        print(f"\nSEPARATION (KEEP − REJECT mean fwd return): {edge:+.2f} pp")
        verdict = ("guard SEPARATES — rejected knives underperform kept dips"
                   if edge > 0.30 else
                   "INCONCLUSIVE — buckets too close / sample too small; do not assert edge")
        print(f"VERDICT: {verdict}")
    print("\n⚠ limitations: ~8-wk window, ~1 regime, no >200EMA base filter, no slippage. "
          "Separation test, not a PF claim.")


if __name__ == "__main__":
    main()
