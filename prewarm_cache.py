"""
prewarm_cache.py — keep EODHD caches warm so user-initiated scans run fast.

Problem this solves
────────────────────
EODHD cache TTLs (from CLAUDE.md):
  fundamentals  1 day      eod  12 h    news      4 h
  intraday     10 min      rt    5 min  options   2 h

When a /Swing-Trade scan fires and a TTL has expired, that endpoint refetches
across the universe — up to 9000+ network calls gated by EODHD's 14/sec limit.
A cold scan can take 2+ hours. A warm scan finishes in ~10 min.

This script refreshes the SHORTEST-TTL endpoints (news + intraday) at the
cadence they expire, plus eod once after market close. Run via launchd every
30 min during market hours.

Endpoints refreshed:
  • news_articles    every run  (4h TTL, refresh every 30m keeps it always warm)
  • intraday 1H      every run  (10m TTL — only used during market hours)
  • fundamentals     once/day   (1d TTL)
  • eod              once after 4pm ET close (12h TTL)
  • real_time        every run, batch    (5m TTL)

CLI:
  python3 prewarm_cache.py                  # refresh news+intraday+rt for top 100
  python3 prewarm_cache.py --all            # all enrichment endpoints
  python3 prewarm_cache.py --tickers 200    # custom top-N

Universe = top-N tickers by score from cache/last_bundle.json (the most recent
scan output). No score file → bail (nothing to prewarm).
"""

from __future__ import annotations
import argparse
import json
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

log = logging.getLogger("prewarm")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)

BUNDLE = BASE / "cache" / "last_bundle.json"
TICKERS_JSON = BASE / "infra" / "prototype" / "tickers.json"


def load_universe(top_n: int = 100) -> list[str]:
    """Pick top-N tickers by score from the most recent scan output."""
    candidates: list[tuple[str, float]] = []
    # Prefer tickers.json (lighter, sorted by score already)
    if TICKERS_JSON.exists():
        try:
            data = json.loads(TICKERS_JSON.read_text())
            for sym, payload in data.items():
                score = payload.get("score") or 0
                candidates.append((sym, score))
        except Exception as e:
            log.warning(f"tickers.json unreadable: {e}")
    # Fallback to last_bundle.json
    elif BUNDLE.exists():
        try:
            data = json.loads(BUNDLE.read_text())
            for row in data.get("short_term", []):
                sym = row.get("ticker")
                score = row.get("score") or 0
                if sym:
                    candidates.append((sym, score))
        except Exception as e:
            log.warning(f"last_bundle unreadable: {e}")
    candidates.sort(key=lambda x: x[1], reverse=True)
    return [t for t, _ in candidates[:top_n]]


def refresh_news(tickers: list[str], workers: int = 14) -> tuple[int, int, float]:
    """Fetch news_articles for each ticker. Cache TTL 4h."""
    import eodhd_client as e
    t0 = time.time()
    ok = err = 0

    def _one(t):
        try:
            r = e.news(ticker=t, limit=8, cache_ttl=14400)
            return bool(r is not None), None
        except Exception as ex:
            return False, ex

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_one, t): t for t in tickers}
        for fut in as_completed(futs):
            ok_, ex = fut.result()
            if ok_:
                ok += 1
            else:
                err += 1
    return ok, err, time.time() - t0


def refresh_intraday(tickers: list[str], workers: int = 14) -> tuple[int, int, float]:
    """Fetch intraday 1H for each ticker. Cache TTL 10min."""
    import eodhd_client as e
    t0 = time.time()
    ok = err = 0

    def _one(t):
        try:
            r = e.intraday(t, interval="1h", cache_ttl=600)
            return bool(r is not None), None
        except Exception as ex:
            return False, ex

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_one, t): t for t in tickers}
        for fut in as_completed(futs):
            ok_, ex = fut.result()
            if ok_:
                ok += 1
            else:
                err += 1
    return ok, err, time.time() - t0


def refresh_realtime(tickers: list[str]) -> tuple[int, int, float]:
    """Fetch real-time quotes for the whole universe via batch endpoint (1 call per ~50)."""
    import eodhd_client as e
    t0 = time.time()
    ok = err = 0
    # Batch 50 at a time
    for i in range(0, len(tickers), 50):
        chunk = tickers[i:i + 50]
        try:
            r = e.real_time(chunk, cache_ttl=300)
            if r is not None:
                ok += len(chunk)
            else:
                err += len(chunk)
        except Exception:
            err += len(chunk)
    return ok, err, time.time() - t0


def refresh_fundamentals(tickers: list[str], workers: int = 14) -> tuple[int, int, float]:
    """Fetch fundamentals for each ticker. Cache TTL 1 day."""
    import eodhd_client as e
    t0 = time.time()
    ok = err = 0

    def _one(t):
        try:
            r = e.fundamentals(t, cache_ttl=86400)
            return bool(r is not None), None
        except Exception as ex:
            return False, ex

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_one, t): t for t in tickers}
        for fut in as_completed(futs):
            ok_, ex = fut.result()
            if ok_:
                ok += 1
            else:
                err += 1
    return ok, err, time.time() - t0


def main():
    import time as _time
    _t0 = _time.time()
    p = argparse.ArgumentParser()
    p.add_argument("--tickers", type=int, default=100, help="Top-N tickers (default 100)")
    p.add_argument("--all", action="store_true", help="Refresh ALL endpoints (incl. fundamentals)")
    p.add_argument("--workers", type=int, default=14)
    args = p.parse_args()

    try:
        universe = load_universe(args.tickers)
        if not universe:
            log.warning("no universe — run /Swing-Trade once to seed tickers.json")
            try:
                from lib.autorun_reporter import report
                report("prewarm-cache", "warning", summary="No universe — tickers.json missing")
            except Exception:
                pass
            return 1

        log.info(f"prewarming top {len(universe)} tickers · workers={args.workers}")
        log.info(f"sample: {', '.join(universe[:8])}...")

        results = {}
        ok, err, dt = refresh_news(universe, args.workers)
        log.info(f"news:        {ok}/{len(universe)} ok · {err} err · {dt:.1f}s")
        results["news"] = f"{ok}/{len(universe)}"

        ok, err, dt = refresh_intraday(universe, args.workers)
        log.info(f"intraday 1H: {ok}/{len(universe)} ok · {err} err · {dt:.1f}s")
        results["intraday"] = f"{ok}/{len(universe)}"

        ok, err, dt = refresh_realtime(universe)
        log.info(f"real-time:   {ok}/{len(universe)} ok · {err} err · {dt:.1f}s")
        results["real-time"] = f"{ok}/{len(universe)}"

        if args.all:
            ok, err, dt = refresh_fundamentals(universe, args.workers)
            log.info(f"fundamentals: {ok}/{len(universe)} ok · {err} err · {dt:.1f}s")
            results["fundamentals"] = f"{ok}/{len(universe)}"

        log.info("done — caches refreshed; next scan will hit warm cache")
        try:
            from lib.autorun_reporter import report
            report("prewarm-cache", "success",
                   summary=f"Prewarmed {len(universe)} tickers across {len(results)} endpoints",
                   duration_sec=_time.time() - _t0,
                   details=results)
        except Exception:
            pass
        return 0
    except Exception as e:
        try:
            from lib.autorun_reporter import report_failed
            report_failed("prewarm-cache", str(e), duration_sec=_time.time() - _t0)
        except Exception:
            pass
        raise


if __name__ == "__main__":
    sys.exit(main())
