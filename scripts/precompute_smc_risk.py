#!/usr/bin/env python3
"""precompute_smc_risk.py — nightly batch pre-compute of the SMC + Risk engines.

Writes cache/pattern_precompute/{engine}_{TICKER}_{MODE}.json for the whole scan
universe so /api/pattern/{engine}/{ticker} serves INSTANTLY from cache instead of
running a live (EODHD-fetching) compute on every user click. At 500+ users this is
what keeps EODHD under its 100K/day cap: load moves from hundreds of unpredictable
daytime cold-computes to one predictable overnight batch (quota fresh, off-peak).

Hybrid model (mirrors scripts/precompute_targets.py):
- This script writes cache for ~1,500 tickers × modes nightly.
- The FastAPI endpoint writes to the SAME cache on-demand for off-universe tickers.
- 12h TTL · re-runs at the start of each new trading day.

Usage:
    python3 scripts/precompute_smc_risk.py                         # smc+risk, all modes, full universe
    python3 scripts/precompute_smc_risk.py --engines smc           # one engine
    python3 scripts/precompute_smc_risk.py --modes SWING POSITION  # specific modes
    python3 scripts/precompute_smc_risk.py --tickers ATEX AMD      # specific tickers
    python3 scripts/precompute_smc_risk.py --limit 50              # cap (testing)
    python3 scripts/precompute_smc_risk.py --dry-run               # plan only
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CACHE_DIR = ROOT / "cache" / "pattern_precompute"
ENGINES = ["smc", "risk"]
MODES = ["SWING", "POSITION", "INVESTMENT"]


def load_universe() -> list:
    """SP500 ∪ R1000 ∪ custom watchlist · de-duped, sorted (same source as targets)."""
    import data_fetcher as dfm
    tickers = set()
    for name, fn in (("SP500", "get_sp500"), ("R1000", "get_russell1000")):
        try:
            got = getattr(dfm, fn)() or []
            tickers.update(got)
            print(f"  {name}: {len(got)} tickers")
        except Exception as e:
            print(f"  {name} fetch failed: {e}")
    wl_path = ROOT / "config" / "watchlist.json"
    if wl_path.exists():
        try:
            wl = json.loads(wl_path.read_text())
            custom = wl.get("tickers", []) if isinstance(wl, dict) else (wl or [])
            tickers.update(t.upper() for t in custom)
            print(f"  Custom watchlist: {len(custom)} tickers")
        except Exception as e:
            print(f"  Watchlist read failed: {e}")
    return sorted(tickers)


def _cache_path(engine: str, ticker: str, mode: str) -> Path:
    return CACHE_DIR / f"{engine}_{ticker.upper()}_{mode.upper()}.json"


def precompute(tickers, engines, modes, dry_run=False, log_every=50) -> dict:
    import pattern_engines
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    total = len(tickers) * len(engines) * len(modes)
    if dry_run:
        print(f"\n[DRY RUN] Would precompute {total} entries "
              f"({len(tickers)} tickers × {len(engines)} engines × {len(modes)} modes)")
        print(f"  Sample tickers: {tickers[:5]}{'…' if len(tickers) > 5 else ''}")
        print(f"  Engines: {engines} · Modes: {modes}")
        return {"dry_run": True, "would_compute": total}

    stats = {"ok": 0, "no_data": 0, "error": 0, "written": 0}
    t0 = time.time()
    done = 0
    for tk in tickers:
        for eng in engines:
            for md in modes:
                done += 1
                try:
                    out = pattern_engines.detect(eng, tk, md)
                    if isinstance(out, dict) and out.get("ok"):
                        stats["ok"] += 1
                        _cache_path(eng, tk, md).write_text(json.dumps(out))
                        stats["written"] += 1
                    else:
                        stats["no_data"] += 1
                        # cache the honest "no data" too, so the endpoint doesn't
                        # re-attempt a live fetch on every click for a dead symbol
                        if isinstance(out, dict):
                            _cache_path(eng, tk, md).write_text(json.dumps(out))
                            stats["written"] += 1
                except Exception as e:
                    stats["error"] += 1
                    if stats["error"] <= 5:
                        print(f"  ! {eng}/{tk}/{md}: {type(e).__name__}: {e}")
                if done % log_every == 0:
                    rate = done / max(1e-6, time.time() - t0)
                    print(f"  {done}/{total}  ok={stats['ok']} nodata={stats['no_data']} "
                          f"err={stats['error']}  ({rate:.1f}/s)")
    stats["elapsed_s"] = round(time.time() - t0, 1)
    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engines", nargs="+", default=ENGINES)
    ap.add_argument("--modes", nargs="+", default=MODES)
    ap.add_argument("--tickers", nargs="+", default=None)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    engines = [e.lower() for e in args.engines]
    modes = [m.upper() for m in args.modes]
    print(f"=== precompute_smc_risk · engines={engines} modes={modes} ===")
    tickers = [t.upper() for t in args.tickers] if args.tickers else load_universe()
    if args.limit and args.limit > 0:
        tickers = tickers[:args.limit]
    print(f"  universe: {len(tickers)} tickers → cache: {CACHE_DIR}")

    stats = precompute(tickers, engines, modes, dry_run=args.dry_run)
    print(f"\nDONE: {json.dumps(stats)}")


if __name__ == "__main__":
    main()
