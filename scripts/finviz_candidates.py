#!/usr/bin/env python3
"""finviz_candidates.py — per-sleeve candidate generation via Finviz Elite screener.

The untapped lever from docs/data_loading_diagram.html Tab ⑤ section A: instead
of listing index members and scoring *everything*, ask the Finviz Elite export
screener (server-side `f=` filters) for each sleeve's actual daily movers in ONE
CSV call each — including off-index small-caps the index-member universe misses.

CRITICAL — Open Risk #7 / CLAUDE.md principle 6 (survivorship) + 19 (realism):
  A Finviz preset is a CURRENT SNAPSHOT. It is un-backtestable look-ahead data.
  These functions ONLY produce a CANDIDATE TICKER LIST. They must NEVER gate or
  decide a trade by themselves. The scan's existing 5-pillar scoring + the sleeve
  detectors still confirm the signal on EODHD bars. Finviz widens the funnel; it
  never closes it. See swing_trade.py universe-assembly wiring + the
  `universe.finviz_candidate_gen` flag (default FALSE).

Each function = ONE Finviz Elite export call (the export endpoint returns the
entire filtered result set in a single CSV — it ignores `r=` paging).

Filter codes (verified live 2026-06-09 against elite.finviz.com/export.ashx):
  ta_rsi_os30        RSI(14) < 30                    [VERIFIED]
  ta_rsi_40to60      RSI(14) 40–60                   [VERIFIED]
  ta_sma20_pa        price ABOVE SMA20               [VERIFIED]
  ta_sma50_pa        price ABOVE SMA50               [VERIFIED]
  ta_sma200_pa       price ABOVE SMA200              [VERIFIED]
  ta_perf_4wup       perf (1 month) up               [VERIFIED]
  ta_gap_u           gap up (any positive gap)       [VERIFIED]
  sh_relvol_o1.5     relative volume > 1.5           [VERIFIED]
  sh_relvol_o2       relative volume > 2             [VERIFIED]
  sh_avgvol_o500     avg volume > 500K               [VERIFIED]
  sh_price_o5        price > $5                       [VERIFIED]
  sh_short_o20       short float > 20%               [VERIFIED]
  sh_insiderown_o20  insider ownership > 20%         [VERIFIED]
  ta_beta_u0.8       beta < 0.8                       [VERIFIED]
  sec_utilities      sector = Utilities              [VERIFIED]
  sec_consumerdefensive  sector = Consumer Defensive [VERIFIED]
  ind_exchangetradedfund  asset type = ETF           [VERIFIED]
  ind_stocksonly     asset type = common stock       [VERIFIED]
  earningsdate_thisweek   earnings this week         [VERIFIED]
  earningsdate_nextweek   earnings next week         [VERIFIED]
  an_recom_buybetter analyst recom buy-or-better     [VERIFIED]

UNSURE / proxy codes (documented, not exact intent):
  * Insider Cluster: Finviz exposes NO screener `f=` code for "≥3 insiders
    bought in 30d" — the insider data lives on a separate HTML page with no CSV
    export (tested it_latestbuys / it_insidertransactions_pos → both ignored,
    fell back to full 11k universe). We use `sh_insiderown_o20` (high insider
    ownership) as the closest documented PROXY. True cluster-buy detection
    already lives in scripts/build_universe_insider_cluster.py (page scrape).
  * ESP Play: "analyst upgrades + EPS-rev+" has no single export code; we use
    `an_recom_buybetter` + `earningsdate_nextweek` as the documented proxy.
    True Zacks ESP>0 + Rank≤3 comes from the Zacks layer, not Finviz.
  * PEAD: there is no "EPS surprise > 0" screener code; we approximate the
    post-earnings drift candidate with earnings-this-week + gap-up + RVOL>2.
    The actual EPS-surprise confirmation happens in the PEAD detector on bars.

Usage:
  python3 scripts/finviz_candidates.py              # print all sleeve counts + samples
  python3 scripts/finviz_candidates.py mean_reversion
"""
from __future__ import annotations

import sys
import time
from io import StringIO
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import requests  # noqa: E402

EXPORT_URL = "https://elite.finviz.com/export.ashx"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "text/csv,*/*",
    "Referer": "https://elite.finviz.com/screener.ashx",
}

# Default liquidity floors appended to every preset so we never hand the scan
# illiquid junk it would only drop later. min_price keeps it in our tradeable band.
_LIQUIDITY = ["sh_avgvol_o500", "sh_price_o5"]


def _token() -> str:
    import data_fetcher
    return data_fetcher._finviz_token()


def _screen(filters: list[str], signal: str | None = None,
            view: int = 111, limit: int | None = 300) -> list[str]:
    """Run ONE Finviz Elite export screener call. Returns an uppercase ticker list.

    NOTE: produces CANDIDATES ONLY — never a trade decision (Open Risk #7).
    """
    token = _token()
    if not token:
        return []
    params: dict = {"v": view, "f": ",".join(filters), "auth": token}
    if signal:
        params["s"] = signal
    try:
        import pandas as pd
        r = requests.get(EXPORT_URL, params=params, headers=_HEADERS, timeout=45)
        if r.status_code != 200:
            return []
        df = pd.read_csv(StringIO(r.text))
        if "Ticker" not in df.columns or df.empty:
            return []
        tickers = [str(t).upper().strip() for t in df["Ticker"].tolist() if str(t).strip()]
        # Dedup, preserve order
        seen: set[str] = set()
        out: list[str] = []
        for t in tickers:
            if t not in seen:
                seen.add(t)
                out.append(t)
        return out[:limit] if limit else out
    except Exception:
        return []


# ── Per-sleeve presets (docs Tab ⑤ section A) ──────────────────────────────
# Each returns a CANDIDATE list. Signal confirmed on EODHD bars downstream.

def mean_reversion_candidates() -> list[str]:
    """Mean Reversion: RSI<30 + price>SMA200 (oversold dip in healthy uptrend).
    Mechanism: short-term oversold mean reversion while the long trend is intact."""
    return _screen(["ta_rsi_os30", "ta_sma200_pa", *_LIQUIDITY])


def pead_candidates() -> list[str]:
    """PEAD: earnings this week + gap up + RVOL>2 (post-earnings drift candidates).
    PROXY: no EPS-surprise screener code → gap+RVOL approximates the beat-and-gap;
    actual EPS-surprise confirmation is in the PEAD detector on bars."""
    return _screen(["earningsdate_thisweek", "ta_gap_u", "sh_relvol_o2", *_LIQUIDITY])


def momentum_candidates() -> list[str]:
    """Momentum: above all SMAs + RVOL>1.5 + 1-month perf up (strength breakouts,
    incl. off-index movers). Mechanism: trend continuation on expanding volume."""
    return _screen(["ta_sma20_pa", "ta_sma50_pa", "ta_sma200_pa",
                    "sh_relvol_o1.5", "ta_perf_4wup", *_LIQUIDITY])


def insider_cluster_candidates() -> list[str]:
    """Insider Cluster: high insider ownership PROXY.
    UNSURE: Finviz has no `f=` code for '≥3 insiders bought $200K+ in 30d' (the
    insider page has no CSV export). `sh_insiderown_o20` is the closest documented
    filter. Real cluster-buy detection: scripts/build_universe_insider_cluster.py."""
    return _screen(["sh_insiderown_o20", *_LIQUIDITY])


def esp_play_candidates() -> list[str]:
    """ESP Play: analyst buy-or-better + earnings next week (pre-earnings drift).
    PROXY: true Zacks ESP>0 + Rank≤3 is computed in the Zacks layer, not Finviz."""
    return _screen(["earningsdate_nextweek", "an_recom_buybetter", *_LIQUIDITY])


def pullback_candidates() -> list[str]:
    """Pullback to Value: above SMA50 & SMA200 + RSI 40–60 (uptrend retracing to value).
    Mechanism: institutional re-add point on a pullback within an established trend."""
    return _screen(["ta_sma50_pa", "ta_sma200_pa", "ta_rsi_40to60", *_LIQUIDITY])


def defensive_candidates() -> list[str]:
    """Defensive Rotation: low-beta defensives (utilities + staples) + ETFs.
    Two screens merged: low-beta defensive equities and the ETF set (for XLU/GLD-style
    risk-off rotation leaders). Mechanism: capital rotates to low-beta in risk-off."""
    equities = _screen(["ta_beta_u0.8", "sec_utilities", *_LIQUIDITY]) \
        + _screen(["ta_beta_u0.8", "sec_consumerdefensive", *_LIQUIDITY])
    time.sleep(0.5)
    etfs = _screen(["ind_exchangetradedfund", "ta_beta_u0.8", *_LIQUIDITY])
    seen: set[str] = set()
    out: list[str] = []
    for t in equities + etfs:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def squeeze_candidates() -> list[str]:
    """Squeeze overlay: short float>20% + RVOL>2 (squeeze fuel; feeds Momentum/Special).
    Mechanism: high short interest + abnormal volume = short-covering ignition risk."""
    return _screen(["sh_short_o20", "sh_relvol_o2", *_LIQUIDITY])


# sleeve key → generator (consumed by swing_trade.py universe assembly)
SLEEVE_PRESETS = {
    "mean_reversion":  mean_reversion_candidates,
    "pead":            pead_candidates,
    "momentum":        momentum_candidates,
    "insider_cluster": insider_cluster_candidates,
    "esp_play":        esp_play_candidates,
    "pullback":        pullback_candidates,
    "defensive":       defensive_candidates,
    "squeeze":         squeeze_candidates,
}


def all_candidates(sleep_between: float = 0.6) -> dict[str, list[str]]:
    """Run every sleeve preset (one call each, fair-use spaced). Returns
    {sleeve: [tickers]}. CANDIDATES ONLY — never a trade decision (Open Risk #7)."""
    out: dict[str, list[str]] = {}
    for i, (name, fn) in enumerate(SLEEVE_PRESETS.items()):
        if i:
            time.sleep(sleep_between)
        try:
            out[name] = fn()
        except Exception:
            out[name] = []
    return out


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else None
    if which and which in SLEEVE_PRESETS:
        res = SLEEVE_PRESETS[which]()
        print(f"{which}: {len(res)} candidates")
        print("  sample:", res[:15])
    else:
        print("Finviz Elite sleeve candidate generation (CANDIDATES ONLY — never gates a trade)\n")
        res = all_candidates()
        for name, tks in res.items():
            print(f"{name:18s} {len(tks):5d} candidates  sample: {tks[:8]}")
