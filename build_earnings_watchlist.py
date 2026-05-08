#!/usr/bin/env python3
"""
build_earnings_watchlist.py — pre-earnings watchlist builder.

For each US ticker reporting in the next 10 days, captures:
  ticker, report_date, days_to_earnings, before_after_market, estimate

Output: data/earnings_watchlist.json (overwritten daily).

Wired into swing_trade.py pre-screen so these tickers are GUARANTEED
inclusion in the analysis universe regardless of pre-screen score.
This catches names like INOD that were consolidating in the pre-screen
ranking but had a known catalyst within 10 days.

Schedule:
  Daily 5:30am PT via launchd, before the morning scan.
"""
from __future__ import annotations
import json
import logging
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
LOG_FILE = BASE / "cache" / "logs" / "earnings_watchlist.log"
OUT_FILE = BASE / "data" / "earnings_watchlist.json"

LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [earnings_watchlist] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


def _is_us_ticker(code: str) -> bool:
    """EODHD codes are 'AAPL.US', 'TITAN.BSE', 'V02.F', etc.
    US tickers either have .US suffix or no suffix at all."""
    if not code:
        return False
    if "." not in code:
        return True
    suffix = code.rsplit(".", 1)[1].upper()
    return suffix in ("US",)


def _strip_suffix(code: str) -> str:
    return code.split(".")[0].upper() if code else ""


def _load_tradeable_universe() -> set[str]:
    """Build the set of tickers we actually scan: S&P 500 + Russell 1000 +
    Russell 2000 + Zacks #1 + custom watchlist + open positions.

    Filters out ADRs (5-letter codes ending in F/Y), pink sheets, and
    foreign listings that the user would never trade.
    """
    universe: set[str] = set()
    import eodhd_client as e
    try:
        for idx in ("SP500", "RUI", "RUT"):
            tickers = e.index_components(idx) or []
            universe |= {t.upper() for t in tickers if isinstance(t, str)}
        log.info(f"  Universe loaded: SP500 + R1000 + R2000 = {len(universe)} tickers")
    except Exception as ex:
        log.warning(f"index_components fetch failed: {ex}")

    # Zacks #1 from cache (built by daily scan)
    try:
        zk = json.loads((BASE / "cache" / "zacks_data.json").read_text())
        for t in (zk.get("zacks_rank1") or []):
            if isinstance(t, str):
                universe.add(t.upper())
    except Exception:
        pass

    # Custom watchlist from config
    try:
        cfg = json.loads((BASE / "config" / "config.json").read_text())
        for t in (cfg.get("universe", {}).get("custom_watchlist") or []):
            if isinstance(t, str):
                universe.add(t.upper())
    except Exception:
        pass

    # Currently held positions — always include even if outside universe
    try:
        ps = json.loads((BASE / "data" / "portfolio_state.json").read_text())
        for p in (ps.get("positions") or []):
            t = (p.get("ticker") or "").upper()
            if t and p.get("status") == "OPEN":
                universe.add(t)
    except Exception:
        pass

    return universe


def main(days_ahead: int = 10) -> int:
    # Lazy-load .env so SCHWAB_APP_KEY etc. are present (not used here, but
    # keeps the env consistent with other scripts).
    for line in (BASE / ".env").read_text().splitlines() if (BASE / ".env").exists() else []:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

    today = date.today()
    end   = today + timedelta(days=days_ahead)

    # Build the tradeable-universe filter so we drop foreign ADRs / pinks /
    # noise tickers that pollute the watchlist (AAFRF, AKEJF, etc.).
    log.info(f"Loading tradeable universe (SP500 + R1000 + R2000 + Zacks + positions)...")
    universe = _load_tradeable_universe()
    log.info(f"  Universe size: {len(universe)} tickers")

    log.info(f"Fetching EODHD earnings calendar {today} → {end} ({days_ahead}d)")
    import eodhd_client as e
    raw = e.earnings_calendar(from_date=str(today), to_date=str(end))
    if not isinstance(raw, dict):
        log.error(f"earnings_calendar returned non-dict: {type(raw)}")
        return 1
    entries = raw.get("earnings") or raw.get("data") or []
    log.info(f"Total earnings entries (global): {len(entries)}")

    # Filter to US + universe + dedupe. The raw US filter alone leaves 1,840
    # entries including a lot of foreign ADRs (AAFRF, AKEJF) and pinks the
    # user never trades. Intersecting with the tradeable universe collapses
    # to a focused list (~150-300 names).
    seen: set[str] = set()
    out: list[dict] = []
    n_universe_filtered = 0
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        code = entry.get("code", "")
        if not _is_us_ticker(code):
            continue
        ticker = _strip_suffix(code)
        if ticker in seen or not ticker:
            continue
        seen.add(ticker)
        # Universe filter — only keep tickers we actually scan/hold
        if universe and ticker not in universe:
            n_universe_filtered += 1
            continue
        rep_date = entry.get("report_date")
        if not rep_date:
            continue
        try:
            d_to = (datetime.strptime(rep_date, "%Y-%m-%d").date() - today).days
        except ValueError:
            continue
        if d_to < 0 or d_to > days_ahead:
            continue
        out.append({
            "ticker":              ticker,
            "report_date":         rep_date,
            "days_to_earnings":    d_to,
            "before_after_market": entry.get("before_after_market") or "",
            "estimate":            entry.get("estimate"),
            "actual":              entry.get("actual"),
            "currency":            entry.get("currency") or "USD",
        })

    out.sort(key=lambda x: (x["days_to_earnings"], x["ticker"]))
    payload = {
        "generated_at":    datetime.now().isoformat(),
        "window_days":     days_ahead,
        "from_date":       str(today),
        "to_date":         str(end),
        "total_us":        len(out),
        "watchlist":       out,
    }
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(payload, indent=2, default=str))

    log.info(f"Wrote {OUT_FILE.name}: {len(out)} tradeable tickers reporting in next {days_ahead}d "
             f"(filtered out {n_universe_filtered} non-universe US listings)")
    log.info(f"  by day-bucket: {dict([(d, sum(1 for x in out if x['days_to_earnings'] == d)) for d in range(0, days_ahead + 1)])}")
    if out:
        next5 = ", ".join("{}({}d)".format(x["ticker"], x["days_to_earnings"]) for x in out[:5])
        log.info(f"  next 5 reporting: {next5}")
    return 0


if __name__ == "__main__":
    sys.exit(main(days_ahead=10))
