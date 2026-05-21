#!/usr/bin/env python3
"""Tier-4 thematic universe layers:

  A) ETF HOLDINGS — pulls the holdings of curated sector / theme ETFs
     (XLK / XLF / XBI / SMH / ARKK / IBIT etc.) via EODHD's
     etf_fundamentals endpoint. Each ETF returns ~50 holdings. Use to
     capture thematic exposure that may overflow the cap-weighted S&P /
     Russell base — e.g., XBI holds 100+ biotechs many of which are below
     R2000 inclusion thresholds.

  B) CRYPTO-ADJACENT EQUITIES — hardcoded curated list of US-listed
     crypto-exposure names (COIN, MARA, RIOT, MSTR, CLSK, IBIT, FBTC,
     etc.). Most are already in R2000 but a hardcoded list ensures complete
     coverage even when index reconstitution lags or names get demoted.

  C) EODHD SCREENER — dynamic universe via EODHD's screener endpoint.
     Pulls US-listed names matching custom filters
     (market_cap > $500M AND avgvol > 500K AND refund_5d_p > 3% etc.).
     Generates a `momentum`-flavored watchlist that updates daily.

Output: cache/universe_thematic.json
  {
    "_meta": {generated_at, n_etf_holdings, n_crypto, n_screener, total},
    "etf_holdings": {ETF: [tickers]},   # per-ETF breakdown
    "etf_holdings_union": [tickers],    # deduped union of all ETF holdings
    "crypto_adjacent": [tickers],
    "screener_momentum": [tickers],
    "all_thematic": [tickers],          # full union for universe wire-up
  }

Wired into swing_trade.py via _load_universe_thematic() (next).
"""
from __future__ import annotations
import datetime
import json
import sys
from pathlib import Path

BASE = Path(__file__).parent.parent
OUT = BASE / "cache" / "universe_thematic.json"
sys.path.insert(0, str(BASE))


# Curated thematic ETFs — sector + factor + thematic. Holdings collectively
# cover ~500-800 unique names with high overlap with S&P/Russell base.
# Tune by adding/removing tickers from this list.
ETF_UNIVERSE = [
    # Sector SPDRs (9 industries)
    "XLK",   # Technology
    "XLF",   # Financials
    "XLV",   # Healthcare
    "XLI",   # Industrials
    "XLE",   # Energy
    "XLB",   # Materials
    "XLY",   # Consumer Discretionary
    "XLP",   # Consumer Staples
    "XLU",   # Utilities
    "XLRE",  # Real Estate
    "XLC",   # Communication Services
    # Sub-industry / thematic
    "SMH",   # Semiconductors
    "XBI",   # Biotech (broad ~100 names, many below R2000 thresholds)
    "ARKK",  # ARK Innovation (disruptive growth)
    "ARKG",  # ARK Genomic Revolution
    "ARKW",  # ARK Next-Gen Internet
    "ICLN",  # Clean Energy
    "JETS",  # Airlines
    "ITA",   # Aerospace & Defense
    "KRE",   # Regional Banks (catches small-cap banks)
    "IYR",   # Real Estate
    "GDX",   # Gold Miners
    # Crypto-ETFs that hold equities (some are spot crypto, those return 0 equities)
    # IBIT/FBTC are spot bitcoin, NOT equity holdings — included in crypto_adjacent list instead
]


# Hardcoded crypto-adjacent equity universe. Mostly R2000 candidates but
# this hardcoded list ensures coverage even when:
#   - new crypto IPOs (e.g., Circle, eToro) hit before Russell reconstitution
#   - existing names get demoted from R2000 mid-year
#   - the index methodology excludes certain structures (foreign domicile,
#     dual-class shares, etc.)
CRYPTO_ADJACENT = [
    # Pure-play crypto exchanges / brokers
    "COIN",   # Coinbase
    # Bitcoin treasury companies
    "MSTR",   # MicroStrategy
    # Public miners
    "MARA",   # Marathon Digital
    "RIOT",   # Riot Platforms
    "CLSK",   # CleanSpark
    "CIFR",   # Cipher Mining
    "HUT",    # Hut 8
    "BITF",   # Bitfarms
    "BTBT",   # Bit Digital
    "HIVE",   # HIVE Digital
    "WULF",   # TeraWulf
    "IREN",   # Iris Energy
    "APLD",   # Applied Digital
    "CORZ",   # Core Scientific
    # Crypto-infrastructure / payments
    "PYPL",   # PayPal (crypto rails)
    "SQ",     # Block (crypto rails)
    # Spot Bitcoin / Ether ETFs (mostly large enough for S&P but listed for completeness)
    "IBIT",   # iShares Bitcoin Trust
    "FBTC",   # Fidelity Wise Origin Bitcoin
    "GBTC",   # Grayscale Bitcoin
    "ETHE",   # Grayscale Ethereum
]


# EODHD screener pulls US-listed momentum candidates. Conservative filters:
#   - market_cap >= $500M (skip micro-caps)
#   - avgvol_200d >= 500K (liquidity floor)
#   - refund_5d_p >= 3% (5-day return at least +3% — momentum filter)
# Returns up to SCREENER_LIMIT names per scan.
SCREENER_LIMIT = 200
SCREENER_FILTERS = [
    ["market_capitalization", ">=", 500_000_000],
    ["avgvol_200d", ">=", 500_000],
    ["refund_5d_p", ">=", 3.0],
    ["exchange", "=", "us"],   # US-listed only
]


def _build_etf_holdings() -> dict:
    """Returns {ETF_SYMBOL: [list of US tickers in that ETF]}. Skips ETFs
    with no equity holdings (spot bitcoin trusts return empty)."""
    import eodhd_client as ec
    by_etf: dict = {}
    for etf in ETF_UNIVERSE:
        try:
            f = ec.etf_fundamentals(etf) or {}
            holdings = (f.get("ETF_Data") or {}).get("Holdings") or {}
            tickers = []
            for h_key, h in holdings.items():
                if not isinstance(h, dict):
                    continue
                code = (h.get("Code") or "").upper()
                ex = (h.get("Exchange") or "").upper()
                if not code:
                    continue
                # US-listed only
                if ex not in ("US", "NASDAQ", "NYSE", "AMEX", "BATS", "NYSE ARCA"):
                    continue
                # Skip cash / non-equity placeholders
                if code in ("CASH", "USD", "N/A") or len(code) > 5:
                    continue
                tickers.append(code)
            if tickers:
                by_etf[etf] = sorted(set(tickers))
        except Exception as e:
            print(f"[thematic] ETF {etf} failed: {e}", file=sys.stderr)
    return by_etf


def _build_screener_momentum() -> list[str]:
    """EODHD screener API · US momentum filter."""
    import eodhd_client as ec
    try:
        result = ec.screener(filters=SCREENER_FILTERS, limit=SCREENER_LIMIT)
        if not result:
            return []
        rows = result.get("data") if isinstance(result, dict) else result
        if not isinstance(rows, list):
            return []
        out = []
        for r in rows:
            if not isinstance(r, dict):
                continue
            code = (r.get("code") or "").upper().strip()
            ex = (r.get("exchange") or "").upper().strip()
            # Defense-in-depth: enforce US-listed even if filter slipped
            if not code or len(code) > 5:
                continue
            if ex and ex not in ("US", "NASDAQ", "NYSE", "AMEX", "BATS", "NYSE ARCA"):
                continue
            out.append(code)
        return sorted(set(out))
    except Exception as e:
        print(f"[thematic] screener failed: {e}", file=sys.stderr)
        return []


def main() -> int:
    print(f"[thematic] building ETF holdings ({len(ETF_UNIVERSE)} ETFs) + crypto + screener …", file=sys.stderr)

    etf_holdings = _build_etf_holdings()
    etf_union = sorted({t for v in etf_holdings.values() for t in v})
    print(f"[thematic]   ETF holdings: {len(etf_holdings)} ETFs · {len(etf_union)} unique tickers", file=sys.stderr)

    crypto = sorted(set(CRYPTO_ADJACENT))
    print(f"[thematic]   Crypto-adjacent: {len(crypto)} hardcoded tickers", file=sys.stderr)

    screener = _build_screener_momentum()
    print(f"[thematic]   Screener momentum: {len(screener)} tickers", file=sys.stderr)

    all_thematic = sorted(set(etf_union) | set(crypto) | set(screener))

    out = {
        "_meta": {
            "generated_at": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "n_etf_holdings": len(etf_union),
            "n_crypto": len(crypto),
            "n_screener": len(screener),
            "total": len(all_thematic),
            "etfs_scanned": len(etf_holdings),
            "screener_filters": SCREENER_FILTERS,
        },
        "etf_holdings": etf_holdings,
        "etf_holdings_union": etf_union,
        "crypto_adjacent": crypto,
        "screener_momentum": screener,
        "all_thematic": all_thematic,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2))
    print(f"[thematic] wrote {OUT} · {len(all_thematic)} unique thematic tickers")
    return 0


if __name__ == "__main__":
    sys.exit(main())
