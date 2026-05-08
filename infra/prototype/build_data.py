#!/usr/bin/env python3
"""Rebuild prototype data.json + tickers.json from cache/last_bundle.json.

Includes BUY + WATCH + SHORT rows from the rich candidate lists (105+ fields each),
mapped down to the compact schema the prototype dashboard expects, while preserving
nested dicts (elliott_wave, reaction_checklist, trade_plan) in tickers.json for the
elite-detail full-analysis page.
"""
import json
from pathlib import Path

import sys
ROOT   = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "cache/last_bundle.json"
BUNDLE_HISTORY = ROOT / "cache/bundles"  # dated snapshots for scan-over-scan diff
PORTFOLIO = ROOT / "data/portfolio_state.json"
SIGNAL_LOG = ROOT / "data/signal_log.json"
sys.path.insert(0, str(ROOT))  # so we can import eodhd_client


# Module-level cache for prior-bundle index (set by main(), read by compact_row())
_PREV_BUNDLE_INDEX: dict = {}
_PREV_BUNDLE_DATE: str = ""

# System-level gating state (circuit breaker / forced cash / macro blackout) —
# set by main() so _compute_mode_verdicts can demote Position/Invest BUYs in
# lockdown, matching what the engine already does for Swing.
_SYSTEM_GATE_ACTIVE: bool = False
_SYSTEM_GATE_REASON: str = ""


def _sanitize_options(od: dict) -> dict:
    """Collapse stale Schwab OAuth error blobs into a clean placeholder.

    When source==schwab AND there's an error AND iv_rank is None, the data
    is unusable. Return a minimal placeholder so V2 renders cleanly without
    a 200-character OAuth stack trace leaking into the bundle.
    """
    if not isinstance(od, dict) or not od:
        return od
    has_data = od.get("iv_rank") is not None or od.get("put_call_ratio") is not None
    if has_data:
        return od
    err = od.get("error") or ""
    if err or od.get("source") in ("schwab", "unavailable"):
        return {
            "iv_rank": None, "iv_pct": None, "current_iv": None,
            "put_call_ratio": None, "total_call_oi": 0, "total_put_oi": 0,
            "total_call_vol": 0, "total_put_vol": 0, "max_pain": None,
            "uoa_calls": 0, "uoa_puts": 0,
            "source": "unavailable",
            "error": None,
        }
    return od


def _reject_reason_for(r: dict):
    """Resolve the reject_reason field for V2 display.

    BUYs never get a reject_reason (would contradict the verdict). Non-BUYs
    cascade: engine output → decision_state.label → kill_reason → vgm_verdict.
    """
    v = (r.get("verdict") or "").upper()
    if v == "BUY":
        return None
    rr = r.get("reject_reason")
    if rr:
        return rr
    ds = r.get("decision_state")
    if isinstance(ds, dict):
        label = ds.get("label")
        if label:
            return label
    return r.get("kill_reason") or r.get("vgm_verdict") or None


def _load_previous_bundle_index() -> dict:
    """Return {ticker: prior_record} from the most recent prior dated snapshot.

    Used for scan-over-scan diff (audit log panel). Returns {} if no prior
    snapshot exists or load fails — diff fields will simply be absent.
    """
    try:
        if not BUNDLE_HISTORY.exists():
            return {}
        snaps = sorted(BUNDLE_HISTORY.glob("20[0-9][0-9]-[0-9][0-9]-[0-9][0-9].json"))
        if len(snaps) < 2:
            return {}
        # Use second-most-recent (most recent might be today's, just-written)
        prev = json.loads(snaps[-2].read_text())
        idx: dict = {}
        for sec in ("buy_candidates", "watch_list", "all_scored", "killed",
                    "medium_term_picks", "extended_leaders"):
            for r in prev.get(sec) or []:
                if isinstance(r, dict) and r.get("ticker") and r["ticker"] not in idx:
                    idx[r["ticker"]] = r
        idx["_snapshot_date"] = snaps[-2].stem  # type: ignore
        return idx
    except Exception:
        return {}


def _compute_change_log(today: dict, prior: dict, prior_date: str) -> dict:
    """Compute scan-over-scan changes for one ticker. Returns {} if no prior."""
    if not prior:
        return {}
    cl: dict = {"prior_date": prior_date, "changes": []}
    # Verdict change
    pv = (prior.get("decision") or {}).get("verdict") if isinstance(prior.get("decision"), dict) else prior.get("verdict")
    cv = (today.get("decision") or {}).get("verdict") if isinstance(today.get("decision"), dict) else today.get("verdict")
    if pv and cv and pv != cv:
        cl["changes"].append({"field": "verdict", "from": pv, "to": cv})
    # Score delta
    ps, cs = prior.get("score"), today.get("score")
    if isinstance(ps, (int, float)) and isinstance(cs, (int, float)) and abs(cs - ps) >= 1:
        cl["changes"].append({"field": "score", "from": round(float(ps), 1), "to": round(float(cs), 1),
                              "delta": round(float(cs) - float(ps), 1)})
    # Entry quality change
    pe, ce = prior.get("entry_quality"), today.get("entry_quality")
    if pe and ce and pe != ce:
        cl["changes"].append({"field": "entry_quality", "from": pe, "to": ce})
    # Stop change
    ps_st, cs_st = prior.get("stop"), today.get("stop")
    if isinstance(ps_st, (int, float)) and isinstance(cs_st, (int, float)) and abs(cs_st - ps_st) > 0.01:
        cl["changes"].append({"field": "stop", "from": round(float(ps_st), 2), "to": round(float(cs_st), 2)})
    return cl if cl["changes"] else {}


def _fetch_fundamentals_enrichment(tickers: list) -> dict:
    """Fetch Beta, MarketCap, Float, 52wk from EODHD for missing fields.

    Also pulls extended fundamentals (segments, geo split, FCF, capex) for
    deep-dive panel in the detail page.

    2026-04-30: cap bumped 30 → 100 so every ticker shown in v2 gets a real
    company name + industry. EODHD All-In-One has 1000/min headroom so
    100 calls in proto-build phase is well under cap.
    """
    try:
        import eodhd_client as ec
        result = {}
        for sym in tickers[:100]:  # bumped from 30 — covers full v2 dashboard
            try:
                f = ec.fundamentals(sym)
                if not f:
                    continue
                gen  = f.get('General', {})
                hi   = f.get('Highlights', {})
                tech = f.get('Technicals', {})
                ss   = f.get('SharesStats', {})
                # Cash flow extras (TTM)
                cf = (f.get('Financials') or {}).get('Cash_Flow') or {}
                cf_ttm = (cf.get('quarterly') or {})
                # Sum last 4 quarters for TTM
                fcf_ttm = capex_ttm = ocf_ttm = div_ttm = buyback_ttm = None
                try:
                    quarters = list(cf_ttm.values())[:4]
                    if quarters:
                        fcf_ttm   = sum(float(q.get('freeCashFlow') or 0) for q in quarters) or None
                        capex_ttm = sum(float(q.get('capitalExpenditures') or 0) for q in quarters) or None
                        ocf_ttm   = sum(float(q.get('totalCashFromOperatingActivities') or 0) for q in quarters) or None
                        div_ttm   = sum(float(q.get('dividendsPaid') or 0) for q in quarters) or None
                        buyback_ttm = sum(float(q.get('purchaseOfStock') or 0) for q in quarters) or None
                except Exception:
                    pass
                # Revenue TTM (from income statement)
                inc = (f.get('Financials') or {}).get('Income_Statement') or {}
                inc_q = list((inc.get('quarterly') or {}).values())[:4]
                rev_ttm = None
                try:
                    rev_ttm = sum(float(q.get('totalRevenue') or 0) for q in inc_q) or None
                except Exception:
                    pass
                # Segments (revenue by business unit) — not always present in EODHD; try ESG/Other keys
                # In EODHD, segment data is in 'SegmentList' or under operational metrics; varies by ticker
                segments = []
                # Attempt parse — EODHD doesn't expose this consistently, so we leave empty if not found
                result[sym] = {
                    'name':          gen.get('Name'),
                    'industry':      gen.get('Industry'),
                    'description':   (gen.get('Description') or '')[:200],
                    'beta':          tech.get('Beta'),
                    'market_cap':    hi.get('MarketCapitalization'),
                    'float_shares':  ss.get('SharesFloat'),
                    'shares_out':    ss.get('SharesOutstanding'),
                    'week52_high':   tech.get('52WeekHigh'),
                    'week52_low':    tech.get('52WeekLow'),
                    'profit_margin': hi.get('ProfitMargin'),
                    'fwd_pe':        hi.get('ForwardPE') or hi.get('PERatio'),
                    'div_yield':     hi.get('DividendYield'),
                    'peg':           hi.get('PEGRatio'),
                    # Extended fields for fundamentals deep-dive
                    'eodhd_fund_extras': {
                        'free_cash_flow_ttm': fcf_ttm,
                        'capex_ttm': abs(capex_ttm) if capex_ttm else None,
                        'operating_cash_flow_ttm': ocf_ttm,
                        'dividends_paid_ttm': abs(div_ttm) if div_ttm else None,
                        'buybacks_ttm': abs(buyback_ttm) if buyback_ttm else None,
                        'revenue_ttm': rev_ttm,
                        'segments': segments,
                        'geographic_split': [],
                        'shares_outstanding': ss.get('SharesOutstanding'),
                        'shares_outstanding_chg_pct': ss.get('SharesOutstandingPctChange'),
                    },
                }
            except Exception:
                pass
        return result
    except ImportError:
        return {}


def _fetch_economic_events(days_ahead: int = 14) -> list:
    """Fetch upcoming US economic events from EODHD."""
    try:
        import eodhd_client as ec, requests, datetime
        key = ec._load_api_key()
        if not key:
            return []
        today = datetime.date.today().isoformat()
        end   = (datetime.date.today() + datetime.timedelta(days=days_ahead)).isoformat()
        url   = f'https://eodhd.com/api/economic-events?api_token={key}&fmt=json&from={today}&to={end}&limit=20&country=US'
        r = requests.get(url, timeout=8)
        if not r.ok:
            return []
        data = r.json()
        # Filter to high-impact US events
        important = ['Federal', 'Interest Rate', 'CPI', 'Non-Farm', 'GDP', 'PMI',
                     'PPI', 'Unemployment', 'Retail Sales', 'Housing', 'FOMC']
        filtered = [e for e in data if any(kw in (e.get('type', '')) for kw in important)]
        return filtered[:12]
    except Exception:
        return []


def _fetch_sentiment(tickers: list) -> dict:
    """
    Fetch EODHD daily sentiment aggregator scores per ticker.

    EODHD sentiments endpoint returns:
      { "AAPL.US": [{"date": "2026-04-29", "count": 12, "normalized": 0.34}, ...], ... }

    Returns: dict mapping bare-ticker (no .US suffix) → flattened summary
      { "AAPL": {"latest": 0.34, "avg_7d": 0.21, "avg_30d": 0.18, "count": 12,
                 "date": "2026-04-29", "trend": "rising|falling|flat",
                 "history": [{date, count, normalized}, ...last 30] } }

    Fix vs prior version:
      - was capped at first 20 tickers — now batches in groups of 30 to cover all
      - was reading sd.get('normalized') on a list — now flattens list-per-ticker correctly
    """
    out = {}
    try:
        import eodhd_client as ec
    except Exception:
        return out

    BATCH = 30
    for i in range(0, len(tickers), BATCH):
        chunk = tickers[i:i+BATCH]
        try:
            syms = ','.join(chunk)
            data = ec.sentiments(syms) or {}
        except Exception:
            continue

        # Normalize key (strip ".US" / other exchange suffixes)
        records_by_ticker = {}
        if isinstance(data, list):
            for item in data:
                code = item.get('code', '') or item.get('symbol', '')
                if code:
                    records_by_ticker.setdefault(code.split('.')[0], []).append(item)
        elif isinstance(data, dict):
            for code, recs in data.items():
                bare = code.split('.')[0]
                if isinstance(recs, list):
                    records_by_ticker[bare] = recs
                elif isinstance(recs, dict):
                    records_by_ticker[bare] = [recs]

        for ticker, recs in records_by_ticker.items():
            if not recs:
                continue
            # Sort by date desc, take recent window
            recs_sorted = sorted(recs, key=lambda r: r.get('date', ''), reverse=True)
            latest = recs_sorted[0] if recs_sorted else {}
            window_7  = recs_sorted[:7]
            window_30 = recs_sorted[:30]

            def _avg(rows, key='normalized'):
                vals = [r.get(key) for r in rows if r.get(key) is not None]
                return sum(vals) / len(vals) if vals else None

            avg_7  = _avg(window_7)
            avg_30 = _avg(window_30)
            # Trend: compare 7d avg to 30d avg
            trend = 'flat'
            if avg_7 is not None and avg_30 is not None:
                if avg_7 > avg_30 + 0.05: trend = 'rising'
                elif avg_7 < avg_30 - 0.05: trend = 'falling'

            count_total = sum(r.get('count', 0) or 0 for r in window_30)

            out[ticker] = {
                'latest':   latest.get('normalized'),
                'avg_7d':   avg_7,
                'avg_30d':  avg_30,
                'count':    count_total,
                'date':     latest.get('date'),
                'trend':    trend,
                'history':  recs_sorted[:30],
            }
    return out
OUT    = Path(__file__).parent
DATA   = OUT / "data.json"
TICKS  = OUT / "tickers.json"


def _compute_esp_play_signal(r: dict, earn) -> dict:
    """
    Earnings ESP Play signal (P0-2).

    Zacks documents ~70% beat rate when ESP > 0 AND Rank ≤ 3 AND earnings imminent.
    Returns a structured dict so the dashboard can show: signal, esp_pct, rank,
    earnings_in_days, reason. `signal=true` only when all three conditions hold.
    """
    esp_pct = r.get("zacks_earnings_esp")
    rank    = r.get("zacks_rank") or r.get("zacks_rank_text")
    # Map Zacks "Strong Buy"/"Buy"/etc text to numeric 1-5 if needed
    rank_num = None
    if isinstance(rank, (int, float)):
        rank_num = int(rank)
    elif isinstance(rank, str):
        _map = {"strong buy": 1, "buy": 2, "hold": 3, "sell": 4, "strong sell": 5}
        rank_num = _map.get(rank.lower().strip())
    # Already-flagged Rank #1 from bundle-level zacks_rank1 boolean
    if rank_num is None and r.get("zacks_rank1") is True:
        rank_num = 1

    earn_days = earn.get("days_until") if isinstance(earn, dict) else None

    has_esp_data = esp_pct is not None
    has_rank     = rank_num is not None
    has_earnings = earn_days is not None and earn_days >= 0

    cond_esp_positive  = has_esp_data and float(esp_pct) > 0
    cond_rank_le_3     = has_rank and rank_num <= 3
    cond_earn_within_7 = has_earnings and earn_days <= 7

    signal = cond_esp_positive and cond_rank_le_3 and cond_earn_within_7
    if signal:
        reason = f"ESP +{esp_pct}% · Rank {rank_num} · earnings in {earn_days}d"
    elif not has_esp_data:
        reason = "no ESP data"
    elif not cond_esp_positive:
        reason = f"ESP {esp_pct}% not positive"
    elif not cond_rank_le_3:
        reason = f"Rank {rank_num or '—'} > 3"
    elif not cond_earn_within_7:
        reason = f"earnings {earn_days if earn_days is not None else '—'}d away"
    else:
        reason = "—"

    return {
        "signal":         signal,
        "esp_pct":        float(esp_pct) if esp_pct is not None else None,
        "zacks_rank":     rank_num,
        "earn_days":      earn_days,
        "esp_positive":   cond_esp_positive,
        "rank_qualifies": cond_rank_le_3,
        "earnings_imminent": cond_earn_within_7,
        "reason":         reason,
    }


def _compute_elite_picks_safe(short_term: list, medium_term: list, long_term: list,
                                 st_rows: list, mt_rows: list, invest_rows: list,
                                 accuracy: dict, hmm: dict, macro: dict) -> dict:
    """Elite Picks (2026-05-04): top-5 per (mode × stage) via critic engine.

    Builds enriched per-mode rows by joining compact lists (which have stage)
    with raw bundle rows (which have rich fields like monte_carlo, conviction,
    etc.). Then delegates to elite_picks.compute_elite_picks().
    """
    try:
        import sys
        proj = OUT.parent.parent
        sys.path.insert(0, str(proj))
        import elite_picks as ep

        # Build ticker-indexed map of raw bundle rows for rich-field lookup
        raw_index = {}
        for r in (st_rows or []) + (mt_rows or []) + (invest_rows or []):
            tk = r.get("ticker")
            if tk and tk not in raw_index:
                raw_index[tk] = r

        def _enrich(compact_rows):
            out = []
            for cr in (compact_rows or []):
                tk = cr.get("ticker")
                raw = raw_index.get(tk, {}) if tk else {}
                # Merge: compact row first (has stage, score after demotion),
                # then raw fields fill in (trade_plan, conviction, monte_carlo, etc.)
                merged = {**raw, **cr}
                # Inline-compute MC + Forward Dist if absent (live merge picks won't have them on rich row)
                if "monte_carlo" not in merged:
                    merged["monte_carlo"] = _compute_monte_carlo_safe(merged) or {}
                if "forward_dist" not in merged:
                    merged["forward_dist"] = _compute_forward_dist_safe(merged.get("ohlcv")) or {}
                # rr_inconsistent flag from compact row
                merged["rr_inconsistent"] = cr.get("_rr_inconsistent") or merged.get("rr_inconsistent")
                out.append(merged)
            return out

        return ep.compute_elite_picks(
            short_term=_enrich(short_term),
            medium_term=_enrich(medium_term),
            long_term=_enrich(long_term),
            accuracy=accuracy or {},
            hmm=hmm or {},
            macro=macro or {},
        )
    except Exception as e:
        return {"error": str(e), "Swing": {"BUY":[],"WATCH":[],"SHORT":[]},
                "Position": {"BUY":[],"WATCH":[],"SHORT":[]},
                "Invest": {"BUY":[],"WATCH":[],"SHORT":[]}}


def _coherent_rr(tp: dict) -> float:
    """Canonical R:R from trade_plan: (target1 - entry_mid) / (entry_mid - stop).

    Replaces tp.rr_ratio (which has been written wrong by some code paths).
    Returns 0 if any input is missing or stop >= entry_mid.
    """
    if not isinstance(tp, dict): return 0.0
    e_lo = tp.get("entry_low")  or tp.get("primary_zone_low")
    e_hi = tp.get("entry_high") or tp.get("primary_zone_high")
    stop = tp.get("stop")
    t1   = tp.get("target1")
    try:
        e_lo = float(e_lo) if e_lo is not None else None
        e_hi = float(e_hi) if e_hi is not None else e_lo
        stop = float(stop) if stop is not None else None
        t1   = float(t1)   if t1   is not None else None
    except (TypeError, ValueError):
        return 0.0
    if not (e_lo and stop and t1): return 0.0
    if e_hi is None: e_hi = e_lo
    entry_mid = (e_lo + e_hi) / 2
    direction = (tp.get("direction") or "long").lower()
    if direction == "short":
        risk = max(0.01, stop - entry_mid)
        reward = max(0, entry_mid - t1)
    else:
        risk = max(0.01, entry_mid - stop)
        reward = max(0, t1 - entry_mid)
    if risk <= 0 or reward <= 0: return 0.0
    return round(reward / risk, 1)


def _rr_is_inconsistent(tp: dict, threshold: float = 0.20) -> bool:
    """True if the cached tp.rr_ratio disagrees with computed _coherent_rr by >threshold (relative)."""
    cached = tp.get("rr_ratio") if isinstance(tp, dict) else None
    if cached is None or cached == 0: return False
    computed = _coherent_rr(tp)
    if computed == 0: return False
    rel_diff = abs(cached - computed) / max(0.1, computed)
    return rel_diff > threshold


def _compute_monte_carlo_safe(r: dict) -> dict:
    """V-1: Monte Carlo path simulator (Merton jump-diffusion). Never raises.
    V-5: Uses earnings_jump calibration for jump parameters when available."""
    try:
        import sys
        proj = OUT.parent.parent
        sys.path.insert(0, str(proj))
        import monte_carlo as mc
        import earnings_jump as ej
        import numpy as np

        ohlcv = r.get("ohlcv")
        closes = []
        if isinstance(ohlcv, list) and ohlcv and isinstance(ohlcv[0], dict):
            closes = [float(b.get("Close") or b.get("close") or 0) for b in ohlcv if (b.get("Close") or b.get("close"))]
        elif isinstance(ohlcv, dict):
            c = ohlcv.get("close") or ohlcv.get("Close") or []
            closes = [float(x) for x in c if x]
        if len(closes) < 60:
            return {"error": "insufficient history"}

        S0 = closes[-1]
        # Estimate μ/σ from log returns
        log_rets = [np.log(closes[i] / closes[i-1]) for i in range(1, len(closes)) if closes[i-1] > 0]
        if len(log_rets) < 30:
            return {"error": "too few returns"}
        mu_daily   = float(np.mean(log_rets))
        sigma_daily = float(np.std(log_rets, ddof=1))
        mu_annual    = mu_daily * 252
        sigma_annual = sigma_daily * np.sqrt(252)

        # Basel YELLOW recalibration (2026-05-08): empirical sigma underpredicts
        # tail events. Audit_360 reports 18 exceptions vs 12 expected over 250
        # closed signals (7.2% rate vs 5% target). Inflate σ by sqrt(7.2/5.0)
        # ≈ 1.20 to bring exception rate to target. This widens MC's 95%/97.5%
        # bands (VaR-95, CVaR-975) by the same factor and de-biases p_profit
        # downward toward reality. Re-measure after 50+ new signals close.
        _BASEL_SIGMA_INFLATION = 1.20
        sigma_annual *= _BASEL_SIGMA_INFLATION

        # V-5: Earnings jump calibration with sector fallback
        jcal = ej.calibrate(r.get("ticker", ""), closes, sector=r.get("sector"))
        lambda_jump = float(jcal.get("lambda_J", 0.0))
        mu_jump     = float(jcal.get("mu_J", 0.0))
        sigma_jump  = float(jcal.get("sigma_J", 0.0))

        # Get target/stop from trade_plan if available — compute hit-probabilities
        tp = r.get("trade_plan") or {}
        target = tp.get("target1")
        stop   = tp.get("stop")
        if target and stop and target > S0 > stop:
            return mc.simulate_with_target_stop(S0, mu_annual, sigma_annual,
                                                  target=float(target), stop=float(stop),
                                                  T=63, n_paths=3000,
                                                  lambda_jump=lambda_jump,
                                                  mu_jump=mu_jump, sigma_jump=sigma_jump,
                                                  seed=42)
        return mc.simulate(S0, mu_annual, sigma_annual, T=63, n_paths=3000,
                            lambda_jump=lambda_jump,
                            mu_jump=mu_jump, sigma_jump=sigma_jump, seed=42)
    except Exception as e:
        return {"error": str(e)}


def _compute_forward_dist_safe(ohlcv) -> dict:
    """V-3: Empirical forward-distribution metrics from OHLCV history. Never raises."""
    try:
        import sys
        proj = OUT.parent.parent
        sys.path.insert(0, str(proj))
        import forward_dist as fd
        # Extract closes from ohlcv (handles list-of-dicts, dict-of-lists, parquet path)
        closes = []
        if isinstance(ohlcv, list) and ohlcv and isinstance(ohlcv[0], dict):
            closes = [float(b.get("Close") or b.get("close") or 0) for b in ohlcv if (b.get("Close") or b.get("close"))]
        elif isinstance(ohlcv, dict):
            c = ohlcv.get("close") or ohlcv.get("Close") or []
            closes = [float(x) for x in c if x]
        if len(closes) < 50:
            return {"error": "insufficient history"}
        return fd.forward_distribution_metrics(closes, horizon_days=10)
    except Exception as e:
        return {"error": str(e)}


def _compute_cvar_optimizer_safe(short_term: list, medium_term: list, max_tickers: int = 12) -> dict:
    """V-11: CVaR-constrained portfolio optimizer (Rockafellar-Uryasev LP). Never raises."""
    try:
        import sys
        proj = OUT.parent.parent
        sys.path.insert(0, str(proj))
        import cvar_optimizer as cvo
        import numpy as np

        # Accept either compact "stage" or raw "decision.verdict"
        def _is_buy(r):
            if r.get("stage") == "BUY": return True
            d = r.get("decision") or {}
            return (d.get("verdict") or "").upper() == "BUY"
        buys = [r for r in (short_term + medium_term) if _is_buy(r)][:max_tickers]
        if len(buys) < 2:
            return {"error": "need ≥2 BUY candidates"}

        # Build expected returns (use mean of MC simulation if available, else use scoring proxy)
        exp_rets = []
        scenarios = []
        sectors = []
        tickers_used = []
        for r in buys:
            mc = r.get("monte_carlo") or {}
            ohlcv = r.get("ohlcv")
            closes = []
            if isinstance(ohlcv, list) and ohlcv and isinstance(ohlcv[0], dict):
                closes = [float(b.get("Close") or b.get("close") or 0) for b in ohlcv if (b.get("Close") or b.get("close"))]
            if len(closes) < 65:
                continue

            # Expected return: prefer MC mean, fallback to historical
            if mc.get("stats") and "mean_pct" in (mc.get("stats") or {}):
                er = float(mc["stats"]["mean_pct"]) / 100.0
            else:
                rets = [(closes[i] / closes[i-1] - 1) for i in range(1, len(closes))]
                er = float(np.mean(rets) * 63)  # 63-day horizon

            # Scenario returns: bootstrap from history (simpler than re-running MC here)
            rets = np.array([(closes[i] / closes[i-1] - 1) for i in range(1, len(closes))])
            n_scenarios = 250
            horizon = 63
            scenario_rets = []
            np.random.seed(42 + len(scenarios))
            for _ in range(n_scenarios):
                sample = np.random.choice(rets, size=horizon, replace=True)
                scenario_rets.append(np.prod(1 + sample) - 1)
            scenarios.append(scenario_rets)
            exp_rets.append(er)
            sectors.append(r.get("sector") or "Unknown")
            tickers_used.append(r.get("ticker"))

        if len(exp_rets) < 2:
            return {"error": "insufficient valid candidates"}

        exp_arr = np.array(exp_rets)
        scen_arr = np.array(scenarios).T  # (S, N)
        result = cvo.optimize_cvar_portfolio(
            exp_arr, scen_arr, sectors=sectors,
            alpha=0.95, cvar_budget_pct=8.0,
            max_gross=0.80, max_per_position=0.10, max_per_sector=0.30,
        )
        result["tickers"] = tickers_used
        # Pair tickers with their weights for UI consumption
        if "weights" in result and len(result["weights"]) == len(tickers_used):
            result["holdings"] = [
                {"ticker": tickers_used[i], "weight_pct": round(float(result["weights"][i]) * 100, 2),
                 "sector": sectors[i], "expected_return_pct": round(exp_rets[i] * 100, 2)}
                for i in range(len(tickers_used))
                if result["weights"][i] > 0.0001
            ]
            result["holdings"].sort(key=lambda h: -h["weight_pct"])
        return result
    except Exception as e:
        return {"error": str(e)}


def _compute_student_t_copula_safe(short_term: list, medium_term: list, max_tickers: int = 8) -> dict:
    """V-10: Student-t copula tail dependence. Never raises."""
    try:
        import sys
        proj = OUT.parent.parent
        sys.path.insert(0, str(proj))
        import student_t_copula as stc
        import pandas as pd
        # Accept either compact "stage" or raw "decision.verdict"
        def _is_buy(r):
            if r.get("stage") == "BUY": return True
            d = r.get("decision") or {}
            return (d.get("verdict") or "").upper() == "BUY"
        buys = [r for r in (short_term + medium_term) if _is_buy(r)][:max_tickers]
        if len(buys) < 2:
            return {"error": "need ≥2 BUY tickers"}
        returns_data = {}
        for r in buys:
            ohlcv = r.get("ohlcv")
            closes = []
            if isinstance(ohlcv, list) and ohlcv and isinstance(ohlcv[0], dict):
                closes = [float(b.get("Close") or b.get("close") or 0) for b in ohlcv if (b.get("Close") or b.get("close"))]
            if len(closes) >= 65:
                rets = [(closes[i] / closes[i-1] - 1) for i in range(1, len(closes))]
                returns_data[r.get("ticker")] = rets[-90:]
        if len(returns_data) < 2:
            return {"error": "insufficient ticker history"}
        min_len = min(len(v) for v in returns_data.values())
        aligned = {t: v[-min_len:] for t, v in returns_data.items()}
        df = pd.DataFrame(aligned)
        return stc.fit_student_t_copula(df, max_tickers=max_tickers)
    except Exception as e:
        return {"error": str(e)}


def _compute_dcc_garch_safe(short_term: list, medium_term: list, max_tickers: int = 12) -> dict:
    """V-8: DCC-GARCH dynamic portfolio correlation. Never raises."""
    try:
        import sys
        proj = OUT.parent.parent
        sys.path.insert(0, str(proj))
        import dcc_garch as dg
        import pandas as pd
        import numpy as np

        # Get top BUYs from short + medium term, fetch their OHLCV from cache
        # Accept either compact "stage" or raw "decision.verdict"
        def _is_buy(r):
            if r.get("stage") == "BUY": return True
            d = r.get("decision") or {}
            return (d.get("verdict") or "").upper() == "BUY"
        buys = [r for r in (short_term + medium_term) if _is_buy(r)][:max_tickers]
        if len(buys) < 2:
            return {"error": "need ≥2 BUY tickers for DCC-GARCH"}
        returns_data = {}
        for r in buys:
            ohlcv = r.get("ohlcv")
            closes = []
            if isinstance(ohlcv, list) and ohlcv and isinstance(ohlcv[0], dict):
                closes = [float(b.get("Close") or b.get("close") or 0) for b in ohlcv if (b.get("Close") or b.get("close"))]
            if len(closes) >= 65:
                rets = [(closes[i] / closes[i-1] - 1) for i in range(1, len(closes))]
                returns_data[r.get("ticker")] = rets[-90:]  # last 90 days

        if len(returns_data) < 2:
            return {"error": "insufficient ticker history"}
        # Align lengths
        min_len = min(len(v) for v in returns_data.values())
        aligned = {t: v[-min_len:] for t, v in returns_data.items()}
        df = pd.DataFrame(aligned)
        return dg.fit_dcc_garch(df, max_tickers=max_tickers)
    except Exception as e:
        return {"error": str(e)}


def _compute_hmm_regime_safe() -> dict:
    """V-2: Soft regime probabilities P(Bull/Neutral/Bear) from SPY returns. Never raises."""
    try:
        import sys
        proj = OUT.parent.parent
        sys.path.insert(0, str(proj))
        import regime_hmm as rh
        import eodhd_client as _e
        from datetime import date, timedelta
        rows = _e.eod("SPY", from_date=(date.today() - timedelta(days=60)).isoformat())
        if not rows or len(rows) < 22:
            return {"error": "insufficient SPY history for HMM"}
        closes = [float(r.get("adjusted_close") or r.get("close") or 0) for r in rows]
        return rh.regime_probabilities_from_closes(closes, lookback=21)
    except Exception as e:
        return {"error": str(e)}


def _compute_sector_pairs_safe() -> dict:
    """S-6: Compute sector RS pair candidates. Never raises."""
    try:
        import sys
        proj = OUT.parent.parent
        sys.path.insert(0, str(proj))
        import sector_pair as sp
        return sp.find_sector_pairs()
    except Exception as e:
        return {"error": str(e), "pairs": [], "n_pairs": 0}


def _compute_accuracy_safe() -> dict:
    """Run the accuracy framework on signal_log; never raise."""
    try:
        import sys
        proj = OUT.parent.parent
        sys.path.insert(0, str(proj))
        import accuracy_framework as af
        log_path = proj / "data" / "signal_log.json"
        if not log_path.exists():
            return {"error": "signal_log.json not found"}
        log = json.loads(log_path.read_text())
        return af.compute_all_accuracy_metrics(log)
    except Exception as e:
        return {"error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Zacks helpers — per-ticker enrichment from bundle-level Zacks data
# ─────────────────────────────────────────────────────────────────────────────
ZACKS_SERVICES = (
    # Currently scraping (verified 2026-05-01):
    "ultimate", "tazr", "bbt", "counterstrike", "headlinetrader",
    "alt_energy", "blockchain", "tech_innovators",
    # Phase 2 — to be added by next round of scraper extension:
    "surprise_trader", "insider_trader", "value_investor", "home_run_investor",
    "income_investor", "options_trader", "stocks_under_10",
    "marijuana_innovators",
)


def _zacks_services_holding_ticker(ticker, bundle: dict) -> list:
    """
    Scan all Zacks Premium service portfolios for the given ticker.
    Returns list of {service, entry_date, gain_pct, current_price, position_status}.
    """
    if not ticker:
        return []
    held = []
    t = ticker.upper().strip()
    for svc in ZACKS_SERVICES:
        svc_data = bundle.get(svc) or {}
        # ultimate has nested all_trades
        candidates = []
        if svc == "ultimate":
            candidates = svc_data.get("all_trades") or []
        else:
            candidates = svc_data.get("trades") or []
        for tr in candidates:
            if not isinstance(tr, dict):
                continue
            sym = (tr.get("symbol") or tr.get("sym") or tr.get("ticker") or "").upper().strip()
            if sym == t:
                held.append({
                    "service":      svc,
                    "entry_date":   tr.get("entry_date") or tr.get("date") or tr.get("date_added"),
                    "entry_price":  tr.get("entry_price") or tr.get("price_added") or tr.get("buy_price"),
                    "current_price":tr.get("current_price") or tr.get("last_price"),
                    "gain_pct":     tr.get("gain_pct") or tr.get("pct_chg") or tr.get("change_pct"),
                    "type":         tr.get("type"),
                    "name":         tr.get("name") or tr.get("company"),
                })
    return held


def _zacks_email_mentions_for_ticker(ticker, gmail_zacks: dict) -> dict:
    """
    Filter the gmail_zacks digest for entries mentioning this ticker.
    Returns: {rank_changes:[], trade_alerts:[], bull_bear:[], commentary:[]}
    """
    out = {"rank_changes": [], "trade_alerts": [], "bull_bear": [], "commentary": []}
    if not ticker or not gmail_zacks:
        return out
    t = ticker.upper().strip()
    # ticker_mentions can be: dict[ticker]→list (rich) OR dict[ticker]→int (count-only)
    mentions_raw = (gmail_zacks.get("ticker_mentions") or {}).get(t, [])
    if isinstance(mentions_raw, int):
        # Only have a count, no per-mention detail — return empty per-category lists
        return out
    if not isinstance(mentions_raw, list):
        return out
    mentions = mentions_raw
    for m in mentions:
        cat = (m.get("category") or "").lower()
        if "rank" in cat:
            out["rank_changes"].append(m)
        elif "trade" in cat or "alert" in cat:
            out["trade_alerts"].append(m)
        elif "bull" in cat or "bear" in cat:
            out["bull_bear"].append(m)
        else:
            out["commentary"].append(m)
    return out



def stage_of(row: dict) -> str:
    """Derive stage label — prefer top-level verdict (decision_engine output).

    Phase 2.1 (2026-05-06): top-level `verdict` is the single source of truth
    written by decision_engine.compute_final_verdict(). Fall back to nested
    decision.verdict for legacy rows, and finally to score-based heuristic only
    if neither is set (defense-in-depth, should never fire post-engine wire-in).
    """
    # Single source of truth: top-level verdict from decision_engine
    top = (row.get("verdict") or "").upper()
    if top in {"BUY", "WATCH", "SELL", "SHORT", "AVOID", "WAIT"}:
        if top == "SHORT": return "SELL"
        if top == "WAIT": return "WATCH"  # WAIT renders as WATCH in stage taxonomy
        return top
    # Legacy fallback: nested decision.verdict
    dec = row.get("decision") or {}
    v = (dec.get("verdict") or "").upper()
    if v in {"BUY", "WATCH", "SELL", "SHORT", "AVOID"}:
        return "SELL" if v == "SHORT" else v
    if (row.get("direction") or "").lower() == "short":
        return "SELL"
    # Last-resort score heuristic — should not reach here post-engine wire-in
    s = row.get("score") or 0
    return "BUY" if s >= 70 else "WATCH" if s >= 60 else "AVOID"


def _parse_pct(s):
    """Pull first numeric % out of strings like '8.5% (2/5)' → 8.5"""
    if isinstance(s, (int, float)):
        return float(s)
    if not isinstance(s, str):
        return None
    import re
    m = re.search(r'(-?\d+(?:\.\d+)?)\s*%', s)
    return float(m.group(1)) if m else None


def _real_fund(r: dict) -> dict:
    """Pull real fundamentals from the bundle row (revenue, margin, valuation)."""
    f  = r.get("fundamentals") or {}
    fd = (f.get("details") or {})
    out = {
        "rev_growth_pct":  _parse_pct(fd.get("revenue_growth")),
        "profit_margin_str": fd.get("profit_margin") or "",
    }
    pm = fd.get("profit_margin") or ""
    import re
    nm = re.search(r'net\s+(-?\d+(?:\.\d+)?)\s*%', pm)
    om = re.search(r'op\s+(-?\d+(?:\.\d+)?)\s*%', pm)
    gm = re.search(r'gross\s+(-?\d+(?:\.\d+)?)\s*%', pm)
    out["net_margin_pct"]   = float(nm.group(1)) if nm else None
    out["op_margin_pct"]    = float(om.group(1)) if om else None
    out["gross_margin_pct"] = float(gm.group(1)) if gm else None
    bs = fd.get("balance_sheet") or ""
    roe = re.search(r'ROE=(-?\d+(?:\.\d+)?)\s*%', bs)
    roa = re.search(r'ROA=(-?\d+(?:\.\d+)?)\s*%', bs)
    out["roe_pct"]  = float(roe.group(1)) if roe else None
    out["roa_pct"]  = float(roa.group(1)) if roa else None
    val = fd.get("valuation") or ""
    peg = re.search(r'PEG=(-?\d+(?:\.\d+)?)', val)
    out["peg"] = float(peg.group(1)) if peg else None
    out["price_to_book"] = _parse_pct((fd.get("price_to_book") or "").replace("%","")) if fd.get("price_to_book") else None
    out["bull_drivers"] = f.get("bull_drivers") or []
    out["bear_risks"]   = f.get("bear_risks")   or []
    return out


def _real_analyst(r: dict) -> dict:
    """Real analyst consensus from bundle."""
    a = r.get("analyst") or {}
    return {
        "target_mean":  a.get("target_mean"),
        "target_high":  a.get("target_high"),
        "target_low":   a.get("target_low"),
        "upside_pct":   a.get("upside_pct"),
        "consensus":    a.get("consensus"),
        "total_analysts": a.get("total_analysts"),
        "strong_buy":   a.get("strong_buy", 0),
        "buy":          a.get("buy", 0),
        "hold":         a.get("hold", 0),
        "sell":         a.get("sell", 0),
        "strong_sell":  a.get("strong_sell", 0),
        "upgrades_10d":   a.get("upgrades_10d", 0),
        "downgrades_10d": a.get("downgrades_10d", 0),
    }


def _real_insider(r: dict) -> dict:
    i = r.get("insider_data") or {}
    return {
        "buys": i.get("buys", 0),
        "sells": i.get("sells", 0),
        "sentiment": i.get("sentiment", "neutral"),
        "ceo_buy": bool(i.get("ceo_buy")),
        "cfo_buy": bool(i.get("cfo_buy")),
        "days_since_last": i.get("days_since_last"),
    }


def _real_news(r: dict) -> dict:
    n = r.get("news_data") or {}
    return {
        "score":     n.get("score", 0),
        "headlines": n.get("headlines", 0),
        "bias":      n.get("bias", "neutral"),
    }


def compact_row(r: dict) -> dict:
    """Flatten a rich bundle row into the dashboard's compact 22-col schema."""
    tp     = r.get("trade_plan") or {}
    techs  = r.get("technicals") or {}
    score  = r.get("score") or 0
    rb     = (r.get("scoring_breakdown") or {})
    earn   = (r.get("earnings") or {})
    news_s = r.get("news_sentiment_score") or r.get("polygon_news_score") or 0
    # Pull real company name from EODHD fund_enrichment when r.name == ticker
    # (fund_enrichment is built earlier in main(); fall back gracefully here)
    sym = r.get("ticker") or ""
    fe = (globals().get("_FUND_ENRICHMENT_GLOBAL") or {}).get(sym, {}) if sym else {}
    raw_name = r.get("name") or r.get("company_name") or ""
    if not raw_name or raw_name == sym:
        raw_name = fe.get("name") or (r.get("info") or {}).get("longName") or sym
    return {
        "ticker":     sym,
        "name":       raw_name,
        "sector":     r.get("sector") or fe.get("sector") or "",
        "industry":   r.get("industry") or fe.get("industry") or "",
        "setup":      r.get("setup_family") or r.get("setup") or "",
        "stage":      stage_of(r),
        "score":      score,
        "rs_rank":    r.get("rs_rank"),
        "rsi":        techs.get("rsi") or r.get("rsi"),
        "rvol":       r.get("rvol"),
        # MA flags actually live at technicals.indicators.above_{20,50}ema /
        # above_200sma — set by analysis.py:2779. Fall back to legacy paths
        # for older bundles. (2026-05-07 — ATEN was rendering as below all EMAs
        # because we were reading the wrong key.)
        "above_50ema": bool((techs.get("indicators") or {}).get("above_50ema")
                            or techs.get("above_ema50") or techs.get("ema_stack")),
        "above_200sma": bool((techs.get("indicators") or {}).get("above_200sma")
                             or techs.get("above_sma200")),
        "macd_bullish": bool((r.get("macd_signal") or "") in ("bullish","bull")),
        "price":      r.get("price"),
        "pct_chg":    techs.get("pct_chg") or r.get("pct_chg") or 0,
        "perf_week":  techs.get("perf_week"),
        "perf_month": techs.get("perf_month"),
        "entry_lo":   tp.get("entry_low") or tp.get("primary_zone_low"),
        "entry_hi":   tp.get("entry_high") or tp.get("primary_zone_high"),
        "stop":       tp.get("stop"),
        "t1":         tp.get("target1"),
        "t2":         tp.get("target2"),
        # 2026-05-04: ALWAYS recompute rr from (T1-entry_mid)/(entry_mid-stop) as the
        # canonical R:R. The stored plan["rr_ratio"] has been wrong in places (SMC OB
        # override path used progress-from-entry-low which has different semantics).
        # Trust the math, not the cached field.
        "rr":         _coherent_rr(tp),
        # Flag for UI: True if cached rr disagrees with computed rr by >20% — means
        # something upstream wrote inconsistent values; trader should treat the plan
        # as suspect and not place the trade until reconciled.
        "_rr_inconsistent": _rr_is_inconsistent(tp),
        # Sector ranking demotion (Phase 3 sector_relative_ranking gate, F-3)
        "sector_pct_rank":  r.get("sector_pct_rank"),
        "sector_demoted":   bool((r.get("decision") or {}).get("sector_demotion_reason")),
        "sector_demotion_reason": (r.get("decision") or {}).get("sector_demotion_reason"),
        "fractal_low":  r.get("fractal_low"),
        "fractal_high": r.get("fractal_high"),
        "analyst_consensus": ((r.get("analyst") or {}).get("consensus")
                              or (r.get("analyst") or {}).get("recommendation")),
        "analyst_strong_buy": (r.get("analyst") or {}).get("strong_buy"),
        "analyst_buy":   (r.get("analyst") or {}).get("buy"),
        "analyst_hold":  (r.get("analyst") or {}).get("hold"),
        "analyst_sell":  (r.get("analyst") or {}).get("sell"),
        "tv_rating":     (r.get("tv_rating") or {}).get("recommendation"),
        "tech_pts":   rb.get("technicals", {}).get("score") if isinstance(rb.get("technicals"), dict) else rb.get("technicals"),
        "fund_pts":   rb.get("fundamentals", {}).get("score") if isinstance(rb.get("fundamentals"), dict) else rb.get("fundamentals"),
        "smc_pts":    rb.get("smc", {}).get("score") if isinstance(rb.get("smc"), dict) else rb.get("smc"),
        "earn_days":  earn.get("days_until") if isinstance(earn, dict) else None,
        # P0-2: ESP Play signal — Zacks ESP > 0 + Rank ≤ 3 + earnings within 7 days
        # Documented ~70% beat rate when both conditions hold. Lights up automatically
        # as zacks_per_ticker enrichment populates the underlying fields.
        "esp_play": _compute_esp_play_signal(r, earn),
        "news":       int(news_s) if isinstance(news_s, (int, float)) else 0,
        # REAL fundamentals — surface for the dashboard expand panel
        "rev_growth": _parse_pct((r.get("fundamentals") or {}).get("details", {}).get("revenue_growth")),
        "net_margin": (lambda pm: (lambda m: float(m.group(1)) if m else None)(__import__('re').search(r'net\s+(-?\d+(?:\.\d+)?)', pm or '')))((r.get("fundamentals") or {}).get("details", {}).get("profit_margin", "")),
        "analyst_target": ((r.get("analyst") or {}).get("target_mean")),
        "analyst_consensus": ((r.get("analyst") or {}).get("consensus")),
        "analyst_upside": ((r.get("analyst") or {}).get("upside_pct")),
        "insider_buys": ((r.get("insider_data") or {}).get("buys", 0)),
        "insider_sells": ((r.get("insider_data") or {}).get("sells", 0)),
        "reaction_checklist": r.get("reaction_checklist") or [],
        "beta":         r.get("beta") or (r.get("kelly_size") or {}).get("beta"),
        "market_cap":   r.get("market_cap"),
        "week52_high":  r.get("week52_high"),
        "week52_low":   r.get("week52_low"),
        "conviction_tier": r.get("conviction_tier"),
        "entry_quality":  r.get("entry_quality"),
        "star_rating":    r.get("star_rating"),
        "reaction_checklist": r.get("reaction_checklist") or [],
        "trade_thesis":   r.get("trade_thesis"),
        "decision_state": (r.get("decision_state") or {}).get("state") if isinstance(r.get("decision_state"), dict) else None,
        "decision_label": (r.get("decision_state") or {}).get("label") if isinstance(r.get("decision_state"), dict) else None,
        "zone_quality":   r.get("zone_quality"),
        "setup_quality":  r.get("setup_quality"),
        "entry_subtype":  r.get("entry_subtype"),
        "market_phase":   r.get("market_phase"),
        "catalyst_tags":  r.get("catalyst_tags"),
        "catalyst_tier":  r.get("catalyst_tier"),
        # Same nested-vs-flat issue as above_50ema — real flags live in
        # technicals.indicators.above_{8,20}ema. above_20ema is treated as the
        # 21EMA proxy (analysis.py uses 20-period ema for the short MA).
        "above_8ema":     bool(((r.get("technicals") or {}).get("indicators") or {}).get("above_8ema")
                               or (r.get("technicals") or {}).get("above_ema8")),
        "above_21ema":    bool(((r.get("technicals") or {}).get("indicators") or {}).get("above_20ema")
                               or (r.get("technicals") or {}).get("above_ema21")),
        "adx":            (r.get("technicals") or {}).get("adx"),
        "alloc_pct":      ((r.get("trade_plan") or {}).get("allocation_pct")
                          or r.get("allocation_pct") or 0),
        "primary_zone_low": (r.get("trade_plan") or {}).get("primary_zone_low") or (r.get("trade_plan") or {}).get("entry_low"),
        "primary_zone_high": (r.get("trade_plan") or {}).get("primary_zone_high") or (r.get("trade_plan") or {}).get("entry_high"),
        "deep_zone_low":  (r.get("trade_plan") or {}).get("deep_zone_low"),
        "deep_zone_high": (r.get("trade_plan") or {}).get("deep_zone_high"),
        "shallow_zone_low":  (r.get("trade_plan") or {}).get("shallow_zone_low"),
        "shallow_zone_high": (r.get("trade_plan") or {}).get("shallow_zone_high"),
        "expected_pullback": (r.get("trade_plan") or {}).get("expected_pullback"),
        "hold_period_min": (r.get("hold_period_guide") if isinstance(r.get("hold_period_guide"), dict) else {} or {}).get("min_days"),
        "hold_period_max": (r.get("hold_period_guide") if isinstance(r.get("hold_period_guide"), dict) else {} or {}).get("max_days"),
        "tech_max":       (r.get("technicals") or {}).get("max", 35),
        "fund_max":       (r.get("fundamentals") or {}).get("max", 10),
        "sent_max":       15,
        "smc_max":        15,
        "tech_score":     (r.get("technicals") or {}).get("score") or (r.get("scoring_breakdown") or {}).get("technicals", {}).get("score") if isinstance((r.get("scoring_breakdown") or {}).get("technicals"), dict) else None,
        "fund_score":     (r.get("fundamentals") or {}).get("score"),
        "sent_score":     (r.get("news_sentiment_score") or r.get("polygon_news_score") if isinstance(r.get("news_sentiment_score") or r.get("polygon_news_score"), (int, float)) else 0),
        "iv_rank":        (r.get("options_data") or {}).get("iv_rank"),
        "put_call_ratio": (r.get("options_data") or {}).get("put_call_ratio"),
        "squeeze_on":     bool((r.get("squeeze") or {}).get("on")) if isinstance(r.get("squeeze"), dict) else bool(r.get("squeeze")),
        "vwap":           (r.get("vwap") or {}).get("price") if isinstance(r.get("vwap"), dict) else None,
        "ema_signal":     r.get("ema_signal"),
        "macd_signal":    r.get("macd_signal"),
        "weekly_bull":    r.get("weekly_bull"),
        "perf_4h":        r.get("perf_4h"),
        "perf_1d":        r.get("pct_chg") or 0,
        "perf_1w":        (r.get("technicals") or {}).get("perf_week"),
        "insider_recent": ((r.get("insider_data") or {}).get("recent_buys") or 0) - ((r.get("insider_data") or {}).get("recent_sells") or 0),
        "insider_days":   (r.get("insider_data") or {}).get("days_since_last"),
        "short_pct":      r.get("short_float_pct") or (r.get("borrow") or {}).get("short_float_pct"),
        "tv_rec_str":     (r.get("tv_rating") or {}).get("recommendation") if isinstance(r.get("tv_rating"), dict) else None,
        "rev_growth":     r.get("rev_growth"),
        "net_margin":     r.get("net_margin"),
        "peg":            r.get("peg"),
        "earnings_beat":  ((r.get("earnings") or {}).get("beat_rate") if isinstance(r.get("earnings"), dict) else None),
        "thesis":         r.get("trade_thesis") or r.get("dashboard_message"),
        # For Killed/AVOID tab — explain why it was killed.
        # Bug fix #1 (2026-05-06): never display reject_reason on BUY tickers
        # (was showing decision_state.label even on BUYs, contradicting verdict).
        "reject_reason": _reject_reason_for(r),
        # Decision engine outputs (Phase 1+2 — for Why-this-is-BUY/WAIT panel)
        "gates_evaluated":         r.get("gates_evaluated") or [],
        "caveats":                 r.get("caveats") or [],
        "setup_size_multiplier":   r.get("setup_size_multiplier"),
        "audit_trail":             r.get("audit_trail") or {},
        # Scan-over-scan diff (audit log panel)
        "change_log":              _compute_change_log(r, _PREV_BUNDLE_INDEX.get(r.get("ticker"), {}), _PREV_BUNDLE_DATE),
    }


def _trim_ohlcv(ohlcv, n=90, ticker=None):
    """Last N bars of OHLCV as compact records.

    Handles three input formats:
      1. list of dicts {time, open, high, low, close, volume}  ← scan bundle format
      2. dict of arrays {dates|Date, open|Open, ...}            ← legacy format
      3. None/empty → fall back to cache/ohlcv/{TICKER}.parquet (parquet archive)
    """
    bars = []
    # Format 1: list of dicts
    if isinstance(ohlcv, list) and ohlcv and isinstance(ohlcv[0], dict):
        from datetime import datetime
        for row in ohlcv[-n:]:
            ts = row.get("time") or row.get("t") or row.get("timestamp")
            if ts and isinstance(ts, (int, float)):
                d = datetime.utcfromtimestamp(int(ts)).strftime("%Y-%m-%d")
            else:
                d = str(row.get("date") or row.get("Date") or "")
            bars.append({
                "d": d,
                "o": float(row["open"]) if row.get("open") is not None else None,
                "h": float(row["high"]) if row.get("high") is not None else None,
                "l": float(row["low"])  if row.get("low")  is not None else None,
                "c": float(row["close"])if row.get("close")is not None else None,
                "v": int(row["volume"]) if row.get("volume") is not None else 0,
            })
        return bars
    # Format 2: dict of arrays
    if isinstance(ohlcv, dict):
        dates = ohlcv.get("dates") or ohlcv.get("Date") or []
        o = ohlcv.get("open") or ohlcv.get("Open") or []
        h = ohlcv.get("high") or ohlcv.get("High") or []
        l = ohlcv.get("low") or ohlcv.get("Low") or []
        c = ohlcv.get("close") or ohlcv.get("Close") or []
        v = ohlcv.get("volume") or ohlcv.get("Volume") or []
        if c:
            zipped = list(zip(dates[-n:], o[-n:], h[-n:], l[-n:], c[-n:], v[-n:]))
            return [{"d": str(d), "o": float(oo) if oo else None, "h": float(hh) if hh else None,
                     "l": float(ll) if ll else None, "c": float(cc) if cc else None,
                     "v": int(vv) if vv else 0}
                    for (d, oo, hh, ll, cc, vv) in zipped]
    # Format 3: parquet fallback
    if ticker:
        try:
            import os
            here = os.path.dirname(os.path.abspath(__file__))
            pq_path = os.path.normpath(os.path.join(here, "..", "..", "cache", "ohlcv", f"{ticker}.parquet"))
            if os.path.exists(pq_path):
                import pandas as pd
                df = pd.read_parquet(pq_path).tail(n)
                df = df.reset_index() if df.index.name else df
                date_col = next((c for c in ["date", "Date", "index", "timestamp"] if c in df.columns), None)
                for _, row in df.iterrows():
                    bars.append({
                        "d": str(row[date_col])[:10] if date_col else "",
                        "o": float(row.get("open", row.get("Open", 0)) or 0) or None,
                        "h": float(row.get("high", row.get("High", 0)) or 0) or None,
                        "l": float(row.get("low",  row.get("Low",  0)) or 0) or None,
                        "c": float(row.get("close",row.get("Close",0)) or 0) or None,
                        "v": int(row.get("volume", row.get("Volume", 0)) or 0),
                    })
                return bars
        except Exception:
            pass
    return []


_POSITION_MODE_W = (25, 10, 30, 5, 30)  # tech, cat, rs, sm, fund — RS-heavy
_INVEST_MODE_W   = (15,  5, 10, 5, 65)  # fundamentals-driven


def _compute_mode_verdicts(r: dict) -> dict:
    """
    Compute Position + Invest scores using the same re-weighted pillar method
    used for the dashboard tab lists. Ensures per-ticker badges match the
    main dashboard verdicts (no more AVOID-everywhere on Invest).
    """
    sb = r.get("scoring_breakdown") or {}
    fund = (r.get("fundamentals") or {}).get("score", 0) or 0
    t  = float(sb.get("tech_score") or 0)
    c  = float(sb.get("cat_score") or 0)
    rs = float(sb.get("rs_score")  or 0)
    sm = float(sb.get("sm_score")  or 0)

    def _score(weights):
        wt, wc, wr, wsm, wf = weights
        return ((t/35)*wt + (c/20)*wc + (rs/20)*wr + (sm/15)*wsm + (fund/15)*wf)

    pos_score = round(_score(_POSITION_MODE_W), 1)
    inv_score = round(_score(_INVEST_MODE_W), 1)

    # Verdict thresholds match the main dashboard mode lists
    def _verdict(score: float, mode: str) -> str:
        if mode == "position":
            if score >= 70: return "BUY"
            if score >= 55: return "WATCH"
            return "AVOID"
        else:  # invest
            if score >= 65: return "BUY"
            if score >= 50: return "WATCH"
            return "AVOID"

    # Pull gate info from analysis.py path (still informative even when score differs)
    mt_analysis = r.get("medium_term") or {}

    # System gate enforcement — if circuit breaker / forced cash / macro blackout
    # is active, demote Position/Invest BUYs to WATCH (mirrors what decision_engine
    # already does for Swing). Same trust principle: a system-wide stop must
    # affect ALL timeframes, not just short-term.
    pos_v = _verdict(pos_score, "position")
    inv_v = _verdict(inv_score, "invest")
    if _SYSTEM_GATE_ACTIVE:
        if pos_v == "BUY":
            pos_v = "WATCH"
        if inv_v == "BUY":
            inv_v = "WATCH"

    return {
        "medium_term_score":         pos_score,
        "medium_term_verdict":       pos_v,
        "medium_term_gate_status":   "system_gate_active" if _SYSTEM_GATE_ACTIVE else mt_analysis.get("gate_status"),
        "medium_term_gate_reasons":  ([_SYSTEM_GATE_REASON] if _SYSTEM_GATE_ACTIVE
                                       else (mt_analysis.get("gate_reasons") or [])),
        "long_term_score":           inv_score,
        "long_term_verdict":         inv_v,
        "long_term_breakdown":       (r.get("long_term") or {}).get("breakdown") or {},
    }


def _build_audit_trail(r: dict) -> dict:
    """
    P4.39 — Build the per-ticker audit trail from the full result dict.

    Returns structured why-buy / red-flags reasoning aggregated from all
    gates + scoring + theory confluence + options. Designed for v2 PLAN
    tab "Why BUY" panel.
    """
    sb = r.get("scoring_breakdown") or {}
    gate = r.get("gate") or {}
    tc = r.get("theory_confluence") or {}
    mc = r.get("methodology_checklist") or {}
    ok = r.get("options_kpis") or {}
    tp = r.get("trade_plan") or {}
    rg = r.get("regime") or {}
    er = r.get("earnings") or {}
    info = r.get("info") or {}
    decision = r.get("decision") or {}

    why_buy: list = []
    red_flags: list = []

    score = r.get("score") or sb.get("total_score") or 0
    if score >= 80:
        why_buy.append(f"Score {score}/100 — high conviction")
    elif score >= 70:
        why_buy.append(f"Score {score}/100 — solid setup")
    elif score < 60:
        red_flags.append(f"Score {score}/100 — below threshold")

    if tc.get("hard_gate_pass") and tc.get("direction") == "BULLISH":
        bull_aligned = [k for k, v in (tc.get("bull_aligned") or {}).items() if v]
        if bull_aligned:
            why_buy.append(f"Theory confluence: {len(bull_aligned)}/4 ({', '.join(bull_aligned)})")
    elif tc.get("hard_gate_pass") is False:
        red_flags.append(f"Theory confluence FAIL: {tc.get('evidence_summary', 'insufficient agreement')}")

    if mc.get("verdict") == "STRONG":
        why_buy.append(f"Technical confirmation STRONG ({mc.get('passes', 0)}/5 indicators)")
    elif mc.get("verdict") == "WEAK":
        red_flags.append(f"Technical confirmation WEAK ({mc.get('passes', 0)}/5 indicators)")

    opt_v = ((ok.get("verdict") or {}).get("verdict")) if ok else None
    opt_edge = ((ok.get("verdict") or {}).get("edge")) if ok else 0
    if opt_v == "BULLISH":
        why_buy.append(f"Options flow BULLISH (edge {opt_edge}/10)")
    elif opt_v == "BEARISH":
        red_flags.append(f"Options flow BEARISH — institutional hedging")

    rr = tp.get("rr_ratio") or r.get("rr_ratio") or 0
    if rr >= 3.5:
        why_buy.append(f"R:R {rr:.1f}:1 — asymmetric reward")
    elif rr and rr < 2.0:
        red_flags.append(f"R:R {rr:.1f}:1 — thin reward")

    eq = r.get("entry_quality") or tp.get("entry_quality") or ""
    if eq in ("FRESH", "PULLBACK"):
        why_buy.append(f"Entry quality: {eq}")
    elif eq in ("EXTENDED", "MISSED"):
        red_flags.append(f"Entry quality: {eq} — late location risk")

    days_to_earn = er.get("days_to_earnings") or r.get("days_to_earnings")
    if days_to_earn is None or days_to_earn > 14:
        earnings_risk = "clear"
    elif days_to_earn <= 5:
        earnings_risk = f"BLACKOUT ({days_to_earn}d)"
        red_flags.append(f"Earnings in {days_to_earn} days")
    else:
        earnings_risk = f"{days_to_earn}d"

    return {
        "ticker": r.get("ticker"),
        "verdict": decision.get("verdict") or r.get("verdict") or "WATCH",
        "hard_gates_passed": gate.get("passed", True),
        "gate_failures": gate.get("reasons", []),
        "theory_confluence": {
            "direction": tc.get("direction"),
            "count": tc.get("bull_count"),
            "min_required": tc.get("min_required"),
            "gate_pass": tc.get("hard_gate_pass"),
            "states": tc.get("states", {}),
        },
        "scoring": {
            "total": score,
            "tech": sb.get("tech_score"),
            "catalyst": sb.get("cat_score"),
            "rs_sector": sb.get("rs_score"),
            "smart_money": sb.get("sm_score"),
            "quality": sb.get("qg_score") or sb.get("fund_score"),
        },
        "risk_reward": rr,
        "entry_quality": eq,
        "earnings_risk": earnings_risk,
        "regime": rg.get("regime") or rg.get("regime4"),
        "options_verdict": opt_v,
        "why_buy": why_buy,
        "red_flags": red_flags,
    }


def rich_row(r: dict, b: dict = None) -> dict:
    if b is None: b = {}
    """Per-ticker payload for elite-detail (preserves nested analysis dicts)."""
    base = compact_row(r)
    fund   = _real_fund(r)
    ana    = _real_analyst(r)
    ins    = _real_insider(r)
    news   = _real_news(r)
    techs  = r.get("technicals") or {}
    fmts   = r.get("fundamentals") or {}
    base.update({
        "name":         r.get("name") or r.get("ticker"),
        "industry":     r.get("industry") or "",
        "verdict":      base["stage"],
        "setup_family": r.get("setup_family"),
        "max_hold_days": (r.get("hold_period_guide") or {}).get("max_days") if isinstance(r.get("hold_period_guide"), dict) else 14,
        "regime":       r.get("regime4") or "neutral",

        # REAL Elliott Wave + reaction checklist + trade plan
        "elliott_wave": r.get("elliott_wave") or {},
        "reaction_checklist": r.get("reaction_checklist") or [],
        "trade_plan":   r.get("trade_plan") or {},
        # Methodology pre-trade checklist (5 booleans: Dow / Wyckoff / MA / Sector / no-late-wave)
        "methodology_checklist": r.get("methodology_checklist") or {},
        # Theory confluence — strict Dow/Wyckoff/Elliott/Gann states + hard gate
        "theory_confluence": r.get("theory_confluence") or {},
        # P4.39 — Audit trail per BUY: structured record of why this verdict
        "audit_trail": _build_audit_trail(r),
        # Options intelligence — IV rank, P/C, UOA, skew, term, gamma, verdict + thesis + per-mode overlay
        "options_kpis": r.get("options_kpis") or {},
        # Per-mode verdicts — use the SAME re-weighted scoring that builds the
        # Position/Invest tab lists, so per-ticker badges match what user sees
        # on the dashboard. Falls back to analysis.py results if re-weighted
        # score isn't computable.
        **_compute_mode_verdicts(r),
        "fib_382":      (r.get("trade_plan") or {}).get("fib_382"),
        "fib_500":      (r.get("trade_plan") or {}).get("fib_500"),
        "fib_618":      (r.get("trade_plan") or {}).get("fib_618"),

        # Pillar scores
        "tech_score":   techs.get("score") or base.get("tech_pts"),
        "tech_max":     techs.get("max", 38),
        "fund_score":   fmts.get("score") or base.get("fund_pts"),
        "fund_max":     fmts.get("max", 30),
        "smc_score":    base.get("smc_pts"),
        "sent_score":   r.get("news_sentiment_score") or r.get("polygon_news_score") if isinstance(r.get("news_sentiment_score") or r.get("polygon_news_score"), (int, float)) else ((r.get("news_sentiment_score") or r.get("polygon_news_score") or {}).get("score") or 0),
        "sent_max":     10,

        # Trade plan basics
        "entry_low":    base.get("entry_lo"),
        "entry_high":   base.get("entry_hi"),
        "target1":      base.get("t1"),
        "target2":      base.get("t2"),
        "rr_ratio":     base.get("rr"),
        # 2026-05-04: coherence flag — if cached upstream rr differed from canonical math
        "rr_inconsistent": base.get("_rr_inconsistent", False),
        "atr_pct":      r.get("atr_pct"),

        # REAL fundamentals breakdown
        "fund_real":    fund,
        "fund_details": fmts.get("details") or {},
        "fund_total":   {"score": fmts.get("score"), "max": fmts.get("max", 30)},

        # REAL analyst, insider, news
        "analyst":      ana,
        "analyst_full": r.get("analyst") or {},
        "insider":      ins,
        "insider_full": r.get("insider_data") or {},
        "news":         news,
        # EODHD News API — honest naming (Polygon decommissioned 2026-04-25).
        "news_articles":        (r.get("news_articles") or r.get("polygon_news") or [])[:8],
        "news_sentiment_score": r.get("news_sentiment_score") or r.get("polygon_news_score") or {},

        # Tier 1 strategy enhancements (6 detectors — see tier1_signals.py)
        "tier1_signals":      r.get("tier1_signals") or {},

        # Social
        "stocktwits":   r.get("stocktwits") or {},
        "reddit_wsb":   r.get("reddit_wsb") or {},
        "sentiment":    r.get("sentiment") or {},
        "congressional":r.get("congressional") or {},

        # SEC filings + institutional
        "sec_filings":  r.get("sec_filings") or {},
        "inst_trend":   r.get("inst_trend") or {},

        # Technicals (full breakdown for Chart tab)
        "tech_details": (techs.get("details") or {}),
        "ema_signal":   r.get("ema_signal"),
        "macd_signal":  r.get("macd_signal"),
        "fractal_signal": r.get("fractal_signal"),
        "fractal_high": r.get("fractal_high"),
        "fractal_low":  r.get("fractal_low"),
        "squeeze_on":   r.get("squeeze") if isinstance(r.get("squeeze"), bool) else (r.get("squeeze") or {}).get("on"),
        "squeeze":      r.get("squeeze") if isinstance(r.get("squeeze"), dict) else {"on": bool(r.get("squeeze"))},
        "patterns":     r.get("patterns") or {},
        "vwap":         r.get("vwap") or {},
        "premarket":    r.get("premarket") or {},
        "smc":          r.get("smc") or {},
        "trade_thesis": r.get("trade_thesis"),
        "market_phase": r.get("market_phase"),

        # OHLCV (last 90 daily bars, compact) for real chart rendering
        "ohlcv":        _trim_ohlcv(r.get("ohlcv"), 90, ticker=r.get("ticker")),
        # V-3: Forward-distribution metrics (VaR-95, CVaR-97.5, P-profit, fwd-Sharpe)
        "forward_dist": _compute_forward_dist_safe(r.get("ohlcv")),
        # V-1: Monte Carlo simulation (Merton jump-diffusion · 3K paths × 63d · Numba JIT)
        "monte_carlo":  _compute_monte_carlo_safe(r),
        # Extended fundamentals (FCF, capex, segments, geo) for deep-dive panel
        "eodhd_fund_extras": r.get("eodhd_fund_extras") or {},

        # Risk / sizing
        "kelly_size":   r.get("kelly_size") or {},
        "sizing_multiplier": r.get("sizing_multiplier"),
        "beta":         r.get("beta") or (r.get("kelly_size") or {}).get("beta"),
        "market_cap":   r.get("market_cap"),
        "float_shares": r.get("float_shares"),
        "shares_out":   r.get("shares_out"),
        "week52_high":  r.get("week52_high"),
        "week52_low":   r.get("week52_low"),
        "eodhd_sentiment": r.get("eodhd_sentiment") or {},

        # Zacks
        "zacks_grades": {
            "growth":  r.get("grade_growth"),
            "value":   r.get("grade_value"),
            "momentum":r.get("grade_momentum"),
            "vgm":     r.get("grade_vgm"),
            "verdict": r.get("vgm_verdict"),
            "raw_growth_score":   r.get("raw_growth_score"),
            "raw_value_score":    r.get("raw_value_score"),
            "raw_momentum_score": r.get("raw_momentum_score"),
        },
        "zacks_rank1":  bool(r.get("zacks_rank1")),
        "zacks_sell":   bool(r.get("zacks_sell")),
        # Per-ticker R1 score rationale (when available)
        "zacks_rank_rationale": (b.get("zacks_r1_scores") or {}).get(r.get("ticker")),
        # Service membership — which Zacks Premium services hold this ticker
        "zacks_held_by_services": _zacks_services_holding_ticker(r.get("ticker"), b),
        # Email digest mentions for this ticker
        "zacks_email_mentions": _zacks_email_mentions_for_ticker(r.get("ticker"), b.get("gmail_zacks") or {}),
        # Phase 1 — per-ticker quote-page enrichment
        "zacks_industry_rank":   r.get("zacks_industry_rank"),
        "zacks_industry_total":  r.get("zacks_industry_total"),
        "zacks_industry_pct":    r.get("zacks_industry_pct"),
        "zacks_sector_rank":     r.get("zacks_sector_rank"),
        "zacks_sector_total":    r.get("zacks_sector_total"),
        "zacks_earnings_esp":    r.get("zacks_earnings_esp"),
        "zacks_lt_growth":       r.get("zacks_lt_growth"),
        "zacks_recommendation":  r.get("zacks_recommendation"),
        "zacks_estimate_revisions": r.get("zacks_estimate_revisions"),
        "zacks_revision_counts": r.get("zacks_revision_counts"),
        "zacks_eps_surprise_history": r.get("zacks_eps_surprise_history"),
        "zacks_brokerage_recommendations": r.get("zacks_brokerage_recommendations"),
        "tv_rating":    r.get("tv_rating") or {},
        "uoa":          r.get("uoa") or {},
        # Sanitize stale Schwab refresh-token error blobs — when source unavailable,
        # collapse to a clean placeholder so V2 renders '—' instead of a 200-char
        # OAuth error string. (2026-05-07 — Schwab options decommissioned.)
        "options_data": _sanitize_options(r.get("options_data") or {}),
        "gamma":        r.get("gamma") or {},
        "optionality":  r.get("optionality") or {},

        # Conv tier
        "conviction":   r.get("conviction") or {},
        "decision":     r.get("decision") or {},
        "entry_quality":r.get("entry_quality"),
        "entry_subtype":r.get("entry_subtype"),

        # Convenience back-compat
        "news_score":   news.get("score", 0),
        "insider_buys": ins.get("buys", 0),
        "insider_sells":ins.get("sells", 0),
    })
    return base


def main():
    global _PREV_BUNDLE_INDEX, _PREV_BUNDLE_DATE, _SYSTEM_GATE_ACTIVE, _SYSTEM_GATE_REASON
    _prev = _load_previous_bundle_index()
    _PREV_BUNDLE_DATE = _prev.pop("_snapshot_date", "") if _prev else ""
    _PREV_BUNDLE_INDEX = _prev or {}
    b = json.loads(BUNDLE.read_text())
    # Capture system-level gates so _compute_mode_verdicts can honor them too
    _ss = b.get("system_status") or {}
    _cb = (_ss.get("circuit_breaker") or {}).get("active")
    _fc = (_ss.get("forced_cash") or {}).get("active")
    _mb = (_ss.get("macro_calendar") or {}).get("blackout_today")
    _SYSTEM_GATE_ACTIVE = bool(_cb or _fc or _mb)
    if _cb:
        _SYSTEM_GATE_REASON = (_ss["circuit_breaker"].get("reasons") or ["circuit breaker active"])[0]
    elif _fc:
        _SYSTEM_GATE_REASON = "forced cash mode active"
    elif _mb:
        _SYSTEM_GATE_REASON = "macro blackout: " + (_ss["macro_calendar"].get("blackout_reason") or "FOMC/CPI")
    else:
        _SYSTEM_GATE_REASON = ""

    # Enrich with EODHD data (Beta, MarketCap, Float, 52wk, Sentiment, Events)
    all_candidate_rows = (b.get("buy_candidates") or []) + (b.get("watch_list") or []) + \
                         (b.get("near_short_blocked") or []) + (b.get("medium_term_picks") or [])
    all_symbols = list({r.get("ticker") for r in all_candidate_rows if r.get("ticker")})
    print(f"Fetching EODHD enrichment for {len(all_symbols)} symbols...")
    fund_enrichment = _fetch_fundamentals_enrichment(all_symbols)
    globals()["_FUND_ENRICHMENT_GLOBAL"] = fund_enrichment  # so compact_row can pull names/industry
    sentiment_data  = _fetch_sentiment(all_symbols)
    economic_events = _fetch_economic_events(days_ahead=14)
    print(f"  Fundamentals enriched: {len(fund_enrichment)}, Sentiments: {len(sentiment_data)}, Events: {len(economic_events)}")

    # Live re-fetch analyst consensus for top tickers (bypasses bundle's stale "—")
    print("Re-fetching analyst consensus for top tickers (Finviz scrape)...")
    try:
        import sys as _sys
        _sys.path.insert(0, str(ROOT))
        from data_fetcher import get_analyst_data as _get_analyst
        _top = [r.get("ticker") for r in all_candidate_rows[:25]]
        for _t in _top:
            try:
                _a = _get_analyst(_t) or {}
                if _a.get("consensus") and _a.get("consensus") not in ("—", "-"):
                    # Find row + overwrite analyst dict
                    for _r in all_candidate_rows:
                        if _r.get("ticker") == _t:
                            _existing = _r.get("analyst") or {}
                            _existing.update({
                                "consensus": _a.get("consensus"),
                                "target_mean": _a.get("target_mean") or _existing.get("target_mean"),
                                "upside_pct":  _a.get("upside_pct") if _a.get("upside_pct") is not None else _existing.get("upside_pct"),
                                "recent_upgrades":   _a.get("recent_upgrades", _existing.get("recent_upgrades", 0)),
                                "recent_downgrades": _a.get("recent_downgrades", _existing.get("recent_downgrades", 0)),
                                "latest_actions": _a.get("latest_actions") or _existing.get("latest_actions", []),
                            })
                            _r["analyst"] = _existing
                            break
            except Exception:
                pass
    except Exception as _e:
        print(f"  (analyst refetch skipped: {_e})")

    # Patch enrichment back into candidate rows
    for r in all_candidate_rows:
        sym = r.get("ticker", "")
        if sym in fund_enrichment:
            fe = fund_enrichment[sym]
            if r.get("beta") is None:          r["beta"]          = fe.get("beta")
            if r.get("market_cap") is None:    r["market_cap"]    = fe.get("market_cap")
            if r.get("float_shares") is None:  r["float_shares"]  = fe.get("float_shares")
            if r.get("shares_out") is None:    r["shares_out"]    = fe.get("shares_out")
            if r.get("week52_high") is None:   r["week52_high"]   = fe.get("week52_high")
            if r.get("week52_low") is None:    r["week52_low"]    = fe.get("week52_low")
            if r.get("profit_margin") is None: r["profit_margin"] = fe.get("profit_margin")
            # Extended fundamentals deep-dive payload
            if fe.get("eodhd_fund_extras"):
                r["eodhd_fund_extras"] = fe["eodhd_fund_extras"]
        if sym in sentiment_data:
            # _fetch_sentiment now returns a rich summary: latest, avg_7d, avg_30d, trend, history
            r["eodhd_sentiment"] = sentiment_data[sym]

    # Short term = BUY + WATCH + SHORT candidates merged
    st_rows = (b.get("buy_candidates") or []) \
            + (b.get("watch_list") or []) \
            + (b.get("near_short_blocked") or [])
    mt_rows = b.get("medium_term_picks") or []
    lt_rows = []  # not populated by current scan

    # Force SHORT stage on near_short rows
    short_set = {(r.get("ticker") or "") for r in (b.get("near_short_blocked") or [])}

    def with_forced_short(row):
        cr = compact_row(row)
        if cr["ticker"] in short_set:
            cr["stage"] = "SELL"
        return cr

    short_term  = [with_forced_short(r) for r in st_rows if r.get("ticker")]
    # Tag swing-mode rows so dashboard mode toggle can filter
    for cr in short_term:
        cr["mode"] = "swing"

    # ── POSITION (3wk-3mo) + INVEST (3mo+) modes ──
    # analysis.py's score_medium_term/score_long_term depend on weekly_df +
    # schwab_fund which are sparse, producing scores capped at 25/18 — too few
    # qualifying picks. Instead we re-weight the existing 5-pillar swing
    # breakdown with mode-specific weights:
    #   POSITION: tech 25 + cat 10 + rs 30 + sm 5 + fundamentals 30  (RS-heavy + quality)
    #   INVEST:   tech 15 + cat  5 + rs 10 + sm 5 + fundamentals 65  (fundamentals-driven)
    # Universe gates pulled from fund_enrichment (mcap), regardless of Zacks rank.
    def _mode_score(r: dict, weights: tuple[int, int, int, int, int]) -> float:
        sb = r.get("scoring_breakdown") or {}
        fund = (r.get("fundamentals") or {}).get("score", 0) or 0
        t  = float(sb.get("tech_score") or 0)
        c  = float(sb.get("cat_score") or 0)
        rs = float(sb.get("rs_score")  or 0)
        sm = float(sb.get("sm_score")  or 0)
        wt, wc, wr, wsm, wf = weights
        return ((t/35)*wt + (c/20)*wc + (rs/20)*wr + (sm/15)*wsm + (fund/15)*wf)

    POSITION_W = (25, 10, 30, 5, 30)
    INVEST_W   = (15,  5, 10, 5, 65)

    position_rows = []
    invest_rows = []
    for r in (b.get("all_scored") or []):
        sb = r.get("scoring_breakdown") or {}
        if sb.get("tech_score") is None:
            continue
        # Skip explicit short signals — we only build long-mode candidates here
        if (r.get("decision") or {}).get("verdict") == "SELL":
            continue

        sym = r.get("ticker") or ""
        # Pull mcap from enrichment (all_scored doesn't carry it natively)
        mcap = (fund_enrichment.get(sym) or {}).get("market_cap") or r.get("market_cap") or 0

        # ---- Mode-specific stop/target overrides (Phase C) ----
        # Swing: 1.25× ATR (current). Position: 2× ATR or weekly low. Invest: 200d MA breach.
        techs = r.get("technicals") or {}
        atr_pct = techs.get("atr_pct") or 0
        sma200  = techs.get("sma200") or techs.get("sma_200")
        ema21_w = (r.get("weekly") or {}).get("ema21") if isinstance(r.get("weekly"), dict) else None
        px = r.get("price") or 0

        def _mode_plan(mode: str) -> dict:
            """Return mode-specific stop/T1/T2 overrides on top of swing trade_plan.
            ATR-based methods need atr_pct; fall back to fixed % if missing."""
            if not px:
                return {}
            atr_abs = (atr_pct / 100.0) * px if atr_pct else (px * 0.025)  # default 2.5% if no ATR
            if mode == "position":
                # 2× ATR stop (or 5% fallback), T1 = +3×ATR, T2 = +6×ATR
                return {
                    "stop":    round(px - 2.0 * atr_abs, 2),
                    "target1": round(px + 3.0 * atr_abs, 2),
                    "target2": round(px + 6.0 * atr_abs, 2),
                    "rr_ratio": 3.0,
                    "stop_method": "2× ATR" if atr_pct else "-5% fixed",
                }
            if mode == "invest":
                # Stop at 200d MA breach (or -15% drawdown), T1 = +25%, T2 = +50%
                stop = sma200 * 0.97 if sma200 else px * 0.85
                return {
                    "stop":    round(stop, 2),
                    "target1": round(px * 1.25, 2),
                    "target2": round(px * 1.50, 2),
                    "rr_ratio": round((px * 0.25) / max(0.01, px - stop), 2) if px > stop else 0,
                    "stop_method": "SMA200 trail" if sma200 else "-15% drawdown",
                }
            return {}

        # POSITION: admission ≥55, BUY ≥68, WATCH 55-68, mcap ≥ $2B
        pos = _mode_score(r, POSITION_W)
        if pos >= 55 and (mcap == 0 or mcap >= 2_000_000_000):
            cr = compact_row(r)
            cr["mode"]    = "position"
            cr["score"]   = round(pos, 1)
            # Gate check (2026-05-07): Position must also honor decision_engine gates,
            # not just score threshold. Otherwise BUY headlines contradict 'entry MISSED'
            # / 'tail filter demoted' / 'fund < 50%' details (186-issue audit caught this).
            _gates = cr.get("gates_evaluated") or []
            _gates_ok = all(g.get("passed") for g in _gates) if _gates else True
            if _SYSTEM_GATE_ACTIVE:
                cr["stage"] = "WATCH"
                if pos >= 68:
                    cr["reject_reason"] = _SYSTEM_GATE_REASON
            elif not _gates_ok and pos >= 68:
                cr["stage"] = "WATCH"
                _failed = next((g for g in _gates if not g.get("passed")), None)
                if _failed:
                    cr["reject_reason"] = _failed.get("reason") or f"gate {_failed.get('name')} failed"
            else:
                cr["stage"] = "BUY" if pos >= 68 else "WATCH"
                if cr["stage"] == "BUY":
                    cr["reject_reason"] = None  # clear any stale carry-over reject text
            cr["market_cap"] = mcap or cr.get("market_cap")
            cr["hold_period_min"] = 21
            cr["hold_period_max"] = 90
            # Mode-specific stop/target
            mp = _mode_plan("position")
            if mp:
                cr["stop"] = mp["stop"]; cr["t1"] = mp["target1"]; cr["t2"] = mp["target2"]
                cr["rr"]   = mp["rr_ratio"]; cr["stop_method"] = mp["stop_method"]
            position_rows.append(cr)

        # INVEST: admission ≥60, BUY ≥72, WATCH 60-72, mcap ≥ $10B
        inv = _mode_score(r, INVEST_W)
        if inv >= 60 and (mcap == 0 or mcap >= 10_000_000_000):
            cr = compact_row(r)
            cr["mode"]    = "invest"
            cr["score"]   = round(inv, 1)
            _gates = cr.get("gates_evaluated") or []
            _gates_ok = all(g.get("passed") for g in _gates) if _gates else True
            if _SYSTEM_GATE_ACTIVE:
                cr["stage"] = "WATCH"
                if inv >= 72:
                    cr["reject_reason"] = _SYSTEM_GATE_REASON
            elif not _gates_ok and inv >= 72:
                cr["stage"] = "WATCH"
                _failed = next((g for g in _gates if not g.get("passed")), None)
                if _failed:
                    cr["reject_reason"] = _failed.get("reason") or f"gate {_failed.get('name')} failed"
            else:
                cr["stage"] = "BUY" if inv >= 72 else "WATCH"
                if cr["stage"] == "BUY":
                    cr["reject_reason"] = None
            cr["market_cap"] = mcap or cr.get("market_cap")
            cr["hold_period_min"] = 90
            cr["hold_period_max"] = 540
            mp = _mode_plan("invest")
            if mp:
                cr["stop"] = mp["stop"]; cr["t1"] = mp["target1"]; cr["t2"] = mp["target2"]
                cr["rr"]   = mp["rr_ratio"]; cr["stop_method"] = mp["stop_method"]
            invest_rows.append(cr)

    # Sort each mode by score desc. Caps:
    # - Swing stays at top 5 (set upstream in swing_trade.py via top_n_buy)
    # - Position/Invest show more — user has $25K and wants 5-8 active positions
    #   per mode, so surface top 100 candidates so they can pick from a wider pool.
    position_rows.sort(key=lambda r: r.get("score") or 0, reverse=True)
    invest_rows.sort(key=lambda r: r.get("score") or 0, reverse=True)
    position_rows = position_rows[:100]
    invest_rows = invest_rows[:100]

    medium_term = position_rows
    long_term   = invest_rows

    from collections import Counter
    print(f"short_term  n={len(short_term)} mode=swing    stages={dict(Counter(r['stage'] for r in short_term))}")
    print(f"medium_term n={len(medium_term)} mode=position stages={dict(Counter(r['stage'] for r in medium_term))}")
    print(f"long_term   n={len(long_term)} mode=invest   stages={dict(Counter(r['stage'] for r in long_term))}")

    # Top-N from all_scored for Screener tab
    all_scored = sorted(b.get("all_scored") or [], key=lambda r: r.get("score", 0), reverse=True)[:50]
    screener_rows = [compact_row(r) for r in all_scored if r.get("ticker")]

    # Themes — flatten each thematic list to a compact array
    themes = {}
    for theme_key in ('alt_energy','blockchain','tech_innovators','counterstrike','headlinetrader','tazr','bbt','ultimate'):
        t = b.get(theme_key) or {}
        trades = t.get('trades') or t.get('rows') or []
        themes[theme_key] = [
            {
                "ticker":     r.get("ticker"),
                "company":    r.get("company") or r.get("name") or "",
                "price_add":  r.get("price_add"),
                "price_last": r.get("price_last"),
                "pct_chg":    r.get("pct_chg"),
                "date_add":   r.get("date_add"),
            }
            for r in trades[:30] if r.get("ticker")
        ]

    # Industries — top by avg_score (only those with ≥2 tickers)
    inds = sorted(
        [i for i in (b.get("industries") or []) if (i.get("count") or 0) >= 2],
        key=lambda x: x.get("avg_score", 0), reverse=True
    )[:30]

    # Setup attribution from mtm_data — count by setup_family + verdict
    from collections import Counter
    mtm = b.get("mtm_data") or []
    by_setup = Counter()
    by_verdict = Counter()
    for r in mtm:
        if r.get('setup_family'): by_setup[r['setup_family']] += 1
        if r.get('verdict'):      by_verdict[r['verdict']]    += 1

    # ---- Portfolio (open + closed positions, equity) ----
    portfolio = {"positions": [], "closed": [], "equity": None, "cash": None,
                 "monthly_pnl": {}, "equity_curve": []}
    if PORTFOLIO.exists():
        try:
            ps = json.loads(PORTFOLIO.read_text())
            portfolio["positions"]    = ps.get("positions") or []
            portfolio["closed"]       = ps.get("closed_trades") or []
            portfolio["equity"]       = ps.get("equity")
            portfolio["cash"]         = ps.get("cash")
            portfolio["monthly_pnl"]  = ps.get("monthly_pnl") or {}
            portfolio["equity_curve"] = ps.get("equity_curve") or []
        except Exception as e:
            portfolio["error"] = str(e)

    # ---- Audit Trail enrichment helper ----
    # For each signal, compute trading-day forward prices using OHLCV archive.
    # Lookback offsets (trading days, not calendar):
    #   D1, D2, D3, D4, D5  → 1-5 days post entry
    #   W1...W5             → 5, 10, 15, 20, 25 days
    #   M1...M6             → 21, 42, 63, 84, 105, 126 days (~monthly)
    _AUDIT_DAY_OFFSETS = {'D1':1, 'D2':2, 'D3':3, 'D4':4, 'D5':5}
    _AUDIT_WEEK_OFFSETS = {'W1':5, 'W2':10, 'W3':15, 'W4':20, 'W5':25}
    _AUDIT_MONTH_OFFSETS = {'M1':21, 'M2':42, 'M3':63, 'M4':84, 'M5':105, 'M6':126}
    _AUDIT_OFFSETS = {**_AUDIT_DAY_OFFSETS, **_AUDIT_WEEK_OFFSETS, **_AUDIT_MONTH_OFFSETS}

    _ohlcv_cache: dict = {}
    def _audit_enrich(sig: dict) -> dict:
        """Compute forward prices D1-D5, W1-W5, M1-M6 from OHLCV archive."""
        out = dict(sig)
        # Mode tagging — all historical signal_log entries are Swing (only mode tracked).
        # New signals can carry an explicit `mode` field; default to "Swing" otherwise.
        out["mode"] = sig.get("mode") or "Swing"
        sym = (sig.get("ticker") or "").upper()
        entry_px = sig.get("entry_price")
        sig_date = sig.get("date")
        if not (sym and entry_px and sig_date):
            return out
        try:
            import pandas as _pd
            from pathlib import Path as _Path
            if sym not in _ohlcv_cache:
                p = _Path(f"data/ohlcv/{sym}.parquet")
                if not p.exists():
                    _ohlcv_cache[sym] = None
                else:
                    df = _pd.read_parquet(p)
                    if not isinstance(df.index, _pd.DatetimeIndex):
                        df.index = _pd.to_datetime(df.index)
                    _ohlcv_cache[sym] = df.sort_index()
            df = _ohlcv_cache[sym]
            if df is None or df.empty:
                return out
            # Find row index >= sig_date
            sig_ts = _pd.to_datetime(sig_date)
            after = df[df.index >= sig_ts]
            if after.empty:
                return out
            entry_idx = df.index.get_loc(after.index[0])
            close = df["Close"].squeeze() if hasattr(df["Close"], "squeeze") else df["Close"]
            today_close = float(close.iloc[-1])
            out["today"] = round(today_close, 2)
            out["pct_now"] = round((today_close / entry_px - 1) * 100, 2)
            for label, n in _AUDIT_OFFSETS.items():
                target_idx = entry_idx + n
                if target_idx < len(close):
                    px = float(close.iloc[target_idx])
                    out[label] = round(px, 2)
                    out[f"{label}_pct"] = round((px / entry_px - 1) * 100, 2)
        except Exception:
            pass
        return out

    # ---- Pre-compute elite picks BEFORE the audit_trail merge so we can
    # ---- tag each live audit entry with its elite_score + rank.
    # Bug fix (2026-05-06): respect system circuit breaker — when active,
    # elite_picks must not surface BUYs that have been gated out.
    _ss = b.get("system_status") or {}
    _cb_active = (_ss.get("circuit_breaker") or {}).get("active") or \
                 (_ss.get("forced_cash") or {}).get("active") or \
                 (_ss.get("macro_calendar") or {}).get("blackout_today")
    if _cb_active:
        _cb_reasons = (_ss.get("circuit_breaker") or {}).get("reasons") or ["system gate active"]
        _elite = {
            "Swing":    {"BUY": [], "WATCH": [], "SHORT": []},
            "Position": {"BUY": [], "WATCH": [], "SHORT": []},
            "Invest":   {"BUY": [], "WATCH": [], "SHORT": []},
            "meta": {
                "blocked": True,
                "reason": "; ".join(_cb_reasons),
                "note":   "Elite Picks suppressed — system circuit breaker active",
            },
        }
    else:
        _elite = _compute_elite_picks_safe(
            short_term=short_term, medium_term=medium_term, long_term=long_term,
            st_rows=st_rows, mt_rows=mt_rows, invest_rows=invest_rows,
            accuracy=_compute_accuracy_safe(),
            hmm=_compute_hmm_regime_safe(),
            macro=(b.get("regime") or {}).get("macro_signals") or b.get("macro_signals") or {},
        )
    # Build {(ticker, mode, stage): {elite_score, rank, verdict_line}} lookup
    _elite_lookup = {}
    for _mode in ("Swing", "Position", "Invest"):
        for _stage in ("BUY", "WATCH", "SHORT"):
            for _i, _p in enumerate((_elite.get(_mode) or {}).get(_stage, [])):
                _elite_lookup[(_p["ticker"], _mode, _stage)] = {
                    "elite_score": _p["elite_score"],
                    "elite_rank":  _i + 1,
                    "elite_verdict_line": _p.get("verdict_line"),
                }

    # ---- Signal history / performance attribution ----
    perf = {"total": 0, "open": 0, "closed": 0, "wins": 0, "losses": 0,
            "win_rate": None, "by_strategy": {}, "by_score_bucket": {},
            "mae_avg": None, "mfe_avg": None, "rr_avg": None,
            "recent": [], "audit_trail": []}
    if SIGNAL_LOG.exists():
        try:
            sl = json.loads(SIGNAL_LOG.read_text())
            perf["total"]  = len(sl)
            perf["open"]   = sum(1 for r in sl if r.get("status") == "OPEN")
            done = [r for r in sl if r.get("outcome_10d") in ("win", "loss", "breakeven")]
            perf["closed"] = len(done)
            perf["wins"]   = sum(1 for r in done if r.get("outcome_10d") == "win")
            perf["losses"] = sum(1 for r in done if r.get("outcome_10d") == "loss")
            perf["win_rate"] = round(perf["wins"] / perf["closed"] * 100, 1) if perf["closed"] else None
            from collections import Counter
            by_strat = Counter()
            mae_vals, mfe_vals, rr_vals = [], [], []
            for r in sl:
                s = r.get("strategy")
                if s: by_strat[s] += 1
                if isinstance(r.get("mae_pct"), (int, float)): mae_vals.append(r["mae_pct"])
                if isinstance(r.get("mfe_pct"), (int, float)): mfe_vals.append(r["mfe_pct"])
                if isinstance(r.get("rr"), (int, float)):       rr_vals.append(r["rr"])
            perf["by_strategy"] = dict(by_strat.most_common())
            # Per-strategy ticker rosters (most recent first, deduped)
            tickers_by_strategy = {}
            for r in reversed(sl):
                s = r.get("strategy")
                if not s: continue
                if s not in tickers_by_strategy:
                    tickers_by_strategy[s] = {}
                t = r.get("ticker")
                if t and t not in tickers_by_strategy[s]:
                    tickers_by_strategy[s][t] = {
                        "ticker":      t,
                        "date":        r.get("date"),
                        "score":       r.get("score"),
                        "stars":       r.get("stars"),
                        "rs_rank":     r.get("rs_rank"),
                        "entry_price": r.get("entry_price"),
                        "stop":        r.get("stop"),
                        "target1":     r.get("target1"),
                        "rr":          r.get("rr"),
                        "mae_pct":     r.get("mae_pct"),
                        "mfe_pct":     r.get("mfe_pct"),
                        "status":      r.get("status"),
                    }
            perf["tickers_by_strategy"] = {
                k: list(v.values())[:25] for k, v in tickers_by_strategy.items()
            }
            perf["mae_avg"] = round(sum(mae_vals)/len(mae_vals), 2) if mae_vals else None
            perf["mfe_avg"] = round(sum(mfe_vals)/len(mfe_vals), 2) if mfe_vals else None
            perf["rr_avg"]  = round(sum(rr_vals)/len(rr_vals), 2)  if rr_vals  else None
            score_buckets = Counter()
            for r in sl:
                sc = r.get("score") or 0
                bucket = "90+" if sc >= 90 else "80-89" if sc >= 80 else "70-79" if sc >= 70 else "60-69" if sc >= 60 else "<60"
                score_buckets[bucket] += 1
            perf["by_score_bucket"] = dict(score_buckets)
            # Full historical signal log (most recent first) — ALL records, not just 30
            perf["recent"] = [
                {k: r.get(k) for k in [
                    'ticker','date','strategy','entry_price','stop','target1','target2','rr',
                    'score','stars','status','mae_pct','mfe_pct','direction',
                    'outcome_5d','outcome_10d','actual_pnl_pct','result',
                    'day5_price','day10_price','rs_rank',
                ]}
                for r in sl[::-1]   # all rows, newest first
            ]
            # Audit Trail: enriched with D1-D5, W1-W5, M1-M6 forward prices
            # from OHLCV archive. Used by the AUDIT sub-tab in v2 dashboard.
            audit_entries = [_audit_enrich(r) for r in sl[::-1]]

            # ── 2026-05-04: LIVE MERGE — inject today's bundle picks if not yet logged ──
            # Reason: signal_log is written when swing_trade.py runs (full scan).
            # Between scans, today's picks should still appear in the audit trail.
            # We merge in BUY/WATCH/SHORT from short_term + medium_term + long_term,
            # tagging each with mode (Swing/Position/Invest) and a `live: True` flag.
            try:
                from datetime import datetime as _dt
                _today = _dt.now().strftime("%Y-%m-%d")
                _logged_keys = {(e.get("ticker"), e.get("date"), e.get("mode", "Swing")) for e in audit_entries}
                _live_picks = []

                def _flatten_bundle_pick(r, mode_label, compact_r=None):
                    """Use raw rich `r` for Tier A fields; fall back to compact_r for stage/entry."""
                    stage = (compact_r or r).get("stage")
                    if not stage:
                        # Raw rows may have stage in r['decision']['verdict']
                        d = r.get("decision") or {}
                        stage = (d.get("verdict") or "").upper()
                    stage = (stage or "").upper()
                    if stage not in ("BUY", "WATCH", "SELL"):
                        return None
                    verdict = "SHORT" if stage == "SELL" else stage
                    tk = r.get("ticker")
                    if not tk:
                        return None
                    if (tk, _today, mode_label) in _logged_keys:
                        return None
                    plan = r.get("trade_plan") or {}
                    conv = r.get("conviction") or {}
                    # MC + Forward Dist: compute inline via safe helpers (Numba-cached, fast)
                    mc = _compute_monte_carlo_safe(r) or {}
                    fd = _compute_forward_dist_safe(r.get("ohlcv")) or {}
                    return {
                        "ticker":     tk,
                        "date":       _today,
                        "mode":       mode_label,
                        "verdict":    verdict,
                        "direction":  r.get("direction") or ("short" if verdict == "SHORT" else "long"),
                        "strategy":   r.get("setup_family") or plan.get("setup_type") or "Core Swing",
                        "score":      r.get("score") or 0,
                        "stars":      r.get("star_rating") or (compact_r or {}).get("stars") or 0,
                        "rs_rank":    r.get("rs_rank"),
                        "entry_price":(plan.get("entry_low") or r.get("entry_lo") or r.get("price") or 0),
                        "stop":       plan.get("stop") or r.get("stop") or 0,
                        "target1":    plan.get("target1") or r.get("t1") or 0,
                        "target2":    plan.get("target2") or r.get("t2") or 0,
                        "rr":         plan.get("rr_ratio") or r.get("rr") or 0,
                        "status":     "OPEN",
                        "live":       True,
                        # Tier A — pulled from rich row (these aren't in compact_row)
                        "conviction_label":     conv.get("label"),
                        "entry_quality":        r.get("entry_quality"),
                        "setup_family":         r.get("setup_family"),
                        "tail_filter_demoted":  bool(conv.get("tail_filter_demoted")),
                        "mc_p_profit":          mc.get("p_profit"),
                        "mc_p_target_first":    mc.get("p_hit_target_first"),
                        "mc_p_stop_first":      mc.get("p_hit_stop_first"),
                        "fd_var_95_pct":        fd.get("var_95_pct"),
                        "fd_cvar_975_pct":      fd.get("cvar_975_pct"),
                    }

                # Iterate the FULL recomputed lists (not just the raw bundle source).
                # medium_term/long_term are re-scored from buy_candidates+watch_list with
                # mode-specific pillar weights → they have ~100 entries each, not just 10.
                # We index raw bundle rows by ticker so we can pull rich fields (MC, FD, conviction).
                _raw_index = {r.get("ticker"): r for r in (st_rows + mt_rows) if r.get("ticker")}

                def _emit(compact_row, mode_label):
                    tk = compact_row.get("ticker")
                    if not tk: return None
                    raw = _raw_index.get(tk) or compact_row
                    return _flatten_bundle_pick(raw, mode_label, compact_r=compact_row)

                for cr in (short_term or []):
                    e = _emit(cr, "Swing")
                    if e: _live_picks.append(e)
                for cr in (medium_term or []):
                    e = _emit(cr, "Position")
                    if e: _live_picks.append(e)
                for cr in (long_term or []):
                    e = _emit(cr, "Invest")
                    if e: _live_picks.append(e)

                # Tier A scan-context — same for every live pick this scan
                # HMM lives in the `data` dict (computed via _compute_hmm_regime_safe);
                # call it directly here since `data` isn't built yet at this point.
                _hmm = _compute_hmm_regime_safe() or {}
                _regime_blob = b.get("regime") or {}
                _scan_ctx = {
                    "regime4":         _regime_blob.get("regime4"),
                    "regime_name":     _regime_blob.get("regime"),
                    "vix_at_signal":   (_regime_blob.get("vix") or {}).get("vix_current"),
                    "hmm_p_bull":      _hmm.get("p_bull"),
                    "hmm_p_neutral":   _hmm.get("p_neutral"),
                    "hmm_p_bear":      _hmm.get("p_bear"),
                    "hmm_regime":      _hmm.get("regime"),
                    "hmm_confidence":  _hmm.get("confidence"),
                }
                for e in _live_picks:
                    e.update(_scan_ctx)
                    # Tag with elite-pick metadata if this (ticker, mode, stage) made the cut
                    _elite_match = _elite_lookup.get((e.get("ticker"), e.get("mode"), e.get("verdict")))
                    if _elite_match:
                        e["is_elite"] = True
                        e["elite_score"] = _elite_match["elite_score"]
                        e["elite_rank"] = _elite_match["elite_rank"]
                        e["elite_verdict_line"] = _elite_match["elite_verdict_line"]
                    else:
                        e["is_elite"] = False

                # Enrich with forward prices (will mostly be empty since trade just opened)
                _live_enriched = [_audit_enrich(p) for p in _live_picks]

                # Newest-first ordering — live picks at the top
                audit_entries = _live_enriched + audit_entries
            except Exception as _live_err:
                print(f"[audit-live-merge] non-fatal: {_live_err}")

            perf["audit_trail"] = audit_entries
            # Setup family attribution (for Performance tab attribution table)
            from collections import defaultdict
            sf_stats = defaultdict(lambda: {"trades": 0, "wins": 0, "losses": 0, "rr_sum": 0, "mfe_sum": 0, "mae_sum": 0})
            for r in done:
                fam = r.get("strategy") or "unknown"
                s = sf_stats[fam]
                s["trades"] += 1
                if r.get("outcome_10d") == "win":  s["wins"]   += 1
                if r.get("outcome_10d") == "loss": s["losses"] += 1
                if isinstance(r.get("rr"), (int, float)):      s["rr_sum"]  += r["rr"]
                if isinstance(r.get("mfe_pct"), (int, float)): s["mfe_sum"] += r["mfe_pct"]
                if isinstance(r.get("mae_pct"), (int, float)): s["mae_sum"] -= abs(r["mae_pct"])
            perf["setup_attribution"] = {
                fam: {
                    "trades": s["trades"], "wins": s["wins"], "losses": s["losses"],
                    "win_rate": round(s["wins"] / s["trades"] * 100, 1) if s["trades"] else None,
                    "avg_r":   round(s["rr_sum"]  / s["trades"], 2) if s["trades"] else None,
                    "avg_win": round(s["mfe_sum"] / s["wins"],   2) if s["wins"]   else None,
                    "avg_loss":round(s["mae_sum"] / s["losses"], 2) if s["losses"] else None,
                    "expectancy":     round((s["wins"]/s["trades"]) * (s["mfe_sum"]/max(1,s["wins"])) - ((s["losses"]/s["trades"]) * abs(s["mae_sum"]/max(1,s["losses"]))) if s["trades"] else 0, 2),
                    "profit_factor":  round(s["mfe_sum"] / abs(s["mae_sum"]), 2) if s["mae_sum"] else None,
                }
                for fam, s in sf_stats.items()
            }
        except Exception as e:
            perf["error"] = str(e)

    data = {
        "run_date":      b.get("run_date"),
        "run_timestamp": b.get("run_timestamp"),
        "regime":        b.get("regime") or {},
        "buy_count":     sum(1 for r in short_term if r["stage"] == "BUY"),
        "watch_count":   sum(1 for r in short_term if r["stage"] == "WATCH"),
        "short_count":   sum(1 for r in short_term if r["stage"] == "SELL"),
        "killed_count":  len(b.get("killed") or []),
        "killed":        [compact_row(r) for r in (b.get("killed") or [])],
        "scan_count":    len(b.get("all_scored") or []),
        "short_term":    short_term,
        "medium_term":   medium_term,
        "long_term":     long_term,
        "screener":      screener_rows,
        "industries":    inds,
        "sector_etf":    b.get("sector_etf_data") or {},
        "market_breadth": b.get("market_breadth") or {},
        "macro_signals": b.get("macro_signals") or {},
        # Phase 2 — surface system_status (macro_calendar, circuit_breaker, forced_cash)
        "system_status": b.get("system_status") or {},
        "themes":        themes,
        "data_health":   b.get("data_health") or {},
        "setup_counts":  dict(by_setup),
        "verdict_counts": dict(by_verdict),
        "zacks_count":   len(b.get("zacks_r1_full") or []),
        # ── Zacks (v2 migration off legacy dashboard) ─────────────────────
        # Universe-wide Rank #1 list, scoring rationale, sell list
        "zacks_universe": {
            "r1_full":     b.get("zacks_r1_full") or [],
            "r1_missing":  b.get("zacks_r1_missing") or {},
            "r1_scores":   b.get("zacks_r1_scores") or {},
            "sell_list":   b.get("zacks_sell_list") or [],
        },
        # Premium services (only services that successfully scraped this run)
        "zacks_premium_services": {
            svc: b.get(svc) for svc in (
                "ultimate", "tazr", "bbt", "counterstrike", "headlinetrader",
                "alt_energy", "blockchain", "tech_innovators",
                "surprise_trader", "insider_trader", "value_investor",
                "home_run_investor", "income_investor", "options_trader",
                "stocks_under_10", "marijuana_innovators",
            ) if b.get(svc)
        },
        # Gmail digest summary (rank changes, trade alerts, bull/bear, ticker mentions)
        "zacks_email_digest": b.get("gmail_zacks") or {},
        "portfolio":     portfolio,
        "performance":   perf,
        "economic_events": economic_events,
        # Accuracy framework (V-7 / P0-B · 2026-05-03) — Kupiec, Christoffersen, Basel
        "accuracy":      _compute_accuracy_safe(),
        # S-6: Sector RS pair candidates (market-neutral)
        "sector_pairs":  _compute_sector_pairs_safe(),
        # V-2: Soft regime probabilities P(Bull/Neutral/Bear)
        "hmm_regime":    _compute_hmm_regime_safe(),
        # V-8: DCC-GARCH dynamic portfolio correlation (uses raw rows with ohlcv)
        "dcc_garch":     _compute_dcc_garch_safe(st_rows, mt_rows),
        # V-10: Student-t copula tail dependence
        "tail_copula":   _compute_student_t_copula_safe(st_rows, mt_rows),
        # V-11: CVaR-constrained portfolio optimizer (Rockafellar-Uryasev LP)
        "cvar_portfolio": _compute_cvar_optimizer_safe(st_rows, mt_rows),
        # P0-2: ESP Play roll-up — list of tickers with positive ESP signal this scan
        "esp_picks": [
            {
                "ticker":    s.get("ticker"),
                "score":     s.get("score"),
                "esp_pct":   s.get("esp_play", {}).get("esp_pct"),
                "rank":      s.get("esp_play", {}).get("zacks_rank"),
                "earn_days": s.get("esp_play", {}).get("earn_days"),
                "stage":     s.get("stage"),
                "verdict":   s.get("stage"),
            }
            for s in (short_term + medium_term)
            if isinstance(s.get("esp_play"), dict) and s["esp_play"].get("signal") is True
        ],
        "esp_play_meta": {
            "n_tickers_with_esp_data": sum(
                1 for s in (short_term + medium_term)
                if isinstance(s.get("esp_play"), dict)
                and s["esp_play"].get("esp_pct") is not None
            ) if (short_term or medium_term) else 0,
            "n_tickers_total": len(short_term) + len(medium_term),
            "criteria":  "ESP > 0 AND Rank ≤ 3 AND earnings within 7 days · ~70% historical beat rate",
        },
    }
    # Sanitize NaN / Infinity → None before serializing (invalid JSON otherwise)
    def _clean(o):
        import math
        if isinstance(o, float):
            return None if (math.isnan(o) or math.isinf(o)) else o
        if isinstance(o, dict):
            return {k: _clean(v) for k, v in o.items()}
        if isinstance(o, list):
            return [_clean(v) for v in o]
        return o
    # Elite Picks — already computed above (before audit_trail) so live entries
    # can be tagged with elite_score. Reuse the same result here.
    data["elite_picks"] = _elite

    # Live Options Flow — top 30 UOA imbalance candidates from
    # options_flow_scanner. Surfaced as a separate dashboard panel for
    # institutional-flow-following entry triggers.
    data["options_flow_top30"] = b.get("options_flow_top30") or []

    data = _clean(data)
    DATA.write_text(json.dumps(data, default=str, indent=0, allow_nan=False))
    print(f"wrote {DATA} ({DATA.stat().st_size:,} bytes)")

    # Tickers — rich payload for elite-detail page
    all_rich = {}
    for src in (st_rows + mt_rows):
        t = src.get("ticker")
        if not t or t in all_rich: continue
        all_rich[t] = rich_row(src, b)
        if t in short_set:
            all_rich[t]["stage"] = "SELL"
            all_rich[t]["verdict"] = "SELL"
    all_rich = _clean(all_rich)
    TICKS.write_text(json.dumps(all_rich, default=str, allow_nan=False))
    print(f"wrote {TICKS} (n={len(all_rich)} tickers, {TICKS.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
