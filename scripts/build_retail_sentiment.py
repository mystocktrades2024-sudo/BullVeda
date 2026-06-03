#!/usr/bin/env python3
"""
build_retail_sentiment.py — free retail-sentiment scraper (Reddit/WSB + StockTwits).

No paid feed. Two free sources:
  1. Reddit r/wallstreetbets (+ r/stocks, r/options) — public .json endpoints.
     Extracts $TICKER / ALLCAPS mentions from hot+new posts, counts them,
     filters to real tickers (cross-referenced against our universe), ranks.
  2. StockTwits — public api.stocktwits.com streams; per-symbol bullish/bearish
     message tags → a crowd sentiment score for watchlist / held / top tickers.

Writes cache/retail_sentiment.json:
  { generated_at, wsb_trending:[{ticker,mentions,rank}],
    stocktwits:{TICKER:{bullish,bearish,msgs,sentiment}}, errors:[] }

Defensive: short timeouts, custom UA (Reddit 429s default UA), per-source
try/except so one source failing never kills the other. Cached output is the
fallback if both fail.

Usage:
  python3 scripts/build_retail_sentiment.py
  python3 scripts/build_retail_sentiment.py --tickers NVDA,IONQ,CORZ   # St only on these
  python3 scripts/build_retail_sentiment.py --dry-run                  # print, don't write
"""
from __future__ import annotations
import argparse, json, re, sys, time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "cache" / "retail_sentiment.json"
# Clean browser UA — Reddit 403s the old "Kairos-SwingTrade/1.0" suffix (flagged as
# a bot). StockTwits already accepts a browser UA, so this is safe across both. (2026-06-03)
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

# Words that look like tickers but aren't — common WSB noise
_STOP = {
    "A","I","ALL","AND","ARE","BE","BUY","CEO","CFO","DD","EOD","FD","FOMO","FOR","FROM",
    "GDP","IMO","IPO","IRA","IT","ITM","LOL","OTM","PT","SEC","SELL","THE","TO","USA","WSB",
    "YOLO","YOY","ATH","EPS","ER","ETF","GG","IV","NO","OK","ON","OR","PE","RH","RIP","SO",
    "UP","US","WE","TLDR","CALL","PUT","HOLD","MOON","BAN","NOW","NEW","ONE","TWO","OUT","WIN",
    "GO","HE","SHE","HER","HIS","NOT","BUT","CAN","WILL","JUST","ELON","FED","API","DOJ","FBI",
}


def _safe_load(p: Path):
    try: return json.loads(p.read_text()) if p.exists() else None
    except Exception: return None


def _universe_set() -> set:
    """Real tradeable tickers to validate WSB mentions against."""
    syms = set()
    try:
        import data_fetcher as df
        syms |= set(df.get_sp500() or [])
        try: syms |= set(df.get_russell1000() or [])
        except Exception: pass
    except Exception:
        pass
    # add R2000 from membership csv if present
    r2 = REPO / "data" / "membership" / "r2000_2026-05.csv"
    if r2.exists():
        for line in r2.read_text().splitlines()[1:]:
            t = line.split(",")[0].strip().upper()
            if t: syms.add(t)
    return {s.upper() for s in syms}


# ── Reddit / WSB ────────────────────────────────────────────────────────────
_TICKER_RE = re.compile(r"\$?([A-Z]{1,5})\b")

def scrape_reddit(universe: set, subs=("wallstreetbets", "stocks", "options"),
                  limit=100) -> tuple[list, list]:
    # Reddit's own public .json now 403s all non-OAuth clients (2023+ API lockdown) —
    # confirmed dead on both www. and old. hosts regardless of UA (2026-06-03). We read
    # the FREE ApeWisdom aggregator instead (apewisdom.io) — it rolls up r/wallstreetbets
    # + r/stocks mention counts, no auth, no block. Same signal (ticker mentions/rank).
    import urllib.request
    errors = []
    counts = Counter()
    aw_subs = tuple(s for s in subs if s in ("wallstreetbets", "stocks", "options"))
    for sub in (aw_subs or ("wallstreetbets",)):
        url = f"https://apewisdom.io/api/v1.0/filter/{sub}/page/1"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read())
            for row in (data.get("results") or []):
                sym = (row.get("ticker") or "").upper()
                if sym in universe and sym not in _STOP:
                    counts[sym] += int(row.get("mentions") or 0)
            time.sleep(0.3)  # be polite
        except Exception as e:
            errors.append(f"apewisdom {sub}: {type(e).__name__}: {str(e)[:80]}")
    ranked = [{"ticker": t, "mentions": n, "rank": i + 1}
              for i, (t, n) in enumerate(counts.most_common(25))]
    return ranked, errors


# ── StockTwits ──────────────────────────────────────────────────────────────
def scrape_stocktwits(tickers: list) -> tuple[dict, list]:
    import urllib.request
    out, errors = {}, []
    for sym in tickers[:30]:  # rate-limit friendly
        url = f"https://api.stocktwits.com/api/2/streams/symbol/{sym}.json"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=8) as r:
                data = json.loads(r.read())
            msgs = data.get("messages") or []
            bull = bear = 0
            for m in msgs:
                ent = (m.get("entities") or {}).get("sentiment") or {}
                b = (ent.get("basic") or "").lower()
                if b == "bullish": bull += 1
                elif b == "bearish": bear += 1
            tagged = bull + bear
            score = round((bull - bear) / tagged, 2) if tagged else None
            out[sym] = {"bullish": bull, "bearish": bear, "msgs": len(msgs),
                        "sentiment": score,
                        "label": ("bullish" if (score or 0) > 0.2 else
                                  "bearish" if (score or 0) < -0.2 else "mixed")}
            time.sleep(0.5)
        except Exception as e:
            errors.append(f"stocktwits {sym}: {type(e).__name__}: {str(e)[:60]}")
    return out, errors


def _default_tickers() -> list:
    """Tickers to pull StockTwits sentiment for: held + watchlist + top picks."""
    syms = []
    b = _safe_load(REPO / "cache" / "last_bundle.json") or {}
    for p in (b.get("buy_candidates") or [])[:10]:
        if p.get("ticker"): syms.append(p["ticker"])
    ps = _safe_load(REPO / "data" / "portfolio_state.json") or {}
    for p in (ps.get("positions") or []):
        if p.get("ticker"): syms.append(p["ticker"])
    # dedupe, preserve order
    seen, out = set(), []
    for s in syms:
        if s not in seen: seen.add(s); out.append(s)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", default="", help="comma list for StockTwits (else held+picks)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-reddit", action="store_true")
    ap.add_argument("--no-stocktwits", action="store_true")
    args = ap.parse_args()

    errors = []
    print("building universe set for WSB validation...")
    universe = _universe_set()
    print(f"  universe size: {len(universe)} tickers")

    wsb = []
    if not args.no_reddit:
        print("scraping Reddit (WSB + stocks + options)...")
        wsb, e = scrape_reddit(universe)
        errors += e
        print(f"  WSB trending: {len(wsb)} tickers · top: {[w['ticker'] for w in wsb[:8]]}")

    st_tickers = ([t.strip().upper() for t in args.tickers.split(",") if t.strip()]
                  if args.tickers else _default_tickers())
    stocktwits = {}
    if not args.no_stocktwits and st_tickers:
        print(f"scraping StockTwits for {len(st_tickers)} tickers...")
        stocktwits, e = scrape_stocktwits(st_tickers)
        errors += e
        bullish = [s for s, v in stocktwits.items() if v.get("label") == "bullish"]
        print(f"  StockTwits: {len(stocktwits)} pulled · bullish: {bullish[:8]}")

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "wsb_trending": wsb,
        "stocktwits": stocktwits,
        "errors": errors,
        "sources": ["reddit:wallstreetbets,stocks,options", "stocktwits"],
    }

    if args.dry_run:
        print("\n" + json.dumps(payload, indent=2)[:2500])
        return 0

    # If both sources failed, keep prior cache rather than overwrite with empty
    if not wsb and not stocktwits:
        if OUT.exists():
            print("both sources empty — keeping prior cache (not overwriting)")
            return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2))
    print(f"\nwrote {OUT} · WSB {len(wsb)} · StockTwits {len(stocktwits)} · errors {len(errors)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
