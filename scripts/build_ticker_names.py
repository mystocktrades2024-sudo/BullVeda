#!/usr/bin/env python3
"""Build a free ticker -> company-name map from Wikipedia constituent tables.

WHY: the scan feed sets `name = ticker` (no company name), so the scanner's
NAME column just repeats the TICKER. Wikipedia's index-constituent tables carry
"Symbol" + "Security/Company" columns for free — no paid data, no EODHD quota,
honoring the no-new-paid-license policy. Names rarely change, so this is cached
to cache/ticker_names.json and joined into /api/universe at serve time.

Coverage = S&P 500 + NASDAQ-100 + Dow 30 (~600 distinct names). Tickers outside
these indices fall back to the symbol (honest).

Run: python3 scripts/build_ticker_names.py   (idempotent; safe to re-run weekly)
"""
from __future__ import annotations
import json, sys, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "cache" / "ticker_names.json"
HDR = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}

# (url, ticker-column candidates, name-column candidates)
SOURCES = [
    ("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", ["Symbol"], ["Security"]),
    ("https://en.wikipedia.org/wiki/List_of_S%26P_400_companies", ["Symbol"], ["Security", "Company"]),
    ("https://en.wikipedia.org/wiki/List_of_S%26P_600_companies", ["Symbol"], ["Security", "Company"]),
    ("https://en.wikipedia.org/wiki/Nasdaq-100", ["Ticker", "Symbol"], ["Company", "Company name"]),
    ("https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average", ["Symbol"], ["Company"]),
]


def _norm_ticker(t: str) -> str:
    # Wikipedia uses dots (BRK.B); the engine uses the same — keep, just clean.
    return re.sub(r"\s+", "", str(t)).upper().replace("​", "")


def build() -> dict:
    import requests, pandas as pd
    from io import StringIO
    names: dict[str, str] = {}
    for url, tcols, ncols in SOURCES:
        try:
            html = requests.get(url, headers=HDR, timeout=20).text
            tables = pd.read_html(StringIO(html))
        except Exception as e:
            print(f"  ! {url} fetch/parse failed: {e}", file=sys.stderr)
            continue
        added = 0
        for df in tables:
            cols = {str(c).strip(): c for c in df.columns}
            tcol = next((cols[c] for c in tcols if c in cols), None)
            ncol = next((cols[c] for c in ncols if c in cols), None)
            if tcol is None or ncol is None:
                continue
            for _, row in df.iterrows():
                tk = _norm_ticker(row[tcol])
                nm = str(row[ncol]).strip()
                if tk and nm and tk.upper() != nm.upper() and len(tk) <= 8 and nm.lower() != "nan":
                    names.setdefault(tk, nm)   # first source wins
                    added += 1
            break  # first matching table per page is the constituents table
        print(f"  + {url.split('/')[-1]}: +{added} names (total {len(names)})")
    return names


def main():
    names = build()
    if not names:
        print("ERROR: no names built — leaving existing cache untouched", file=sys.stderr)
        sys.exit(1)
    payload = {"_built_at": None, "count": len(names), "source": "wikipedia_constituents", "names": names}
    OUT.write_text(json.dumps(payload, indent=0))
    print(f"✓ wrote {len(names)} ticker→name pairs → {OUT}")
    # show a few samples
    for tk in list(names)[:5]:
        print(f"    {tk} → {names[tk]}")


if __name__ == "__main__":
    main()
