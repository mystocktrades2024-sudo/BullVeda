"""
correlation_factor.py — P2.30 + P2.31

P2.30: Pairwise 60-day correlation across CANDIDATE picks (not just held).
       Drop the lower-scored ticker if correlation > 0.7 with another pick.

P2.31: Factor exposure tracking. Tags candidates with factor labels
       (momentum, growth, mega-cap-tech, semis, AI, rate-sensitive,
       small-cap, cyclical) and caps exposure per factor.
"""
from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

log = logging.getLogger("correlation_factor")


# ── Pairwise correlation among new candidates ──────────────────────────────

def candidate_correlation_filter(picks: list, market_data: dict,
                                  threshold: float = 0.7,
                                  lookback_days: int = 60) -> tuple[list, list]:
    """
    Drop high-correlation duplicates from the BUY list.

    For each pair of picks with correlation > threshold over `lookback_days`,
    keep the higher-scored ticker, drop the lower-scored.

    Args:
      picks       — list of result dicts (each has ticker + score)
      market_data — {ticker: DataFrame with Close column}
      threshold   — pairwise correlation cutoff (default 0.7)
      lookback_days — how many bars of returns to use (default 60)

    Returns:
      (kept_picks, dropped_pairs)
      dropped_pairs = [(kept_ticker, dropped_ticker, correlation)]
    """
    if not picks or len(picks) < 2:
        return picks, []

    # Compute daily returns over the lookback window for each pick
    returns: dict[str, "pd.Series"] = {}
    for r in picks:
        t = r.get("ticker")
        if not t:
            continue
        df = market_data.get(t)
        if df is None or "Close" not in df:
            continue
        try:
            close = df["Close"].squeeze() if hasattr(df["Close"], "squeeze") else df["Close"]
            if len(close) < lookback_days:
                continue
            ret = close.pct_change().tail(lookback_days).dropna()
            if len(ret) >= 30:
                returns[t] = ret
        except Exception:
            continue

    if len(returns) < 2:
        return picks, []

    dropped: set = set()
    dropped_pairs: list = []

    # Score-rank picks descending so we keep higher-scored on conflict
    score_map = {r.get("ticker"): r.get("score", 0) or 0 for r in picks if r.get("ticker")}
    tickers_sorted = sorted(returns.keys(), key=lambda t: -score_map.get(t, 0))

    for i, t1 in enumerate(tickers_sorted):
        if t1 in dropped:
            continue
        for t2 in tickers_sorted[i+1:]:
            if t2 in dropped:
                continue
            try:
                # Align indexes by intersection
                common = returns[t1].index.intersection(returns[t2].index)
                if len(common) < 30:
                    continue
                corr = returns[t1].loc[common].corr(returns[t2].loc[common])
                if pd.notna(corr) and abs(corr) > threshold:
                    # Drop the lower-scored one (t2 since list is score-sorted desc)
                    dropped.add(t2)
                    dropped_pairs.append((t1, t2, round(float(corr), 3)))
            except Exception:
                continue

    kept = [r for r in picks if r.get("ticker") not in dropped]
    return kept, dropped_pairs


# ── Factor tag classification ──────────────────────────────────────────────

# Static factor mappings — refined as patterns emerge
_AI_TICKERS = {"NVDA", "AVGO", "AMD", "MU", "MRVL", "SMCI", "ARM", "PLTR", "AI", "BBAI", "C3AI"}
_SEMI_ETFS = {"SMH", "SOXX", "USD"}
_SEMI_TICKERS = {"NVDA", "AMD", "MU", "INTC", "AVGO", "QCOM", "MRVL", "AMAT", "LRCX", "KLAC", "ASML", "ARM", "ON", "MCHP"}
_MEGA_CAP_TECH = {"AAPL", "MSFT", "GOOG", "GOOGL", "META", "AMZN", "NVDA", "TSLA"}
_RATE_SENSITIVE_SECTORS = {"XLU", "XLRE", "Financial Services", "Real Estate", "Utilities"}
_CYCLICAL_SECTORS = {"XLI", "XLB", "XLY", "Industrials", "Materials", "Consumer Cyclical"}


def classify_factors(r: dict) -> list:
    """
    Tag a result dict with factor labels. Returns list of factor strings.
    """
    tags: list = []
    sym = (r.get("ticker") or "").upper()
    info = r.get("info") or {}
    sector = (info.get("sector") or r.get("sector") or "").lower()
    industry = (info.get("industry") or r.get("industry") or "").lower()
    sector_etf = (info.get("sector_etf") or "").upper()
    mcap = info.get("market_cap") or info.get("marketCap") or 0

    # Momentum tag — RS rank ≥ 80
    rs = r.get("rs_rank") or (r.get("technicals") or {}).get("rs_rank") or 0
    if rs >= 80:
        tags.append("momentum")

    # Growth tag — high revenue or eps growth
    fund = r.get("fundamentals") or r.get("extra_fund") or {}
    rev_g = fund.get("rev_growth_ttm") or fund.get("rev_change_ttm") or 0
    if rev_g and rev_g >= 20:
        tags.append("growth")

    # Mega-cap tech
    if sym in _MEGA_CAP_TECH:
        tags.append("mega_cap_tech")

    # Semiconductors
    if sym in _SEMI_TICKERS or "semiconductor" in industry:
        tags.append("semis")

    # AI theme
    if sym in _AI_TICKERS or "artificial intelligence" in industry:
        tags.append("ai_theme")

    # Rate-sensitive
    if sector_etf in _RATE_SENSITIVE_SECTORS or "real estate" in sector or "utility" in sector:
        tags.append("rate_sensitive")

    # Small caps
    if mcap and mcap < 2_000_000_000:
        tags.append("small_cap")

    # Cyclicals
    if sector_etf in _CYCLICAL_SECTORS or "cyclical" in sector or "industrial" in sector:
        tags.append("cyclical")

    # High beta
    beta = info.get("beta") or 0
    if beta and beta >= 1.5:
        tags.append("high_beta")

    return tags


def factor_exposure_summary(picks: list,
                             max_per_factor: int = 3) -> dict:
    """
    Tag each pick with factor labels and compute exposure summary.

    Returns:
      {
        by_factor: {factor: [tickers]},
        breaches: [(factor, count, max)],
        ticker_factors: {ticker: [factors]},
      }
    """
    ticker_factors: dict = {}
    by_factor: dict = {}

    for r in picks:
        t = r.get("ticker")
        if not t:
            continue
        tags = classify_factors(r)
        ticker_factors[t] = tags
        for tag in tags:
            by_factor.setdefault(tag, []).append(t)

    breaches: list = []
    for factor, tickers in by_factor.items():
        if len(tickers) > max_per_factor:
            breaches.append((factor, len(tickers), max_per_factor))

    return {
        "by_factor": by_factor,
        "breaches": breaches,
        "ticker_factors": ticker_factors,
    }
