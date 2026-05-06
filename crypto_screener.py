"""
crypto_screener.py — Professional crypto screener
Data sources:
  CoinGecko (free)  : universe ranking, market cap, ATH, stablecoin/wrapped detection
  Binance REST       : real-time price, 24h high/low, USDT volume
  Binance Futures    : funding rates per perp contract
  alternative.me     : Fear & Greed Index
"""

from __future__ import annotations

import logging
import time
from datetime import datetime

import numpy as np
import pandas as pd
import requests
from data_fetcher import yf  # _YfStub: empty no-op (yfinance removed 2026-04-25)

log = logging.getLogger(__name__)

# ── Exclusion lists ────────────────────────────────────────────────────────────

STABLECOINS: set[str] = {
    "usdt", "usdc", "dai", "busd", "tusd", "frax", "usdp", "gusd",
    "pyusd", "fdusd", "usde", "usdd", "lusd", "crvusd", "susd", "mim",
    "rai", "dola", "eurt", "eurs", "usdn", "usdj", "husd", "cusd",
}

WRAPPED_SYMBOLS: set[str] = {
    "wbtc", "steth", "wsteth", "weeth", "cbbtc", "reth", "solvbtc",
    "ezeth", "rseth", "eeth", "lseth", "oseth", "sweth", "ankreth",
    "cbeth", "frxeth", "sfrxeth", "wbeth", "meth", "ethx",
}

WRAPPED_KEYWORDS: list[str] = [
    "wrapped", "staked", "bridged", "synthetic", "liquid staking",
]

# Meme / pure-speculation coins — no utility, no fundamentals, no place in a
# rules-based swing system.  Add new ones here as they appear in top 100.
MEME_COINS: set[str] = {
    "pepe", "dogecoin", "shiba-inu", "floki", "bonk", "dogwifcoin",
    "book-of-meme", "meme", "catinthemoon", "baby-doge-coin",
    "coq-inu", "myro", "popcat", "brett", "mog-coin", "neiro",
    "turbo", "volt-inu", "kishu-inu", "pitbull",
}

# ── Category taxonomy ──────────────────────────────────────────────────────────

CORE_MAJORS: set[str] = {"bitcoin", "ethereum"}

L1_PLATFORMS: set[str] = {
    "solana", "cardano", "avalanche-2", "toncoin", "polkadot",
    "near", "aptos", "sui", "cosmos", "algorand", "fantom",
    "hedera-hashgraph", "internet-computer", "stellar", "flow",
    "injective-protocol", "sei-network", "mantra-dao",
}

INFRA_DEFI: set[str] = {
    "binancecoin", "chainlink", "uniswap", "aave", "lido-dao",
    "maker", "curve-dao-token", "okb", "crypto-com-chain",
    "the-graph", "render-token", "filecoin", "arweave",
    "worldcoin-wld", "celestia",
}


# ── Data fetchers ──────────────────────────────────────────────────────────────

def _get(url: str, timeout: int = 15) -> list | dict | None:
    try:
        r = requests.get(url, timeout=timeout,
                         headers={"User-Agent": "SwingTrade/1.0"})
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.warning(f"[crypto] GET {url[:60]} failed: {e}")
        return None


def get_coingecko_top100() -> list[dict]:
    """Top 100 coins by market cap with 24h/7d/30d price change data."""
    url = (
        "https://api.coingecko.com/api/v3/coins/markets"
        "?vs_currency=usd&order=market_cap_desc&per_page=100&page=1"
        "&sparkline=false&price_change_percentage=24h,7d,30d"
    )
    data = _get(url)
    return data if isinstance(data, list) else []


def get_binance_spot_tickers() -> dict[str, dict]:
    """Spot 24hr tickers keyed by Binance-style symbol (BTCUSDT).

    Binance endpoints (api.binance.com, fapi.binance.com) return HTTP 451 from US IPs,
    so we source from OKX and rewrite its pair format (BTC-USDT → BTCUSDT) to preserve
    the downstream shape the scorer expects (quoteVolume key).
    """
    data = _get("https://www.okx.com/api/v5/market/tickers?instType=SPOT")
    if not isinstance(data, dict):
        return {}
    rows = data.get("data", []) or []
    out: dict[str, dict] = {}
    for row in rows:
        inst = row.get("instId", "")
        if not inst.endswith("-USDT"):
            continue
        sym = inst.replace("-", "")
        # volCcy24h is USDT-denominated 24h volume on OKX; closest proxy to Binance quoteVolume
        out[sym] = {
            "symbol":      sym,
            "lastPrice":   row.get("last"),
            "highPrice":   row.get("high24h"),
            "lowPrice":    row.get("low24h"),
            "quoteVolume": row.get("volCcy24h"),
            "volume":      row.get("vol24h"),
            "_source":     "okx",
        }
    return out


def get_binance_funding_rates(symbols: list[str] | None = None) -> dict[str, float]:
    """Latest perp funding rate for each symbol. Keyed BTCUSDT-style.

    OKX doesn't have a bulk funding endpoint — we loop over the passed coins only
    (typically <=15 after gating). Bounded concurrency keeps latency <3s.
    """
    if not symbols:
        return {}
    import concurrent.futures as _cf
    base = "https://www.okx.com/api/v5/public/funding-rate"
    def _one(sym: str) -> tuple[str, float | None]:
        inst = sym.replace("USDT", "-USDT-SWAP")
        data = _get(f"{base}?instId={inst}", timeout=6)
        try:
            rate = (data or {}).get("data", [{}])[0].get("fundingRate")
            return sym, float(rate) if rate is not None else None
        except Exception:
            return sym, None
    out: dict[str, float] = {}
    with _cf.ThreadPoolExecutor(max_workers=8) as pool:
        for sym, rate in pool.map(_one, symbols):
            if rate is not None:
                out[sym] = rate
    return out


def get_fear_greed() -> dict:
    """Crypto Fear & Greed from alternative.me."""
    data = _get("https://api.alternative.me/fng/?limit=1", timeout=8)
    try:
        entry = data["data"][0]
        return {
            "value": int(entry["value"]),
            "label": entry["value_classification"],
        }
    except Exception:
        return {"value": 50, "label": "Neutral"}


def get_btc_dominance() -> float | None:
    """BTC market dominance % from CoinGecko global endpoint."""
    data = _get("https://api.coingecko.com/api/v3/global", timeout=8)
    try:
        return round(data["data"]["market_cap_percentage"]["btc"], 1)
    except Exception:
        return None


# ── DexScreener enrichment ─────────────────────────────────────────────────────

# Map CoinGecko symbol → DexScreener search query (some symbols need help)
_DEX_SYMBOL_MAP: dict[str, str] = {
    "BNB": "WBNB",   # BNB is wrapped on DEXes
}

def _parse_dex_pair(pair: dict) -> dict:
    """Extract the fields we care about from one DexScreener pair result."""
    txns = pair.get("txns", {})
    vol  = pair.get("volume", {})
    pc   = pair.get("priceChange", {})

    buys_24h  = txns.get("h24", {}).get("buys",  0)
    sells_24h = txns.get("h24", {}).get("sells", 0)
    buys_1h   = txns.get("h1", {}).get("buys",   0)
    sells_1h  = txns.get("h1", {}).get("sells",  0)
    buys_6h   = txns.get("h6", {}).get("buys",   0)
    sells_6h  = txns.get("h6", {}).get("sells",  0)

    bsr_24h = round(buys_24h / sells_24h, 2) if sells_24h > 0 else 0
    bsr_1h  = round(buys_1h  / sells_1h,  2) if sells_1h  > 0 else 0

    return {
        "dex_name":       pair.get("dexId",     ""),
        "chain":          pair.get("chainId",   ""),
        "pair_label":     pair.get("baseToken", {}).get("symbol", "") + "/" +
                          pair.get("quoteToken",{}).get("symbol", ""),
        "liquidity_usd":  pair.get("liquidity", {}).get("usd", 0) or 0,
        "vol_5m":         vol.get("m5",  0) or 0,
        "vol_1h":         vol.get("h1",  0) or 0,
        "vol_6h":         vol.get("h6",  0) or 0,
        "vol_24h":        vol.get("h24", 0) or 0,
        "buys_24h":       buys_24h,
        "sells_24h":      sells_24h,
        "bsr_24h":        bsr_24h,
        "buys_1h":        buys_1h,
        "sells_1h":       sells_1h,
        "bsr_1h":         bsr_1h,
        "buys_6h":        buys_6h,
        "sells_6h":       sells_6h,
        "pc_5m":          pc.get("m5",  0) or 0,
        "pc_1h":          pc.get("h1",  0) or 0,
        "pc_6h":          pc.get("h6",  0) or 0,
        "pc_24h":         pc.get("h24", 0) or 0,
    }


def get_dexscreener_batch(symbols: list[str]) -> dict[str, dict]:
    """
    Fetch DexScreener data for each symbol.  For each symbol, pick the
    highest-liquidity USD-quoted pair from the search results.
    Returns {SYMBOL: dex_data_dict, ...}.
    Rate limit: 300 req/min — fine for ≤15 symbols.
    """
    out: dict[str, dict] = {}
    quote_tokens = {"USDT", "USDC", "WETH", "WBNB", "WSOL", "USD", "DAI", "BUSD"}

    for sym in symbols:
        query = _DEX_SYMBOL_MAP.get(sym, sym)
        data = _get(f"https://api.dexscreener.com/latest/dex/search?q={query}", timeout=10)
        if not data or not isinstance(data.get("pairs"), list):
            continue

        # Filter to USD-quoted pairs, then pick highest liquidity
        candidates = []
        for p in data["pairs"]:
            base_sym  = p.get("baseToken",  {}).get("symbol", "").upper()
            quote_sym = p.get("quoteToken", {}).get("symbol", "").upper()
            liq = (p.get("liquidity") or {}).get("usd", 0) or 0

            # Match: base must match our symbol, quote must be a USD-ish token
            if base_sym == sym and quote_sym in quote_tokens and liq > 0:
                candidates.append((liq, p))

        if not candidates:
            continue

        # Pick highest liquidity pair
        candidates.sort(key=lambda x: x[0], reverse=True)
        best_pair = candidates[0][1]
        out[sym] = _parse_dex_pair(best_pair)

    log.info(f"[crypto] DexScreener: enriched {len(out)}/{len(symbols)} symbols")
    return out


# ── 4-hour technicals (MACD + EMA stack) ─────────────────────────────────────

# Some CG symbols don't match yfinance tickers directly
_YF_OVERRIDE: dict[str, str] = {
    "AVAX": "AVAX-USD", "MATIC": "MATIC-USD", "DOT": "DOT-USD",
}


def _calc_ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _detect_fractals(high: pd.Series, low: pd.Series, n: int = 2) -> tuple[list, list]:
    """
    Williams Fractals (5-bar pattern, n=2 lookback each side).
    Up fractal (resistance): High[i] > all n neighbours' highs.
    Down fractal (support):  Low[i]  < all n neighbours' lows.
    Returns (up_fractals, down_fractals) as lists of (index_pos, price).
    """
    up_fractals: list[tuple[int, float]]   = []
    down_fractals: list[tuple[int, float]] = []

    for i in range(n, len(high) - n):
        # Up fractal — this bar's high is higher than all 2n neighbours
        if all(high.iloc[i] > high.iloc[i - j] for j in range(1, n + 1)) and \
           all(high.iloc[i] > high.iloc[i + j] for j in range(1, n + 1)):
            up_fractals.append((i, float(high.iloc[i])))

        # Down fractal — this bar's low is lower than all 2n neighbours
        if all(low.iloc[i] < low.iloc[i - j] for j in range(1, n + 1)) and \
           all(low.iloc[i] < low.iloc[i + j] for j in range(1, n + 1)):
            down_fractals.append((i, float(low.iloc[i])))

    return up_fractals, down_fractals


def get_4h_technicals(symbols: list[str]) -> dict[str, dict]:
    """
    Download 1h OHLCV from yfinance, resample to 4h candles, then compute:
      - MACD (12, 26, 9) with golden/death cross detection
      - EMA stack (5, 8, 13, 20, 50) alignment
      - Williams Fractals (5-bar) for S/R and breakout detection
    Returns {SYMBOL: technicals_dict, ...}.
    """
    if not symbols:
        return {}

    # Map cg symbol → EODHD crypto symbol (BTC-USD.CC, ETH-USD.CC, etc.)
    eod_map: dict[str, str] = {}  # eod_ticker → cg_symbol
    for sym in symbols:
        eod_map[f"{sym}-USD.CC"] = sym

    out: dict[str, dict] = {}

    import eodhd_client as _eod
    import pandas as _pd
    for eod_tick, cg_sym in eod_map.items():
        try:
            # Pass full suffixed symbol (e.g. "BTC-USD.CC") so the client routes correctly
            rows = _eod.intraday(eod_tick, interval="1h")
            if not rows:
                continue
            df = _pd.DataFrame(rows)
            ts_col = "datetime" if "datetime" in df.columns else "timestamp"
            if ts_col not in df.columns:
                continue
            df[ts_col] = _pd.to_datetime(df[ts_col])
            df = df.set_index(ts_col).sort_index()
            df = df.rename(columns={"open":"Open","high":"High","low":"Low","close":"Close","volume":"Volume"})
            df = df.dropna(subset=["Close"])
            if len(df) < 60:
                continue

            # Resample 1h → 4h
            df4 = df.resample("4h").agg({
                "Open": "first", "High": "max", "Low": "min",
                "Close": "last", "Volume": "sum",
            }).dropna()

            if len(df4) < 30:
                continue

            close = df4["Close"]

            # ── MACD (12, 26, 9) ──
            ema12 = _calc_ema(close, 12)
            ema26 = _calc_ema(close, 26)
            macd_line   = ema12 - ema26
            signal_line = _calc_ema(macd_line, 9)
            histogram   = macd_line - signal_line

            macd_now   = float(macd_line.iloc[-1])
            signal_now = float(signal_line.iloc[-1])
            hist_now   = float(histogram.iloc[-1])
            hist_prev  = float(histogram.iloc[-2]) if len(histogram) > 1 else 0.0

            # Cross detection — scan last 3 bars
            golden_cross = False
            death_cross  = False
            cross_bars_ago = 0
            for offset in range(-3, 0):
                idx = offset
                prev_idx = offset - 1
                if prev_idx < -len(macd_line):
                    continue
                m_now = macd_line.iloc[idx]
                m_prev = macd_line.iloc[prev_idx]
                s_now = signal_line.iloc[idx]
                s_prev = signal_line.iloc[prev_idx]
                if m_now > s_now and m_prev <= s_prev:
                    golden_cross = True
                    cross_bars_ago = abs(offset)
                if m_now < s_now and m_prev >= s_prev:
                    death_cross = True
                    cross_bars_ago = abs(offset)

            macd_above_zero = macd_now > 0
            hist_expanding  = abs(hist_now) > abs(hist_prev)
            hist_positive   = hist_now > 0

            # ── EMAs (5, 8, 13, 20, 50) ──
            ema_spans = [5, 8, 13, 20, 50]
            ema_vals  = {sp: float(_calc_ema(close, sp).iloc[-1]) for sp in ema_spans}
            price_now = float(close.iloc[-1])

            ordered = [ema_vals[sp] for sp in ema_spans]
            bullish_stack = (price_now >= ordered[0] and
                            all(ordered[i] >= ordered[i + 1]
                                for i in range(len(ordered) - 1)))
            bearish_stack = (price_now <= ordered[0] and
                            all(ordered[i] <= ordered[i + 1]
                                for i in range(len(ordered) - 1)))
            emas_above = sum(1 for v in ordered if price_now > v)

            # EMA 5/13 short-term cross
            e5s  = _calc_ema(close, 5)
            e13s = _calc_ema(close, 13)
            ema_golden = (float(e5s.iloc[-1]) > float(e13s.iloc[-1]) and
                          float(e5s.iloc[-2]) <= float(e13s.iloc[-2]))

            # ── Williams Fractals (5-bar) ──
            up_fractals, down_fractals = _detect_fractals(df4["High"], df4["Low"])

            # Most recent fractal levels
            frac_high = up_fractals[-1][1] if up_fractals else None      # resistance
            frac_low  = down_fractals[-1][1] if down_fractals else None  # support

            # Price position vs fractal levels
            fractal_breakout     = frac_high is not None and price_now > frac_high
            fractal_support_test = (frac_low is not None and
                                    abs(price_now - frac_low) / frac_low < 0.02)
            fractal_breakdown    = frac_low is not None and price_now < frac_low

            if fractal_breakout:
                fractal_signal = "BREAKOUT"
            elif fractal_support_test:
                fractal_signal = "SUPPORT TEST"
            elif fractal_breakdown:
                fractal_signal = "BREAKDOWN"
            elif frac_high and frac_low:
                fractal_signal = "BETWEEN S/R"
            else:
                fractal_signal = "NO DATA"

            # Count recent fractals for trend context (last 20 bars)
            recent_up   = sum(1 for pos, _ in up_fractals if pos >= len(df4) - 20)
            recent_down = sum(1 for pos, _ in down_fractals if pos >= len(df4) - 20)

            # ── Summary signals ──
            if golden_cross:
                macd_signal = "GOLDEN CROSS"
            elif death_cross:
                macd_signal = "DEATH CROSS"
            elif macd_now > signal_now and hist_expanding and hist_positive:
                macd_signal = "BULLISH MOMENTUM"
            elif macd_now > signal_now:
                macd_signal = "BULLISH"
            elif macd_now < signal_now and hist_expanding and not hist_positive:
                macd_signal = "BEARISH MOMENTUM"
            elif macd_now < signal_now:
                macd_signal = "BEARISH"
            else:
                macd_signal = "NEUTRAL"

            if bullish_stack:
                ema_signal = "BULLISH STACK"
            elif bearish_stack:
                ema_signal = "BEARISH STACK"
            elif emas_above >= 4:
                ema_signal = "MOSTLY BULLISH"
            elif emas_above <= 1:
                ema_signal = "MOSTLY BEARISH"
            else:
                ema_signal = "MIXED"

            out[cg_sym] = {
                "macd":            round(macd_now, 6),
                "signal":          round(signal_now, 6),
                "histogram":       round(hist_now, 6),
                "golden_cross":    golden_cross,
                "death_cross":     death_cross,
                "cross_bars_ago":  cross_bars_ago,
                "macd_above_zero": macd_above_zero,
                "hist_expanding":  hist_expanding,
                "hist_positive":   hist_positive,
                "macd_signal":     macd_signal,
                "ema5":  round(ema_vals[5],  4),
                "ema8":  round(ema_vals[8],  4),
                "ema13": round(ema_vals[13], 4),
                "ema20": round(ema_vals[20], 4),
                "ema50": round(ema_vals[50], 4),
                "bullish_stack":   bullish_stack,
                "bearish_stack":   bearish_stack,
                "emas_above":      emas_above,
                "ema_signal":      ema_signal,
                "ema_golden":      ema_golden,
                # Fractals
                "fractal_high":        frac_high,
                "fractal_low":         frac_low,
                "fractal_breakout":    fractal_breakout,
                "fractal_support_test": fractal_support_test,
                "fractal_breakdown":   fractal_breakdown,
                "fractal_signal":      fractal_signal,
                "recent_up_fractals":  recent_up,
                "recent_down_fractals": recent_down,
            }

        except Exception as e:
            log.debug(f"[crypto] 4h technicals for {cg_sym} failed: {e}")
            continue

    log.info(f"[crypto] 4h technicals: {len(out)}/{len(symbols)} symbols computed")
    return out


# ── Filters ────────────────────────────────────────────────────────────────────

def _is_stablecoin(coin: dict) -> bool:
    sym  = coin.get("symbol", "").lower()
    name = coin.get("name", "").lower()
    if sym in STABLECOINS:
        return True
    # catch names like "USD Coin", "TrueUSD", "Pax Dollar"
    stable_words = ["usd coin", "dollar", "trueusd", "pax", "tether"]
    return any(w in name for w in stable_words)


def _is_wrapped(coin: dict) -> bool:
    sym  = coin.get("symbol", "").lower()
    name = coin.get("name", "").lower()
    return sym in WRAPPED_SYMBOLS or any(kw in name for kw in WRAPPED_KEYWORDS)


def _gate(coin: dict) -> list[str]:
    """Return list of rejection reasons. Empty list = passes all gates."""
    reasons: list[str] = []

    if _is_stablecoin(coin):
        return ["Stablecoin"]
    if _is_wrapped(coin):
        return ["Wrapped / synthetic token"]
    if coin.get("id", "") in MEME_COINS:
        return ["Meme coin — no utility or fundamentals"]

    mcap = coin.get("market_cap") or 0
    vol  = coin.get("total_volume") or 0
    d7   = coin.get("price_change_percentage_7d_in_currency") or 0.0
    d30  = coin.get("price_change_percentage_30d_in_currency") or 0.0

    # Quality floor — $5B cap filters out most speculative small-caps
    if mcap < 5_000_000_000:
        reasons.append(f"Market cap ${mcap / 1e9:.1f}B < $5B")

    if vol < 50_000_000:
        reasons.append(f"24h volume ${vol / 1e6:.0f}M < $50M")

    if mcap > 0 and vol / mcap < 0.015:
        reasons.append(f"Vol/MCap {vol / mcap * 100:.1f}% < 1.5% — zombie")

    # Parabolic momentum gates — already extended, not a swing entry
    if d7 > 25:
        reasons.append(f"7d +{d7:.0f}% — parabolic, wait for base to form")
    if d30 > 60:
        reasons.append(f"30d +{d30:.0f}% — already extended, risk/reward unfavorable")

    return reasons


# ── Scoring ────────────────────────────────────────────────────────────────────

def _score_coin(
    coin: dict,
    spot: dict[str, dict],
    funding: dict[str, float],
    technicals: dict | None = None,
) -> dict:
    """
    Score one coin across 4 pillars (100 pts) + funding overlay.
    Pillars: Momentum(25) + Volume(20) + Structure(20) + Technical(35)
    Technical pillar uses MACD + EMA on 4h timeframe for buy/sell decisions.
    """
    cg_sym    = coin.get("symbol", "").upper()
    b_sym     = cg_sym + "USDT"
    bdata     = spot.get(b_sym, {})
    fund_rate = funding.get(b_sym)
    tech      = technicals or {}

    price   = coin.get("current_price") or 0
    mcap    = coin.get("market_cap") or 1
    vol_cg  = coin.get("total_volume") or 0

    # Prefer Binance quoteVolume (more accurate USDT volume)
    vol_usd = float(bdata.get("quoteVolume", vol_cg) or vol_cg)

    d24 = coin.get("price_change_percentage_24h_in_currency") \
          or coin.get("price_change_percentage_24h") or 0.0
    d7  = coin.get("price_change_percentage_7d_in_currency") or 0.0
    d30 = coin.get("price_change_percentage_30d_in_currency") or 0.0

    score = 0
    pillar: dict[str, dict] = {}

    # ── Pillar 1: Momentum (25 pts) ──────────────────────────────────────────
    if   -3  <= d24 <= 3:  p24 = 10
    elif  3  <  d24 <= 8:  p24 = 5
    elif -8  <= d24 < -3:  p24 = 3
    else:                  p24 = 0

    p7d  = 5 if d7  >  2 else (3 if d7  > 0 else 0)
    p30d = 5 if d30 >  5 else (3 if d30 > 0 else 0)
    rsi_proxy = 5 if -5 < d7 < 18 else 0

    mom = min(25, p24 + p7d + p30d + rsi_proxy)
    score += mom
    pillar["momentum"] = {"score": mom, "max": 25,
                           "d24h": round(d24, 2), "d7d": round(d7, 2),
                           "d30d": round(d30, 2)}

    # ── Pillar 2: Volume (20 pts) ─────────────────────────────────────────────
    vol_mcap = vol_usd / mcap if mcap else 0
    rvol     = vol_mcap / 0.05

    rvol_pts = 10 if rvol > 1.5 else (7 if rvol > 1.0 else (4 if rvol > 0.6 else 0))
    vol_trend = 10 if (d7 > 0 and vol_mcap > 0.05) else (5 if vol_mcap > 0.03 else 0)

    vol = min(20, rvol_pts + vol_trend)
    score += vol
    pillar["volume"] = {"score": vol, "max": 20,
                         "vol_usd": round(vol_usd), "vol_mcap_pct": round(vol_mcap * 100, 1),
                         "rvol": round(rvol, 2)}

    # ── Pillar 3: Structure (20 pts) ──────────────────────────────────────────
    ath_pct  = coin.get("ath_change_percentage") or -50
    high_24h = coin.get("high_24h") or price
    low_24h  = coin.get("low_24h")  or price

    if   -30 <= ath_pct <= -10: ath_pts = 10
    elif -50 <= ath_pct <  -30: ath_pts = 7
    elif  -10 < ath_pct <=   0: ath_pts = 3
    else:                        ath_pts = 0

    rng = ((high_24h - low_24h) / low_24h * 100) if low_24h > 0 else 10
    rng_pts = 6 if rng < 5 else (4 if rng < 8 else (2 if rng < 12 else 0))

    if high_24h > low_24h:
        day_pos = (price - low_24h) / (high_24h - low_24h)
    else:
        day_pos = 0.5
    pos_pts = 4 if day_pos >= 0.75 else (2 if day_pos >= 0.5 else 0)

    struct = min(20, ath_pts + rng_pts + pos_pts)
    score += struct
    pillar["structure"] = {"score": struct, "max": 20,
                            "ath_pct": round(ath_pct, 1),
                            "day_range_pct": round(rng, 1),
                            "day_pos_pct": round(day_pos * 100)}

    # ── Pillar 4: Technical — 4h MACD + EMA (35 pts) ─────────────────────────
    macd_pts = 0
    ema_pts  = 0
    macd_signal_str = tech.get("macd_signal", "NO DATA")
    ema_signal_str  = tech.get("ema_signal",  "NO DATA")

    if tech:
        # MACD scoring (20 pts max)
        if tech.get("golden_cross"):
            macd_pts = 20
        elif macd_signal_str == "BULLISH MOMENTUM":
            macd_pts = 15 if tech.get("macd_above_zero") else 12
        elif macd_signal_str == "BULLISH":
            macd_pts = 12 if tech.get("macd_above_zero") else 8
        elif macd_signal_str == "NEUTRAL":
            macd_pts = 5
        elif macd_signal_str in ("BEARISH", "BEARISH MOMENTUM"):
            macd_pts = 2
        elif tech.get("death_cross"):
            macd_pts = 0

        # EMA stack scoring (15 pts max)
        if tech.get("bullish_stack"):
            ema_pts = 15
        elif tech.get("emas_above", 0) >= 4:
            ema_pts = 10
        elif tech.get("emas_above", 0) >= 3:
            ema_pts = 7
        elif tech.get("emas_above", 0) >= 2:
            ema_pts = 4
        else:
            ema_pts = 0

        # Bonus: EMA 5/13 golden cross on top of bullish MACD
        if tech.get("ema_golden") and macd_pts >= 8:
            ema_pts = min(15, ema_pts + 3)

    tech_score = min(35, macd_pts + ema_pts)
    score += tech_score
    pillar["technical"] = {
        "score": tech_score, "max": 35,
        "macd_pts": macd_pts, "ema_pts": ema_pts,
        "macd_signal": macd_signal_str,
        "ema_signal": ema_signal_str,
        "golden_cross": tech.get("golden_cross", False),
        "death_cross": tech.get("death_cross", False),
        "bullish_stack": tech.get("bullish_stack", False),
        "emas_above": tech.get("emas_above", 0),
        "macd_above_zero": tech.get("macd_above_zero", False),
    }

    # ── Funding overlay (±5 pts) ──────────────────────────────────────────────
    fund_pts  = 0
    fund_note = "No perp data"
    if fund_rate is not None:
        fp = fund_rate * 100
        if   -0.01 <= fp <= 0.01: fund_pts, fund_note = +5,  f"Healthy ({fp:+.3f}%)"
        elif  fp   >   0.05:      fund_pts, fund_note = -5,  f"Crowded long ({fp:+.3f}%)"
        elif  fp   <  -0.02:      fund_pts, fund_note = +3,  f"Short squeeze candidate ({fp:+.3f}%)"
        else:                     fund_pts, fund_note = +2,  f"Mild ({fp:+.3f}%)"

    score = max(0, min(100, score + fund_pts))

    # ── Fractal overlay (±3 pts) ─────────────────────────────────────────────
    frac_pts  = 0
    frac_sig  = tech.get("fractal_signal", "NO DATA")
    frac_high = tech.get("fractal_high")
    frac_low  = tech.get("fractal_low")

    if frac_sig == "BREAKOUT":
        frac_pts = +3      # price broke above resistance fractal — bullish
    elif frac_sig == "SUPPORT TEST":
        frac_pts = +2      # price testing support fractal — bounce setup
    elif frac_sig == "BREAKDOWN":
        frac_pts = -3      # price below support fractal — bearish
    # BETWEEN S/R and NO DATA = 0

    score = max(0, min(100, score + frac_pts))

    # ── Decision — driven primarily by 4h MACD ───────────────────────────────
    # Strong technical confirmation required for BUY
    if score >= 70 and macd_signal_str in ("GOLDEN CROSS", "BULLISH MOMENTUM", "BULLISH"):
        decision = "BUY"
    elif score >= 70:
        decision = "WATCH"   # score high but technicals not confirming
    elif score >= 50:
        decision = "WATCH"
    else:
        decision = "AVOID"

    # Death cross forces WATCH/AVOID regardless of score
    if tech.get("death_cross") and decision == "BUY":
        decision = "WATCH"

    # ── Category ──────────────────────────────────────────────────────────────
    cid = coin.get("id", "")
    if   cid in CORE_MAJORS:  category = "Core Major"
    elif cid in L1_PLATFORMS: category = "L1 Platform"
    elif cid in INFRA_DEFI:   category = "Infrastructure / DeFi"
    else:                      category = "Speculative Large Cap"

    # ── Qualifying note ───────────────────────────────────────────────────────
    notes = []
    if tech.get("golden_cross"):
        notes.append("4h MACD golden cross")
    if tech.get("death_cross"):
        notes.append("4h MACD death cross")
    if tech.get("bullish_stack"):
        notes.append("EMA stack aligned bullish")
    if frac_sig == "BREAKOUT":
        notes.append("fractal breakout")
    elif frac_sig == "SUPPORT TEST":
        notes.append("testing fractal support")
    elif frac_sig == "BREAKDOWN":
        notes.append("fractal support broken")
    if d7  >  5:        notes.append(f"7d +{d7:.0f}%")
    if d30 > 10:        notes.append(f"30d +{d30:.0f}%")
    if rvol > 1.3:      notes.append(f"RVOL {rvol:.1f}x")
    if -25 <= ath_pct <= -10:
        notes.append(f"base {abs(ath_pct):.0f}% below ATH")
    if rng < 5:         notes.append(f"tight {rng:.1f}% range")
    if fund_pts > 0:    notes.append(fund_note)
    note = " — ".join(notes) if notes else "Passes all gates"

    return {
        "id":           cid,
        "name":         coin.get("name", cg_sym),
        "symbol":       cg_sym,
        "binance_sym":  b_sym,
        "image":        coin.get("image", ""),
        "rank":         coin.get("market_cap_rank", 0),
        "price":        price,
        "market_cap":   mcap,
        "vol_24h":      round(vol_usd),
        "d24h":         round(d24, 2),
        "d7d":          round(d7,  2),
        "d30d":         round(d30, 2),
        "ath_pct":      round(ath_pct, 1),
        "day_range":    round(rng, 1),
        "rvol":         round(rvol, 2),
        "fund_rate":    round(fund_rate * 100, 4) if fund_rate is not None else None,
        "fund_note":    fund_note,
        "score":        score,
        "decision":     decision,
        "category":     category,
        "note":         note,
        "pillar":       pillar,
        # Technical details for HTML display
        "macd_signal":  macd_signal_str,
        "ema_signal":   ema_signal_str,
        "ema5":         tech.get("ema5"),
        "ema8":         tech.get("ema8"),
        "ema13":        tech.get("ema13"),
        "ema20":        tech.get("ema20"),
        "ema50":        tech.get("ema50"),
        # Fractals
        "fractal_signal": frac_sig,
        "fractal_high":   frac_high,
        "fractal_low":    frac_low,
    }


# ── BTC regime ─────────────────────────────────────────────────────────────────

def _btc_regime(coins: list[dict]) -> dict:
    btc = next((c for c in coins if c.get("id") == "bitcoin"), None)
    if not btc:
        return {"regime": "neutral", "d7": 0, "d30": 0, "price": 0}

    d7  = btc.get("price_change_percentage_7d_in_currency") or 0
    d30 = btc.get("price_change_percentage_30d_in_currency") or 0

    if   d7 < -10 or d30 < -20: regime = "bear"
    elif d7 >   5 and d30 > 10: regime = "bull"
    else:                         regime = "neutral"

    return {
        "regime": regime,
        "d7":     round(d7,  2),
        "d30":    round(d30, 2),
        "price":  btc.get("current_price", 0),
    }


# ── Main entry ─────────────────────────────────────────────────────────────────

def run_crypto_scan() -> dict:
    """
    Full scan pipeline. Returns bundle dict consumed by _tab_crypto() in html_generator.
    Runtime: ~3–5 seconds (3 external API calls, all fast).
    """
    log.info("[crypto] Starting scan …")
    t0 = time.time()

    coins    = get_coingecko_top100()
    spot     = get_binance_spot_tickers()
    fg       = get_fear_greed()
    btc_dom  = get_btc_dominance()
    regime   = _btc_regime(coins)

    passed:   list[dict] = []
    rejected: list[dict] = []

    for coin in coins:
        reasons = _gate(coin)
        if reasons:
            rejected.append({"coin": coin, "reasons": reasons})
        else:
            passed.append(coin)

    # Funding rates — fetch only for passed coins (OKX has no bulk endpoint)
    passed_syms_usdt = [c.get("symbol", "").upper() + "USDT" for c in passed]
    funding = get_binance_funding_rates(passed_syms_usdt)

    # ── 4h technicals (MACD + EMA) for all passed coins ──
    passed_syms = [c.get("symbol", "").upper() for c in passed]
    technicals  = get_4h_technicals(passed_syms)

    # ── Score with 4 pillars ──
    scored = [
        _score_coin(c, spot, funding, technicals.get(c.get("symbol", "").upper()))
        for c in passed
    ]
    scored.sort(key=lambda x: x["score"], reverse=True)

    # ── DexScreener enrichment — top 20 scored coins ──
    dex_syms = [r["symbol"] for r in scored[:20]]
    try:
        dex_data = get_dexscreener_batch(dex_syms)
    except Exception as de:
        log.warning(f"[crypto] DexScreener enrichment failed (non-fatal): {de}")
        dex_data = {}

    for r in scored:
        dex = dex_data.get(r["symbol"])
        if dex:
            r["dex"] = dex

    # Apply BTC bear regime override — alts become AVOID
    if regime["regime"] == "bear":
        for r in scored:
            if r["symbol"] not in ("BTC", "ETH"):
                r["decision"]        = "AVOID"
                r["regime_override"] = True

    elapsed = round(time.time() - t0, 1)
    log.info(f"[crypto] Done in {elapsed}s — {len(passed)} passed / "
             f"{len(rejected)} rejected / top score {scored[0]['score'] if scored else 0}")

    return {
        "top_picks":       scored[:15],
        "all_scored":      scored,
        "rejected":        rejected,
        "btc_regime":      regime,
        "btc_dominance":   btc_dom,
        "fear_greed":      fg,
        "run_timestamp":   datetime.now().strftime("%Y-%m-%d %H:%M"),
        "total_universe":  len(coins),
        "total_passed":    len(passed),
        "total_rejected":  len(rejected),
    }


if __name__ == "__main__":
    import json, sys
    logging.basicConfig(level=logging.INFO)
    result = run_crypto_scan()
    print(json.dumps(result["top_picks"][:5], indent=2, default=str))
