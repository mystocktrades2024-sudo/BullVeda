#!/usr/bin/env python3
"""sharpe_per_regime.py — per-stock Sharpe decomposition BY REGIME.

For every scan ticker, segment its historical closes by which regime the
market was in on that day, then compute Sharpe within each regime.

This answers: "ADI Sharpe is 3.85 overall — but is it 5.0 in trending regime
and -1.0 in choppy? Or vice-versa?"  i.e. tells you which stocks have edge in
OUR alpha regime (choppy) vs only-trending names.

Regime mapping built from:
  - picks_history.json entries (regime4 tagged at entry_date)
  - cache/logs/scan_*.log files (grep for regime classification line)
  - forward-fill (carry-forward) between known dates

Output:
  console table (top per-regime Sharpe leaders)
  cache/sharpe_per_regime_<DATE>.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def _build_regime_history() -> dict[str, str]:
    """Build date_str → regime4 mapping from all available sources, then
    forward-fill any gaps between earliest and latest known date."""
    mapping: dict[str, str] = {}

    # Source 1: picks_history.json
    ph = REPO / "cache" / "picks_history.json"
    if ph.exists():
        d = json.loads(ph.read_text())
        for t in d.get("trades") or []:
            ed = t.get("entry_date")
            r = t.get("regime4") or t.get("regime")
            if ed and r and r != "unknown":
                mapping.setdefault(ed, r)

    # Source 2: scan logs — grep for "Regime: X (trending|choppy|...)" patterns
    logs_dir = REPO / "cache" / "logs"
    if logs_dir.exists():
        pat = re.compile(r"regime[_\s]*4?:?\s*(risk_on_trending|risk_on_choppy|risk_off_trending|risk_off_choppy|panic|bull|bear)", re.IGNORECASE)
        for log_path in sorted(logs_dir.glob("scan_*.log")):
            try:
                m = re.search(r"scan_(\d{4}-\d{2}-\d{2})", log_path.name)
                if not m:
                    continue
                ds = m.group(1)
                if ds in mapping:
                    continue
                txt = log_path.read_text(errors="ignore")[:200000]
                hit = pat.search(txt)
                if hit:
                    mapping[ds] = hit.group(1).lower()
            except Exception:
                continue

    # Forward-fill between earliest and latest
    if not mapping:
        return {}
    dates_known = sorted(mapping.keys())
    first = datetime.fromisoformat(dates_known[0]).date()
    last = datetime.fromisoformat(dates_known[-1]).date()
    filled: dict[str, str] = {}
    cur = first
    last_seen = mapping[dates_known[0]]
    while cur <= last:
        ds = cur.isoformat()
        if ds in mapping:
            last_seen = mapping[ds]
        filled[ds] = last_seen
        cur = date.fromordinal(cur.toordinal() + 1)
    return filled


def _segment_closes_by_regime(df, date_to_regime: dict[str, str]) -> dict[str, list[float]]:
    """Group consecutive closes by their regime tag.

    Returns regime → list of closes (in chronological order). Pairs of
    adjacent closes within a single regime period are what feed daily
    returns; gaps (regime change days) are kept by including the close at
    the boundary in BOTH segments.
    """
    if df is None or len(df) == 0:
        return {}
    # Find date column / index
    if hasattr(df, "index") and hasattr(df.index, "date"):
        dates = [d.date().isoformat() if hasattr(d, "date") else str(d)[:10] for d in df.index]
    elif "date" in df.columns:
        dates = [str(d)[:10] for d in df["date"]]
    else:
        return {}
    closes = df["close"].astype(float).tolist() if "close" in df.columns else df["Close"].astype(float).tolist()
    by_reg: dict[str, list[float]] = defaultdict(list)
    for ds, c in zip(dates, closes):
        r = date_to_regime.get(ds)
        if r is None:
            continue
        by_reg[r].append(c)
    return by_reg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--min-bars", type=int, default=30,
                    help="Min bars per regime to compute Sharpe (default 30)")
    args = ap.parse_args()

    from data_archive import load_ticker
    from lib.sharpe_utils import sharpe_annualized

    # Build the regime history map
    print("Building date→regime map...")
    date_to_regime = _build_regime_history()
    if not date_to_regime:
        print("ERROR: no regime tags found. Run a scan first to populate cache/logs/.", file=sys.stderr)
        sys.exit(1)
    from collections import Counter
    regime_days = Counter(date_to_regime.values())
    print(f"  Days mapped: {len(date_to_regime)} ({min(date_to_regime.keys())} → {max(date_to_regime.keys())})")
    print(f"  Distribution: {dict(regime_days)}")

    # Load tickers
    tk_path = REPO / "infra" / "prototype" / "tickers.json"
    if not tk_path.exists():
        print(f"ERROR: {tk_path} not found", file=sys.stderr)
        sys.exit(1)
    tickers = json.loads(tk_path.read_text())
    syms = list(tickers.keys())
    print(f"\nProcessing {len(syms)} tickers...")

    rows = []
    skipped_no_data = 0
    for sym in syms:
        try:
            df = load_ticker(sym)
        except Exception:
            df = None
        if df is None or len(df) < args.min_bars:
            skipped_no_data += 1
            continue
        seg = _segment_closes_by_regime(df, date_to_regime)
        per_reg: dict[str, dict] = {}
        for reg, closes in seg.items():
            if len(closes) < args.min_bars:
                continue
            # Use full segment as lookback
            sh, ret_a, vol_a = sharpe_annualized(closes, lookback=len(closes))
            if sh is None:
                continue
            per_reg[reg] = {"sharpe": sh, "ret_ann_pct": ret_a, "vol_ann_pct": vol_a, "n_bars": len(closes)}
        if not per_reg:
            continue
        rows.append({"ticker": sym, "regimes": per_reg, "score": tickers[sym].get("score"),
                     "verdict": tickers[sym].get("verdict")})

    # Output: top N per regime
    print(f"\n=== TOP {args.top} BY SHARPE PER REGIME ===\n")
    canonical_regimes = ["risk_on_trending", "risk_on_choppy", "risk_off_trending", "panic", "bull", "bear"]
    found_regimes = sorted({r for row in rows for r in row["regimes"].keys()},
                            key=lambda x: (canonical_regimes.index(x) if x in canonical_regimes else 999, x))
    for reg in found_regimes:
        rated = [(r["ticker"], r["regimes"][reg]) for r in rows if reg in r["regimes"]]
        rated.sort(key=lambda x: -x[1]["sharpe"])
        print(f"--- {reg.upper()} (n={len(rated)} tickers with ≥{args.min_bars} bars in regime) ---")
        print(f"  {'#':>3} {'TICKER':<7} {'SHARPE':>7} {'RET%':>7} {'VOL%':>7} {'BARS':>5}")
        for i, (t, s) in enumerate(rated[:args.top], 1):
            print(f"  {i:>3} {t:<7} {s['sharpe']:>7.2f} {s['ret_ann_pct']:>+6.1f}% {s['vol_ann_pct']:>6.1f}% {s['n_bars']:>5}")
        print()

    # Find names that work in CHOPPY (our alpha regime) but NOT trending
    if "risk_on_choppy" in found_regimes and "risk_on_trending" in found_regimes:
        print("=" * 80)
        print("CHOPPY-EDGE NAMES (high Sharpe in choppy, low in trending) — our alpha picks")
        print("=" * 80)
        choppy_only = []
        for r in rows:
            ch = r["regimes"].get("risk_on_choppy", {}).get("sharpe")
            tr = r["regimes"].get("risk_on_trending", {}).get("sharpe")
            if ch is not None and tr is not None and ch > 1.0 and ch - tr > 1.0:
                choppy_only.append((r["ticker"], ch, tr, ch - tr))
        choppy_only.sort(key=lambda x: -x[3])
        for t, ch, tr, diff in choppy_only[:args.top]:
            print(f"  {t:<7}  choppy {ch:+5.2f}  trending {tr:+5.2f}  edge {diff:+5.2f}")

    # Persist
    out = {
        "generated_at": date.today().isoformat(),
        "regime_days_mapped": dict(regime_days),
        "n_tickers_processed": len(syms),
        "n_tickers_with_data": len(rows),
        "skipped_no_data": skipped_no_data,
        "rows": rows,
    }
    out_p = REPO / "cache" / f"sharpe_per_regime_{date.today().isoformat()}.json"
    out_p.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved: {out_p}")


if __name__ == "__main__":
    main()
