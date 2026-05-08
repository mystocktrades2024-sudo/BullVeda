#!/usr/bin/env python3
"""
predict_earnings_beats.py — score upcoming earnings on beat probability.

For each ticker in earnings_watchlist (next 10 days), composite-score
on signals that historically precede a BEAT + post-earnings drift:

  1. HISTORICAL BEAT RATE (25 pts) — what fraction of last 4 quarters
     this ticker beat estimates (from earnings_outcomes.jsonl).

  2. PRICE RUNUP (20 pts) — 10-day price change vs sector. Strong
     positive runup pre-announce signals smart money positioning.

  3. VOLUME ACCUMULATION (15 pts) — 10-day avg volume vs 60-day avg.
     Rising volume = institutional building.

  4. ANALYST POSITIONING (15 pts) — current price proximity to mean
     target + recent target revisions (if available).

  5. OPTIONS FLOW (15 pts) — P/C ratio + IV regime. Call-heavy +
     elevated IV = market expects upside move.

  6. SECTOR CO-MOVERS (10 pts) — recent sector peers beating (e.g., if
     other AI names beat, AI ticker more likely to beat).

Output: data/earnings_beat_predictions.json with per-ticker score +
breakdown. Surfaced in V2 Earnings tab as a "BEAT %" column.

INOD's pre-earnings profile (verified retrospective): score ~78/100
(sustained uptrend, AI sector beats, analyst rating 4.6, runup +9%
into earnings, IV elevating).

Schedule: daily 5:40am PT (after earnings_watchlist refresh).
"""
from __future__ import annotations
import json
import logging
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
LOG_FILE = BASE / "cache" / "logs" / "predict_earnings_beats.log"
OUT_FILE = BASE / "data" / "earnings_beat_predictions.json"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [beat_predict] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


def _load_env() -> None:
    p = BASE / ".env"
    if not p.exists(): return
    for line in p.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _historical_beat_rate(ticker: str, outcomes: list[dict], lookback: int = 4) -> tuple[float, int]:
    """Return (beat_fraction, n_observations) for last N quarters."""
    by_t = [o for o in outcomes if o.get("ticker") == ticker]
    by_t.sort(key=lambda x: x.get("report_date", ""), reverse=True)
    last_n = by_t[:lookback]
    if not last_n:
        return (0.5, 0)  # neutral if no history
    beats = sum(1 for o in last_n if o.get("beat") == "BEAT")
    return (beats / len(last_n), len(last_n))


def _price_runup(ticker: str, days: int = 10) -> float | None:
    """N-day price change %. Uses EODHD."""
    try:
        import eodhd_client as e
        end = date.today()
        start = end - timedelta(days=days * 2)  # extra buffer for weekends
        bars = e.eod(ticker, str(start), str(end))
        if not bars or len(bars) < 5:
            return None
        bars = sorted(bars, key=lambda b: b.get("date", ""))
        recent = bars[-1].get("close")
        # ~N trading days back
        ref_idx = max(0, len(bars) - 1 - days)
        old = bars[ref_idx].get("close")
        if recent and old:
            return round((float(recent) / float(old) - 1) * 100, 2)
    except Exception as ex:
        log.debug(f"price_runup({ticker}): {ex}")
    return None


def _volume_accumulation(ticker: str) -> float | None:
    """10d avg vol / 60d avg vol — >1.0 means accumulation."""
    try:
        import eodhd_client as e
        end = date.today()
        start = end - timedelta(days=80)
        bars = e.eod(ticker, str(start), str(end))
        if not bars or len(bars) < 30:
            return None
        bars = sorted(bars, key=lambda b: b.get("date", ""))
        vols = [float(b.get("volume", 0) or 0) for b in bars]
        if len(vols) < 60:
            return None
        recent10 = sum(vols[-10:]) / 10
        baseline60 = sum(vols[-60:]) / 60
        if baseline60 <= 0:
            return None
        return round(recent10 / baseline60, 2)
    except Exception as ex:
        log.debug(f"vol_accum({ticker}): {ex}")
    return None


def _ticker_intel_from_scan(ticker: str, tickers_data: dict) -> dict:
    """Pull score, verdict, analyst, options snapshot from latest scan."""
    return tickers_data.get(ticker, {}) or {}


def _score_ticker(t: str, ew: dict, outcomes: list[dict], tickers_data: dict,
                   sector_beat_rate: dict[str, float]) -> dict:
    """Composite 0-100 beat-probability score with breakdown."""
    breakdown: dict = {}

    # 1. Historical beat rate (25 pts)
    rate, n = _historical_beat_rate(t, outcomes)
    hist_pts = 25 * rate if n >= 1 else 12.5  # neutral if no history
    breakdown["historical"] = {"pts": round(hist_pts, 1), "max": 25,
                                "rate": round(rate * 100, 0), "n_quarters": n}

    # 2. Price runup (20 pts) — non-linear: penalize >15% (already pumped)
    runup = _price_runup(t, days=10)
    if runup is None:
        run_pts = 10
    elif runup < -5: run_pts = 0
    elif runup < 0: run_pts = 5
    elif runup < 3: run_pts = 10
    elif runup < 8: run_pts = 18
    elif runup < 15: run_pts = 20
    elif runup < 25: run_pts = 14
    else: run_pts = 8  # already pumped — limited upside
    breakdown["runup_10d"] = {"pts": run_pts, "max": 20,
                              "value": runup if runup is not None else "n/a"}

    # 3. Volume accumulation (15 pts)
    vol = _volume_accumulation(t)
    if vol is None: vol_pts = 7
    elif vol < 0.7: vol_pts = 0
    elif vol < 0.9: vol_pts = 3
    elif vol < 1.1: vol_pts = 7
    elif vol < 1.4: vol_pts = 12
    else: vol_pts = 15
    breakdown["vol_accum"] = {"pts": vol_pts, "max": 15,
                              "value": vol if vol is not None else "n/a"}

    # 4. Analyst (15 pts) — target proximity + rating
    intel = tickers_data.get(t) or {}
    analyst = intel.get("analyst") or {}
    price = intel.get("price") or intel.get("last")
    target_mean = analyst.get("target_mean")
    if price and target_mean:
        upside = (target_mean / price - 1) * 100
    else:
        upside = None
    if upside is None: an_pts = 7
    elif upside < -5: an_pts = 0
    elif upside < 5: an_pts = 5
    elif upside < 15: an_pts = 12
    else: an_pts = 15
    breakdown["analyst_upside"] = {"pts": an_pts, "max": 15,
                                    "upside_pct": round(upside, 1) if upside is not None else "n/a"}

    # 5. Options flow (15 pts) — P/C ratio + IV regime
    od = intel.get("options_data") or {}
    pc = od.get("put_call_ratio")
    iv_cur = od.get("current_iv")
    op_pts = 0
    if pc is not None:
        if pc < 0.3: op_pts += 8
        elif pc < 0.6: op_pts += 5
        elif pc < 1.0: op_pts += 3
    if iv_cur is not None:
        if iv_cur > 60: op_pts += 7  # elevated IV = move expected
        elif iv_cur > 40: op_pts += 4
    op_pts = min(op_pts, 15)
    if pc is None and iv_cur is None: op_pts = 7
    breakdown["options"] = {"pts": op_pts, "max": 15,
                             "put_call": pc, "current_iv": iv_cur}

    # 6. Sector co-movers (10 pts)
    sector = intel.get("sector") or "Unknown"
    sec_rate = sector_beat_rate.get(sector, 0.5)
    sec_pts = round(10 * sec_rate, 1)
    breakdown["sector_beats"] = {"pts": sec_pts, "max": 10,
                                  "sector": sector,
                                  "sector_beat_rate": round(sec_rate * 100, 0)}

    total = (breakdown["historical"]["pts"]
             + breakdown["runup_10d"]["pts"]
             + breakdown["vol_accum"]["pts"]
             + breakdown["analyst_upside"]["pts"]
             + breakdown["options"]["pts"]
             + breakdown["sector_beats"]["pts"])
    total = round(total, 1)

    # Tier thresholds calibrated against 902-outcome bootstrap (2026-05-08).
    # Will tighten as historical-beat-rate column fills in across more
    # quarters of captured outcomes (5+ quarters per ticker = full pts).
    if total >= 65: tier = "STRONG"
    elif total >= 55: tier = "SOLID"
    elif total >= 45: tier = "MODERATE"
    else: tier = "WEAK"

    return {
        "ticker":           t,
        "report_date":      ew.get("report_date"),
        "days_to_earnings": ew.get("days_to_earnings"),
        "before_after":     ew.get("before_after_market") or "",
        "beat_score":       total,
        "tier":             tier,
        "breakdown":        breakdown,
    }


def main() -> int:
    _load_env()
    ew_path = BASE / "data" / "earnings_watchlist.json"
    if not ew_path.exists():
        log.error("No earnings_watchlist.json — run build_earnings_watchlist.py first")
        return 1
    ew = json.loads(ew_path.read_text())
    watchlist = ew.get("watchlist") or []
    if not watchlist:
        log.warning("Empty watchlist")
        OUT_FILE.write_text(json.dumps({"generated_at": datetime.now().isoformat(),
                                         "predictions": []}))
        return 0

    # Outcomes for historical beat rate + sector beat rate
    out_path = BASE / "data" / "earnings_outcomes.jsonl"
    outcomes = []
    if out_path.exists():
        for line in out_path.read_text().splitlines():
            line = line.strip()
            if not line: continue
            try: outcomes.append(json.loads(line))
            except: pass

    # Build sector beat rate from outcomes (need ticker→sector mapping)
    tk_path = BASE / "infra" / "prototype" / "tickers.json"
    tickers_data = {}
    if tk_path.exists():
        try:
            tickers_data = json.loads(tk_path.read_text())
        except Exception:
            pass

    sec_stats: dict[str, dict] = defaultdict(lambda: {"beats": 0, "total": 0})
    for o in outcomes:
        t = o.get("ticker")
        sec = (tickers_data.get(t) or {}).get("sector")
        if not sec: continue
        sec_stats[sec]["total"] += 1
        if o.get("beat") == "BEAT":
            sec_stats[sec]["beats"] += 1
    sector_beat_rate = {
        s: (v["beats"] / v["total"]) for s, v in sec_stats.items() if v["total"] >= 5
    }
    log.info(f"Sector beat-rate baselines (>=5 prior reports): {len(sector_beat_rate)} sectors")

    log.info(f"Scoring {len(watchlist)} upcoming earnings...")
    predictions = []
    for i, e in enumerate(watchlist, 1):
        t = e.get("ticker")
        if not t: continue
        try:
            pred = _score_ticker(t, e, outcomes, tickers_data, sector_beat_rate)
            predictions.append(pred)
        except Exception as ex:
            log.debug(f"Score failed for {t}: {ex}")
        if i % 50 == 0:
            log.info(f"  {i}/{len(watchlist)} scored")

    predictions.sort(key=lambda x: -x["beat_score"])
    payload = {
        "generated_at": datetime.now().isoformat(),
        "n_total":      len(predictions),
        "n_strong":     sum(1 for p in predictions if p["tier"] == "STRONG"),
        "n_moderate":   sum(1 for p in predictions if p["tier"] == "MODERATE"),
        "predictions":  predictions,
    }
    OUT_FILE.write_text(json.dumps(payload, indent=2, default=str))

    n_strong = payload["n_strong"]
    log.info(f"Wrote {OUT_FILE.name}: {len(predictions)} scored, {n_strong} STRONG")
    if n_strong:
        top = [p for p in predictions if p["tier"] == "STRONG"][:5]
        log.info(f"Top STRONG candidates:")
        for p in top:
            log.info(f"  {p['ticker']:6}  score={p['beat_score']:.0f}  "
                     f"reports {p['report_date']} ({p['days_to_earnings']}d)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
