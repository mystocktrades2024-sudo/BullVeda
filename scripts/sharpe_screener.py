#!/usr/bin/env python3
"""
sharpe_screener.py — list scan tickers with Sharpe ≥ threshold.

Computes annualized Sharpe ratio per ticker from data_archive OHLCV:
  Sharpe = (mean_daily_return / stdev_daily_return) × √252

Defaults: lookback 126 trading days (~6 months), risk-free 0%.
Filters to scan-active tickers (in tickers.json), excludes killed/AVOID.

Output: ranked table + saves cache/sharpe_screen_<DATE>.json.

Usage:
  python3 scripts/sharpe_screener.py                 # default threshold 1.25
  python3 scripts/sharpe_screener.py --min 1.5       # custom threshold
  python3 scripts/sharpe_screener.py --lookback 252  # 1-year window
  python3 scripts/sharpe_screener.py --include-killed  # include AVOID tickers
"""
from __future__ import annotations
import argparse
import json
import math
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def _ann_sharpe(closes, lookback: int = 126) -> tuple[float | None, float | None, float | None]:
    """Returns (sharpe_annualized, return_annualized_pct, vol_annualized_pct)."""
    n = len(closes)
    if n < lookback + 1:
        return None, None, None
    sub = closes[-lookback:]
    rets = []
    for i in range(1, len(sub)):
        if sub[i - 1] > 0:
            rets.append((sub[i] - sub[i - 1]) / sub[i - 1])
    if len(rets) < 30:
        return None, None, None
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    std = math.sqrt(var) if var > 0 else 0
    if std == 0:
        return None, None, None
    sharpe = (mean / std) * math.sqrt(252)
    ret_ann = mean * 252 * 100
    vol_ann = std * math.sqrt(252) * 100
    return round(sharpe, 3), round(ret_ann, 2), round(vol_ann, 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min", type=float, default=1.25, help="Minimum Sharpe (default 1.25)")
    ap.add_argument("--lookback", type=int, default=126, help="Trading days lookback (default 126 ≈ 6mo)")
    ap.add_argument("--include-killed", action="store_true", help="Include killed/AVOID tickers")
    ap.add_argument("--top", type=int, default=50, help="Show top N by Sharpe")
    args = ap.parse_args()

    from data_archive import load_ticker

    tk_path = REPO / "infra" / "prototype" / "tickers.json"
    if not tk_path.exists():
        print(f"ERROR: {tk_path} not found — run /Swing-Trade first", file=sys.stderr)
        sys.exit(1)
    tickers = json.loads(tk_path.read_text())
    syms = list(tickers.keys())
    print(f"Computing {args.lookback}-day Sharpe for {len(syms)} scan tickers (threshold ≥ {args.min})...")

    results = []
    skipped_no_data = 0
    skipped_killed = 0
    for sym in syms:
        t = tickers[sym]
        if not args.include_killed:
            if t.get("killed") or t.get("verdict") == "AVOID" or t.get("stage") == "AVOID":
                skipped_killed += 1
                continue
        try:
            df = load_ticker(sym)
        except Exception:
            df = None
        if df is None or len(df) < args.lookback + 1:
            skipped_no_data += 1
            continue
        closes = df["Close"].values.tolist()
        sharpe, ret_ann, vol_ann = _ann_sharpe(closes, lookback=args.lookback)
        if sharpe is None:
            skipped_no_data += 1
            continue
        results.append({
            "ticker": sym,
            "sharpe": sharpe,
            "return_ann_pct": ret_ann,
            "vol_ann_pct": vol_ann,
            "score": t.get("score"),
            "verdict": t.get("verdict"),
            "stage": t.get("stage"),
            "entry_quality": t.get("entry_quality"),
            "setup_family": t.get("setup_family") or t.get("setup", "—"),
            "sector": t.get("sector"),
            "price": t.get("price"),
            "earn_days": t.get("earn_days"),
        })

    results.sort(key=lambda r: -r["sharpe"])
    above = [r for r in results if r["sharpe"] >= args.min]

    print()
    print(f"=== {len(above)} tickers with Sharpe ≥ {args.min} (out of {len(results)} computed) ===")
    print(f"  skipped: {skipped_killed} killed/AVOID · {skipped_no_data} insufficient OHLCV")
    print()
    print(f"{'#':>3} {'TICKER':<7} {'SHARPE':>7} {'RET%':>7} {'VOL%':>7} {'SCORE':>5} {'VERD':<6} {'ENTRY_Q':<10} {'SETUP':<22} {'SECTOR':<22}")
    print("-" * 110)
    show = above[:args.top]
    for i, r in enumerate(show, 1):
        v = (r.get("verdict") or "—")[:6]
        eq = (r.get("entry_quality") or "—")[:10]
        st = (r.get("setup_family") or "—")[:22]
        sec = (r.get("sector") or "—")[:22]
        sc = r.get("score")
        print(f"{i:>3} {r['ticker']:<7} {r['sharpe']:>7.2f} {r['return_ann_pct']:>+6.1f}% "
              f"{r['vol_ann_pct']:>6.1f}% {sc if sc is not None else '—':>5} "
              f"{v:<6} {eq:<10} {st:<22} {sec:<22}")

    # Persist
    out = {
        "generated_at": date.today().isoformat(),
        "threshold": args.min,
        "lookback_days": args.lookback,
        "n_tickers_scan": len(syms),
        "n_computed": len(results),
        "n_above_threshold": len(above),
        "skipped_killed": skipped_killed,
        "skipped_no_data": skipped_no_data,
        "tickers_above": above,
    }
    out_p = REPO / "cache" / f"sharpe_screen_{date.today().isoformat()}.json"
    out_p.write_text(json.dumps(out, indent=2, default=str))
    print()
    print(f"Saved: {out_p}")


if __name__ == "__main__":
    main()
