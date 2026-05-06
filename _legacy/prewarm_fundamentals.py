"""
prewarm_fundamentals.py — Nightly cache pre-warmer for fundamentals.

Run via cron at 3 AM PST (before market open) to ensure the morning scan
gets 100% sqlite cache hits on fundamentals. Only re-fetches tickers that
are stale (>30d) or just reported earnings.

Usage:
  python3 prewarm_fundamentals.py           # dry run — show what would refresh
  python3 prewarm_fundamentals.py --apply   # actually refresh stale tickers

Cron setup (macOS):
  crontab -e
  0 3 * * * cd /Volumes/MyMacDisk/Claude\ Skills/SwingTrade && python3 prewarm_fundamentals.py --apply >> cache/logs/prewarm.log 2>&1
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("prewarm")

BASE = Path(__file__).parent


def _get_universe() -> list[str]:
    """Load the current ticker universe from the latest bundle or config."""
    # Try bundle
    bundle_path = BASE / "cache" / "last_bundle.json"
    if bundle_path.exists():
        try:
            b = json.loads(bundle_path.read_text())
            tickers = [r.get("ticker") for r in b.get("all_scored", []) if r.get("ticker")]
            if tickers:
                return tickers
        except Exception:
            pass
    # Fallback: archive parquet filenames
    ohlcv_dir = BASE / "data" / "ohlcv"
    if ohlcv_dir.exists():
        return [p.stem for p in ohlcv_dir.glob("*.parquet")]
    return []


def run(apply: bool = False, ttl_days: int = 30) -> None:
    import fundamentals_store as fs
    from data_fetcher import get_stock_info

    universe = _get_universe()
    log.info(f"Universe: {len(universe)} tickers")

    stale = fs.tickers_needing_refresh(universe, ttl_days=ttl_days)
    log.info(f"Stale (need refresh): {len(stale)} / {len(universe)}")

    if not stale:
        log.info("All tickers fresh within TTL. Nothing to do.")
        return

    if not apply:
        log.info("Dry run — showing first 20 stale tickers:")
        for t in stale[:20]:
            log.info(f"  {t}")
        log.info(f"Re-run with --apply to actually refresh {len(stale)} tickers.")
        return

    # Refresh stale tickers
    start = time.time()
    ok = 0
    fail = 0
    for i, ticker in enumerate(stale):
        try:
            info = get_stock_info(ticker)
            if info and not info.get("error"):
                ok += 1
            else:
                fail += 1
        except Exception:
            fail += 1

        if (i + 1) % 50 == 0:
            elapsed = time.time() - start
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            eta = (len(stale) - i - 1) / rate if rate > 0 else 0
            log.info(f"  Progress: {i+1}/{len(stale)} ({ok} OK, {fail} fail) — {eta:.0f}s remaining")

    elapsed = time.time() - start
    log.info(f"Done in {elapsed:.0f}s: {ok} refreshed, {fail} failed out of {len(stale)}")

    # Report final stats
    stats = fs.stats()
    log.info(f"Cache stats: {stats['total_rows']} rows, sources={stats['sources']}, "
             f"fresh <1d: {stats['fresh_within']['1d']}, <7d: {stats['fresh_within']['7d']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="Actually refresh stale tickers")
    ap.add_argument("--ttl", type=int, default=30, help="TTL in days (default 30)")
    args = ap.parse_args()

    # Auto-update OHLCV archive so D1-D5 Performance columns are fresh
    # even before the first scan of the day runs.
    try:
        from data_archive import delta_update
        log.info("Updating OHLCV archive (pre-scan freshness)...")
        delta_update()
        log.info("Archive updated ✓")
    except Exception as e:
        log.warning(f"Archive update failed: {e}")

    # Pre-compute mark-to-market so D1-D5 columns are populated
    # when the dashboard loads (even before the first scan).
    try:
        from tracker import mark_to_market, evaluate_pending
        log.info("Evaluating pending picks (5d hold)...")
        n_eval = evaluate_pending(hold_days=5)
        log.info(f"  Evaluated {n_eval} picks")
        log.info("Computing mark-to-market for D1-D5 columns...")
        mtm = mark_to_market()
        filled = sum(1 for m in mtm if m.get("D1") is not None)
        log.info(f"  MTM: {len(mtm)} picks, D1 filled: {filled}")
    except Exception as e:
        log.warning(f"MTM pre-compute failed: {e}")

    run(apply=args.apply, ttl_days=args.ttl)
