#!/usr/bin/env python3
"""Build supplemental universe layers that fill structural gaps:

  - Recent IPOs (>$300M market cap, >21 trading days old, <=400 days old)
    Catches names like WYFI that IPO'd after the Russell reconstitution and
    won't be eligible for R2000/R1000 until the next June rebalance.

  - Post-earnings movers (>5% EPS beat OR >5% gap last 5 trading days)
    PEAD sleeve candidates — the catalyst-driven sleeve wants these even
    when they're not in any index.

Output: cache/universe_extras.json with shape:
  {
    "_meta": {"generated_at": ..., "n_ipos": N, "n_pead": N, "total": N},
    "recent_ipos": [...tickers...],
    "post_earnings_movers": [...tickers...],
    "all_extras": [...union, deduped...],
  }

Plumbed into swing_trade.py universe build via _load_universe_extras() (next).
Runs as part of run_daily_scan.sh on the morning scan (cheap, ~5s).
"""
from __future__ import annotations
import datetime
import json
import sys
from pathlib import Path

BASE = Path(__file__).parent.parent
OUT = BASE / "cache" / "universe_extras.json"
sys.path.insert(0, str(BASE))


# Configurable thresholds — tuned for retail-scale + EODHD quota constraints.
IPO_MIN_CAP_M = 300        # $M · minimum market cap for IPO inclusion
IPO_MIN_AGE_DAYS = 21      # post-IPO floor (CLAUDE.md: "First 6 weeks noisy")
IPO_MAX_AGE_DAYS = 400     # ~13 months · covers two missed Russell rebalances
IPO_MIN_ADV_M = 5          # $M · 21d avg dollar volume floor
PEAD_LOOKBACK_DAYS = 5     # bars back to look for the earnings reaction
PEAD_MIN_SURPRISE_PCT = 5  # EPS surprise threshold


def _load_corporate_events() -> dict:
    p = BASE / "cache" / "corporate_events.json"
    if not p.exists():
        return {"ipos": []}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {"ipos": []}


def _build_recent_ipos(days_lookback: int = IPO_MAX_AGE_DAYS) -> list[str]:
    """Pull IPOs from the last `days_lookback` days, filter by cap + ADV + age.

    Uses EODHD calendar/ipos via the existing fetcher. Then fundamentals +
    eod for each candidate to filter cap + liquidity. Cheap because corp
    events cache already exists; we add 2 EODHD calls per IPO candidate.
    """
    import eodhd_client as ec

    today = datetime.date.today()
    start = (today - datetime.timedelta(days=days_lookback)).isoformat()
    end = today.isoformat()

    # Fetch the IPO calendar for the lookback window (different range than
    # forward-30d cache uses, so we make a fresh call)
    try:
        raw = ec.financial_events(from_date=start, to_date=end, event_type="ipos") or {}
        ipos = raw.get("ipos") if isinstance(raw, dict) else raw
    except Exception as e:
        print(f"[universe_extras] IPO fetch failed: {e}", file=sys.stderr)
        return []

    eligible: list[str] = []
    skipped_reasons: dict = {"too_recent": 0, "no_cap": 0, "small_cap": 0, "no_adv": 0, "low_adv": 0, "foreign": 0}

    for r in (ipos or []):
        code = (r.get("code") or "").upper()
        ex = (r.get("exchange") or "").upper()
        if not code:
            continue
        # US-only
        if ex and ex not in ("NYSE", "NASDAQ", "NYSE ARCA", "BATS", "AMEX"):
            if not code.endswith(".US") and "." in code:
                skipped_reasons["foreign"] += 1
                continue
        ticker = code.replace(".US", "")
        # Age gate
        try:
            ipo_date = datetime.date.fromisoformat((r.get("start_date") or r.get("filing_date") or "")[:10])
        except Exception:
            continue
        age = (today - ipo_date).days
        if age < IPO_MIN_AGE_DAYS:
            skipped_reasons["too_recent"] += 1
            continue
        if age > IPO_MAX_AGE_DAYS:
            continue
        # Cap + ADV gate — cost 2 EODHD calls per candidate
        try:
            f = ec.fundamentals(ticker)
            cap = ((f or {}).get("Highlights") or {}).get("MarketCapitalization")
            if cap is None:
                skipped_reasons["no_cap"] += 1
                continue
            cap_m = cap / 1e6
            if cap_m < IPO_MIN_CAP_M:
                skipped_reasons["small_cap"] += 1
                continue
        except Exception:
            skipped_reasons["no_cap"] += 1
            continue
        try:
            wstart = (today - datetime.timedelta(days=30)).isoformat()
            bars = ec.eod(ticker, from_date=wstart, to_date=end) or []
            if not isinstance(bars, list) or not bars:
                skipped_reasons["no_adv"] += 1
                continue
            recent = bars[-21:] if len(bars) >= 21 else bars
            adv = sum((b.get("volume") or 0) * (b.get("close") or 0) for b in recent) / max(len(recent), 1)
            if adv / 1e6 < IPO_MIN_ADV_M:
                skipped_reasons["low_adv"] += 1
                continue
        except Exception:
            skipped_reasons["no_adv"] += 1
            continue
        eligible.append(ticker)

    print(f"[universe_extras] IPO scan: {len(ipos or [])} raw → {len(eligible)} eligible · skipped {skipped_reasons}", file=sys.stderr)
    return sorted(set(eligible))


def _build_post_earnings_movers() -> list[str]:
    """Pull tickers with recent (last 5d) EPS surprise >= 5% from the local
    earnings_outcomes log. Doesn't add an EODHD call — pure local read."""
    log = BASE / "data" / "earnings_outcomes.jsonl"
    if not log.exists():
        return []
    today = datetime.date.today()
    cutoff = today - datetime.timedelta(days=PEAD_LOOKBACK_DAYS)
    eligible: set[str] = set()
    try:
        with open(log) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                rd = (o.get("report_date") or "")[:10]
                if not rd:
                    continue
                try:
                    rdate = datetime.date.fromisoformat(rd)
                except Exception:
                    continue
                if rdate < cutoff or rdate > today:
                    continue
                surp = o.get("eps_surprise_pct")
                if surp is None or float(surp) < PEAD_MIN_SURPRISE_PCT:
                    continue
                tk = (o.get("ticker") or "").upper()
                if tk:
                    eligible.add(tk)
    except Exception as e:
        print(f"[universe_extras] PEAD scan failed: {e}", file=sys.stderr)
        return []
    print(f"[universe_extras] PEAD scan: {len(eligible)} tickers with surprise >= {PEAD_MIN_SURPRISE_PCT}% in last {PEAD_LOOKBACK_DAYS} days", file=sys.stderr)
    return sorted(eligible)


def main() -> int:
    print("[universe_extras] building recent IPOs + post-earnings movers …", file=sys.stderr)
    ipos = _build_recent_ipos()
    pead = _build_post_earnings_movers()
    all_extras = sorted(set(ipos) | set(pead))
    out = {
        "_meta": {
            "generated_at": datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "n_ipos": len(ipos),
            "n_pead": len(pead),
            "total": len(all_extras),
            "thresholds": {
                "IPO_MIN_CAP_M": IPO_MIN_CAP_M,
                "IPO_MIN_AGE_DAYS": IPO_MIN_AGE_DAYS,
                "IPO_MAX_AGE_DAYS": IPO_MAX_AGE_DAYS,
                "IPO_MIN_ADV_M": IPO_MIN_ADV_M,
                "PEAD_LOOKBACK_DAYS": PEAD_LOOKBACK_DAYS,
                "PEAD_MIN_SURPRISE_PCT": PEAD_MIN_SURPRISE_PCT,
            },
        },
        "recent_ipos": ipos,
        "post_earnings_movers": pead,
        "all_extras": all_extras,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2))
    print(f"[universe_extras] wrote {OUT} · IPOs={len(ipos)} · PEAD={len(pead)} · total unique={len(all_extras)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
