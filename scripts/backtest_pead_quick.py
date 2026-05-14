#!/usr/bin/env python3
"""backtest_pead_quick.py — quick historical PEAD validation.

Pulls EODHD earnings_calendar for the last N days, filters to entries
matching the PEAD detector criteria (EPS surprise ≥ min, post-report
gap ≥ min), computes 5d/10d/20d forward returns from data_archive parquets,
aggregates WR / avg return / PF / Wilson LB.

CLAUDE.md compliance:
  - n >= 30 floor before drawing conclusions (Principle 1)
  - Wilson LB surfaced (Principle 1)
  - Slippage applied (Principle 19 — 3bp entry + 2bp exit)
  - No look-ahead (uses only data available at entry)
  - Mechanism check: per-bucket stratification by EPS / gap strength

Usage:
  python3 scripts/backtest_pead_quick.py             # 60d default
  python3 scripts/backtest_pead_quick.py --days 180  # longer window
"""
from __future__ import annotations
import argparse
import json
import math
import statistics
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def _wilson_lb(wins: int, n: int, z: float = 1.96) -> float:
    if n == 0:
        return 0.0
    p = wins / n
    denom = 1 + (z * z) / n
    num = p + (z * z) / (2 * n) - z * math.sqrt((p * (1 - p) + (z * z) / (4 * n)) / n)
    return num / denom


def _forward_return_pct(ticker: str, entry_date: date, hold_days: int) -> float | None:
    """Compute forward return from data_archive parquet (no look-ahead)."""
    try:
        from data_archive import load_ticker
        df = load_ticker(ticker)
        if df is None or len(df) < hold_days + 2:
            return None
        # Find first bar AT or AFTER entry_date
        post = df[df.index.date >= entry_date]
        if len(post) < hold_days + 1:
            return None
        entry_price = float(post.iloc[0]["Open"]) if "Open" in post.columns else float(post.iloc[0]["open"])
        exit_idx = min(hold_days, len(post) - 1)
        exit_price = float(post.iloc[exit_idx]["Close"]) if "Close" in post.columns else float(post.iloc[exit_idx]["close"])
        if entry_price <= 0:
            return None
        gross = ((exit_price - entry_price) / entry_price) * 100
        # Slippage: 3bp entry + 2bp exit = 5bp = 0.05%
        net = gross - 0.05
        return round(net, 3)
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=60, help="Lookback window (default 60d)")
    ap.add_argument("--min-eps", type=float, default=5.0, help="Min EPS surprise %")
    ap.add_argument("--min-gap", type=float, default=3.0, help="Min post-report gap %")
    ap.add_argument("--max-gap", type=float, default=999.0, help="Max post-report gap %")
    args = ap.parse_args()

    print(f"PEAD historical replay — last {args.days} days")
    print(f"Trigger: EPS surprise ≥ {args.min_eps}% AND gap in [{args.min_gap}%, {args.max_gap}%]")
    print()

    import eodhd_client as e
    today = date.today()
    from_date = (today - timedelta(days=args.days)).isoformat()
    to_date = today.isoformat()
    print(f"Fetching EODHD earnings calendar: {from_date} → {to_date}...")
    ec = e.earnings_calendar(from_date=from_date, to_date=to_date)
    rows = ec.get("earnings") if isinstance(ec, dict) else []
    print(f"  Found {len(rows)} earnings entries")

    # Filter to ones with actual EPS reported
    reported = [r for r in rows if r.get("actual") is not None and r.get("estimate") is not None]
    print(f"  With actual EPS: {len(reported)}")

    # Compute surprise + look up post-report gap
    trades = []
    skipped_low_eps = 0
    skipped_no_gap = 0
    skipped_us_only = 0
    skipped_no_archive = 0
    for r in reported:
        code_full = (r.get("code") or "").upper()
        if not code_full:
            continue
        # EODHD uses TICKER.EXCHANGE — keep only .US (or no suffix)
        parts = code_full.split(".")
        if len(parts) > 1 and parts[1] not in ("US", ""):
            skipped_us_only += 1
            continue
        code = parts[0]
        actual = float(r["actual"])
        estimate = float(r["estimate"])
        if estimate == 0:
            continue
        eps_pct = r.get("percent")
        if eps_pct is None:
            eps_pct = ((actual - estimate) / abs(estimate)) * 100
        eps_pct = float(eps_pct)
        if eps_pct < args.min_eps:
            skipped_low_eps += 1
            continue
        # Look up report date
        ed_str = r.get("report_date") or r.get("date")
        if not ed_str:
            continue
        try:
            ed = datetime.fromisoformat(ed_str[:10]).date()
        except Exception:
            continue
        # Need archive data
        try:
            from data_archive import load_ticker
            df = load_ticker(code)
            if df is None or len(df) < 30:
                skipped_no_archive += 1
                continue
        except Exception:
            skipped_no_archive += 1
            continue
        # Compute post-report gap
        try:
            pre = df[df.index.date < ed]
            post = df[df.index.date >= ed]
            if len(pre) < 1 or len(post) < 1:
                continue
            report_close = float(pre.iloc[-1]["Close"]) if "Close" in pre.columns else float(pre.iloc[-1]["close"])
            next_open = float(post.iloc[0]["Open"]) if "Open" in post.columns else float(post.iloc[0]["open"])
            if report_close <= 0:
                continue
            gap_pct = ((next_open - report_close) / report_close) * 100
        except Exception:
            continue
        if gap_pct < args.min_gap or gap_pct > args.max_gap:
            skipped_no_gap += 1
            continue
        # Compute forward returns at multiple horizons
        # Entry: day AFTER report (post-gap, capture drift not gap)
        entry_d = post.iloc[1 if len(post) > 1 else 0]
        entry_date = entry_d.name.date() if hasattr(entry_d.name, "date") else ed + timedelta(days=1)
        ret_5d = _forward_return_pct(code, entry_date, 5)
        ret_10d = _forward_return_pct(code, entry_date, 10)
        ret_20d = _forward_return_pct(code, entry_date, 20)
        if ret_5d is None and ret_10d is None and ret_20d is None:
            continue
        trades.append({
            "ticker": code,
            "report_date": ed.isoformat(),
            "entry_date": entry_date.isoformat() if hasattr(entry_date, "isoformat") else str(entry_date),
            "eps_surprise_pct": round(eps_pct, 2),
            "post_report_gap_pct": round(gap_pct, 2),
            "ret_5d": ret_5d,
            "ret_10d": ret_10d,
            "ret_20d": ret_20d,
        })

    print()
    print(f"=== Filter funnel ===")
    print(f"  After EPS filter (>= {args.min_eps}%): {len(reported) - skipped_low_eps - skipped_us_only}")
    print(f"  Skipped non-US: {skipped_us_only}")
    print(f"  Skipped no archive: {skipped_no_archive}")
    print(f"  Skipped gap < {args.min_gap}%: {skipped_no_gap}")
    print(f"  Final trades: {len(trades)}")
    print()

    if not trades:
        print("No trades to analyze. Try lowering thresholds or extending --days.")
        return

    # Stratify by hold period
    print(f"=== Performance by hold period (slippage 5bp applied) ===")
    print(f"{'Horizon':<8} {'n':>4} {'WR':>6} {'WLB':>6} {'avg':>8} {'σ':>6} {'PF':>5} {'maxW':>7} {'maxL':>7}")
    print("-" * 70)
    for horizon, key in [("5d", "ret_5d"), ("10d", "ret_10d"), ("20d", "ret_20d")]:
        rets = [t[key] for t in trades if t[key] is not None]
        n = len(rets)
        if n < 5:
            print(f"  {horizon:<6} {n:>4}  (insufficient sample)")
            continue
        wins = sum(1 for r in rets if r > 0)
        wr = wins / n
        wlb = _wilson_lb(wins, n)
        avg = statistics.mean(rets)
        std = statistics.stdev(rets) if n >= 2 else 0
        win_pnls = [r for r in rets if r > 0]
        loss_pnls = [r for r in rets if r <= 0]
        pf = sum(win_pnls) / max(abs(sum(loss_pnls)), 0.01)
        flag = "" if n >= 30 else " ⚠️ n<30"
        print(f"  {horizon:<6} {n:>4} {wr*100:>5.1f}% {wlb*100:>5.1f}% {avg:>+7.2f}% {std:>5.2f} {pf:>5.2f} {max(rets):>+6.2f}% {min(rets):>+6.2f}%{flag}")

    # Stratify by EPS surprise strength
    print()
    print(f"=== Stratified by EPS surprise band (5d return) ===")
    print(f"{'Band':<14} {'n':>4} {'WR':>6} {'avg':>8} {'PF':>5}")
    print("-" * 50)
    bands = [("5-10%", 5, 10), ("10-20%", 10, 20), ("20-50%", 20, 50), (">50%", 50, 1e9)]
    for label, lo, hi in bands:
        bucket = [t for t in trades if lo <= t["eps_surprise_pct"] < hi and t["ret_5d"] is not None]
        n = len(bucket)
        if n < 3:
            print(f"  {label:<14} {n:>4}  (too small)")
            continue
        wins = sum(1 for t in bucket if t["ret_5d"] > 0)
        avg = statistics.mean(t["ret_5d"] for t in bucket)
        win_pnls = [t["ret_5d"] for t in bucket if t["ret_5d"] > 0]
        loss_pnls = [t["ret_5d"] for t in bucket if t["ret_5d"] <= 0]
        pf = sum(win_pnls) / max(abs(sum(loss_pnls)), 0.01)
        print(f"  {label:<14} {n:>4} {wins/n*100:>5.1f}% {avg:>+7.2f}% {pf:>5.2f}")

    # Stratify by gap strength
    print()
    print(f"=== Stratified by post-report gap band (5d return) ===")
    print(f"{'Band':<14} {'n':>4} {'WR':>6} {'avg':>8} {'PF':>5}")
    print("-" * 50)
    gap_bands = [("3-5%", 3, 5), ("5-10%", 5, 10), ("10-20%", 10, 20), (">20%", 20, 1e9)]
    for label, lo, hi in gap_bands:
        bucket = [t for t in trades if lo <= t["post_report_gap_pct"] < hi and t["ret_5d"] is not None]
        n = len(bucket)
        if n < 3:
            print(f"  {label:<14} {n:>4}  (too small)")
            continue
        wins = sum(1 for t in bucket if t["ret_5d"] > 0)
        avg = statistics.mean(t["ret_5d"] for t in bucket)
        win_pnls = [t["ret_5d"] for t in bucket if t["ret_5d"] > 0]
        loss_pnls = [t["ret_5d"] for t in bucket if t["ret_5d"] <= 0]
        pf = sum(win_pnls) / max(abs(sum(loss_pnls)), 0.01)
        print(f"  {label:<14} {n:>4} {wins/n*100:>5.1f}% {avg:>+7.2f}% {pf:>5.2f}")

    # Top contributors / detractors
    print()
    print(f"=== Top 10 winners (5d return) ===")
    print(f"{'Ticker':<7} {'Date':<11} {'EPS%':>7} {'Gap%':>7} {'Ret5d%':>8}")
    sorted_w = sorted([t for t in trades if t["ret_5d"] is not None], key=lambda x: -x["ret_5d"])[:10]
    for t in sorted_w:
        print(f"  {t['ticker']:<7} {t['report_date']:<11} {t['eps_surprise_pct']:>+6.1f}% {t['post_report_gap_pct']:>+6.1f}% {t['ret_5d']:>+7.2f}%")
    print()
    print(f"=== Top 10 losers (5d return) ===")
    sorted_l = sorted([t for t in trades if t["ret_5d"] is not None], key=lambda x: x["ret_5d"])[:10]
    for t in sorted_l:
        print(f"  {t['ticker']:<7} {t['report_date']:<11} {t['eps_surprise_pct']:>+6.1f}% {t['post_report_gap_pct']:>+6.1f}% {t['ret_5d']:>+7.2f}%")

    # Honest CLAUDE.md verdict
    print()
    print("=" * 70)
    rets_5d = [t["ret_5d"] for t in trades if t["ret_5d"] is not None]
    n = len(rets_5d)
    if n >= 30:
        wr = sum(1 for r in rets_5d if r > 0) / n
        wlb = _wilson_lb(sum(1 for r in rets_5d if r > 0), n)
        avg = statistics.mean(rets_5d)
        win_pnls = [r for r in rets_5d if r > 0]
        loss_pnls = [r for r in rets_5d if r <= 0]
        pf = sum(win_pnls) / max(abs(sum(loss_pnls)), 0.01)
        haircut_pf = pf - 0.20  # Survivorship + execution haircut per CLAUDE.md
        print(f"AGGREGATE VERDICT (5d hold, n={n}):")
        print(f"  WR: {wr*100:.1f}%  WLB95: {wlb*100:.1f}%")
        print(f"  Avg: {avg:+.2f}%  PF: {pf:.2f}  Real-world PF (after -0.20 haircut): {haircut_pf:.2f}")
        if haircut_pf >= 1.3 and wlb >= 0.45:
            print(f"  → MECHANISM HOLDS — pass Phase 1 (PF≥1.3, WLB≥45%)")
        else:
            print(f"  → MECHANISM WEAK — does not pass Phase 1 floor (need PF≥1.3 + WLB≥45%)")
    else:
        print(f"AGGREGATE n={n} < 30 — CLAUDE.md Principle 1 floor not met.")
        print(f"Cannot conclude. Extend --days or lower --min-eps to grow sample.")

    # Persist
    out = {
        "generated_at": date.today().isoformat(),
        "lookback_days": args.days,
        "min_eps_pct": args.min_eps,
        "min_gap_pct": args.min_gap,
        "n_total_trades": len(trades),
        "trades": trades,
    }
    out_p = REPO / "cache" / f"backtest_pead_quick_{date.today().isoformat()}.json"
    out_p.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved: {out_p}")


if __name__ == "__main__":
    main()
