#!/usr/bin/env python3
"""enrich_nightly.py — Pre-warm the per-ticker enrichment cache.

Designed to run via cron (or launchd) at ~02:00 PT every night. Pre-populates
the EODHD on-disk cache + the in-process module caches so the next daily scan
reads from cache instead of hitting EODHD live.

What it warms:
  - bulk_eod (Phase 2)               · 1 call · all US last-day OHLCV
  - calendar/trends (Phase 3)        · ~7 calls · EPS estimates + revisions
  - calendar/earnings                · ~7 calls · upcoming earnings dates
  - bulk insider transactions        · 1 call · last-day insider trades
  - per-ticker fundamentals          · ~3000 calls · 24h TTL
  - sector ETF rotation snapshot     · 1 call · macro context

Default universe is SP500 ∪ Russell-1000 ∪ custom_tickers (de-duped). Override
with `--universe sp500|r1000|r2000|all` or `--tickers AAPL,MSFT,...`.

Quota math (typical full warm):
    ~3,015 EODHD calls @ 14/s ≈ 4 min
    All within the 100k/day quota; runs once per night so daily quota usage is
    spread evenly across 24h instead of concentrated at scan time.

Usage:
    python3 enrich_nightly.py                       # default universe
    python3 enrich_nightly.py --universe sp500      # SP500 only
    python3 enrich_nightly.py --tickers AAPL,NVDA   # explicit list
    python3 enrich_nightly.py --skip-fundamentals   # only Phase 2/3 bulks
    python3 enrich_nightly.py --dry-run             # plan, don't fetch
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("enrich_nightly")

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))


def _resolve_universe(args) -> list[str]:
    """Return the deduped ticker universe based on CLI args."""
    if args.tickers:
        return [t.strip().upper() for t in args.tickers.split(",") if t.strip()]

    from data_fetcher import get_sp500, get_russell1000, load_config
    cfg = load_config()
    custom = list((cfg.get("universe") or {}).get("custom_tickers") or [])

    if args.universe == "sp500":
        return sorted(set(get_sp500() + custom))
    if args.universe == "r1000":
        return sorted(set(get_russell1000() + custom))
    if args.universe == "r2000":
        try:
            from data_fetcher import get_russell2000
            return sorted(set(get_russell2000() + custom))
        except Exception:
            log.warning("R2000 universe unavailable; falling back to R1000")
            return sorted(set(get_russell1000() + custom))
    # all = SP500 + R1000 + custom
    return sorted(set(get_sp500() + get_russell1000() + custom))


def _warm_bulk_eod() -> dict:
    """Phase 2 warm: 1 call → all US last-day OHLCV cached for 7200s."""
    try:
        import eodhd_client as eod
        t0 = time.time()
        rows = eod.bulk_eod(exchange="US")
        elapsed = time.time() - t0
        n = len(rows) if isinstance(rows, list) else 0
        log.info(f"  [bulk_eod] {n:,} stocks last-day cached ({elapsed:.1f}s)")
        return {"ok": True, "rows": n, "elapsed_sec": elapsed}
    except Exception as e:
        log.warning(f"  [bulk_eod] failed: {e}")
        return {"ok": False, "error": str(e)}


def _warm_calendar_trends(tickers: list[str]) -> dict:
    """Phase 3 warm: chunked bulk calendar/trends fetches."""
    try:
        import eodhd_client as eod
        t0 = time.time()
        res = eod.prewarm_calendar_trends(tickers)
        log.info(
            f"  [calendar/trends] {res.get('n_tickers')}/{len(tickers)} tickers in "
            f"{res.get('calls')} bulk calls ({res.get('elapsed_sec')}s)"
        )
        return {"ok": True, **res}
    except Exception as e:
        log.warning(f"  [calendar/trends] failed: {e}")
        return {"ok": False, "error": str(e)}


def _warm_calendar_earnings(tickers: list[str]) -> dict:
    """Bulk upcoming earnings dates (replaces per-ticker get_earnings_date warms)."""
    try:
        import eodhd_client as eod
        import datetime as _dt
        t0 = time.time()
        today = _dt.date.today()
        to_date = (today + _dt.timedelta(days=30)).isoformat()
        n_calls = 0
        n_events = 0
        for i in range(0, len(tickers), 100):
            chunk = tickers[i:i + 100]
            r = eod.bulk_calendar_earnings(chunk, from_date=today.isoformat(), to_date=to_date)
            n_calls += 1
            if r and isinstance(r, dict):
                n_events += len(r.get("earnings") or [])
        elapsed = time.time() - t0
        log.info(f"  [calendar/earnings] {n_events} events, {n_calls} calls ({elapsed:.1f}s)")
        return {"ok": True, "events": n_events, "calls": n_calls, "elapsed_sec": elapsed}
    except Exception as e:
        log.warning(f"  [calendar/earnings] failed: {e}")
        return {"ok": False, "error": str(e)}


def _warm_fundamentals(tickers: list[str]) -> dict:
    """Per-ticker fundamentals (24h cache). Threaded for throughput."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    try:
        import eodhd_client as eod
    except Exception as e:
        log.warning(f"  [fundamentals] eodhd_client unavailable: {e}")
        return {"ok": False, "error": str(e)}

    t0 = time.time()
    n_ok = 0
    n_fail = 0

    def _one(t: str) -> bool:
        try:
            data = eod.fundamentals(t, cache_ttl=86400)
            return bool(data)
        except Exception:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = {pool.submit(_one, t): t for t in tickers}
        for n_done, fut in enumerate(as_completed(futs), 1):
            if fut.result():
                n_ok += 1
            else:
                n_fail += 1
            if n_done % 250 == 0:
                log.info(f"  [fundamentals] {n_done}/{len(tickers)} ({time.time() - t0:.0f}s)")

    elapsed = time.time() - t0
    log.info(f"  [fundamentals] {n_ok} cached, {n_fail} failed, {elapsed:.0f}s total")
    return {"ok": True, "cached": n_ok, "failed": n_fail, "elapsed_sec": elapsed}


def _warm_insider_summary(tickers: list[str], limit: int = 200) -> dict:
    """Light insider warm — only top tickers (full universe is unbounded)."""
    try:
        from data_fetcher import get_insider_activity
        t0 = time.time()
        n_ok = 0
        for t in tickers[:limit]:
            try:
                d = get_insider_activity(t)
                if d:
                    n_ok += 1
            except Exception:
                pass
        elapsed = time.time() - t0
        log.info(f"  [insider] {n_ok}/{min(limit, len(tickers))} tickers warmed ({elapsed:.0f}s)")
        return {"ok": True, "cached": n_ok, "elapsed_sec": elapsed}
    except Exception as e:
        log.warning(f"  [insider] failed: {e}")
        return {"ok": False, "error": str(e)}


def main():
    ap = argparse.ArgumentParser(description="Nightly enrichment cache warmer")
    ap.add_argument("--universe", default="all", choices=("all", "sp500", "r1000", "r2000"))
    ap.add_argument("--tickers", default=None, help="Explicit comma-list")
    ap.add_argument("--skip-fundamentals", action="store_true")
    ap.add_argument("--skip-insider", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    log.info("=" * 60)
    log.info("Nightly enrichment cache warmer")
    log.info("=" * 60)

    tickers = _resolve_universe(args)
    log.info(f"Universe: {len(tickers)} tickers ({args.universe})")

    if args.dry_run:
        log.info("DRY-RUN — no API calls will be made")
        log.info(f"  Would warm: bulk_eod (1 call), calendar/trends "
                 f"(~{(len(tickers)+99)//100} calls), calendar/earnings "
                 f"(~{(len(tickers)+99)//100} calls)"
                 + ("" if args.skip_fundamentals else f", fundamentals ({len(tickers)} calls)")
                 + ("" if args.skip_insider else f", insider (~200 calls)"))
        return

    overall_t0 = time.time()

    log.info("Phase 2: bulk_eod ...")
    _warm_bulk_eod()

    log.info("Phase 3: calendar/trends ...")
    _warm_calendar_trends(tickers)

    log.info("Bulk: calendar/earnings ...")
    _warm_calendar_earnings(tickers)

    if not args.skip_fundamentals:
        log.info("Per-ticker: fundamentals (24h TTL) ...")
        _warm_fundamentals(tickers)

    if not args.skip_insider:
        log.info("Per-ticker: insider transactions (top 200) ...")
        _warm_insider_summary(tickers, limit=200)

    _duration = time.time() - overall_t0
    log.info("=" * 60)
    log.info(f"Done in {_duration:.0f}s. Cache is warm for the next scan.")
    log.info("=" * 60)

    try:
        from lib.autorun_reporter import report
        report("enrich-nightly", "success",
               summary=f"Warmed {len(tickers)} tickers across bulk_eod + trends + earnings"
                       + ("" if args.skip_fundamentals else " + fundamentals")
                       + ("" if args.skip_insider else " + insider"),
               duration_sec=_duration,
               details={"universe": args.universe, "tickers": len(tickers)})
    except Exception:
        pass


if __name__ == "__main__":
    main()
