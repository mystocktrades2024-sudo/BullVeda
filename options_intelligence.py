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


def _compute_skew(chain: dict, underlying_price: float) -> Optional[float]:
    """25-delta skew = put_IV(25Δ) - call_IV(25Δ). Positive = put-fear, negative = call-bid."""
    call_map = chain.get("callExpDateMap") or {}
    put_map = chain.get("putExpDateMap") or {}
    # Find front-month expiry
    if not call_map or not put_map:
        return None
    front_call_exp = sorted(call_map.keys())[0]
    front_put_exp = sorted(put_map.keys())[0]
    call_strikes = call_map.get(front_call_exp, {})
    put_strikes = put_map.get(front_put_exp, {})

    def _find_25d(strike_map: dict, side: str) -> Optional[float]:
        candidates = []
        for strike_str, contracts in strike_map.items():
            cs = contracts if isinstance(contracts, list) else [contracts]
            for c in cs:
                d = abs(c.get("delta") or 0)
                if 0.20 <= d <= 0.30 and c.get("volatility"):
                    candidates.append((abs(d - 0.25), c["volatility"]))
        if not candidates:
            return None
        candidates.sort()
        return candidates[0][1]

    put_iv_25d = _find_25d(put_strikes, "put")
    call_iv_25d = _find_25d(call_strikes, "call")
    if put_iv_25d is None or call_iv_25d is None:
        return None
    return round(put_iv_25d - call_iv_25d, 2)


def _compute_term_structure(chain: dict) -> dict:
    """Front-month vs back-month ATM IV → contango/backwardation."""
    call_map = chain.get("callExpDateMap") or {}
    underlying_price = chain.get("underlyingPrice") or 0
    if not call_map or not underlying_price:
        return {}
    expiries = sorted(call_map.keys())
    if len(expiries) < 2:
        return {}

    def _atm_iv(strikes: dict) -> Optional[float]:
        best = None
        best_diff = float("inf")
        for sp_str, contracts in strikes.items():
            cs = contracts if isinstance(contracts, list) else [contracts]
            for c in cs:
                sp = c.get("strikePrice") or 0
                iv = c.get("volatility")
                if sp and iv:
                    d = abs(sp - underlying_price)
                    if d < best_diff:
                        best_diff = d
                        best = iv
        return best

    front_iv = _atm_iv(call_map[expiries[0]])
    back_iv = _atm_iv(call_map[expiries[min(3, len(expiries)-1)]])
    if front_iv is None or back_iv is None:
        return {}
    diff = front_iv - back_iv
    structure = "backwardation" if diff > 1.5 else "contango" if diff < -1.5 else "flat"
    return {"front_iv": round(front_iv, 1), "back_iv": round(back_iv, 1),
            "diff": round(diff, 1), "structure": structure}


def _classify_uoa_type(contract: dict) -> str:
    """sweep (single trade > 50% of vol) vs block (large size, normal exec)."""
    vol = contract.get("totalVolume", 0) or 0
    if vol >= 5000:
        return "block"
    if vol >= 500:
        return "sweep"
    return "normal"


def _build_verdict(kpis: dict) -> dict:
    """
    Compose the options verdict from kpis. Returns:
      {verdict: BULLISH|BEARISH|NEUTRAL|MIXED|NO_DATA,
       confidence: HIGH|MED|LOW,
       edge: 0-10,
       narrative: str (the verdict ribbon copy),
       confluences: [str, ...] (signals that fired)}
    """
    if not kpis:
        return {"verdict": "NO_DATA", "confidence": "LOW", "edge": 0,
                "narrative": "Options chain unavailable", "confluences": []}

    bull_signals: list[str] = []
    bear_signals: list[str] = []

    # Signal 1: Put/Call ratio
    pc = kpis.get("put_call_ratio")
    if pc is not None:
        if pc < 0.7:
            bull_signals.append(f"P/C {pc} (call-heavy)")
        elif pc > 1.3:
            bear_signals.append(f"P/C {pc} (put-heavy)")

    # Signal 2: UOA
    if kpis.get("uoa_calls") and not kpis.get("uoa_puts"):
        bull_signals.append("call sweep")
    if kpis.get("uoa_puts") and not kpis.get("uoa_calls"):
        bear_signals.append("put sweep")

    # Signal 3: IV regime — cheap upside vs expensive fear
    iv_pct = kpis.get("iv_percentile")
    if iv_pct is not None:
        if iv_pct < 35:
            bull_signals.append(f"IV rank {iv_pct} (cheap upside)")
        elif iv_pct > 75:
            bear_signals.append(f"IV rank {iv_pct} (fear priced in)")

    # Signal 4: Skew
    skew = kpis.get("skew_25d")
    if skew is not None:
        if skew < -1.5:
            bull_signals.append(f"calls bid up (skew {skew})")
        elif skew > 3.0:
            bear_signals.append(f"put protection demand (skew {skew})")

    # Signal 5: Gamma
    g = kpis.get("gamma_net")
    if g is not None:
        if g > 0:
            bull_signals.append("positive gamma (stabilizing)")
        elif g < -1_000_000:
            bear_signals.append("large negative gamma (volatile)")

    # Aggregate
    bull_count = len(bull_signals)
    bear_count = len(bear_signals)

    if bull_count == 0 and bear_count == 0:
        verdict = "NEUTRAL"; confidence = "LOW"
    elif bull_count >= 2 and bull_count > bear_count:
        verdict = "BULLISH"
        confidence = "HIGH" if bull_count >= 3 else "MED"
    elif bear_count >= 2 and bear_count > bull_count:
        verdict = "BEARISH"
        confidence = "HIGH" if bear_count >= 3 else "MED"
    elif bull_count > 0 and bear_count > 0:
        verdict = "MIXED"; confidence = "MED"
    else:
        verdict = "NEUTRAL"; confidence = "LOW"

    # Edge score 0-10 — combination of signal count + confluence direction
    edge = min(10, max(0, abs(bull_count - bear_count) * 2 + (bull_count + bear_count)))

    # One-liner narrative (used in compact ribbon)
    if verdict == "BULLISH":
        narrative = " + ".join(bull_signals[:2]).capitalize()
    elif verdict == "BEARISH":
        narrative = " + ".join(bear_signals[:2]).capitalize()
    elif verdict == "MIXED":
        narrative = f"Conflicting: {bull_signals[0] if bull_signals else ''} vs {bear_signals[0] if bear_signals else ''}"
    else:
        narrative = "Flow neutral — no clear directional signal"

    # Full thesis — multi-sentence paragraph that reads like a trader's note.
    # Weaves the actual fired signals into a story explaining WHY the verdict.
    thesis_parts: list[str] = []
    pc = kpis.get("put_call_ratio")
    iv_pct = kpis.get("iv_percentile")
    skew = kpis.get("skew_25d")
    g = kpis.get("gamma_net")
    term = kpis.get("term_structure", {}) or {}
    uoa_call = kpis.get("uoa_calls")
    uoa_put = kpis.get("uoa_puts")
    uoa_call_detail = kpis.get("uoa_call_detail")
    uoa_put_detail = kpis.get("uoa_put_detail")
    max_pain = kpis.get("max_pain")

    if verdict == "BULLISH":
        thesis_parts.append("Smart money is positioning for upside.")
        if uoa_call:
            thesis_parts.append(
                f"Unusual call activity ({uoa_call_detail or 'sweep detected'}) suggests "
                f"institutional accumulation expecting near-term breakout."
            )
        if iv_pct is not None and iv_pct < 35:
            thesis_parts.append(
                f"IV rank at {iv_pct} means options are cheap — upside isn't yet priced in, "
                f"so calls offer asymmetric reward if the stock moves."
            )
        if pc is not None and pc < 0.7:
            thesis_parts.append(
                f"Put/call OI ratio of {pc} confirms call-heavy positioning across the chain."
            )
        if skew is not None and skew < -1.5:
            thesis_parts.append(
                f"Skew of {skew} (calls bid up vs puts) reinforces the bullish stance."
            )
        if term.get("structure") == "contango":
            thesis_parts.append(
                "Term structure in normal contango — no near-term hedging fear from institutions."
            )
        if g is not None and g > 0:
            thesis_parts.append(
                f"Net gamma of {g:+,} keeps dealers stabilizing the price (they buy dips)."
            )

    elif verdict == "BEARISH":
        thesis_parts.append("Options market is positioning defensively.")
        if uoa_put:
            thesis_parts.append(
                f"Unusual put activity ({uoa_put_detail or 'block detected'}) signals "
                f"institutional hedging or directional bearish bets."
            )
        if iv_pct is not None and iv_pct > 75:
            thesis_parts.append(
                f"IV rank at {iv_pct} means fear is priced in — option premiums are elevated, "
                f"likely reflecting near-term event risk or institutional protection."
            )
        if pc is not None and pc > 1.3:
            thesis_parts.append(
                f"Put/call OI ratio of {pc} is heavy on the put side — broad protection demand."
            )
        if skew is not None and skew > 3.0:
            thesis_parts.append(
                f"Skew of +{skew} (puts bid up) confirms downside protection demand."
            )
        if term.get("structure") == "backwardation":
            thesis_parts.append(
                "Term structure in backwardation — institutions are positioning for near-term stress."
            )
        if g is not None and g < -1_000_000:
            thesis_parts.append(
                f"Negative net gamma ({g:+,}) means dealer hedging amplifies moves — expect volatility."
            )

    elif verdict == "MIXED":
        thesis_parts.append(
            "Options flow is sending conflicting signals. Bull-side and bear-side positioning "
            "are both visible — likely indicates a binary catalyst is pending or institutions "
            "are split on direction."
        )
        if uoa_call and uoa_put:
            thesis_parts.append(
                "Both unusual call and put activity detected — this could be a hedged trade "
                "(directional bet with downside protection) or genuinely conflicting views."
            )
        if iv_pct is not None and iv_pct > 50:
            thesis_parts.append(
                f"IV rank at {iv_pct} suggests the market is pricing in event risk — proceed "
                f"with smaller size until the catalyst resolves."
            )

    else:  # NEUTRAL or NO_DATA
        if not kpis or all(v is None for v in [pc, iv_pct, uoa_call, uoa_put]):
            thesis_parts.append(
                "Insufficient options activity to form a directional read. Either liquidity is "
                "thin, the chain hasn't moved meaningfully, or data isn't yet available."
            )
        else:
            thesis_parts.append(
                "Options flow is balanced — no clear institutional positioning either way. "
                "This often happens in low-volatility consolidation periods where neither side "
                "has conviction."
            )
            if iv_pct is not None and iv_pct < 30:
                thesis_parts.append(
                    f"IV rank at {iv_pct} (cheap) means if a catalyst emerges, options will "
                    f"offer good leverage — worth watching for breakout signals."
                )

    if max_pain and kpis.get("total_call_oi", 0) > 1000:
        thesis_parts.append(
            f"Max pain sits at ${max_pain} — price tends to gravitate here near monthly expiry."
        )

    thesis = " ".join(thesis_parts)

    return {
        "verdict": verdict,
        "confidence": confidence,
        "edge": edge,
        "narrative": narrative,
        "thesis": thesis,
        "confluences": bull_signals + bear_signals,
        "bull_count": bull_count,
        "bear_count": bear_count,
    }


def _per_mode_overlay(kpis: dict, base_verdicts: dict) -> dict:
    """
    For each mode (swing/position/invest), compute how options flow MODIFIES
    the base verdict. Returns:
      {swing: {score_delta, status: CONFIRMED|CAUTIONED|CONTRADICTED, narrative, edge},
       position: {...},
       invest: {...}}
    """
    out = {}
    if not kpis:
        return {m: {"score_delta": 0, "status": "NO_DATA", "narrative": "Options data unavailable", "edge": "—"}
                for m in ("swing", "position", "invest")}

    v = kpis.get("verdict", {}).get("verdict") if isinstance(kpis.get("verdict"), dict) else None
    pc = kpis.get("put_call_ratio")
    iv_pct = kpis.get("iv_percentile")
    uoa_call = kpis.get("uoa_calls")
    uoa_put = kpis.get("uoa_puts")
    term = kpis.get("term_structure", {}) or {}

    def _mode_card(mode: str, base_verdict: str) -> dict:
        delta = 0
        bullets = []
        edge = "MED"
        # Per-mode signal sensitivity:
        if mode == "swing":
            # Swing (2-21d) — cares most about UOA + near-term IV + gamma squeeze
            if uoa_call and base_verdict == "BUY":
                delta += 4; bullets.append("call sweep aligns with BUY")
                edge = "HIGH"
            if uoa_put and base_verdict == "BUY":
                delta -= 5; bullets.append("put sweep contradicts BUY (smart money hedging)")
                edge = "LOW"
            if iv_pct is not None and iv_pct < 30 and base_verdict == "BUY":
                delta += 2; bullets.append(f"IV rank {iv_pct} = cheap upside priced")
            if iv_pct is not None and iv_pct > 80:
                delta -= 2; bullets.append(f"IV rank {iv_pct} = elevated risk priced")
        elif mode == "position":
            # Position (1-3mo) — cares about term structure + monthly OI + sector flow
            if term.get("structure") == "contango":
                delta += 1; bullets.append("normal IV term structure = no near-term fear")
            if term.get("structure") == "backwardation":
                delta -= 3; bullets.append("IV backwardation = institutional positioning for stress")
                edge = "HIGH"
            if pc is not None and pc < 0.6:
                delta += 1; bullets.append(f"strong call OI bias (P/C {pc})")
        elif mode == "invest":
            # Invest (6-12mo) — cares about LEAPS positioning + long-dated put protection
            if pc is not None and pc > 1.4:
                delta -= 3; bullets.append(f"long-dated puts accumulating (P/C {pc})")
                edge = "HIGH"
            if uoa_put:
                delta -= 2; bullets.append("recent put block = institutional hedge demand")
            if iv_pct is not None and iv_pct < 25:
                delta += 1; bullets.append("low IV regime = quiet accumulation period")

        # Determine status
        if delta >= 3:
            status = "CONFIRMED"
        elif delta <= -3:
            status = "CONTRADICTED"
        elif delta != 0:
            status = "CAUTIONED"
        else:
            status = "NEUTRAL"

        return {
            "score_delta": delta,
            "status": status,
            "narrative": " · ".join(bullets) if bullets else "Flow not directional for this horizon",
            "edge": edge,
            "bullets": bullets,
        }

    out["swing"]    = _mode_card("swing",    base_verdicts.get("swing", "WATCH"))
    out["position"] = _mode_card("position", base_verdicts.get("position", "WATCH"))
    out["invest"]   = _mode_card("invest",   base_verdicts.get("invest", "WATCH"))
    return out


def fetch_and_analyze(ticker: str, last_price: float = 0,
                      base_verdicts: dict | None = None) -> Optional[dict]:
    """Convenience: fetch Schwab chain + analyze + enrich + verdict.

    Returns the full options_kpis dict including:
      - All raw KPIs (IV, OI, vol, P/C, UOA, max pain, gamma)
      - skew_25d, term_structure (added 2026-04-29)
      - verdict {verdict, confidence, edge, narrative, confluences}
      - per_mode {swing, position, invest} with score_delta + status + narrative
    """
    try:
        import schwab_client as sc
        chain = sc.get_chains(ticker, strike_count=15)
        if not chain:
            return None
        kpis = analyze_chain(ticker, chain, last_price)
        # Enrich with skew + term structure
        underlying = chain.get("underlyingPrice") or last_price or 0
        kpis["skew_25d"] = _compute_skew(chain, underlying)
        kpis["term_structure"] = _compute_term_structure(chain)
        # Verdict
        kpis["verdict"] = _build_verdict(kpis)
        # Per-mode overlay
        kpis["per_mode"] = _per_mode_overlay(kpis, base_verdicts or {})
        return kpis
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
