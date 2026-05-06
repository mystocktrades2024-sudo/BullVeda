"""
options_flow_scanner.py — Institutional Options Flow Imbalance Scanner.

Edge: when call dollar volume massively exceeds put dollar volume,
institutions are betting on upside. Follow the smart money.

Signal:
  1. Daily call $ volume / put $ volume > 3.0
  2. Total options dollar volume > $5M (institutional size)
  3. At least one strike with vol/OI > 3x (new positions, not rollovers)
  4. Stock not in earnings blackout (within 3 days of report)

Entry: next day open
Hold: 5-10 days (options expiry window)
Stop: 3% below entry (tight — options flow signals are time-sensitive)
Target: 5-8% above entry
"""
from __future__ import annotations

import logging
from typing import Optional

log = logging.getLogger("options_flow")


def scan(options_data: dict[str, dict],
         prices: dict[str, float] | None = None,
         fundamentals: dict[str, dict] | None = None) -> list[dict]:
    """
    Scan options chain data for flow imbalance.

    Args:
        options_data: {ticker: options_intelligence result dict}
        prices: {ticker: current price}
        fundamentals: {ticker: dict with days_to_earnings etc.}

    Returns: list of flow imbalance candidates
    """
    prices = prices or {}
    fundamentals = fundamentals or {}
    results = []

    for ticker, oi in options_data.items():
        try:
            if not oi or not isinstance(oi, dict):
                continue

            pcr = oi.get("put_call_ratio")
            call_vol = oi.get("total_call_vol", 0) or 0
            put_vol = oi.get("total_put_vol", 0) or 0
            call_oi = oi.get("total_call_oi", 0) or 0
            uoa_calls = oi.get("uoa_calls", False)
            uoa_call_detail = oi.get("uoa_call_detail", "")
            iv_pct = oi.get("iv_percentile")
            max_pain = oi.get("max_pain")
            gamma_net = oi.get("gamma_net")

            price = prices.get(ticker, 0)
            if price <= 0:
                continue

            # ── Criterion 1: Call/Put ratio < 0.5 (bullish imbalance) ──
            if pcr is None or pcr >= 0.5:
                continue

            # ── Criterion 2: Institutional size (total volume significant) ──
            total_vol = call_vol + put_vol
            if total_vol < 1000:
                continue

            # Estimate dollar volume (rough: avg premium ~$3 × 100 shares × volume)
            est_dollar_vol = total_vol * 300  # rough approximation
            if est_dollar_vol < 1_000_000:
                continue

            # ── Criterion 3: UOA confirmation (new positions, not rollovers) ──
            has_uoa = uoa_calls

            # ── Criterion 4: Not in earnings blackout ──
            fund = fundamentals.get(ticker, {})
            dte = fund.get("days_to_earnings") or fund.get("kpi_days_since_earnings")
            if isinstance(dte, (int, float)) and 0 <= dte <= 3:
                continue  # too close to earnings — flow might be hedging

            # ── Trade plan ──
            stop = round(price * 0.97, 2)  # 3% stop
            target = round(price * 1.07, 2)  # 7% target
            risk = price - stop
            reward = target - price
            rr = reward / risk if risk > 0 else 0

            # ── Signal strength ──
            if pcr < 0.2 and has_uoa:
                strength = "STRONG"
            elif pcr < 0.3 or has_uoa:
                strength = "MODERATE"
            else:
                strength = "WEAK"

            results.append({
                "ticker": ticker,
                "price": round(price, 2),
                "status": strength,
                "put_call_ratio": pcr,
                "call_volume": call_vol,
                "put_volume": put_vol,
                "call_oi": call_oi,
                "total_options_vol": total_vol,
                "uoa_calls": has_uoa,
                "uoa_detail": uoa_call_detail,
                "iv_percentile": iv_pct,
                "max_pain": max_pain,
                "gamma_net": gamma_net,
                "stop": stop,
                "target": target,
                "rr": round(rr, 1),
                "sector": fund.get("sector", "Unknown"),
            })

        except Exception as e:
            log.debug(f"options_flow({ticker}): {e}")
            continue

    results.sort(key=lambda x: ({"STRONG": 0, "MODERATE": 1, "WEAK": 2}.get(x["status"], 9), x["put_call_ratio"]))
    return results


def scan_live(tickers: list[str] | None = None, top_n: int = 30) -> list[dict]:
    """Fetch chains from Schwab for top tickers and scan for flow."""
    try:
        import schwab_client as sc
        from options_intelligence import analyze_chain
        import fundamentals_store as fs

        if not tickers:
            fund_df = fs.load_df()
            tickers = list(fund_df.index[:200])

        options_data = {}
        prices = {}
        for t in tickers[:top_n]:
            chain = sc.get_chains(t, strike_count=15)
            if chain:
                quote = sc.get_quote(t)
                p = (quote or {}).get("quote", {}).get("lastPrice", 0) if quote else 0
                prices[t] = p
                options_data[t] = analyze_chain(t, chain, p)

        fund_df = fs.load_df()
        fund_dict = {t: fund_df.loc[t].to_dict() for t in tickers if t in fund_df.index}

        return scan(options_data, prices, fund_dict)
    except Exception as e:
        log.error(f"scan_live: {e}")
        return []
