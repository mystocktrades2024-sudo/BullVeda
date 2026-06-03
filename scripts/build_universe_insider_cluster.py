#!/usr/bin/env python3
"""Insider cluster scanner — Bettis-Coles edge.

Finds tickers where >=3 insiders bought >=$200K each in the last 30 days.
Empirically (Bettis et al. 2000, Cohen-Malloy-Pomorski 2012), clustered
insider buying with meaningful dollar amounts (not the noise of $5K
auto-purchases) is one of the most persistent retail-accessible edges.

Iterates universe = SP500 + R1000 + R2000 (the names where insider data is
liquid). For each ticker, fetches insider_transactions from EODHD and
filters to BUY codes only with >= MIN_VALUE_PER_TX in the last LOOKBACK_DAYS.

Cost: 1 EODHD insider_transactions call per ticker (~3000 calls), well
within quota. ~3-4 minutes runtime. Morning-scan only.

Output: cache/insider_cluster.json
  {
    "_meta": {generated_at, n_candidates, thresholds},
    "candidates": [{ticker, n_insiders, total_value, latest_buy, insiders: [...]}],
    "tickers": [...just the symbols for universe wire-up]
  }

Wired into swing_trade.py universe build via _load_insider_cluster() (next).
"""
from __future__ import annotations
import datetime
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).parent.parent
OUT = BASE / "cache" / "insider_cluster.json"
sys.path.insert(0, str(BASE))

LOOKBACK_DAYS = 30
MIN_INSIDERS = 3            # cluster threshold (Bettis-Coles 3+ insiders)
MIN_VALUE_PER_TX = 200_000  # $ · per-transaction floor to filter auto-buys
BUY_CODES = ("P", "A")      # P = open-market purchase, A = grant/award (less informative)
# 2026-05-21 default: only count P (open-market). A = comp grant, noisy.
BUY_CODES_STRICT = ("P",)
USE_STRICT = True           # P-only by default; flip for more inclusion


def _load_universe() -> list[str]:
    """Sources, in order: tickers.json → last_bundle.all_scored → SP500 from EODHD.
    Caps at 3000 to bound runtime."""
    tj = BASE / "infra" / "prototype" / "tickers.json"
    if tj.exists():
        try:
            d = json.loads(tj.read_text())
            if isinstance(d, dict) and d:
                return sorted(d.keys())[:3000]
        except Exception:
            pass
    last = BASE / "cache" / "last_bundle.json"
    if last.exists():
        try:
            b = json.loads(last.read_text())
            tks = sorted({r.get("ticker") for r in (b.get("all_scored") or []) if r.get("ticker")})
            if tks:
                return tks[:3000]
        except Exception:
            pass
    try:
        import eodhd_client as ec
        return (ec.index_components("SP500") or [])[:3000]
    except Exception:
        return []


def _scan_openinsider_clusters(min_insiders: int, min_total_value: float,
                               lookback_days: int) -> list[dict] | None:
    """FREE, EODHD-independent cluster detection via openinsider.com/latest-cluster-buys.

    The cluster-buys page is ALREADY aggregated — each row is a ticker with N
    insiders buying, so we get the whole signal in ONE HTTP call instead of
    ~3000 per-ticker EODHD insider_transactions calls. Column layout:
      0=X 1=FilingDate 2=TradeDate 3=Ticker 4=Company 5=Industry 6=Ins(#)
      7=TradeType 8=Price 9=Qty 10=Owned 11=ΔOwn 12=Value(cluster total)
    Returns candidates (same shape as _scan_ticker output) or None on fetch failure.
    """
    import urllib.request
    sys.path.insert(0, str(BASE / "scripts" / "scrapers"))
    try:
        import insider_openinsider as oi
        req = urllib.request.Request("http://openinsider.com/latest-cluster-buys",
                                     headers={"User-Agent": oi.UA, "Accept": "text/html"})
        with urllib.request.urlopen(req, timeout=30) as r:
            html = r.read().decode("utf-8", errors="ignore")
        parser = oi._OITableParser()
        parser.feed(html)
        rows = parser.rows
    except Exception as e:
        print(f"[insider_cluster] openinsider fetch failed: {e}", file=sys.stderr)
        return None

    def _money(s: str) -> float:
        s = re.sub(r"[\$,+]", "", (s or "").strip())
        try:
            return float(s)
        except Exception:
            return 0.0

    cutoff = (datetime.date.today() - datetime.timedelta(days=lookback_days)).isoformat()
    out: list[dict] = []
    for r in rows[1:]:                       # skip header
        if len(r) < 13:
            continue
        ticker = (r[3] or "").upper().strip()
        if not (ticker and 1 <= len(ticker) <= 6):
            continue
        if "P" not in (r[7] or "").upper():   # open-market PURCHASE only (P - Purchase)
            continue
        try:
            n_ins = int(re.sub(r"[^0-9]", "", r[6]) or 0)
        except Exception:
            n_ins = 0
        if n_ins < min_insiders:
            continue
        tdate = (r[2] or "")[:10]
        if tdate and tdate < cutoff:
            continue
        total = abs(_money(r[12]))
        if total < min_total_value:
            continue
        out.append({
            "ticker": ticker,
            "company": (r[4] or "").strip(),
            "n_insiders": n_ins,
            "total_value": round(total, 0),
            "latest_buy": tdate,
            "insiders": [],                   # cluster page is pre-aggregated (no per-name rows)
            "source": "openinsider",
        })
    out.sort(key=lambda x: -x["total_value"])
    return out


def _scan_ticker(ticker: str, from_date: str, to_date: str) -> dict | None:
    """Returns cluster summary {ticker, n_insiders, total_value, insiders}
    if it qualifies, else None."""
    import eodhd_client as ec
    try:
        rows = ec.insider_transactions(ticker, from_date=from_date, to_date=to_date) or []
    except Exception:
        return None
    if not rows:
        return None
    valid_codes = BUY_CODES_STRICT if USE_STRICT else BUY_CODES
    by_insider: dict[str, dict] = defaultdict(lambda: {"buys": 0, "total_value": 0.0, "latest": ""})
    for r in rows[:200]:
        code = (r.get("transactionCode") or r.get("type") or "").upper()
        if code not in valid_codes:
            continue
        try:
            shares = float(r.get("transactionAmount") or r.get("shares") or 0)
            price = float(r.get("transactionPrice") or r.get("price") or 0)
        except Exception:
            continue
        value = shares * price
        if value < MIN_VALUE_PER_TX:
            continue
        name = (r.get("ownerName") or r.get("name") or "?").strip()
        date = (r.get("transactionDate") or r.get("date") or "")[:10]
        rec = by_insider[name]
        rec["buys"] += 1
        rec["total_value"] += value
        if date > rec["latest"]:
            rec["latest"] = date
    if len(by_insider) < MIN_INSIDERS:
        return None
    insiders = [{"name": k, **v} for k, v in by_insider.items()]
    insiders.sort(key=lambda x: -x["total_value"])
    total = sum(i["total_value"] for i in insiders)
    return {
        "ticker": ticker,
        "n_insiders": len(by_insider),
        "total_value": round(total, 0),
        "latest_buy": max(i["latest"] for i in insiders),
        "insiders": insiders[:10],
    }


MIN_CLUSTER_TOTAL = 200_000   # $ · floor on the cluster's TOTAL value (openinsider path)


def main() -> int:
    today = datetime.date.today()
    start = (today - datetime.timedelta(days=LOOKBACK_DAYS)).isoformat()
    end = today.isoformat()

    # ── PRIMARY: free, EODHD-independent openinsider cluster-buys (1 HTTP call) ──
    # Replaces the ~3000-call per-ticker EODHD scan. Works even when EODHD quota is
    # exhausted. Falls back to the EODHD per-ticker scan only if the scrape fails.
    src = "openinsider"
    candidates = _scan_openinsider_clusters(MIN_INSIDERS, MIN_CLUSTER_TOTAL, LOOKBACK_DAYS)
    if candidates is None:
        print("[insider_cluster] openinsider unavailable → EODHD per-ticker fallback", file=sys.stderr)
        src = "eodhd"
        universe = _load_universe()
        if not universe:
            print("[insider_cluster] empty universe, skipping", file=sys.stderr)
            return 1
        print(f"[insider_cluster] scanning {len(universe)} tickers · {start} → {end} · strict={USE_STRICT}", file=sys.stderr)
        candidates = []
        for i, tk in enumerate(universe):
            if i % 250 == 0 and i:
                print(f"  [insider_cluster] progress {i}/{len(universe)} · candidates so far={len(candidates)}", file=sys.stderr)
            c = _scan_ticker(tk, start, end)
            if c:
                candidates.append(c)
    candidates.sort(key=lambda x: -x["total_value"])

    out = {
        "_meta": {
            "generated_at": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "n_candidates": len(candidates),
            "source": src,
            "thresholds": {
                "lookback_days": LOOKBACK_DAYS,
                "min_insiders": MIN_INSIDERS,
                "min_value_per_tx": MIN_VALUE_PER_TX,
                "min_cluster_total": MIN_CLUSTER_TOTAL,
                "strict_p_only": USE_STRICT,
            },
        },
        "candidates": candidates[:200],
        "tickers": [c["ticker"] for c in candidates],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2))
    print(f"[insider_cluster] wrote {OUT} · {len(candidates)} clusters · source={src}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
