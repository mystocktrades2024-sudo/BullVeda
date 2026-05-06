"""
Post-Earnings Announcement Drift (PEAD) Strategy Module
========================================================
Exploits the well-documented tendency for stocks to continue drifting in the
direction of an earnings surprise for 10-20 trading days after announcement.
Historical win rate: 65-75%.

Setup family : Impulse Catalyst
Catalyst tier: T1
Hold period  : 10-15 days

Usage:
    from pead_strategy import scan_pead_candidates, score_pead, get_pead_trade_plan
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import requests
from data_fetcher import yf  # _YfStub: empty no-op (yfinance removed 2026-04-25)

log = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config" / "config.json"
CACHE_DIR = BASE_DIR / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Sector ETF mapping (mirrors data_fetcher._SECTOR_ETFS)
_SECTOR_ETFS = {
    "XLK": "Technology", "XLF": "Financials", "XLV": "Healthcare",
    "XLE": "Energy", "XLI": "Industrials", "XLB": "Materials",
    "XLRE": "Real Estate", "XLU": "Utilities", "XLC": "Communication Services",
    "XLP": "Consumer Staples", "XLY": "Consumer Discretionary",
}

# Reverse map: sector name -> ETF ticker
_SECTOR_TO_ETF = {v: k for k, v in _SECTOR_ETFS.items()}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return json.load(f)


def _cache_read(key: str, ttl_seconds: int) -> dict | None:
    fp = CACHE_DIR / f"_cache_{key}.json"
    try:
        if fp.exists():
            age = time.time() - fp.stat().st_mtime
            if age < ttl_seconds:
                return json.loads(fp.read_text())
    except Exception:
        pass
    return None


def _cache_write(key: str, data) -> None:
    try:
        fp = CACHE_DIR / f"_cache_{key}.json"
        fp.write_text(json.dumps(data, default=str))
    except Exception:
        pass


def _fmp_api_key() -> str:
    cfg = _load_config()
    return cfg.get("data_sources", {}).get("fmp_api_key", "")


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def _rs_rank(ticker_close: pd.Series, spy_close: pd.Series, period: int = 63) -> int:
    """Compute IBD-style relative strength rank (0-100) vs SPY."""
    if len(ticker_close) < period or len(spy_close) < period:
        return 50
    t_ret = (ticker_close.iloc[-1] / ticker_close.iloc[-period]) - 1
    s_ret = (spy_close.iloc[-1] / spy_close.iloc[-period]) - 1
    rs_ratio = (1 + t_ret) / (1 + s_ret) if (1 + s_ret) != 0 else 1.0
    if np.isnan(rs_ratio):
        return 50
    return min(100, max(0, int((rs_ratio - 0.8) / 0.4 * 100)))


# ── FMP Earnings Calendar / Surprise ────────────────────────────────────────

def _fetch_fmp_earnings_surprises(ticker: str) -> list[dict]:
    """
    Fetch earnings surprise history from FMP for a single ticker.
    Returns list of dicts with: date, epsActual, epsEstimate, epsSurprisePct,
    revenueActual, revenueEstimate, revSurprisePct.
    """
    cache_key = f"pead_fmp_surprise_{ticker}"
    cached = _cache_read(cache_key, ttl_seconds=86400)
    if cached is not None:
        return cached

    api_key = _fmp_api_key()
    if not api_key:
        return []

    base = "https://financialmodelingprep.com/stable"
    results = []

    try:
        # Earnings surprises endpoint
        r = requests.get(
            f"{base}/earnings-surprises",
            params={"symbol": ticker, "apikey": api_key},
            timeout=10,
        )
        if r.status_code == 200:
            data = r.json()
            for d in (data or []):
                eps_actual = d.get("actualEarningResult")
                eps_est = d.get("estimatedEarning")
                rev_actual = d.get("actualRevenue") or d.get("revenue")
                rev_est = d.get("estimatedRevenue") or d.get("revenueEstimated")

                eps_surprise_pct = None
                if eps_actual is not None and eps_est is not None and eps_est != 0:
                    eps_surprise_pct = round(((eps_actual - eps_est) / abs(eps_est)) * 100, 2)

                rev_surprise_pct = None
                if rev_actual is not None and rev_est is not None and rev_est != 0:
                    rev_surprise_pct = round(((rev_actual - rev_est) / abs(rev_est)) * 100, 2)

                results.append({
                    "date": d.get("date", ""),
                    "eps_actual": eps_actual,
                    "eps_estimate": eps_est,
                    "eps_surprise_pct": eps_surprise_pct,
                    "rev_actual": rev_actual,
                    "rev_estimate": rev_est,
                    "rev_surprise_pct": rev_surprise_pct,
                })
    except Exception as e:
        log.debug(f"FMP earnings surprise {ticker}: {e}")

    _cache_write(cache_key, results)
    return results


def _fetch_fmp_earnings_calendar(from_date: str, to_date: str) -> list[dict]:
    """
    Fetch earnings calendar from FMP for a date range.
    Returns list of dicts with: symbol, date, eps, epsEstimated, revenue, revenueEstimated.
    """
    cache_key = f"pead_fmp_cal_{from_date}_{to_date}"
    cached = _cache_read(cache_key, ttl_seconds=3600)
    if cached is not None:
        return cached

    api_key = _fmp_api_key()
    if not api_key:
        log.warning("PEAD: No FMP API key configured")
        return []

    base = "https://financialmodelingprep.com/stable"
    results = []

    try:
        r = requests.get(
            f"{base}/earning-calendar-confirmed",
            params={"from": from_date, "to": to_date, "apikey": api_key},
            timeout=15,
        )
        if r.status_code == 200:
            results = r.json() or []
        else:
            # Fallback: standard earnings calendar
            r = requests.get(
                f"{base}/earning_calendar",
                params={"from": from_date, "to": to_date, "apikey": api_key},
                timeout=15,
            )
            if r.status_code == 200:
                results = r.json() or []
    except Exception as e:
        log.debug(f"FMP earnings calendar: {e}")

    _cache_write(cache_key, results)
    return results


def _fetch_yf_earnings_surprise(ticker: str) -> dict | None:
    """
    Fallback: get most recent earnings surprise from yfinance.
    Returns dict with eps_surprise_pct and date, or None.
    """
    try:
        t = yf.Ticker(ticker)
        hist = getattr(t, "earnings_history", None)
        if hist is None or (isinstance(hist, pd.DataFrame) and hist.empty):
            hist = getattr(t, "quarterly_earnings", None)

        if hist is None or (isinstance(hist, pd.DataFrame) and hist.empty):
            return None

        if isinstance(hist, pd.DataFrame) and not hist.empty:
            row = hist.iloc[-1]
            if "Surprise(%)" in hist.columns:
                return {
                    "eps_surprise_pct": float(row["Surprise(%)"]),
                    "date": str(row.name) if hasattr(row, "name") else "",
                }
            # Try computing from Actual vs Estimate columns
            actual_col = [c for c in hist.columns if "actual" in c.lower() or c == "Actual"]
            est_col = [c for c in hist.columns if "estimat" in c.lower() or c == "Estimate"]
            if actual_col and est_col:
                actual = float(row[actual_col[0]])
                est = float(row[est_col[0]])
                if est != 0:
                    return {
                        "eps_surprise_pct": round(((actual - est) / abs(est)) * 100, 2),
                        "date": str(row.name) if hasattr(row, "name") else "",
                    }
    except Exception as e:
        log.debug(f"yfinance earnings surprise {ticker}: {e}")
    return None


def _get_ohlcv(ticker: str, period: str = "6mo") -> pd.DataFrame | None:
    """Load OHLCV from data_archive first, fallback to yfinance."""
    try:
        from data_archive import load_ticker
        df = load_ticker(ticker)
        if df is not None and len(df) > 20:
            return df
    except ImportError:
        pass

    try:
        df = yf.download(ticker, period=period, interval="1d", progress=False, auto_adjust=True)
        if df is not None and len(df) > 20:
            # Flatten multi-level columns if present
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            return df
    except Exception as e:
        log.debug(f"yfinance OHLCV {ticker}: {e}")
    return None


def _get_spy_close(period: str = "6mo") -> pd.Series | None:
    """Fetch SPY close series for RS calculations."""
    cache_key = "pead_spy_close"
    try:
        spy = yf.download("SPY", period=period, interval="1d", progress=False, auto_adjust=True)
        if spy is not None and len(spy) > 20:
            if isinstance(spy.columns, pd.MultiIndex):
                spy.columns = spy.columns.get_level_values(0)
            return spy["Close"]
    except Exception:
        pass
    return None


def _sector_etf_trending_up(sector: str) -> bool:
    """Check if the sector ETF is trending up (price > EMA21)."""
    etf = _SECTOR_TO_ETF.get(sector)
    if not etf:
        return False
    try:
        df = yf.download(etf, period="3mo", interval="1d", progress=False, auto_adjust=True)
        if df is None or len(df) < 25:
            return False
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        close = df["Close"]
        ema21 = _ema(close, 21)
        return float(close.iloc[-1]) > float(ema21.iloc[-1])
    except Exception:
        return False


# ── Core Functions ───────────────────────────────────────────────────────────

def scan_pead_candidates(days_lookback: int = 30) -> list[dict]:
    """
    Scan for Post-Earnings Announcement Drift candidates.

    Finds stocks that reported earnings in the last `days_lookback` days with:
      - EPS surprise >= 10%
      - Revenue surprise >= 3%
      - Post-earnings move < 15% (not too late)
      - Ideally pulling back toward the gap fill zone

    Returns list of dicts:
        ticker, earnings_date, eps_surprise_pct, rev_surprise_pct,
        gap_pct, current_price, entry_zone, stop, target, score
    """
    log.info(f"PEAD scan: looking back {days_lookback} days")

    to_date = datetime.now().strftime("%Y-%m-%d")
    from_date = (datetime.now() - timedelta(days=days_lookback)).strftime("%Y-%m-%d")

    # Step 1: Get earnings calendar from FMP
    calendar = _fetch_fmp_earnings_calendar(from_date, to_date)

    # Collect unique tickers that reported
    reported_tickers = set()
    cal_by_ticker = {}
    for entry in calendar:
        sym = entry.get("symbol", "")
        if sym and sym.isalpha() and len(sym) <= 5:
            reported_tickers.add(sym)
            # Keep the most recent earnings entry per ticker
            existing = cal_by_ticker.get(sym)
            entry_date = entry.get("date", "")
            if not existing or entry_date > existing.get("date", ""):
                cal_by_ticker[sym] = entry

    if not reported_tickers:
        # Fallback 1: scan cache/last_bundle.json for tickers with recent earnings
        log.info("PEAD: No FMP calendar data, trying last_bundle.json fallback")
        bundle_path = BASE_DIR / "cache" / "last_bundle.json"
        if bundle_path.exists():
            try:
                with open(bundle_path) as _bf:
                    bundle = json.load(_bf)
                all_scored = bundle.get("all_scored", [])
                for item in all_scored:
                    earn = item.get("earnings", {})
                    earn_date_str = earn.get("earnings_date")
                    if not earn_date_str:
                        continue
                    try:
                        earn_dt = datetime.strptime(str(earn_date_str)[:10], "%Y-%m-%d")
                        # Check if earnings were in the past (within lookback window)
                        days_ago = (datetime.now() - earn_dt).days
                        if 0 < days_ago <= days_lookback:
                            ticker_sym = item.get("ticker", "")
                            if ticker_sym and ticker_sym.isalpha() and len(ticker_sym) <= 5:
                                reported_tickers.add(ticker_sym)
                                if ticker_sym not in cal_by_ticker:
                                    cal_by_ticker[ticker_sym] = {
                                        "symbol": ticker_sym,
                                        "date": str(earn_date_str)[:10],
                                    }
                    except (ValueError, TypeError):
                        continue
                if reported_tickers:
                    log.info(f"PEAD: Found {len(reported_tickers)} tickers with recent earnings from last_bundle.json")
            except (json.JSONDecodeError, KeyError) as e:
                log.debug(f"PEAD: last_bundle.json parse error: {e}")

    if not reported_tickers:
        # Fallback 2: use top RS stocks and check earnings beat rate via data_fetcher
        log.info("PEAD: No bundle data, falling back to top RS stocks + beat rate check")
        try:
            bundle_path = BASE_DIR / "cache" / "last_bundle.json"
            if bundle_path.exists():
                with open(bundle_path) as _bf:
                    bundle = json.load(_bf)
                all_scored = bundle.get("all_scored", [])
                # Pick top 50 by RS rank, then check earnings beat rate
                top_rs = sorted(all_scored, key=lambda x: x.get("rs_rank", 0), reverse=True)[:50]
                for item in top_rs:
                    ticker_sym = item.get("ticker", "")
                    if not ticker_sym or not ticker_sym.isalpha():
                        continue
                    try:
                        from data_fetcher import get_earnings_beat_rate
                        beat = get_earnings_beat_rate(ticker_sym)
                        if beat.get("beat_rate") is not None and beat["beat_rate"] >= 0.75:
                            reported_tickers.add(ticker_sym)
                            if len(reported_tickers) >= 30:
                                break
                    except Exception:
                        continue
                if reported_tickers:
                    log.info(f"PEAD: Found {len(reported_tickers)} high-beat-rate tickers via RS fallback")
        except Exception as e:
            log.debug(f"PEAD: RS fallback error: {e}")

    if not reported_tickers:
        # Final fallback: broad universe scan
        log.info("PEAD: All fallbacks exhausted, using broad universe scan")
        try:
            from data_fetcher import get_sp500
            reported_tickers = set(get_sp500()[:200])
        except ImportError:
            log.warning("PEAD: Could not load universe")
            return []

    log.info(f"PEAD: checking {len(reported_tickers)} tickers with recent earnings")

    candidates = []
    spy_close = _get_spy_close()

    for ticker in sorted(reported_tickers):
        try:
            # Get earnings surprise data
            surprises = _fetch_fmp_earnings_surprises(ticker)
            if not surprises:
                continue

            # Find the most recent surprise within our lookback window
            latest = None
            for s in surprises:
                s_date = s.get("date", "")
                if s_date and from_date <= s_date <= to_date:
                    if not latest or s_date > latest["date"]:
                        latest = s
            if not latest:
                # Check calendar entry date + yfinance fallback
                cal_entry = cal_by_ticker.get(ticker)
                if cal_entry:
                    yf_surprise = _fetch_yf_earnings_surprise(ticker)
                    if yf_surprise and yf_surprise.get("eps_surprise_pct") is not None:
                        latest = {
                            "date": cal_entry.get("date", ""),
                            "eps_surprise_pct": yf_surprise["eps_surprise_pct"],
                            "rev_surprise_pct": None,
                        }
                if not latest:
                    continue

            eps_surp = latest.get("eps_surprise_pct")
            rev_surp = latest.get("rev_surprise_pct")
            earnings_date = latest.get("date", "")

            # Filter: EPS surprise >= 10%
            if eps_surp is None or eps_surp < 10.0:
                continue

            # Filter: Revenue surprise >= 3% (skip if unavailable)
            if rev_surp is not None and rev_surp < 3.0:
                continue

            # Get OHLCV to evaluate price action
            df = _get_ohlcv(ticker)
            if df is None or len(df) < 30:
                continue

            close_col = "Close"
            high_col = "High"
            low_col = "Low"
            vol_col = "Volume"

            current_price = float(df[close_col].iloc[-1])

            # Find the earnings date in OHLCV to compute gap
            earnings_dt = pd.Timestamp(earnings_date)
            # Find the trading day on or after earnings
            mask_after = df.index >= earnings_dt
            mask_before = df.index < earnings_dt
            if not mask_after.any() or not mask_before.any():
                continue

            post_earnings_idx = df.index[mask_after][0]
            pre_earnings_close = float(df[close_col].loc[df.index[mask_before][-1]])
            post_earnings_open = float(df["Open"].loc[post_earnings_idx])
            post_earnings_high = float(df[high_col].loc[post_earnings_idx:].max())

            # Gap percentage
            gap_pct = round(((post_earnings_open - pre_earnings_close) / pre_earnings_close) * 100, 2)

            # Check: hasn't already run 15%+ from pre-earnings close
            total_move_pct = ((current_price - pre_earnings_close) / pre_earnings_close) * 100
            if total_move_pct > 15.0:
                continue

            # Compute entry zone, stop, target
            gap_midpoint = pre_earnings_close + (post_earnings_open - pre_earnings_close) * 0.5
            ema8 = _ema(df[close_col], 8)
            ema8_val = float(ema8.iloc[-1])

            # Entry: pullback to 50% of gap or EMA8 touch (whichever is higher for longs)
            entry_zone = round(max(gap_midpoint, ema8_val), 2)

            # Stop: below pre-earnings close (the gap must hold)
            atr = _atr(df[high_col], df[low_col], df[close_col])
            atr_val = float(atr.iloc[-1]) if not np.isnan(atr.iloc[-1]) else current_price * 0.02
            stop = round(pre_earnings_close - atr_val * 0.25, 2)

            # Target 1: post-earnings high
            target1 = round(post_earnings_high, 2)
            # Target 2: 2x the earnings gap
            target2 = round(pre_earnings_close + (post_earnings_open - pre_earnings_close) * 2, 2)

            # Quick R:R check
            risk = entry_zone - stop
            reward = target1 - entry_zone
            if risk <= 0 or reward / risk < 1.5:
                continue

            # Score the candidate
            earnings_data = {
                "eps_surprise_pct": eps_surp,
                "rev_surprise_pct": rev_surp,
                "earnings_date": earnings_date,
                "pre_earnings_close": pre_earnings_close,
                "post_earnings_open": post_earnings_open,
                "post_earnings_high": post_earnings_high,
            }
            pead_score = score_pead(ticker, earnings_data, df, spy_close=spy_close)

            candidates.append({
                "ticker": ticker,
                "earnings_date": earnings_date,
                "eps_surprise_pct": eps_surp,
                "rev_surprise_pct": rev_surp if rev_surp is not None else "N/A",
                "gap_pct": gap_pct,
                "total_move_pct": round(total_move_pct, 2),
                "current_price": round(current_price, 2),
                "entry_zone": entry_zone,
                "stop": stop,
                "target1": target1,
                "target2": target2,
                "score": pead_score,
            })

        except Exception as e:
            log.debug(f"PEAD scan {ticker}: {e}")
            continue

    # Sort by score descending
    candidates.sort(key=lambda x: x["score"], reverse=True)
    log.info(f"PEAD scan complete: {len(candidates)} candidates found")
    return candidates


def score_pead(
    ticker: str,
    earnings_data: dict,
    df: pd.DataFrame,
    spy_close: pd.Series | None = None,
) -> int:
    """
    Score a PEAD candidate 0-100.

    Scoring breakdown:
      - EPS surprise magnitude   (20 pts): 10-20% = 10, 20%+ = 20
      - Revenue surprise          (15 pts): 3-10% = 8, 10%+ = 15
      - Post-earnings volume      (15 pts): day-of volume >= 2x avg = 15
      - Price action              (20 pts): holding above gap = 20,
                                            pulled back to fill = 15, broke gap = 5
      - RS rank                   (15 pts): >= 80 = 15, >= 70 = 10
      - Sector momentum           (15 pts): sector ETF trending up = 15

    Args:
        ticker: stock symbol
        earnings_data: dict with eps_surprise_pct, rev_surprise_pct,
                       earnings_date, pre_earnings_close, post_earnings_open,
                       post_earnings_high
        df: OHLCV DataFrame for the ticker
        spy_close: optional SPY close series for RS calculation

    Returns:
        int score 0-100
    """
    score = 0

    # ── 1. EPS surprise magnitude (20 pts) ──
    eps_surp = earnings_data.get("eps_surprise_pct", 0) or 0
    if eps_surp >= 20:
        score += 20
    elif eps_surp >= 10:
        score += 10

    # ── 2. Revenue surprise (15 pts) ──
    rev_surp = earnings_data.get("rev_surprise_pct")
    if rev_surp is not None:
        if rev_surp >= 10:
            score += 15
        elif rev_surp >= 3:
            score += 8

    # ── 3. Post-earnings volume (15 pts) ──
    try:
        earnings_dt = pd.Timestamp(earnings_data.get("earnings_date", ""))
        mask_after = df.index >= earnings_dt
        if mask_after.any():
            earn_day_idx = df.index[mask_after][0]
            earn_day_vol = float(df["Volume"].loc[earn_day_idx])
            # Average volume over 20 days before earnings
            mask_before = df.index < earnings_dt
            if mask_before.any():
                pre_vol = df["Volume"].loc[mask_before].tail(20).mean()
                if pre_vol > 0 and earn_day_vol >= 2 * pre_vol:
                    score += 15
                elif pre_vol > 0 and earn_day_vol >= 1.5 * pre_vol:
                    score += 8
    except Exception:
        pass

    # ── 4. Price action (20 pts) ──
    try:
        pre_close = earnings_data.get("pre_earnings_close", 0)
        post_open = earnings_data.get("post_earnings_open", 0)
        current = float(df["Close"].iloc[-1])
        gap_top = max(pre_close, post_open)
        gap_bottom = min(pre_close, post_open)
        gap_mid = (gap_top + gap_bottom) / 2

        if current >= post_open:
            # Holding above gap — strongest signal
            score += 20
        elif current >= gap_mid:
            # Pulled back to fill zone — ideal entry
            score += 15
        elif current >= pre_close:
            # Still above pre-earnings close but gap mostly filled
            score += 10
        else:
            # Broke below pre-earnings close — weakest
            score += 5
    except Exception:
        pass

    # ── 5. RS rank (15 pts) ──
    try:
        if spy_close is None:
            spy_close = _get_spy_close()

        if spy_close is not None and len(df) >= 63:
            close = df["Close"]
            rs = _rs_rank(close, spy_close, period=63)
            if rs >= 80:
                score += 15
            elif rs >= 70:
                score += 10
            elif rs >= 60:
                score += 5
    except Exception:
        pass

    # ── 6. Sector momentum (15 pts) ──
    try:
        from data_fetcher import get_fmp_data
        fmp = get_fmp_data(ticker)
        sector = fmp.get("sector", "")
        if sector and _sector_etf_trending_up(sector):
            score += 15
    except Exception:
        # Fallback: try yfinance for sector info
        try:
            info = yf.Ticker(ticker).info or {}
            sector = info.get("sector", "")
            if sector and _sector_etf_trending_up(sector):
                score += 15
        except Exception:
            pass

    return min(100, score)


def get_pead_trade_plan(
    ticker: str,
    df: pd.DataFrame,
    earnings_data: dict,
) -> dict:
    """
    Generate a complete trade plan for a PEAD setup.

    Entry : pullback to 50% of the earnings gap, or EMA8 touch
    Stop  : below pre-earnings close (the gap must hold)
    T1    : post-earnings high
    T2    : 2x the earnings gap
    Hold  : 10-15 days
    Family: Impulse Catalyst
    Tier  : T1

    Args:
        ticker: stock symbol
        df: OHLCV DataFrame
        earnings_data: dict with pre_earnings_close, post_earnings_open,
                       post_earnings_high, eps_surprise_pct, etc.

    Returns:
        dict with full trade plan details
    """
    pre_close = earnings_data["pre_earnings_close"]
    post_open = earnings_data["post_earnings_open"]
    post_high = earnings_data["post_earnings_high"]
    current_price = float(df["Close"].iloc[-1])

    # Gap math
    gap_size = post_open - pre_close
    gap_midpoint = pre_close + gap_size * 0.5

    # EMA8 for entry reference
    ema8 = _ema(df["Close"], 8)
    ema8_val = float(ema8.iloc[-1])

    # Entry: pullback to 50% of the gap or EMA8, whichever is higher (for longs)
    if gap_size > 0:
        entry = round(max(gap_midpoint, ema8_val), 2)
    else:
        # Negative gap (earnings miss causing down-gap) — not a standard PEAD long
        entry = round(min(gap_midpoint, ema8_val), 2)

    # Stop: below pre-earnings close with a small ATR buffer
    atr = _atr(df["High"], df["Low"], df["Close"])
    atr_val = float(atr.iloc[-1]) if not np.isnan(atr.iloc[-1]) else current_price * 0.02
    stop = round(pre_close - atr_val * 0.25, 2)

    # Target 1: post-earnings high
    target1 = round(post_high, 2)

    # Target 2: 2x the earnings gap from pre-earnings close
    target2 = round(pre_close + gap_size * 2, 2)

    # Risk / reward
    risk = entry - stop
    reward1 = target1 - entry
    reward2 = target2 - entry
    rr1 = round(reward1 / risk, 2) if risk > 0 else 0
    rr2 = round(reward2 / risk, 2) if risk > 0 else 0

    # Position sizing hint (1% risk model)
    risk_pct = round((risk / entry) * 100, 2) if entry > 0 else 0

    # Days since earnings
    earnings_dt = pd.Timestamp(earnings_data.get("earnings_date", ""))
    days_since = 0
    if not pd.isna(earnings_dt):
        days_since = (pd.Timestamp(datetime.now()) - earnings_dt).days

    # Determine trade quality
    quality = "FRESH" if days_since <= 5 else "PULLBACK" if days_since <= 15 else "EXTENDED"
    if current_price < pre_close:
        quality = "BROKEN_GAP"

    return {
        "ticker": ticker,
        "setup_type": "PEAD",
        "setup_family": "Impulse Catalyst",
        "catalyst_tier": "T1",

        # Key levels
        "entry": entry,
        "stop": stop,
        "target1": target1,
        "target2": target2,
        "current_price": round(current_price, 2),

        # Risk metrics
        "risk_per_share": round(risk, 2),
        "risk_pct": risk_pct,
        "rr_t1": rr1,
        "rr_t2": rr2,

        # Earnings context
        "earnings_date": str(earnings_data.get("earnings_date", "")),
        "days_since_earnings": days_since,
        "eps_surprise_pct": earnings_data.get("eps_surprise_pct"),
        "rev_surprise_pct": earnings_data.get("rev_surprise_pct"),
        "pre_earnings_close": round(pre_close, 2),
        "post_earnings_open": round(post_open, 2),
        "post_earnings_high": round(post_high, 2),
        "gap_pct": round((gap_size / pre_close) * 100, 2) if pre_close > 0 else 0,

        # Trade management
        "hold_period": "10-15 days",
        "partial_exit": f"50% at T1 ({target1}), move stop to entry",
        "trail_after_t1": f"Trail 1.0x ATR ({round(atr_val, 2)}) after T1 hit",
        "time_stop": "Exit by day 15 if flat",
        "entry_quality": quality,
        "ema8": round(ema8_val, 2),
        "atr14": round(atr_val, 2),

        # Notes
        "thesis": (
            f"{ticker} beat EPS by {earnings_data.get('eps_surprise_pct', 'N/A')}% "
            f"on {earnings_data.get('earnings_date', '?')}. "
            f"PEAD drift expected for 10-20 days post-announcement. "
            f"Entry on pullback to gap fill zone or EMA8 touch."
        ),
    }


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    print("=" * 72)
    print("  PEAD Strategy Scanner — Post-Earnings Announcement Drift")
    print("=" * 72)
    print()

    days = 30
    if len(sys.argv) > 1:
        try:
            days = int(sys.argv[1])
        except ValueError:
            pass

    print(f"Scanning for earnings surprises in the last {days} days...")
    print()

    candidates = scan_pead_candidates(days_lookback=days)

    if not candidates:
        print("No PEAD candidates found.")
        sys.exit(0)

    print(f"Found {len(candidates)} PEAD candidate(s):\n")
    print(f"{'Ticker':<8} {'Date':<12} {'EPS%':>7} {'Rev%':>7} {'Gap%':>7} "
          f"{'Move%':>7} {'Price':>8} {'Entry':>8} {'Stop':>8} {'T1':>8} {'Score':>6}")
    print("-" * 100)

    for c in candidates:
        rev_str = f"{c['rev_surprise_pct']:>7.1f}" if isinstance(c["rev_surprise_pct"], (int, float)) else f"{'N/A':>7}"
        print(
            f"{c['ticker']:<8} {c['earnings_date']:<12} {c['eps_surprise_pct']:>7.1f} "
            f"{rev_str} {c['gap_pct']:>7.1f} {c['total_move_pct']:>7.1f} "
            f"{c['current_price']:>8.2f} {c['entry_zone']:>8.2f} {c['stop']:>8.2f} "
            f"{c['target1']:>8.2f} {c['score']:>6}"
        )

    # Print detailed trade plans for top 5
    print("\n" + "=" * 72)
    print("  Detailed Trade Plans (Top 5)")
    print("=" * 72)

    for c in candidates[:5]:
        ticker = c["ticker"]
        df = _get_ohlcv(ticker)
        if df is None:
            continue

        earnings_data = {
            "earnings_date": c["earnings_date"],
            "eps_surprise_pct": c["eps_surprise_pct"],
            "rev_surprise_pct": c["rev_surprise_pct"] if isinstance(c["rev_surprise_pct"], (int, float)) else None,
            "pre_earnings_close": c["stop"] + 0.01,  # approximate; recalculated inside
        }

        # Re-derive pre_earnings_close and post_earnings_open from df
        try:
            earnings_dt = pd.Timestamp(c["earnings_date"])
            mask_before = df.index < earnings_dt
            mask_after = df.index >= earnings_dt
            if mask_before.any() and mask_after.any():
                pre_close = float(df["Close"].loc[df.index[mask_before][-1]])
                post_idx = df.index[mask_after][0]
                post_open = float(df["Open"].loc[post_idx])
                post_high = float(df["High"].loc[post_idx:].max())

                earnings_data["pre_earnings_close"] = pre_close
                earnings_data["post_earnings_open"] = post_open
                earnings_data["post_earnings_high"] = post_high

                plan = get_pead_trade_plan(ticker, df, earnings_data)
                print(f"\n{'─' * 60}")
                print(f"  {plan['ticker']} — PEAD Trade Plan")
                print(f"{'─' * 60}")
                print(f"  Setup       : {plan['setup_type']} ({plan['setup_family']}, {plan['catalyst_tier']})")
                print(f"  Quality     : {plan['entry_quality']}")
                print(f"  Earnings    : {plan['earnings_date']} ({plan['days_since_earnings']}d ago)")
                print(f"  EPS surprise: {plan['eps_surprise_pct']}%  |  Rev surprise: {plan.get('rev_surprise_pct', 'N/A')}%")
                print(f"  Gap         : {plan['gap_pct']}%")
                print()
                print(f"  Current     : ${plan['current_price']}")
                print(f"  Entry       : ${plan['entry']}  (EMA8: ${plan['ema8']})")
                print(f"  Stop        : ${plan['stop']}  (risk: ${plan['risk_per_share']} = {plan['risk_pct']}%)")
                print(f"  Target 1    : ${plan['target1']}  (R:R {plan['rr_t1']})")
                print(f"  Target 2    : ${plan['target2']}  (R:R {plan['rr_t2']})")
                print()
                print(f"  Hold period : {plan['hold_period']}")
                print(f"  Partial exit: {plan['partial_exit']}")
                print(f"  Trail       : {plan['trail_after_t1']}")
                print(f"  Time stop   : {plan['time_stop']}")
                print()
                print(f"  Thesis: {plan['thesis']}")
        except Exception as e:
            print(f"\n  {ticker}: Could not generate trade plan — {e}")

    print()
