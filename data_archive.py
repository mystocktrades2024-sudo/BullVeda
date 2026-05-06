"""
data_archive.py — Persistent historical data store for fast backtesting.

Downloads OHLCV data once from Polygon.io, stores as Parquet files.
Backtests read from archive (< 2 seconds) instead of re-downloading (60+ min).

Usage:
    python3 data_archive.py download          # Download/update all tickers (run once, then weekly)
    python3 data_archive.py status            # Show what's cached
    python3 data_archive.py load AAPL         # Load a ticker into DataFrame

Storage: data/ohlcv/{ticker}.parquet  (one file per ticker, ~50KB each)
         data/universe.json           (S&P 500 + Russell 1000 ticker list)
         data/spy.parquet             (SPY for regime calculation)
"""

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

log = logging.getLogger("swingtrade.archive")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
OHLCV_DIR = DATA_DIR / "ohlcv"
UNIVERSE_FILE = DATA_DIR / "universe.json"

OHLCV_DIR.mkdir(parents=True, exist_ok=True)


def _download_ticker(ticker: str, days: int = 750) -> bool:
    """Download daily OHLCV for one ticker from Polygon, save as Parquet."""
    from data_fetcher import get_polygon_ohlcv

    try:
        df = get_polygon_ohlcv(ticker, days=days, timespan="day", multiplier=1)
        if df is None or len(df) < 20:
            return False

        # Save as parquet (compact, fast to read)
        out_path = OHLCV_DIR / f"{ticker}.parquet"
        df.to_parquet(out_path, engine="pyarrow")
        return True
    except Exception as e:
        log.debug(f"  {ticker}: {e}")
        return False


def download_universe(days: int = 750, max_workers: int = 10):
    """
    Download full S&P 500 + Russell 1000 OHLCV history.
    750 days = ~3 years of daily bars.
    Skips tickers already downloaded today.
    """
    from data_fetcher import get_sp500, get_russell1000

    log.info("Building universe...")
    sp500 = get_sp500()
    russell = []
    try:
        russell = get_russell1000()
    except Exception:
        log.warning("Russell 1000 fetch failed, using S&P 500 only")

    # Merge and deduplicate
    all_tickers = list(dict.fromkeys(sp500 + russell))  # preserves order, dedupes

    # Always include SPY, QQQ for regime
    for etf in ["SPY", "QQQ", "IWM", "VIX"]:
        if etf not in all_tickers:
            all_tickers.append(etf)

    log.info(f"Universe: {len(all_tickers)} tickers (S&P: {len(sp500)}, Russell: {len(russell)})")

    # Save universe list
    UNIVERSE_FILE.write_text(json.dumps({
        "tickers": all_tickers,
        "sp500_count": len(sp500),
        "russell_count": len(russell),
        "updated": time.strftime("%Y-%m-%d %H:%M"),
    }, indent=2))

    # Check which tickers need downloading
    today = time.strftime("%Y-%m-%d")
    need_download = []
    already_cached = 0
    for ticker in all_tickers:
        parquet_path = OHLCV_DIR / f"{ticker}.parquet"
        if parquet_path.exists():
            # Skip if downloaded today (check mtime)
            mtime = time.strftime("%Y-%m-%d", time.localtime(parquet_path.stat().st_mtime))
            if mtime == today:
                already_cached += 1
                continue
        need_download.append(ticker)

    log.info(f"Already cached today: {already_cached} | Need download: {len(need_download)}")

    if not need_download:
        log.info("All tickers up to date!")
        return

    # Download in parallel
    success = 0
    failed = 0
    start = time.time()

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_download_ticker, t, days): t for t in need_download}
        for i, fut in enumerate(as_completed(futures)):
            ticker = futures[fut]
            try:
                ok = fut.result()
                if ok:
                    success += 1
                else:
                    failed += 1
            except Exception:
                failed += 1

            if (i + 1) % 50 == 0:
                elapsed = time.time() - start
                rate = (i + 1) / elapsed * 60
                remaining = (len(need_download) - i - 1) / rate if rate > 0 else 0
                log.info(f"  Progress: {i+1}/{len(need_download)} "
                         f"({success} OK, {failed} failed) "
                         f"~{remaining:.0f} min remaining")

    elapsed = time.time() - start
    log.info(f"Done! {success} downloaded, {failed} failed in {elapsed:.0f}s")
    log.info(f"Archive: {sum(1 for _ in OHLCV_DIR.glob('*.parquet'))} tickers, "
             f"{sum(f.stat().st_size for f in OHLCV_DIR.glob('*.parquet')) / 1e6:.0f} MB")


def delta_update(max_workers: int = 10):
    """
    Fast daily update — fetch latest bar via EODHD bulk_eod (1 call for all tickers)
    and append to existing Parquet files. ~5x faster than per-ticker eod() loops.
    """
    parquet_files = list(OHLCV_DIR.glob("*.parquet"))
    if not parquet_files:
        log.info("No archive found. Run 'download' first.")
        return

    log.info(f"Delta update: checking {len(parquet_files)} tickers for new bars...")
    start = time.time()
    updated = 0
    skipped = 0
    failed = 0

    # Pre-warm: bulk_eod for the entire US exchange in one call
    bulk_today: dict = {}
    try:
        import eodhd_client as _eod
        rows = _eod.bulk_eod(exchange="US")
        if isinstance(rows, list):
            for r in rows:
                code = (r.get("code") or "").upper()
                if code:
                    bulk_today[code] = r
            log.info(f"Bulk EOD pre-warm: {len(bulk_today)} tickers in one call")
    except Exception as e:
        log.debug(f"bulk_eod pre-warm failed (will fall back per-ticker): {e}")

    def _update_one(path):
        ticker = path.stem
        try:
            existing = pd.read_parquet(path, engine="pyarrow")
            if existing.empty:
                return "skip"

            if existing.index.tz is not None:
                existing.index = existing.index.tz_localize(None)

            last_date = existing.index[-1]
            today_str = time.strftime("%Y-%m-%d")
            if hasattr(last_date, 'strftime') and last_date.strftime("%Y-%m-%d") >= today_str:
                return "skip"

            new_data = None

            # Layer A: bulk_eod hit (cheap — already fetched)
            rec = bulk_today.get(ticker.upper())
            if rec:
                try:
                    new_data = pd.DataFrame([{
                        "Open":   float(rec.get("open", 0)),
                        "High":   float(rec.get("high", 0)),
                        "Low":    float(rec.get("low", 0)),
                        "Close":  float(rec.get("adjusted_close") or rec.get("close", 0)),
                        "Volume": float(rec.get("volume", 0)),
                    }], index=pd.DatetimeIndex([pd.to_datetime(rec.get("date"))]))
                except Exception:
                    new_data = None

            # Layer B: per-ticker EOD (only if bulk missed)
            if new_data is None or new_data.empty:
                try:
                    import eodhd_client as _eod2
                    from datetime import date as _d, timedelta as _td
                    from_date = (_d.today() - _td(days=5)).isoformat()
                    rows = _eod2.eod(ticker, from_date=from_date)
                    if rows:
                        df_new = pd.DataFrame(rows)
                        df_new["date"] = pd.to_datetime(df_new["date"])
                        df_new = df_new.set_index("date").sort_index()
                        df_new = df_new.rename(columns={
                            "open": "Open", "high": "High", "low": "Low",
                            "adjusted_close": "Close", "volume": "Volume",
                        })
                        cols = [c for c in ["Open","High","Low","Close","Volume"] if c in df_new.columns]
                        new_data = df_new[cols].astype(float, errors="ignore").dropna(how="all")
                except Exception:
                    pass
            if new_data is None or new_data.empty:
                return "fail"

            if new_data.index.tz is not None:
                new_data.index = new_data.index.tz_localize(None)

            # Keep only new bars (after last existing date)
            new_bars = new_data[new_data.index > last_date]
            if new_bars.empty:
                return "skip"

            # Align columns
            cols = [c for c in existing.columns if c in new_bars.columns]
            combined = pd.concat([existing[cols], new_bars[cols]])
            combined = combined[~combined.index.duplicated(keep='last')]
            combined.to_parquet(path, engine="pyarrow")
            return "ok"
        except Exception:
            return "fail"

    from concurrent.futures import ThreadPoolExecutor, as_completed
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_update_one, p): p for p in parquet_files}
        for fut in as_completed(futures):
            result = fut.result()
            if result == "ok":
                updated += 1
            elif result == "skip":
                skipped += 1
            else:
                failed += 1

    elapsed = time.time() - start
    log.info(f"Delta update done in {elapsed:.0f}s: {updated} updated, {skipped} already current, {failed} failed")


def load_ticker(ticker: str):
    """Load a ticker from the archive. Returns DataFrame or None."""
    path = OHLCV_DIR / f"{ticker}.parquet"
    if not path.exists():
        return None
    try:
        return pd.read_parquet(path, engine="pyarrow")
    except Exception:
        return None


def load_all(tickers=None):
    """Load multiple tickers from archive. Returns {ticker: df}."""
    if tickers is None:
        # Load universe
        if UNIVERSE_FILE.exists():
            tickers = json.loads(UNIVERSE_FILE.read_text()).get("tickers", [])
        else:
            tickers = [f.stem for f in OHLCV_DIR.glob("*.parquet")]

    result = {}
    for ticker in tickers:
        df = load_ticker(ticker)
        if df is not None:
            result[ticker] = df
    return result


def status():
    """Print archive status."""
    parquet_files = list(OHLCV_DIR.glob("*.parquet"))
    total_size = sum(f.stat().st_size for f in parquet_files) / 1e6

    print(f"\n{'='*50}")
    print(f"DATA ARCHIVE STATUS")
    print(f"{'='*50}")
    print(f"Location:  {OHLCV_DIR}")
    print(f"Tickers:   {len(parquet_files)}")
    print(f"Size:      {total_size:.0f} MB")

    if UNIVERSE_FILE.exists():
        u = json.loads(UNIVERSE_FILE.read_text())
        print(f"Universe:  {len(u.get('tickers', []))} tickers")
        print(f"Updated:   {u.get('updated', 'unknown')}")

    if parquet_files:
        # Check freshness
        newest = max(parquet_files, key=lambda f: f.stat().st_mtime)
        oldest = min(parquet_files, key=lambda f: f.stat().st_mtime)
        from datetime import datetime
        print(f"Newest:    {newest.stem} ({datetime.fromtimestamp(newest.stat().st_mtime).strftime('%Y-%m-%d %H:%M')})")
        print(f"Oldest:    {oldest.stem} ({datetime.fromtimestamp(oldest.stat().st_mtime).strftime('%Y-%m-%d %H:%M')})")

        # Sample: load one and show date range
        sample = load_ticker(parquet_files[0].stem)
        if sample is not None and len(sample) > 0:
            print(f"Date range: {sample.index[0].strftime('%Y-%m-%d')} to {sample.index[-1].strftime('%Y-%m-%d')}")
            print(f"Bars/ticker: ~{len(sample)}")

    print(f"{'='*50}")

    # Speed estimate
    if parquet_files:
        import time
        t0 = time.time()
        _ = load_all([f.stem for f in parquet_files[:100]])
        t1 = time.time()
        per_ticker = (t1 - t0) / min(100, len(parquet_files)) * 1000
        full_est = per_ticker * len(parquet_files) / 1000
        print(f"\nLoad speed: {per_ticker:.1f}ms per ticker")
        print(f"Full universe load: ~{full_est:.1f}s")
        print(f"(vs Polygon API download: ~60+ min)")


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    if cmd == "download":
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 750
        download_universe(days=days)
    elif cmd == "delta":
        delta_update()
    elif cmd == "status":
        status()
    elif cmd == "load":
        ticker = sys.argv[2].upper() if len(sys.argv) > 2 else "SPY"
        df = load_ticker(ticker)
        if df is not None:
            print(f"{ticker}: {len(df)} bars, {df.index[0].strftime('%Y-%m-%d')} to {df.index[-1].strftime('%Y-%m-%d')}")
            print(df.tail())
        else:
            print(f"{ticker}: not in archive")
    else:
        print(f"Usage: python3 data_archive.py [download|status|load TICKER]")
