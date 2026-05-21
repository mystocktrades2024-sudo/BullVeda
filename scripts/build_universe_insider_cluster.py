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


def main() -> int:
    universe = _load_universe()
    if not universe:
        print("[insider_cluster] empty universe, skipping", file=sys.stderr)
        return 1
    today = datetime.date.today()
    start = (today - datetime.timedelta(days=LOOKBACK_DAYS)).isoformat()
    end = today.isoformat()
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
            "thresholds": {
                "lookback_days": LOOKBACK_DAYS,
                "min_insiders": MIN_INSIDERS,
                "min_value_per_tx": MIN_VALUE_PER_TX,
                "strict_p_only": USE_STRICT,
            },
            "universe_size": len(universe),
        },
        "candidates": candidates[:200],
        "tickers": [c["ticker"] for c in candidates],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2))
    print(f"[insider_cluster] wrote {OUT} · {len(candidates)} clusters from {len(universe)} universe")
    return 0


if __name__ == "__main__":
    sys.exit(main())
