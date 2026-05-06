"""
options_intelligence.py — Derive stock-trading signals from options chain data.

NOT for trading options — for informing STOCK entry/exit decisions using
options market intelligence (smart money, IV, hedging flows).

Signals computed:
  iv_percentile    — current IV rank vs 52-week range (0-100)
  put_call_ratio   — put OI / call OI (>1.5 bearish, <0.5 bullish)
  uoa_calls        — unusual call activity (vol/OI > 3×, dollar vol > $500K)
  uoa_puts         — unusual put activity (same threshold)
  max_pain         — strike price where most options expire worthless
  gamma_exposure   — net dealer gamma (positive = magnet, negative = accelerant)

Data source: Schwab /chains endpoint (schwab_client.get_chains).
"""
from __future__ import annotations

import logging
from typing import Optional

log = logging.getLogger("options_intel")


def analyze_chain(ticker: str, chain: dict, last_price: float = 0) -> dict:
    """
    Given a Schwab /chains response, compute stock-relevant options signals.
    Returns dict with all signals; missing data → None.
    """
    result = {
        "ticker":         ticker,
        "iv_percentile":  None,
        "put_call_ratio": None,
        "uoa_calls":      False,
        "uoa_puts":       False,
        "uoa_call_detail": None,
        "uoa_put_detail":  None,
        "max_pain":       None,
        "gamma_net":      None,
        "total_call_oi":  0,
        "total_put_oi":   0,
        "total_call_vol": 0,
        "total_put_vol":  0,
        "iv_current":     None,
    }
    if not chain:
        return result

    underlying_price = chain.get("underlyingPrice") or last_price or 0

    # Flatten all strikes from call/put exp date maps
    call_map = chain.get("callExpDateMap") or {}
    put_map  = chain.get("putExpDateMap") or {}

    calls: list[dict] = []
    puts:  list[dict] = []

    for exp, strikes in call_map.items():
        for strike_str, contracts in strikes.items():
            if isinstance(contracts, list):
                calls.extend(contracts)
            elif isinstance(contracts, dict):
                calls.append(contracts)

    for exp, strikes in put_map.items():
        for strike_str, contracts in strikes.items():
            if isinstance(contracts, list):
                puts.extend(contracts)
            elif isinstance(contracts, dict):
                puts.append(contracts)

    # ── Aggregate OI + volume ────────────────────────────────────────────
    total_call_oi  = sum(c.get("openInterest", 0) or 0 for c in calls)
    total_put_oi   = sum(p.get("openInterest", 0) or 0 for p in puts)
    total_call_vol = sum(c.get("totalVolume", 0) or 0 for c in calls)
    total_put_vol  = sum(p.get("totalVolume", 0) or 0 for p in puts)

    result["total_call_oi"]  = total_call_oi
    result["total_put_oi"]   = total_put_oi
    result["total_call_vol"] = total_call_vol
    result["total_put_vol"]  = total_put_vol

    # ── Put/Call ratio (OI-based, more stable than volume-based) ─────────
    if total_call_oi > 0:
        result["put_call_ratio"] = round(total_put_oi / total_call_oi, 2)

    # ── IV current (weighted average of near-money options) ──────────────
    near_money = [c for c in calls + puts
                  if c.get("strikePrice") and underlying_price
                  and abs(c["strikePrice"] - underlying_price) / underlying_price < 0.05
                  and c.get("volatility") and c["volatility"] > 0]
    if near_money:
        iv_sum = sum(c["volatility"] for c in near_money)
        result["iv_current"] = round(iv_sum / len(near_money), 1)

    # ── IV percentile (from chain's own volatility field if available) ───
    # Schwab doesn't provide historical IV, but we can use the chain's
    # `volatility` field as current IV. True IV percentile needs historical
    # data — approximate by flagging >40% as elevated for stock trading.
    iv = result["iv_current"]
    if iv is not None:
        if iv > 80:
            result["iv_percentile"] = 95
        elif iv > 50:
            result["iv_percentile"] = 75
        elif iv > 30:
            result["iv_percentile"] = 50
        else:
            result["iv_percentile"] = 25

    # ── Unusual Options Activity detection ───────────────────────────────
    # UOA = single-strike volume/OI > 3× AND dollar volume > $500K
    for c in calls:
        oi = c.get("openInterest", 0) or 0
        vol = c.get("totalVolume", 0) or 0
        mark = c.get("mark") or c.get("last") or 0
        if oi > 0 and vol > 0 and vol / oi >= 3.0:
            dollar_vol = vol * mark * 100
            if dollar_vol >= 500_000:
                result["uoa_calls"] = True
                result["uoa_call_detail"] = f"${c.get('strikePrice','?')} call: {vol:,} vol vs {oi:,} OI ({vol/oi:.1f}×), ${dollar_vol:,.0f}"
                break

    for p in puts:
        oi = p.get("openInterest", 0) or 0
        vol = p.get("totalVolume", 0) or 0
        mark = p.get("mark") or p.get("last") or 0
        if oi > 0 and vol > 0 and vol / oi >= 3.0:
            dollar_vol = vol * mark * 100
            if dollar_vol >= 500_000:
                result["uoa_puts"] = True
                result["uoa_put_detail"] = f"${p.get('strikePrice','?')} put: {vol:,} vol vs {oi:,} OI ({vol/oi:.1f}×), ${dollar_vol:,.0f}"
                break

    # ── Max Pain calculation ─────────────────────────────────────────────
    # Strike where total option holder losses are maximized (price tends
    # to gravitate here near expiration)
    if calls or puts:
        strike_set = sorted(set(
            c.get("strikePrice", 0) for c in calls + puts if c.get("strikePrice")
        ))
        if strike_set and underlying_price:
            min_pain = float("inf")
            max_pain_strike = underlying_price
            for test_price in strike_set:
                pain = 0
                for c in calls:
                    sp = c.get("strikePrice", 0)
                    oi = c.get("openInterest", 0) or 0
                    if test_price > sp:
                        pain += (test_price - sp) * oi * 100
                for p in puts:
                    sp = p.get("strikePrice", 0)
                    oi = p.get("openInterest", 0) or 0
                    if test_price < sp:
                        pain += (sp - test_price) * oi * 100
                if pain < min_pain:
                    min_pain = pain
                    max_pain_strike = test_price
            result["max_pain"] = max_pain_strike

    # ── Net gamma exposure (simplified) ──────────────────────────────────
    # Positive gamma = dealers long gamma = they buy dips, sell rallies = stabilizing
    # Negative gamma = dealers short gamma = they sell dips, buy rallies = destabilizing
    gamma_sum = 0
    for c in calls:
        g = c.get("gamma") or 0
        oi = c.get("openInterest", 0) or 0
        gamma_sum += g * oi * 100
    for p in puts:
        g = p.get("gamma") or 0
        oi = p.get("openInterest", 0) or 0
        gamma_sum -= g * oi * 100
    if gamma_sum != 0:
        result["gamma_net"] = round(gamma_sum)

    return result


def fetch_and_analyze(ticker: str, last_price: float = 0) -> Optional[dict]:
    """Convenience: fetch Schwab chain + analyze. Returns None on failure."""
    try:
        import schwab_client as sc
        chain = sc.get_chains(ticker, strike_count=15)
        if not chain:
            return None
        return analyze_chain(ticker, chain, last_price)
    except Exception as e:
        log.debug(f"options_intelligence({ticker}): {e}")
        return None


def batch_analyze(tickers: list[str], prices: dict[str, float] | None = None) -> dict[str, dict]:
    """Analyze multiple tickers. Returns {ticker: signals_dict}."""
    import schwab_client as sc
    prices = prices or {}
    results = {}
    for t in tickers:
        try:
            chain = sc.get_chains(t, strike_count=15)
            if chain:
                results[t] = analyze_chain(t, chain, prices.get(t, 0))
        except Exception as e:
            log.debug(f"batch options_intelligence({t}): {e}")
    return results
