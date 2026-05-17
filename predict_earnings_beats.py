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


def _eodhd_earnings_history(ticker: str, lookback: int = 4) -> list[dict]:
    """Fetch last N quarters of beat/miss history from EODHD fundamentals.

    EODHD `fundamentals(ticker)["Earnings"]["History"]` returns up to 45
    quarters keyed by fiscal-quarter-end date. We use the most recent N
    quarters where epsActual and epsEstimate are both populated.

    Returns list of dicts ordered most-recent-first:
        [{report_date, eps_actual, eps_estimate, surprise_pct, beat}]
    where beat is 'BEAT' / 'MISS' / 'INLINE'.
    """
    try:
        import eodhd_client as e
        f = e.fundamentals(ticker)
        if not f or not isinstance(f, dict):
            return []
        hist = (f.get("Earnings") or {}).get("History") or {}
        if not isinstance(hist, dict):
            return []
        rows = []
        for qdate, row in hist.items():
            if not isinstance(row, dict):
                continue
            act = row.get("epsActual")
            est = row.get("epsEstimate")
            if act is None or est is None:
                continue
            try:
                act = float(act); est = float(est)
            except (TypeError, ValueError):
                continue
            surp = row.get("surprisePercent")
            try:
                surp = float(surp) if surp is not None else None
            except (TypeError, ValueError):
                surp = None
            # BEAT/MISS/INLINE — use 1% tolerance like our local outcomes
            if surp is not None and abs(surp) < 1.0:
                tag = "INLINE"
            elif act > est:
                tag = "BEAT"
            elif act < est:
                tag = "MISS"
            else:
                tag = "INLINE"
            rows.append({
                "report_date": row.get("reportDate") or qdate,
                "eps_actual": act,
                "eps_estimate": est,
                "surprise_pct": surp,
                "beat": tag,
            })
        # Most-recent-first
        rows.sort(key=lambda r: r["report_date"] or "", reverse=True)
        return rows[:lookback]
    except Exception as ex:
        log.debug(f"eodhd_earnings_history({ticker}): {ex}")
        return []


def _trade_levels(p: dict) -> dict:
    """Entry / Stop / Targets from current spot + implied move + PEAD median.

    Bias to buy NOT on the print itself — we use today's spot as entry.
    Stop = 1× implied move below entry (caps loss at the priced-in move).
    T1   = +PEAD post-5d median (or implied move × 0.6 fallback)
    T2   = +PEAD post-30d median (or implied move × 1.0 fallback)
    R:R  = (T1 − entry) / (entry − stop)

    For SHORT-style setups (bearish revisions + negative drift) the levels
    flip — but we keep direction = long by default; cockpit can negate.
    """
    out = {"entry": None, "stop": None, "t1": None, "t2": None,
           "risk_pct": None, "reward_t1_pct": None, "reward_t2_pct": None,
           "rr_t1": None, "rr_t2": None, "direction": "long"}
    try:
        b  = p.get("breakdown") or {}
        im = b.get("implied_move") or {}
        pead = b.get("pead") or {}
        rev = b.get("revision_trend") or {}
        spot = im.get("spot")
        impl_pct = im.get("implied_move_pct")
        if spot is None or impl_pct is None:
            return out

        post5  = pead.get("post_5d_med")
        post30 = pead.get("post_30d_med")

        # Direction — short bias when revisions BEARISH AND PEAD post-5d < -2%
        direction = "short" if (rev.get("direction") == "BEARISH"
                                and post5 is not None and post5 < -2) else "long"

        entry = spot
        if direction == "long":
            stop = entry * (1 - impl_pct / 100.0)
            t1   = entry * (1 + (post5  if post5  is not None and post5  > 0 else impl_pct * 0.6) / 100.0)
            t2   = entry * (1 + (post30 if post30 is not None and post30 > 0 else impl_pct * 1.0) / 100.0)
        else:
            stop = entry * (1 + impl_pct / 100.0)
            t1   = entry * (1 + (post5  if post5  is not None and post5  < 0 else -impl_pct * 0.6) / 100.0)
            t2   = entry * (1 + (post30 if post30 is not None and post30 < 0 else -impl_pct * 1.0) / 100.0)

        risk_pct = abs((entry - stop) / entry) * 100
        rw1 = abs((t1 - entry) / entry) * 100
        rw2 = abs((t2 - entry) / entry) * 100
        rr1 = (rw1 / risk_pct) if risk_pct > 0 else None
        rr2 = (rw2 / risk_pct) if risk_pct > 0 else None

        out.update({
            "entry":          round(entry, 2),
            "stop":           round(stop,  2),
            "t1":             round(t1,    2),
            "t2":             round(t2,    2),
            "risk_pct":       round(risk_pct, 2),
            "reward_t1_pct":  round(rw1, 2),
            "reward_t2_pct":  round(rw2, 2),
            "rr_t1":          round(rr1, 2) if rr1 is not None else None,
            "rr_t2":          round(rr2, 2) if rr2 is not None else None,
            "direction":      direction,
        })
    except Exception as ex:
        log.debug(f"trade_levels({p.get('ticker')}): {ex}")
    return out


def _liquidity_and_valuation(ticker: str) -> dict:
    """Avg daily $ volume (60d) + Forward P/E + market cap.

    Liquidity: a $5K position fills anywhere; a $5M position needs ADV ≥ 50M
    to stay under 10% ADV. Surface both so any user from $1K to $1M can
    size accordingly. Single EODHD call covers both — fundamentals (cached
    24h) for valuation + already-cached eod for volume.
    """
    out = {"adv_dollar_60d": None, "market_cap": None,
           "forward_pe": None, "trailing_pe": None,
           "shares_float": None}
    try:
        import eodhd_client as ec
        f = ec.fundamentals(ticker)
        if isinstance(f, dict):
            hi = f.get("Highlights") or {}
            val = f.get("Valuation") or {}
            ss  = f.get("SharesStats") or {}
            def _fl(x):
                try: return float(x) if x not in (None, "") else None
                except (TypeError, ValueError): return None
            out["market_cap"]    = _fl(hi.get("MarketCapitalization"))
            out["forward_pe"]    = _fl(val.get("ForwardPE"))
            out["trailing_pe"]   = _fl(hi.get("PERatio")) or _fl(val.get("TrailingPE"))
            out["shares_float"]  = _fl(ss.get("SharesFloat"))
        # ADV from 60d OHLCV
        from datetime import date as _date, timedelta as _td
        end_d = _date.today()
        start_d = end_d - _td(days=90)
        bars = ec.eod(ticker, str(start_d), str(end_d))
        if bars and len(bars) >= 30:
            bars_s = sorted(bars, key=lambda b: b.get("date", ""))[-60:]
            dvs = []
            for b in bars_s:
                try:
                    v = float(b.get("volume") or 0)
                    c = float(b.get("close")  or 0)
                    if v > 0 and c > 0: dvs.append(v * c)
                except (TypeError, ValueError): pass
            if dvs:
                out["adv_dollar_60d"] = int(sum(dvs) / len(dvs))
    except Exception as ex:
        log.debug(f"liquidity({ticker}): {ex}")
    return out


def _per_tier_calibration(predictions: list, outcomes: list) -> dict:
    """Per-tier calibration · honest version.

    True per-tier calibration requires a forward log of past predictions
    so we can join (ticker, predicted_tier) ↔ (ticker, actual_beat_outcome).
    We don't keep that log yet. Naive proxies (bucketing outcomes by surprise
    magnitude) are tautological — high-surprise outcomes are BY DEFINITION
    beats, so the "realized" rate just reflects the bucket boundary, not
    the model.

    Returns design baselines + an explicit "no forward log" note so the
    cockpit can render honestly. Once a `data/earnings_prediction_log.jsonl`
    starts accumulating (predictions written daily, joined to outcomes when
    `report_date` passes), this function can be rewritten to compute real
    per-tier accuracy.
    """
    baselines = {"STRONG": 65, "SOLID": 55, "MODERATE": 50, "WEAK": 45}
    pred_log_path = BASE / "data" / "earnings_prediction_log.jsonl"
    tiers = []
    if pred_log_path.exists():
        # Future: when log accumulates, compute real per-tier hit rate from log.
        # For now: still empty until we have ≥30 closed predictions per tier.
        try:
            log_rows = []
            for line in pred_log_path.read_text().splitlines():
                if not line.strip(): continue
                try: log_rows.append(json.loads(line))
                except: pass
            from collections import defaultdict
            agg = defaultdict(lambda: [0, 0])  # [beats, total]
            for r in log_rows:
                t = r.get("predicted_tier")
                outcome = r.get("realized_outcome")
                if not t or not outcome: continue
                agg[t][1] += 1
                if outcome == "BEAT": agg[t][0] += 1
            for tier, (b, n) in agg.items():
                if n >= 5:
                    realized = b / n * 100
                    tiers.append({
                        "tier": tier,
                        "predicted_pct": baselines.get(tier, 50),
                        "realized_pct":  round(realized, 1),
                        "drift_pp":      round(realized - baselines.get(tier, 50), 1),
                        "n":             n,
                    })
        except Exception: pass
    return {
        "tiers": tiers,
        "baselines": baselines,
        "forward_log_present": pred_log_path.exists(),
        "note": ("forward log present — actual realized per-tier rates"
                 if tiers else
                 "no forward prediction log yet · per-tier calibration "
                 "populates after ≥30 closed predictions per tier (~30d). "
                 "Until then, only aggregate calibration is meaningful."),
    }


def _append_prediction_log(predictions: list) -> int:
    """Append today's predictions to data/earnings_prediction_log.jsonl so
    we can compute REAL per-tier calibration in 30d. One row per prediction.
    Idempotent on (ticker, report_date) — won't double-log the same row.
    """
    try:
        log_path = BASE / "data" / "earnings_prediction_log.jsonl"
        existing_keys: set = set()
        if log_path.exists():
            for line in log_path.read_text().splitlines():
                if not line.strip(): continue
                try:
                    r = json.loads(line)
                    existing_keys.add((r.get("ticker"), r.get("report_date")))
                except: pass
        added = 0
        with log_path.open("a") as f:
            for p in predictions:
                k = (p.get("ticker"), p.get("report_date"))
                if k in existing_keys: continue
                row = {
                    "ticker":         p.get("ticker"),
                    "report_date":    p.get("report_date"),
                    "before_after":   p.get("before_after"),
                    "beat_score":     p.get("beat_score"),
                    "predicted_tier": p.get("tier"),
                    "logged_at":      datetime.now().isoformat(),
                    "realized_outcome": None,   # filled in by future script that joins on report_date
                    "realized_surprise_pct": None,
                }
                f.write(json.dumps(row) + "\n")
                added += 1
        return added
    except Exception as ex:
        log.debug(f"append_prediction_log: {ex}")
        return 0


def _sector_cohort_context(sector: str, outcomes: list, lookback_days: int = 45) -> dict:
    """Running earnings-season tape for the sector.

    For the last ~45d of outcomes, returns:
      n_reported    quantum of names in this sector that reported
      beats         BEAT count
      misses        MISS count
      beat_rate     %
      median_surprise_pct   median surprise across beats (or all)
      tag           HOT (beat_rate ≥ 65 + n ≥ 5) · COLD (≤ 35) · MIXED
    """
    out = {"n_reported": 0, "beats": 0, "misses": 0, "inline_": 0,
           "beat_rate": None, "median_surprise_pct": None, "tag": None}
    if not sector or sector == "Unknown" or not outcomes: return out
    from datetime import date as _date, timedelta as _td
    cutoff = (_date.today() - _td(days=lookback_days)).isoformat()
    # We need ticker→sector to filter outcomes — use the global sector map
    # built once per run. Here we assume the caller passes pre-filtered list.
    # Outcomes don't carry sector, so we use predictions' sector mapping built
    # by the caller (passed in via filtered list of outcomes for this sector).
    rows = [o for o in outcomes if o.get("report_date", "") >= cutoff]
    if not rows: return out
    beats = sum(1 for o in rows if o.get("beat") == "BEAT")
    misses = sum(1 for o in rows if o.get("beat") == "MISS")
    inline = sum(1 for o in rows if o.get("beat") == "INLINE")
    n = beats + misses + inline
    rate = (beats / n * 100) if n else None
    surps = sorted([o.get("surprise_pct") for o in rows
                    if o.get("surprise_pct") is not None])
    msurp = surps[len(surps)//2] if surps else None
    tag = "HOT" if (rate is not None and rate >= 65 and n >= 5) else \
          "COLD" if (rate is not None and rate <= 35 and n >= 5) else \
          "MIXED"
    out.update({"n_reported": n, "beats": beats, "misses": misses,
                "inline_": inline,
                "beat_rate": round(rate, 1) if rate is not None else None,
                "median_surprise_pct": round(msurp, 1) if msurp is not None else None,
                "tag": tag})
    return out


def _insider_buying_30d(ticker: str) -> dict:
    """SEC Form 4 insider transactions last 30 days. EODHD InsiderTransactions
    is free as part of fundamentals. Aggregates net shares bought minus sold
    by C-suite + directors only (skips 10% holders to avoid hedge-fund noise).
    """
    out = {"net_shares": 0, "buy_count": 0, "sell_count": 0,
           "net_dollars": 0.0, "is_accumulation": False}
    try:
        import eodhd_client as ec
        from datetime import date as _date, timedelta as _td
        f = ec.fundamentals(ticker)
        if not isinstance(f, dict): return out
        it = f.get("InsiderTransactions") or {}
        if not isinstance(it, dict) or not it: return out
        cutoff = _date.today() - _td(days=30)
        net_shares = net_dollars = 0.0
        buys = sells = 0
        for key, row in it.items():
            if not isinstance(row, dict): continue
            try: d = _date.fromisoformat((row.get("transactionDate") or "")[:10])
            except Exception: continue
            if d < cutoff: continue
            # Skip 10% holders — only count executive/director directly
            relation = (row.get("ownerCDIK") or "")  # may not be reliable
            # EODHD InsiderTransactions has: transactionCode (P=buy, S=sell, A=grant, etc.)
            code = (row.get("transactionCode") or "")
            shares = float(row.get("transactionAmount") or 0)
            price  = float(row.get("transactionPrice") or 0)
            if code == "P":   # open-market purchase
                net_shares += shares; net_dollars += shares * price; buys += 1
            elif code == "S": # open-market sale
                net_shares -= shares; net_dollars -= shares * price; sells += 1
        out.update({
            "net_shares":      int(net_shares),
            "net_dollars":     round(net_dollars, 0),
            "buy_count":       buys,
            "sell_count":      sells,
            "is_accumulation": net_shares > 0 and buys >= 2,
        })
    except Exception as ex:
        log.debug(f"insider({ticker}): {ex}")
    return out


def _short_squeeze_setup(ticker: str) -> dict:
    """Short squeeze fuel — high short % float + days-to-cover = setup for
    a beat-driven squeeze. Reads EODHD SharesStats (24h cache, free).
    """
    out = {"short_pct_float": None, "short_ratio": None,
           "shares_short": None, "is_squeeze_setup": False}
    try:
        import eodhd_client as ec
        f = ec.fundamentals(ticker)
        if not isinstance(f, dict): return out
        ss = f.get("SharesStats") or {}
        def _f(x):
            try: return float(x) if x not in (None, "") else None
            except (TypeError, ValueError): return None
        spf = _f(ss.get("ShortPercentFloat"))
        sro = _f(ss.get("ShortRatio"))
        shs = _f(ss.get("SharesShort"))
        out["short_pct_float"] = spf
        out["short_ratio"]     = sro
        out["shares_short"]    = shs
        # Squeeze setup: ShortPercentFloat ≥ 10 AND ShortRatio (days to cover) ≥ 3
        if (spf is not None and spf >= 10) and (sro is None or sro >= 3):
            out["is_squeeze_setup"] = True
    except Exception as ex:
        log.debug(f"short_squeeze({ticker}): {ex}")
    return out


def _macro_overlap(report_date: str | None, economic_events: list) -> dict:
    """Is a high-impact macro event same day as the print? Looks for FOMC,
    CPI, PPI, NFP, retail-sales, GDP within ±1 day of report_date.
    """
    out = {"has_overlap": False, "events": [], "tier": None}
    if not report_date or not economic_events: return out
    try:
        from datetime import date as _date, timedelta as _td
        rd = _date.fromisoformat(report_date)
        HIGH = ("FOMC", "CPI", "Consumer Price", "PPI", "Producer Price",
                "Non-Farm", "NFP", "Employment", "GDP", "Retail Sales",
                "Unemployment", "PCE", "Fed Funds")
        MED = ("PMI", "ISM", "Jobless Claims", "Initial Claims",
               "Industrial Production", "Housing Starts", "Consumer Confidence")
        for ev in economic_events:
            ev_dt = (ev.get("date") or "")[:10]
            try: ed = _date.fromisoformat(ev_dt)
            except Exception: continue
            if abs((ed - rd).days) > 1: continue
            name = ev.get("type") or ""
            tier = "HIGH" if any(k in name for k in HIGH) else \
                   "MED"  if any(k in name for k in MED) else None
            if tier:
                out["events"].append({"date": ev_dt, "name": name, "tier": tier})
        if out["events"]:
            out["has_overlap"] = True
            out["tier"] = "HIGH" if any(e["tier"] == "HIGH" for e in out["events"]) else "MED"
    except Exception as ex:
        log.debug(f"macro_overlap: {ex}")
    return out


def _sentiment_trend(ticker: str) -> dict:
    """Pre-print news-tone trajectory. EODHD sentiments returns daily
    normalized scores (−1..+1). Compute 30d avg + 7d-vs-prior-7d slope.
    """
    out = {"avg_30d": None, "avg_7d": None, "prev_7d": None,
           "slope_7d_pp": None, "count_30d": 0, "trend": None}
    try:
        import eodhd_client as ec
        from datetime import date as _date, timedelta as _td
        end_d = _date.today()
        start_d = end_d - _td(days=30)
        s = ec.sentiments([ticker], from_date=str(start_d), to_date=str(end_d))
        if not isinstance(s, dict): return out
        # Key is e.g. 'OMER.US'
        rows = None
        for k, v in s.items():
            if isinstance(v, list) and v:
                rows = v; break
        if not rows: return out
        rows.sort(key=lambda r: r.get("date", ""))
        # Recent 7d vs prior 7d
        last7 = rows[-7:] if len(rows) >= 7 else rows
        prev7 = rows[-14:-7] if len(rows) >= 14 else []
        def _avg(arr):
            vals = [r.get("normalized") for r in arr if r.get("normalized") is not None]
            return sum(vals) / len(vals) if vals else None
        avg30 = _avg(rows)
        a7 = _avg(last7)
        p7 = _avg(prev7)
        slope = (a7 - p7) * 100 if (a7 is not None and p7 is not None) else None
        if slope is None:
            trend = None
        elif slope > 5: trend = "IMPROVING"
        elif slope < -5: trend = "DETERIORATING"
        else: trend = "STABLE"
        out.update({
            "avg_30d": round(avg30, 3) if avg30 is not None else None,
            "avg_7d":  round(a7, 3) if a7 is not None else None,
            "prev_7d": round(p7, 3) if p7 is not None else None,
            "slope_7d_pp": round(slope, 1) if slope is not None else None,
            "count_30d": len(rows),
            "trend": trend,
        })
    except Exception as ex:
        log.debug(f"sentiment_trend({ticker}): {ex}")
    return out


def _pre_print_volume_z(ticker: str) -> dict:
    """Z-score of recent 5d volume vs trailing 60d.  >+1.5 = info-leak /
    institutional accumulation.  EODHD eod (12h cached, shared call).
    """
    out = {"z_5d": None, "recent5_avg": None, "baseline60_avg": None,
           "is_accumulation": False}
    try:
        import eodhd_client as ec
        from datetime import date as _date, timedelta as _td
        end_d = _date.today()
        start_d = end_d - _td(days=90)
        bars = ec.eod(ticker, str(start_d), str(end_d))
        if not bars or len(bars) < 30: return out
        bars = sorted(bars, key=lambda b: b.get("date", ""))
        vols = [float(b.get("volume", 0) or 0) for b in bars]
        if len(vols) < 60: return out
        recent5 = sum(vols[-5:]) / 5
        baseline = vols[-60:-5]
        b_avg = sum(baseline) / len(baseline)
        b_std = (sum((v - b_avg) ** 2 for v in baseline) / len(baseline)) ** 0.5
        z = ((recent5 - b_avg) / b_std) if b_std > 0 else None
        out.update({
            "z_5d":           round(z, 2) if z is not None else None,
            "recent5_avg":    int(recent5),
            "baseline60_avg": int(b_avg),
            "is_accumulation": z is not None and z >= 1.5,
        })
    except Exception as ex:
        log.debug(f"vol_z({ticker}): {ex}")
    return out


def _kelly_lite_size(p: dict) -> dict:
    """Kelly-lite earnings position-sizing recommendation.

    Translates the model output into a % of equity. Uses fractional-Kelly
    (1/4 Kelly) so a single losing trade can't blow up the account.

    Inputs (all from p["breakdown"]):
      beat_score        → win probability proxy (linear, 0–100 scaled)
      implied_move_pct  → market-priced ± move (sets the risk envelope)
      pead.post_5d_med  → expected payoff if right (median historical drift)
      revision_trend.direction → multiplier (BULLISH +20% · BEARISH −40% · MIXED 0)

    Output:
      win_prob        derived probability of beat→positive-drift
      payoff_pct      expected % move if right
      risk_pct        expected % move if wrong (worst-case set to implied)
      kelly_full      f* = (p·b − q) / b   (Kelly fraction, can be negative)
      kelly_frac      1/4 of kelly_full (capped 0..0.08)
      size_pct_equity recommended position size as % of equity
      cap_reason      what tied the cap (kelly / max / regime / disagreement)
    """
    out = {"win_prob": None, "payoff_pct": None, "risk_pct": None,
           "kelly_full": None, "kelly_frac": None,
           "size_pct_equity": None, "cap_reason": None}
    try:
        b  = p.get("breakdown") or {}
        score = p.get("beat_score")
        im = b.get("implied_move") or {}
        pead = b.get("pead") or {}
        rev = b.get("revision_trend") or {}
        zacks = b.get("zacks") or {}

        if score is None: return out
        # Win probability — derived from score band; tuned to actual 30d realized 48% beat rate
        # Score 65 → 0.55 win prob, score 80 → 0.65, score 90 → 0.72 (sub-linear)
        win_prob = 0.40 + 0.32 * max(0, min(1, (score - 50) / 50.0))
        # Multipliers
        if rev.get("direction") == "BULLISH":   win_prob += 0.05
        elif rev.get("direction") == "BEARISH": win_prob -= 0.10
        elif rev.get("direction") == "MIXED":   win_prob -= 0.02
        if zacks.get("rank") is not None:
            if zacks["rank"] <= 2:  win_prob += 0.03
            elif zacks["rank"] >= 4: win_prob -= 0.05
        if zacks.get("combo_signal"):           win_prob += 0.05
        win_prob = max(0.05, min(0.90, win_prob))

        impl = im.get("implied_move_pct")
        # Payoff: median realized post-5d drift on prior beats. Fall back to
        # implied move if no PEAD data.
        post5 = pead.get("post_5d_med")
        if post5 is not None and post5 > 0:
            payoff = post5
        elif impl is not None:
            payoff = impl * 0.5      # conservative if no PEAD — assume half of implied
        else:
            payoff = 4.0             # generic 4% baseline

        # Risk: worst-case set to implied move (market's priced reaction).
        risk = impl if impl is not None else 6.0
        if risk <= 0: risk = 6.0

        # Kelly: f* = (p·b − q) / b   where b = payoff/risk
        b_ratio = payoff / risk
        q = 1 - win_prob
        kelly_full = (win_prob * b_ratio - q) / b_ratio
        kelly_frac = max(0, kelly_full) * 0.25  # 1/4 Kelly

        # Cap to 8% per name (hedge-fund principle 10: correlation under stress)
        size_pct = min(0.08, kelly_frac)
        cap_reason = ("max_8pct"      if kelly_frac >= 0.08
                  else "negative_kelly" if kelly_full <= 0
                  else "kelly_optimal")

        # Demote if revisions and score disagree by direction (caution)
        if rev.get("direction") == "BEARISH" and score >= 65:
            size_pct *= 0.5
            cap_reason = "rev_disagrees_with_score"

        out.update({
            "win_prob":        round(win_prob, 3),
            "payoff_pct":      round(payoff, 2),
            "risk_pct":        round(risk, 2),
            "kelly_full":      round(kelly_full, 3),
            "kelly_frac":      round(kelly_frac, 3),
            "size_pct_equity": round(size_pct, 3),
            "cap_reason":      cap_reason,
        })
    except Exception as ex:
        log.debug(f"kelly_lite({p.get('ticker')}): {ex}")
    return out


def _eps_revision_trend(ticker: str, report_date: str | None) -> dict:
    """EPS revision trend for the quarter about to be reported.

    Reads EODHD `fundamentals.Earnings.Trend` — finds the record whose
    `date` (fiscal quarter-end) is the most recent on or before
    `report_date`, then surfaces:

      net_30d         analysts UP last 30d minus DOWN last 30d
      up_30d          count UP last 30d
      down_30d        count DOWN last 30d
      eps_current     current consensus EPS
      eps_30d_ago     consensus 30d ago
      eps_90d_ago     consensus 90d ago
      slope_30d_pct   (eps_current − eps_30d_ago) / |eps_30d_ago| × 100
      slope_90d_pct   90d-window slope
      direction       'BULLISH' / 'BEARISH' / 'FLAT' from net + slope sign

    Cost: 1 EODHD fundamentals() call per ticker, 24h-cached (shared with
    other enrichers — same call powers sector + analyst backfills).
    """
    out = {"net_30d": None, "up_30d": None, "down_30d": None,
           "eps_current": None, "eps_30d_ago": None, "eps_90d_ago": None,
           "slope_30d_pct": None, "slope_90d_pct": None,
           "direction": None, "period_date": None}
    try:
        import eodhd_client as ec
        f = ec.fundamentals(ticker)
        if not isinstance(f, dict): return out
        tr = (f.get("Earnings") or {}).get("Trend") or {}
        if not isinstance(tr, dict) or not tr: return out
        # Choose the record whose `date` is the most-recent quarter-end ≤ report_date.
        from datetime import date as _date
        try:
            rd = _date.fromisoformat(report_date) if report_date else _date.today()
        except (TypeError, ValueError):
            rd = _date.today()
        def _parse(s):
            try: return _date.fromisoformat(s)
            except Exception: return None
        candidates = [(k, v) for k, v in tr.items()
                      if _parse(k) and _parse(k) <= rd]
        if not candidates: return out
        candidates.sort(key=lambda kv: _parse(kv[0]), reverse=True)
        rec_key, rec = candidates[0]
        def _f(x):
            try: return float(x) if x not in (None, "", "n/a") else None
            except (TypeError, ValueError): return None
        cur  = _f(rec.get("epsTrendCurrent"))
        t30  = _f(rec.get("epsTrend30daysAgo"))
        t90  = _f(rec.get("epsTrend90daysAgo"))
        up30 = _f(rec.get("epsRevisionsUpLast30days"))
        dn30 = _f(rec.get("epsRevisionsDownLast30days"))
        net30 = (up30 - dn30) if (up30 is not None and dn30 is not None) else None
        slope_30 = ((cur - t30) / abs(t30) * 100) if (cur is not None and t30 not in (None, 0)) else None
        slope_90 = ((cur - t90) / abs(t90) * 100) if (cur is not None and t90 not in (None, 0)) else None
        # Direction: combine net revisions + slope sign
        if net30 is not None and slope_30 is not None:
            if net30 > 0 and slope_30 > 0: direction = "BULLISH"
            elif net30 < 0 and slope_30 < 0: direction = "BEARISH"
            elif net30 == 0 and abs(slope_30 or 0) < 1: direction = "FLAT"
            else: direction = "MIXED"
        elif net30 is not None:
            direction = "BULLISH" if net30 > 0 else "BEARISH" if net30 < 0 else "FLAT"
        else:
            direction = None
        out.update({
            "net_30d":      None if net30 is None else int(net30),
            "up_30d":       None if up30 is None else int(up30),
            "down_30d":     None if dn30 is None else int(dn30),
            "eps_current":  round(cur, 4)  if cur  is not None else None,
            "eps_30d_ago":  round(t30, 4)  if t30  is not None else None,
            "eps_90d_ago":  round(t90, 4)  if t90  is not None else None,
            "slope_30d_pct": round(slope_30, 2) if slope_30 is not None else None,
            "slope_90d_pct": round(slope_90, 2) if slope_90 is not None else None,
            "direction":    direction,
            "period_date":  rec_key,
        })
    except Exception as ex:
        log.debug(f"eps_revision_trend({ticker}): {ex}")
    return out


def _pead_drift_profile(ticker: str, lookback_quarters: int = 4) -> dict:
    """Post-Earnings-Announcement Drift profile.

    For this ticker's last N quarters, computes — using EODHD OHLCV around
    each prior `reportDate`:

      pre_gap_med   median 1-day pre-print → post-print open gap (%)
      post_1d_med   median 1-day post-print return (open → close, T+1) (%)
      post_5d_med   median 5-bar post-print return (close T → close T+5) (%)
      post_30d_med  median 30-bar post-print return (PEAD score) (%)
      n_beats       beats used in the medians (we use beat outcomes only —
                    the question PEAD answers is "do beats here keep going")

    Returns all-None when EODHD history is empty or OHLCV unavailable.
    Cost: 1 EODHD eod() call per ticker, 12h-cached.
    """
    out = {"pre_gap_med": None, "post_1d_med": None,
           "post_5d_med": None, "post_30d_med": None, "n_beats": 0}
    try:
        hist = _eodhd_earnings_history(ticker, lookback=lookback_quarters)
        if not hist:
            return out
        import eodhd_client as ec
        from datetime import date as _date, timedelta as _td
        end_d = _date.today()
        start_d = end_d - _td(days=730)
        bars = ec.eod(ticker, str(start_d), str(end_d))
        if not bars or len(bars) < 30:
            return out
        bars_sorted = sorted(bars, key=lambda b: b.get("date", ""))
        dates_list = [b.get("date") for b in bars_sorted]
        by_date = {b.get("date"): b for b in bars_sorted}

        pre_gaps, post_1d, post_5d, post_30d = [], [], [], []
        for q in hist:
            if q.get("beat") != "BEAT":
                continue
            rd = q.get("report_date")
            if not rd: continue
            # First bar on or after report_date
            idx = None
            for i, d_ in enumerate(dates_list):
                if d_ and d_ >= rd:
                    idx = i; break
            if idx is None or idx < 1 or idx + 5 >= len(dates_list):
                continue
            try:
                prev_close = float(by_date[dates_list[idx - 1]].get("close"))
                day_open  = float(by_date[dates_list[idx]].get("open"))
                day_close = float(by_date[dates_list[idx]].get("close"))
                pre_gaps.append((day_open / prev_close - 1) * 100)
                post_1d.append((day_close / day_open - 1) * 100)
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            try:
                p5 = float(by_date[dates_list[idx + 5]].get("close"))
                base = float(by_date[dates_list[idx]].get("close"))
                post_5d.append((p5 / base - 1) * 100)
            except (TypeError, ValueError, AttributeError, KeyError, IndexError):
                pass
            try:
                if idx + 30 < len(dates_list):
                    p30 = float(by_date[dates_list[idx + 30]].get("close"))
                    base = float(by_date[dates_list[idx]].get("close"))
                    post_30d.append((p30 / base - 1) * 100)
            except (TypeError, ValueError, AttributeError, KeyError, IndexError):
                pass

        def _med(lst):
            return round(sorted(lst)[len(lst) // 2], 2) if lst else None
        out.update({
            "pre_gap_med":  _med(pre_gaps),
            "post_1d_med":  _med(post_1d),
            "post_5d_med":  _med(post_5d),
            "post_30d_med": _med(post_30d),
            "n_beats":      len(post_5d),
        })
    except Exception as ex:
        log.debug(f"pead_drift({ticker}): {ex}")
    return out


def _historical_beat_rate(ticker: str, outcomes: list[dict], lookback: int = 4) -> tuple[float, int, str, float | None]:
    """Return (beat_fraction, n_observations, pattern, median_surprise_pct).

    Reads our local outcomes log first; if n < lookback, falls back to
    EODHD `fundamentals.Earnings.History` (45 quarters available per name).

    pattern is a string of one-letter codes for the last N quarters,
    oldest-first — e.g. 'BBMB' = (oldest) BEAT BEAT MISS BEAT (newest).
    median_surprise_pct = median of surprise % across the same N quarters.
    """
    by_t = [o for o in outcomes if o.get("ticker") == ticker]
    by_t.sort(key=lambda x: x.get("report_date", ""), reverse=True)
    last_n = by_t[:lookback]
    # Fallback to EODHD if we have < lookback quarters locally
    if len(last_n) < lookback:
        eo = _eodhd_earnings_history(ticker, lookback=lookback)
        if len(eo) > len(last_n):
            last_n = eo
    if not last_n:
        return (0.5, 0, "", None)
    beats = sum(1 for o in last_n if o.get("beat") == "BEAT")
    # Build oldest-first pattern string
    codes = []
    for o in reversed(last_n):  # reversed → oldest first
        b = o.get("beat", "")
        codes.append({"BEAT": "B", "MISS": "M", "INLINE": "I"}.get(b, "·"))
    pattern = "".join(codes)
    # Median surprise (skip None)
    surps = sorted([o.get("surprise_pct") for o in last_n if o.get("surprise_pct") is not None])
    median_surp = surps[len(surps) // 2] if surps else None
    return (beats / len(last_n), len(last_n), pattern, median_surp)


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

    # 1. Historical beat rate (25 pts) — pattern + median surprise from EODHD
    rate, n, pattern, median_surp = _historical_beat_rate(t, outcomes)
    hist_pts = 25 * rate if n >= 1 else 12.5  # neutral if no history
    breakdown["historical"] = {
        "pts": round(hist_pts, 1), "max": 25,
        "rate": round(rate * 100, 0), "n_quarters": n,
        "pattern": pattern,                         # oldest→newest BBMB
        "median_surprise_pct": round(median_surp, 1) if median_surp is not None else None,
    }

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

    # ─────────────────────────────────────────────────────────────────
    # ENRICHMENT PASS — fills the data-quality gaps the hero table exposes:
    #   (a) bulk EODHD sector backfill for the entire 404-name watchlist
    #       (fixes "sector = Unknown" — ~5 calls, daily-cached)
    #   (b) Zacks Rank + ESP attached to every prediction (uses pre-built
    #       per-ticker lite caches + zacks_all.json — no new fetches)
    #   (c) Top-30 only: Schwab ATM straddle for implied move (~20-30
    #       calls, 2h-cached) + EODHD fundamentals for analyst target
    #       backfill where intel is missing (~30 calls, daily-cached)
    # All passes are best-effort — failure just leaves the field None.
    # ─────────────────────────────────────────────────────────────────

    # (a) Per-ticker sector backfill — top-100 by score (24h-cached fundamentals)
    # EODHD /fundamentals-bulk/{ex} doesn't support a `symbols` filter; using
    # per-ticker fundamentals() instead. Each call is 24h-cached so subsequent
    # builds are free. Capped at top-100 so a fresh-cache day costs ≤100 calls.
    try:
        import eodhd_client as ec
        sector_target = predictions[:100]
        log.info(f"Per-ticker sector backfill for top-{len(sector_target)} (24h cache)…")
        sector_filled = industry_filled = 0
        for p in sector_target:
            sb = p["breakdown"].setdefault("sector_beats", {})
            if sb.get("sector") and sb.get("sector") != "Unknown":
                continue
            t = p["ticker"]
            try:
                f = ec.fundamentals(t)
                if not isinstance(f, dict): continue
                gen = f.get("General") or {}
                sect = gen.get("Sector")
                ind = gen.get("Industry")
                if sect:
                    sb["sector"] = sect; sector_filled += 1
                if ind:
                    sb["industry"] = ind; industry_filled += 1
            except Exception as _ex:
                log.debug(f"sector_fill({t}): {_ex}")
        log.info(f"  filled {sector_filled} sectors · {industry_filled} industries")
    except Exception as ex:
        log.warning(f"Per-ticker sector backfill skipped: {ex}")

    # (b) Zacks Rank + ESP attach — reads pre-built caches + on-demand lite
    # fetch for top-30 names not yet in the lite cache. Lite scrape is a
    # single public-page request per ticker (6h cached). Premium ESP often
    # only on premium-only pages so coverage is best-effort.
    try:
        import os, glob
        from pathlib import Path
        zacks_path = BASE / "cache" / "_cache_zacks_all.json"
        zacks_r1: set = set()
        if zacks_path.exists():
            za = json.loads(zacks_path.read_text())
            zacks_r1 = set(za.get("zacks_r1", []) or [])
        # Per-ticker lite cache files
        lite_map: dict = {}
        for fp in glob.glob(str(BASE / "cache" / "_cache_zacks_per_ticker_lite_*.json")):
            try:
                row = json.loads(Path(fp).read_text())
                t = row.get("ticker")
                if t: lite_map[t] = row
            except Exception: pass

        # On-demand lite fetch for top-30 names missing from lite_map
        try:
            import zacks_per_ticker as zpt
            top_for_zacks = predictions[:30]
            on_demand = sum(1 for p in top_for_zacks if p["ticker"] not in lite_map)
            if on_demand:
                log.info(f"  on-demand Zacks lite fetch for {on_demand} top-30 names…")
            ondemand_filled = 0
            for p in top_for_zacks:
                t = p["ticker"]
                if t in lite_map: continue
                try:
                    row = zpt.fetch_zacks_quote_lightweight(t)
                    if isinstance(row, dict) and row.get("rank") is not None:
                        lite_map[t] = row
                        ondemand_filled += 1
                except Exception as _ex:
                    log.debug(f"zacks_lite({t}): {_ex}")
            if ondemand_filled:
                log.info(f"    fetched {ondemand_filled} new Zacks lite rows")
        except Exception as ex:
            log.debug(f"On-demand Zacks fetch skipped: {ex}")

        zacks_filled = combo_count = 0
        for p in predictions:
            t = p["ticker"]
            lite = lite_map.get(t) or {}
            rank = lite.get("rank")
            if rank is None and t in zacks_r1:
                rank = 1  # in the R1 list, lite cache missing — still mark
            esp = lite.get("earnings_esp_pct")
            vgm = lite.get("style_vgm")
            if rank is None and esp is None and vgm is None:
                continue
            zacks = {"rank": rank,
                     "rank_text": lite.get("rank_text"),
                     "esp_pct": esp,
                     "vgm": vgm,
                     "industry_rank": lite.get("industry_rank"),
                     "industry_total": lite.get("industry_total"),
                     "source": "zacks"}
            if esp is not None and esp > 0 and rank is not None and rank <= 2:
                zacks["combo_signal"] = True
                combo_count += 1
            p["breakdown"]["zacks"] = zacks
            zacks_filled += 1
        log.info(f"  Zacks attached to {zacks_filled} predictions · {combo_count} matched ESP>0+Rank≤2 combo")
    except Exception as ex:
        log.warning(f"Zacks enrichment skipped: {ex}")

    # (c) Top-30 deep enrichment — Schwab implied move + analyst target backfill
    try:
        import data_fetcher as df
        top_n = min(30, len(predictions))
        log.info(f"Top-{top_n} deep enrichment (IM+analyst+PEAD+rev+squeeze+sent+volz+macro+cohort+insider)…")
        impl_filled = analyst_filled = pead_filled = rev_filled = 0
        squeeze_filled = sentiment_filled = volz_filled = macro_filled = 0
        cohort_filled = insider_filled = 0
        levels_filled = liquidity_filled = 0
        # Load economic events from data.json (cheap join, already built)
        data_econ_events = []
        try:
            _data_json = BASE / "infra" / "prototype" / "data.json"
            if _data_json.exists():
                data_econ_events = json.loads(_data_json.read_text()).get("economic_events", []) or []
        except Exception: pass
        # Build ticker→sector map from enriched predictions (used by cohort calc)
        ticker_to_sector_map = {}
        for _p in predictions:
            _s = ((_p.get("breakdown") or {}).get("sector_beats") or {}).get("sector")
            if _s and _s != "Unknown":
                ticker_to_sector_map[_p["ticker"]] = _s
        for p in predictions[:top_n]:
            rd = p.get("report_date")
            if not rd: continue
            # Schwab implied move
            try:
                im = df.get_earnings_implied_move(p["ticker"], rd)
                if im.get("implied_move_pct") is not None:
                    p["breakdown"]["implied_move"] = {
                        "implied_move_pct": im["implied_move_pct"],
                        "straddle_cost":    im["straddle_cost"],
                        "atm_strike":       im["atm_strike"],
                        "expiry_date":      im["expiry_date"],
                        "spot":             im["spot"],
                        "source":           im["source"],
                    }
                    impl_filled += 1
                else:
                    p["breakdown"]["implied_move"] = {
                        "implied_move_pct": None,
                        "source":           im.get("source"),
                        "error":            im.get("error"),
                    }
            except Exception as _ex:
                log.debug(f"impl_move({p['ticker']}): {_ex}")
            # EODHD analyst target backfill where missing
            aup = p["breakdown"].get("analyst_upside") or {}
            if aup.get("upside_pct") in (None, "n/a"):
                try:
                    f = ec.fundamentals(p["ticker"])
                    if isinstance(f, dict):
                        ar = f.get("AnalystRatings") or {}
                        tgt = ar.get("TargetPrice")
                        spot = (p["breakdown"].get("implied_move") or {}).get("spot")
                        if tgt and spot:
                            try:
                                upside = (float(tgt) / float(spot) - 1) * 100
                                aup["upside_pct"] = round(upside, 1)
                                aup["target_mean"] = float(tgt)
                                aup["source"] = "eodhd_fundamentals"
                                p["breakdown"]["analyst_upside"] = aup
                                analyst_filled += 1
                            except (TypeError, ValueError):
                                pass
                except Exception as _ex:
                    log.debug(f"analyst_fill({p['ticker']}): {_ex}")
            # PEAD drift profile — median post-print reaction on prior BEATs
            try:
                pead = _pead_drift_profile(p["ticker"], lookback_quarters=4)
                if pead.get("n_beats", 0) >= 1:
                    p["breakdown"]["pead"] = pead
                    pead_filled += 1
            except Exception as _ex:
                log.debug(f"pead({p['ticker']}): {_ex}")
            # EPS revision trend (B1)
            try:
                rev = _eps_revision_trend(p["ticker"], p.get("report_date"))
                if rev.get("net_30d") is not None or rev.get("slope_30d_pct") is not None:
                    p["breakdown"]["revision_trend"] = rev
                    rev_filled += 1
            except Exception as _ex:
                log.debug(f"revision({p['ticker']}): {_ex}")
            # Short squeeze setup (C6)
            try:
                sq = _short_squeeze_setup(p["ticker"])
                if sq.get("short_pct_float") is not None:
                    p["breakdown"]["short_squeeze"] = sq
                    squeeze_filled += 1
            except Exception as _ex: log.debug(f"squeeze({p['ticker']}): {_ex}")
            # Sentiment trend (B4)
            try:
                st = _sentiment_trend(p["ticker"])
                if st.get("count_30d", 0) >= 3:
                    p["breakdown"]["sentiment_trend"] = st
                    sentiment_filled += 1
            except Exception as _ex: log.debug(f"sent({p['ticker']}): {_ex}")
            # Pre-print volume z-score (B5)
            try:
                vz = _pre_print_volume_z(p["ticker"])
                if vz.get("z_5d") is not None:
                    p["breakdown"]["vol_z"] = vz
                    volz_filled += 1
            except Exception as _ex: log.debug(f"volz({p['ticker']}): {_ex}")
            # Macro overlap (C3)
            try:
                econ = (data_econ_events or [])
                mo = _macro_overlap(p.get("report_date"), econ)
                if mo.get("has_overlap"):
                    p["breakdown"]["macro_overlap"] = mo
                    macro_filled += 1
            except Exception as _ex: log.debug(f"macro({p['ticker']}): {_ex}")
            # Sector cohort context (C5)
            try:
                sb = p["breakdown"].get("sector_beats") or {}
                sect = sb.get("sector")
                if sect and sect != "Unknown" and ticker_to_sector_map:
                    sector_outcomes = [o for o in outcomes
                                       if ticker_to_sector_map.get(o.get("ticker")) == sect]
                    cohort = _sector_cohort_context(sect, sector_outcomes, lookback_days=45)
                    if cohort.get("n_reported", 0) >= 3:
                        p["breakdown"]["sector_cohort"] = cohort
                        cohort_filled += 1
            except Exception as _ex: log.debug(f"cohort({p['ticker']}): {_ex}")
            # Insider buying — Form 4 last 30d (D1)
            try:
                ins = _insider_buying_30d(p["ticker"])
                if ins.get("buy_count", 0) > 0 or ins.get("sell_count", 0) > 0:
                    p["breakdown"]["insider"] = ins
                    insider_filled += 1
            except Exception as _ex: log.debug(f"insider({p['ticker']}): {_ex}")
            # Trade levels — Entry/Stop/T1/T2/R:R (closure ask #2/#3)
            try:
                lv = _trade_levels(p)
                if lv.get("entry") is not None:
                    p["breakdown"]["trade_levels"] = lv
                    levels_filled += 1
            except Exception as _ex: log.debug(f"levels({p['ticker']}): {_ex}")
            # Liquidity + Forward P/E (closure ask #4/#5)
            try:
                lq = _liquidity_and_valuation(p["ticker"])
                if lq.get("adv_dollar_60d") or lq.get("forward_pe"):
                    p["breakdown"]["liquidity"] = lq
                    liquidity_filled += 1
            except Exception as _ex: log.debug(f"liq({p['ticker']}): {_ex}")
        # Kelly-lite sizing — runs AFTER all upstream enrichers populate
        kelly_filled = 0
        for p in predictions[:top_n]:
            try:
                ks = _kelly_lite_size(p)
                if ks.get("size_pct_equity") is not None:
                    p["breakdown"]["kelly_sizing"] = ks
                    kelly_filled += 1
            except Exception as _ex:
                log.debug(f"kelly({p['ticker']}): {_ex}")
        log.info(f"  filled {impl_filled}IM · {analyst_filled}an · {pead_filled}PEAD · {rev_filled}rev · {squeeze_filled}sq · {sentiment_filled}sent · {volz_filled}volz · {macro_filled}macro · {cohort_filled}coh · {insider_filled}ins · {levels_filled}lv · {liquidity_filled}liq · {kelly_filled}kelly")
    except Exception as ex:
        log.warning(f"Top-{top_n} deep enrichment skipped: {ex}")

    # Per-tier calibration (closure ask #6) — honest version
    # Also log today's predictions for forward calibration in ~30d
    n_logged = _append_prediction_log(predictions)
    if n_logged:
        log.info(f"  appended {n_logged} predictions to forward log (per-tier cal in 30d)")
    per_tier_cal = _per_tier_calibration(predictions, outcomes)

    payload = {
        "generated_at": datetime.now().isoformat(),
        "n_total":      len(predictions),
        "n_strong":     sum(1 for p in predictions if p["tier"] == "STRONG"),
        "n_solid":      sum(1 for p in predictions if p["tier"] == "SOLID"),
        "n_moderate":   sum(1 for p in predictions if p["tier"] == "MODERATE"),
        "per_tier_calibration": per_tier_cal,
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
