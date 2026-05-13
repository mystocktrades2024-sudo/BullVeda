#!/usr/bin/env python3
"""precompute_targets.py — nightly batch pre-compute of target_engine output.

Writes cache/target_engine/{TICKER}_{MODE}.json for the entire scan universe
(SP500 + R1000 + custom watchlist) so the FastAPI endpoint /v2/trade_engine
serves instantly from cache instead of computing on every click.

Hybrid model:
- Pre-compute (this script) writes cache for ~1,500 tickers nightly
- On-demand FastAPI call writes to the same cache for tickers NOT in universe
- 12h TTL · re-runs at start of each new trading day

Usage:
    python3 scripts/precompute_targets.py                       # all modes, full universe
    python3 scripts/precompute_targets.py --modes swing position # specific modes
    python3 scripts/precompute_targets.py --tickers ROST AVGO    # specific tickers
    python3 scripts/precompute_targets.py --limit 50            # cap for testing
    python3 scripts/precompute_targets.py --dry-run             # show plan, don't compute
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def load_universe() -> list:
    """SP500 ∪ R1000 ∪ custom watchlist · de-duped, sorted."""
    import data_fetcher as df

    tickers = set()
    try:
        sp500 = df.get_sp500() or []
        tickers.update(sp500)
        print(f"  SP500: {len(sp500)} tickers")
    except Exception as e:
        print(f"  SP500 fetch failed: {e}")

    try:
        r1000 = df.get_russell1000() or []
        tickers.update(r1000)
        print(f"  R1000: {len(r1000)} tickers")
    except Exception as e:
        print(f"  R1000 fetch failed: {e}")

    # Custom watchlist
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


def precompute(tickers: list, modes: list, force_refresh: bool = False,
               dry_run: bool = False, log_every: int = 25) -> dict:
    """Run engine for each ticker × mode · write cache files · log progress."""
    import target_engine as te

    total = len(tickers) * len(modes)
    if dry_run:
        print(f"\n[DRY RUN] Would precompute {total} entries ({len(tickers)} tickers × {len(modes)} modes)")
        print(f"  Sample: {tickers[:5]}...{tickers[-3:] if len(tickers) > 5 else []}")
        print(f"  Modes: {modes}")
        return {"dry_run": True, "would_compute": total}

    stats = {
        "total": total, "success": 0, "rejected": 0, "errors": 0,
        "cache_hits": 0, "cache_misses": 0,
        "elapsed_sec": 0, "tickers_processed": 0,
    }
    failures = []
    t_start = time.time()

    for i, ticker in enumerate(tickers, 1):
        for mode in modes:
            try:
                payload = te.analyze_trade_cached(ticker, mode=mode, force_refresh=force_refresh)
                if payload.get("decision") == "reject":
                    stats["rejected"] += 1
                else:
                    stats["success"] += 1
                cache_status = (payload.get("_cache") or {}).get("status", "miss")
                if cache_status == "hit":
                    stats["cache_hits"] += 1
                else:
                    stats["cache_misses"] += 1
            except Exception as e:
                stats["errors"] += 1
                failures.append({"ticker": ticker, "mode": mode, "error": f"{type(e).__name__}: {e}"})

        stats["tickers_processed"] = i
        if i % log_every == 0 or i == len(tickers):
            elapsed = time.time() - t_start
            rate = i / elapsed if elapsed > 0 else 0
            eta_sec = (len(tickers) - i) / rate if rate > 0 else 0
            print(f"  [{i:4d}/{len(tickers)}] {elapsed:6.1f}s elapsed · {rate:5.1f}/s · "
                  f"ETA {eta_sec/60:5.1f}m · success={stats['success']} reject={stats['rejected']} err={stats['errors']}")

    stats["elapsed_sec"] = round(time.time() - t_start, 1)
    stats["failures_first_10"] = failures[:10]
    return stats


def main():
    ap = argparse.ArgumentParser(description="Pre-compute structural-target cache for scan universe")
    ap.add_argument("--tickers", nargs="*", help="explicit ticker list (skips universe load)")
    ap.add_argument("--modes", nargs="*", default=["swing", "position", "invest"],
                    choices=["swing", "position", "invest"])
    ap.add_argument("--limit", type=int, default=None, help="cap ticker count for testing")
    ap.add_argument("--force-refresh", action="store_true", help="bypass cache (recompute all)")
    ap.add_argument("--dry-run", action="store_true", help="show plan, don't compute")
    args = ap.parse_args()

    print(f"\n══ precompute_targets · {time.strftime('%Y-%m-%d %H:%M:%S')} ══")
    if args.tickers:
        tickers = [t.upper() for t in args.tickers]
        print(f"Explicit tickers: {len(tickers)}")
    else:
        print("Loading scan universe...")
        tickers = load_universe()
        print(f"Universe total (deduped): {len(tickers)} tickers")

    if args.limit:
        tickers = tickers[: args.limit]
        print(f"Limited to first {args.limit}")

    print(f"Modes: {args.modes}")
    print(f"Force refresh: {args.force_refresh}")
    print("")

    stats = precompute(tickers, args.modes,
                       force_refresh=args.force_refresh,
                       dry_run=args.dry_run)

    print("\n══ Summary ══")
    for k, v in stats.items():
        if k == "failures_first_10":
            if v:
                print(f"  First 10 failures:")
                for f in v:
                    print(f"    {f['ticker']:6s} {f['mode']:9s} {f['error']}")
        else:
            print(f"  {k}: {v}")

    # Write summary to logs
    log_path = ROOT / "cache" / "logs" / "precompute_targets.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a") as f:
        f.write(json.dumps({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "stats": stats,
            "tickers_total": len(tickers),
            "modes": args.modes,
        }) + "\n")

    # Exit code 1 if too many failures
    if stats.get("errors", 0) > len(tickers) * 0.10:  # >10% failure rate
        print(f"\n⚠ ERROR: failure rate exceeds 10% — abort")
        sys.exit(1)


if __name__ == "__main__":
    main()
