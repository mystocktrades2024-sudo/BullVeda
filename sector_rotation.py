"""
sector_rotation.py — Sector Rotation strategy module for SwingTrade.

When a sector ETF breaks out of a consolidation pattern on volume, the top
relative-strength names in that sector tend to outperform for 1-3 weeks.
We identify the rotating sector and ride the leaders.

Family: Trend Continuation
Hold period: 7-14 days

Usage:
    python3 sector_rotation.py              # Scan for current candidates
    python3 sector_rotation.py scan         # Same as above
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

log = logging.getLogger("swingtrade.sector_rotation")

# ── Sector ETFs to monitor ───────────────────────────────────────────────────

SECTOR_ETFS = [
    "XLK", "XLF", "XLE", "XLV", "XLI", "XLB", "XLU", "XLC", "XLY", "XLP",
    "XBI", "SOXX", "XHB", "XRT",
]

# Map from sector ETF to representative component tickers.
# Used to find leaders when FINVIZ sector mapping is unavailable.
_ETF_COMPONENTS = {
    "XLK":  ["NVDA", "MSFT", "AAPL", "AMD", "INTC", "AVGO", "QCOM", "MU",
             "AMAT", "KLAC", "CRWD", "PANW", "ZS", "NET", "ADBE", "CRM",
             "ORCL", "NOW", "INTU", "SNPS", "CDNS", "FTNT"],
    "XLF":  ["JPM", "BAC", "WFC", "GS", "MS", "BLK", "V", "MA", "AXP",
             "C", "SCHW", "CB", "MMC", "PGR", "TFC", "USB"],
    "XLE":  ["XOM", "CVX", "COP", "EOG", "SLB", "MPC", "PSX", "VLO",
             "OXY", "HES", "DVN", "FANG", "HAL", "BKR"],
    "XLV":  ["LLY", "NVO", "ABBV", "BMY", "MRK", "AMGN", "PFE", "JNJ",
             "MDT", "UNH", "TMO", "ABT", "DHR", "ISRG", "BSX", "SYK"],
    "XLI":  ["AXON", "RTX", "LMT", "NOC", "GD", "CAT", "DE", "UNP",
             "GE", "HON", "BA", "MMM", "WM", "RSG", "FDX", "UPS"],
    "XLB":  ["NEM", "FCX", "NUE", "LIN", "APD", "SHW", "ECL", "DD",
             "VMC", "MLM", "CTVA", "DOW", "PPG", "ALB"],
    "XLU":  ["NEE", "SO", "DUK", "AEP", "D", "SRE", "EXC", "XEL",
             "ED", "WEC", "ES", "AWK", "ATO", "CMS"],
    "XLC":  ["META", "GOOGL", "GOOG", "NFLX", "DIS", "CMCSA", "T", "VZ",
             "SNAP", "PINS", "TTWO", "EA", "RBLX", "WBD"],
    "XLY":  ["AMZN", "TSLA", "HD", "MCD", "NKE", "DECK", "ONON", "CMG",
             "LOW", "TJX", "SBUX", "BKNG", "MAR", "RCL", "LULU"],
    "XLP":  ["PG", "KO", "PEP", "COST", "WMT", "PM", "MO", "CL",
             "MDLZ", "GIS", "KHC", "HSY", "STZ", "KDP", "SJM"],
    "XBI":  ["MRNA", "REGN", "VRTX", "BIIB", "SGEN", "ALNY", "BMRN",
             "IONS", "EXAS", "RARE", "NBIX", "PCVX", "CRNX", "SRPT"],
    "SOXX": ["NVDA", "AMD", "INTC", "AVGO", "QCOM", "MU", "AMAT", "KLAC",
             "MRVL", "ON", "NXPI", "TXN", "ADI", "MPWR", "MCHP", "LSCC"],
    "XHB":  ["DHI", "LEN", "PHM", "NVR", "TOL", "KBH", "MDC", "GRBK",
             "MAS", "SWK", "BLDR", "FBIN", "FBHS", "AWI"],
    "XRT":  ["AMZN", "TSLA", "HD", "LOW", "TJX", "ROST", "BBY", "DG",
             "DLTR", "ORLY", "AZO", "ULTA", "FIVE", "W", "ETSY"],
}


# ── Technical helpers ────────────────────────────────────────────────────────

def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period).mean()


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0).ewm(com=period - 1, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0.0)).ewm(com=period - 1, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _relative_strength_rank(ticker_close: pd.Series, spy_close: pd.Series,
                            period: int = 63) -> int:
    """Compute RS rank (0-100) of a stock vs SPY over `period` days."""
    if len(ticker_close) < period or len(spy_close) < period:
        return 50
    t_ret = (float(ticker_close.iloc[-1]) / float(ticker_close.iloc[-period])) - 1
    s_ret = (float(spy_close.iloc[-1]) / float(spy_close.iloc[-period])) - 1
    rs_ratio = (1 + t_ret) / (1 + s_ret) if (1 + s_ret) != 0 else 1.0
    if np.isnan(rs_ratio):
        return 50
    return min(100, max(0, int((rs_ratio - 0.8) / 0.4 * 100)))


# ── Core functions ───────────────────────────────────────────────────────────

def scan_sector_breakouts() -> list[dict]:
    """
    Monitor sector ETFs for breakouts above 20-day highs on elevated volume.

    For each ETF: check if it crossed above its 20-day high in the last 3 days
    on volume >= 1.3x its 20-day average.

    Returns list of dicts:
        {etf, breakout_date, volume_ratio, rs_vs_spy}
    """
    from data_fetcher import yf  # _YfStub (yfinance removed 2026-04-25)

    etf_list = SECTOR_ETFS + ["SPY"]
    log.info(f"Scanning {len(SECTOR_ETFS)} sector ETFs for breakouts...")

    try:
        raw = yf.download(etf_list, period="3mo", interval="1d",
                          progress=False, threads=False, auto_adjust=True)
        if raw.empty:
            log.warning("No data returned from yfinance for sector ETFs")
            return []
    except Exception as e:
        log.error(f"Failed to download sector ETF data: {e}")
        return []

    # Extract OHLCV DataFrames
    if isinstance(raw.columns, pd.MultiIndex):
        closes = raw["Close"]
        highs = raw["High"]
        volumes = raw["Volume"]
    else:
        closes = raw[["Close"]]
        highs = raw[["High"]]
        volumes = raw[["Volume"]]

    # SPY close for RS calculation
    spy_close = closes["SPY"].dropna() if "SPY" in closes.columns else None

    breakouts = []

    for etf in SECTOR_ETFS:
        try:
            if etf not in closes.columns:
                continue

            close = closes[etf].dropna()
            high = highs[etf].dropna()
            vol = volumes[etf].dropna()

            if len(close) < 25:
                continue

            # 20-day rolling high (excluding today)
            rolling_high_20 = high.shift(1).rolling(20).max()
            avg_vol_20 = vol.rolling(20).mean()

            # Check last 3 trading days for breakout
            for offset in range(0, 3):
                idx = -(1 + offset)
                if abs(idx) > len(close):
                    continue

                day_close = float(close.iloc[idx])
                day_high_20 = float(rolling_high_20.iloc[idx]) if not np.isnan(rolling_high_20.iloc[idx]) else None
                day_vol = float(vol.iloc[idx])
                day_avg_vol = float(avg_vol_20.iloc[idx]) if not np.isnan(avg_vol_20.iloc[idx]) else None

                if day_high_20 is None or day_avg_vol is None or day_avg_vol == 0:
                    continue

                vol_ratio = day_vol / day_avg_vol

                if day_close > day_high_20 and vol_ratio >= 1.3:
                    # Compute RS vs SPY
                    rs_vs_spy = 0.0
                    if spy_close is not None and len(spy_close) >= 63:
                        period = min(63, len(close) - 1)
                        t_ret = (float(close.iloc[-1]) / float(close.iloc[-period]) - 1) * 100
                        s_ret = (float(spy_close.iloc[-1]) / float(spy_close.iloc[-period]) - 1) * 100
                        rs_vs_spy = round(t_ret - s_ret, 2)

                    breakout_date = str(close.index[idx].date()) if hasattr(close.index[idx], "date") else str(close.index[idx])

                    breakouts.append({
                        "etf": etf,
                        "breakout_date": breakout_date,
                        "volume_ratio": round(vol_ratio, 2),
                        "rs_vs_spy": rs_vs_spy,
                        "price": round(day_close, 2),
                    })
                    break  # Only report most recent breakout per ETF

        except Exception as e:
            log.debug(f"Error scanning {etf}: {e}")

    breakouts.sort(key=lambda x: x["volume_ratio"], reverse=True)
    log.info(f"Found {len(breakouts)} sector breakouts")
    return breakouts


def get_sector_leaders(sector_etf: str, top_n: int = 3,
                       spy_close: Optional[pd.Series] = None) -> list[dict]:
    """
    Given a breaking-out sector ETF, find the top `top_n` stocks by RS rank.

    Uses the built-in component map and optionally FINVIZ bulk data for
    sector-to-ticker mapping. Filters: above EMA21, RS rank >= 70, score >= 65.

    Returns list of dicts:
        {ticker, rs_rank, score, setup_type}
    """
    from data_archive import load_ticker

    # Get SPY data if not provided
    if spy_close is None:
        spy_df = load_ticker("SPY")
        if spy_df is not None:
            spy_close = spy_df["Close"].squeeze().dropna()

    # Get component tickers for this ETF
    components = _ETF_COMPONENTS.get(sector_etf, [])

    # Try to augment from FINVIZ bulk data
    try:
        from data_fetcher import get_finviz_bulk
        finviz = get_finviz_bulk()
        if finviz:
            # FINVIZ data has sector info in the ticker data
            # The _TICKER_TO_SECTOR map in data_fetcher maps tickers to ETFs
            from data_fetcher import _TICKER_TO_SECTOR
            extra = [t for t, etf in _TICKER_TO_SECTOR.items()
                     if etf == sector_etf and t not in components]
            components = list(dict.fromkeys(components + extra))
    except Exception:
        pass

    if not components:
        log.warning(f"No component tickers found for {sector_etf}")
        return []

    candidates = []

    for ticker in components:
        try:
            df = load_ticker(ticker)
            if df is None or len(df) < 50:
                continue

            close = df["Close"].squeeze().dropna()
            price = float(close.iloc[-1])
            ema21 = float(_ema(close, 21).iloc[-1])

            # Filter: must be above EMA21
            if price <= ema21:
                continue

            # Compute RS rank
            rs_rank = 50
            if spy_close is not None:
                rs_rank = _relative_strength_rank(close, spy_close)

            # Filter: RS rank >= 70
            if rs_rank < 70:
                continue

            # Compute a quick composite score
            score = _quick_score(df, spy_close)

            # Filter: score >= 65
            if score < 65:
                continue

            # Determine setup type
            ema8 = float(_ema(close, 8).iloc[-1])
            ema50 = float(_ema(close, 50).iloc[-1])
            if price > ema8 > ema21 > ema50:
                setup_type = "Bull Stack Breakout"
            elif price > ema21 > ema50:
                setup_type = "Trend Continuation"
            else:
                setup_type = "Sector Rotation"

            candidates.append({
                "ticker": ticker,
                "rs_rank": rs_rank,
                "score": score,
                "setup_type": setup_type,
                "price": round(price, 2),
                "ema21": round(ema21, 2),
            })

        except Exception as e:
            log.debug(f"Error evaluating {ticker}: {e}")

    # Sort by RS rank descending, take top N
    candidates.sort(key=lambda x: x["rs_rank"], reverse=True)
    return candidates[:top_n]


def _quick_score(df: pd.DataFrame, spy_close: Optional[pd.Series] = None) -> int:
    """Quick composite score (0-100) for screening purposes."""
    try:
        close = df["Close"].squeeze().dropna()
        vol = df["Volume"].squeeze().dropna()
        if len(close) < 50:
            return 0

        price = float(close.iloc[-1])
        score = 0.0

        # EMA alignment (25 pts)
        ema8 = float(_ema(close, 8).iloc[-1])
        ema21 = float(_ema(close, 21).iloc[-1])
        ema50 = float(_ema(close, 50).iloc[-1])
        if price > ema8 > ema21 > ema50:
            score += 25
        elif price > ema21 > ema50:
            score += 15
        elif price > ema50:
            score += 8

        # RS rank (25 pts)
        if spy_close is not None:
            rs = _relative_strength_rank(close, spy_close)
            if rs >= 90:
                score += 25
            elif rs >= 80:
                score += 20
            elif rs >= 70:
                score += 15
            elif rs >= 60:
                score += 10

        # RSI momentum (25 pts)
        rsi_val = float(_rsi(close).iloc[-1])
        if 50 <= rsi_val <= 70:
            score += 25
        elif 45 <= rsi_val < 50:
            score += 15
        elif 70 < rsi_val <= 80:
            score += 10

        # Volume (25 pts)
        if len(vol) >= 20:
            avg_vol = float(vol.rolling(20).mean().iloc[-1])
            if avg_vol > 0:
                rvol = float(vol.iloc[-1]) / avg_vol
                if rvol >= 2.0:
                    score += 25
                elif rvol >= 1.5:
                    score += 20
                elif rvol >= 1.2:
                    score += 10

        return int(min(100, score))
    except Exception:
        return 0


def score_sector_rotation(ticker: str, sector_data: dict) -> dict:
    """
    Score a sector rotation candidate 0-100.

    Components:
      - Sector breakout strength (25 pts): volume ratio, distance above 20d high
      - Individual RS rank (25 pts): >= 90 = 25, >= 80 = 20, >= 70 = 15
      - EMA alignment (20 pts): full bull stack = 20, partial = 10
      - Volume confirmation (15 pts): individual stock RVOL >= 1.5 = 15
      - Momentum (15 pts): RSI 50-70 sweet spot = 15

    Args:
        ticker: Stock ticker symbol
        sector_data: Dict with keys from scan_sector_breakouts() output:
            {etf, volume_ratio, rs_vs_spy, ...}

    Returns dict with:
        {score, breakdown, trade_plan}
    """
    from data_archive import load_ticker

    df = load_ticker(ticker)
    if df is None or len(df) < 50:
        return {"score": 0, "breakdown": {}, "trade_plan": None}

    close = df["Close"].squeeze().dropna()
    high = df["High"].squeeze().dropna()
    low = df["Low"].squeeze().dropna()
    vol = df["Volume"].squeeze().dropna()
    price = float(close.iloc[-1])

    # Load SPY for RS
    spy_df = load_ticker("SPY")
    spy_close = spy_df["Close"].squeeze().dropna() if spy_df is not None else None

    breakdown = {}
    total = 0

    # 1. Sector breakout strength (25 pts)
    sector_pts = 0
    vol_ratio = sector_data.get("volume_ratio", 1.0)
    if vol_ratio >= 2.0:
        sector_pts += 15
    elif vol_ratio >= 1.5:
        sector_pts += 10
    elif vol_ratio >= 1.3:
        sector_pts += 7

    # Distance above 20-day high for the sector (approximated by RS vs SPY)
    rs_vs_spy = sector_data.get("rs_vs_spy", 0)
    if rs_vs_spy >= 5:
        sector_pts += 10
    elif rs_vs_spy >= 2:
        sector_pts += 7
    elif rs_vs_spy > 0:
        sector_pts += 4

    sector_pts = min(25, sector_pts)
    breakdown["sector_breakout"] = sector_pts
    total += sector_pts

    # 2. Individual RS rank (25 pts)
    rs_pts = 0
    rs_rank = 50
    if spy_close is not None:
        rs_rank = _relative_strength_rank(close, spy_close)
    if rs_rank >= 90:
        rs_pts = 25
    elif rs_rank >= 80:
        rs_pts = 20
    elif rs_rank >= 70:
        rs_pts = 15
    elif rs_rank >= 60:
        rs_pts = 10
    breakdown["rs_rank"] = rs_pts
    total += rs_pts

    # 3. EMA alignment (20 pts)
    ema_pts = 0
    ema8 = float(_ema(close, 8).iloc[-1])
    ema21 = float(_ema(close, 21).iloc[-1])
    ema50 = float(_ema(close, 50).iloc[-1])
    sma200 = float(_sma(close, 200).iloc[-1]) if len(close) >= 200 else None

    if sma200 is not None and price > ema8 > ema21 > ema50 > sma200:
        ema_pts = 20  # Full bull stack
    elif price > ema8 > ema21 > ema50:
        ema_pts = 18
    elif price > ema21 > ema50:
        ema_pts = 10
    elif price > ema50:
        ema_pts = 5
    breakdown["ema_alignment"] = ema_pts
    total += ema_pts

    # 4. Volume confirmation (15 pts)
    vol_pts = 0
    if len(vol) >= 20:
        avg_vol = float(vol.rolling(20).mean().iloc[-1])
        if avg_vol > 0:
            rvol = float(vol.iloc[-1]) / avg_vol
            if rvol >= 2.0:
                vol_pts = 15
            elif rvol >= 1.5:
                vol_pts = 12
            elif rvol >= 1.2:
                vol_pts = 8
    breakdown["volume_confirm"] = vol_pts
    total += vol_pts

    # 5. Momentum / RSI (15 pts)
    mom_pts = 0
    rsi_val = float(_rsi(close).iloc[-1])
    if 50 <= rsi_val <= 70:
        mom_pts = 15  # Sweet spot
    elif 45 <= rsi_val < 50:
        mom_pts = 10
    elif 70 < rsi_val <= 80:
        mom_pts = 8
    elif rsi_val > 80:
        mom_pts = 3  # Overextended
    breakdown["momentum"] = mom_pts
    total += mom_pts

    total = min(100, total)

    # Build trade plan
    stop = round(ema21, 2)
    # Target: recent swing high or 2x risk
    risk = price - stop
    target1 = round(price + risk * 1.5, 2) if risk > 0 else round(price * 1.05, 2)
    target2 = round(price + risk * 2.5, 2) if risk > 0 else round(price * 1.10, 2)
    rr_ratio = round(risk * 1.5 / risk, 2) if risk > 0 else 0

    # Entry zone: current price or pullback to EMA8
    entry_high = round(price, 2)
    entry_low = round(ema8, 2)

    trade_plan = {
        "direction": "long",
        "entry_low": entry_low,
        "entry_high": entry_high,
        "stop": stop,
        "target1": target1,
        "target2": target2,
        "rr_ratio": rr_ratio,
        "setup_type": "Sector Rotation",
        "family": "Trend Continuation",
        "hold_days": "7-14",
        "risk_per_share": round(abs(price - stop), 2),
        "price": price,
        "reason": (
            f"Sector Rotation: {sector_data.get('etf', '?')} breaking out "
            f"(vol {vol_ratio:.1f}x). "
            f"RS rank {rs_rank}, RSI {rsi_val:.0f}. "
            f"Enter ${entry_low}-${entry_high}, stop ${stop}, "
            f"targets ${target1}/${target2}."
        ),
    }

    return {
        "score": total,
        "breakdown": breakdown,
        "rs_rank": rs_rank,
        "rsi": round(rsi_val, 1),
        "trade_plan": trade_plan,
    }


# ── Main ─────────────────────────────────────────────────────────────────────

def run_scan():
    """Full sector rotation scan: find breakouts, then find leaders."""
    print("\n" + "=" * 60)
    print("SECTOR ROTATION SCAN")
    print("=" * 60)

    breakouts = scan_sector_breakouts()

    if not breakouts:
        print("\nNo sector breakouts detected in the last 3 days.")
        print("Criteria: ETF closing above 20-day high on >= 1.3x avg volume")
        return []

    print(f"\n{'ETF':<6} {'Date':<12} {'Vol Ratio':>10} {'RS vs SPY':>10} {'Price':>8}")
    print("-" * 50)
    for b in breakouts:
        print(f"{b['etf']:<6} {b['breakout_date']:<12} {b['volume_ratio']:>10.2f}x "
              f"{b['rs_vs_spy']:>+9.2f}% {b['price']:>8.2f}")

    all_candidates = []

    for b in breakouts:
        etf = b["etf"]
        print(f"\n--- {etf} Leaders ---")
        leaders = get_sector_leaders(etf, top_n=3)

        if not leaders:
            print("  No qualified leaders found (need: above EMA21, RS >= 70, score >= 65)")
            continue

        for leader in leaders:
            result = score_sector_rotation(leader["ticker"], b)
            leader["rotation_score"] = result["score"]
            leader["trade_plan"] = result.get("trade_plan")
            leader["breakdown"] = result.get("breakdown", {})
            all_candidates.append({**leader, "sector_etf": etf})

            plan = result.get("trade_plan", {})
            print(f"  {leader['ticker']:<6} RS={leader['rs_rank']:>3}  "
                  f"Score={result['score']:>3}  "
                  f"Setup: {leader['setup_type']}")
            if plan:
                print(f"         Entry ${plan.get('entry_low', 0):.2f}-"
                      f"${plan.get('entry_high', 0):.2f}  "
                      f"Stop ${plan.get('stop', 0):.2f}  "
                      f"T1 ${plan.get('target1', 0):.2f}  "
                      f"T2 ${plan.get('target2', 0):.2f}")

    if all_candidates:
        all_candidates.sort(key=lambda x: x.get("rotation_score", 0), reverse=True)
        print(f"\n{'=' * 60}")
        print(f"TOP SECTOR ROTATION CANDIDATES (sorted by score)")
        print(f"{'=' * 60}")
        print(f"{'Ticker':<7} {'Sector':<6} {'RS':>4} {'Score':>6} {'Setup':<25}")
        print("-" * 55)
        for c in all_candidates:
            print(f"{c['ticker']:<7} {c['sector_etf']:<6} {c['rs_rank']:>4} "
                  f"{c.get('rotation_score', 0):>6} {c['setup_type']:<25}")

    return all_candidates


# ── Wave-1 addition: factor exposure for today's BUY basket ─────────────────

def compute_factor_exposure(buy_basket: list[dict]) -> dict:
    """Given today's BUY basket, compute factor exposure.

    Each entry in `buy_basket` should provide at least a `ticker`, and
    optionally `sector`, `beta`, and `market_cap`. Missing values are handled
    gracefully.

    Returns:
        {
          'basket_size': N,
          'weighted_beta': X,
          'top_sector_pct': 0.45,
          'top_3_sectors': [(sector, pct), ...],
          'concentration_flag': bool,  # True if any single sector > 50%
          'max_factor_exposure': 'Technology 45%'
        }
    """
    empty = {
        "basket_size": 0,
        "weighted_beta": None,
        "top_sector_pct": 0.0,
        "top_3_sectors": [],
        "concentration_flag": False,
        "max_factor_exposure": None,
    }
    if not buy_basket:
        return empty

    # Try to backfill sector/beta from data_fetcher if not provided.
    try:
        from data_fetcher import _TICKER_TO_SECTOR  # type: ignore
    except Exception:
        _TICKER_TO_SECTOR = {}

    enriched = []
    for row in buy_basket:
        if not isinstance(row, dict):
            continue
        ticker = row.get("ticker")
        if not ticker:
            continue
        sector = row.get("sector") or _TICKER_TO_SECTOR.get(ticker) or "Unknown"
        beta = row.get("beta")
        try:
            beta_f = float(beta) if beta is not None else None
        except (TypeError, ValueError):
            beta_f = None
        mcap = row.get("market_cap")
        try:
            mcap_f = float(mcap) if mcap is not None else None
        except (TypeError, ValueError):
            mcap_f = None
        enriched.append({"ticker": ticker, "sector": sector,
                         "beta": beta_f, "market_cap": mcap_f})

    n = len(enriched)
    if n == 0:
        return empty

    # Equal-weight sector pcts (market-cap weighting would bias tiny baskets)
    sector_counts: dict[str, int] = {}
    for r in enriched:
        sector_counts[r["sector"]] = sector_counts.get(r["sector"], 0) + 1
    sector_pcts = {s: c / n for s, c in sector_counts.items()}
    sorted_sectors = sorted(sector_pcts.items(), key=lambda kv: kv[1], reverse=True)
    top_sector, top_pct = sorted_sectors[0]
    top_3 = [(s, round(p, 4)) for s, p in sorted_sectors[:3]]

    # Weighted beta: market-cap-weighted if any caps given, else equal weight
    betas = [r["beta"] for r in enriched if r["beta"] is not None]
    if betas:
        caps = [r["market_cap"] for r in enriched
                if r["beta"] is not None and r["market_cap"] is not None]
        if caps and len(caps) == len(betas) and sum(caps) > 0:
            weights = [r["market_cap"] for r in enriched if r["beta"] is not None]
            total_w = sum(weights)
            weighted_beta = sum(b * w for b, w in zip(betas, weights)) / total_w
        else:
            weighted_beta = sum(betas) / len(betas)
        weighted_beta = round(float(weighted_beta), 3)
    else:
        weighted_beta = None

    concentration = top_pct > 0.50
    max_factor = f"{top_sector} {int(round(top_pct * 100))}%"

    return {
        "basket_size": n,
        "weighted_beta": weighted_beta,
        "top_sector_pct": round(top_pct, 4),
        "top_3_sectors": top_3,
        "concentration_flag": bool(concentration),
        "max_factor_exposure": max_factor,
    }


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                        datefmt="%H:%M:%S")

    cmd = sys.argv[1] if len(sys.argv) > 1 else "scan"

    if cmd == "scan":
        run_scan()
    else:
        print(f"Usage: python3 sector_rotation.py [scan]")
