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


def _compute_perf_1d(ticker):
    """Compute true 1-day % change from EODHD eod cache (last 2 closes).
    Cache hit since scan Step 4 already pulled it. Added 2026-05-11 — the scan
    returns 0 for pct_chg so we recompute here to populate Trending widget etc."""
    if not ticker:
        return None
    try:
        import eodhd_client as _e
        from datetime import date, timedelta
        # last 5 trading days as window — gives 2-3 closes even after weekends
        end = date.today()
        start = end - timedelta(days=7)
        bars = _e.eod(ticker, from_date=start.isoformat(), to_date=end.isoformat(), cache_ttl=43200)
        if not bars or len(bars) < 2:
            return None
        last = bars[-1].get("close") or bars[-1].get("adjusted_close")
        prev = bars[-2].get("close") or bars[-2].get("adjusted_close")
        if last and prev and prev != 0:
            return round(((last / prev) - 1) * 100, 3)
    except Exception:
        pass
    return None


def _setup_distribution_in_scan(b: dict) -> dict:
    """Count tickers per setup_family across the analyzed universe.
    Powers the Strategies tab — shows what scans are firing this run."""
    from collections import Counter
    counts = Counter()
    for sec_key in ("buy_candidates", "watch_list", "near_short_blocked"):
        for r in (b.get(sec_key) or []):
            if not isinstance(r, dict): continue
            sf = r.get("setup_family") or r.get("setup") or "Unknown"
            counts[sf] += 1
    return dict(counts.most_common())


def _cap_bucket(mkt_cap) -> str:
    """Classify market cap into screener buckets (industry-standard).
    Mega: >$200B · Large: $10-200B · Mid: $2-10B · Small: $300M-2B · Micro: <$300M.
    Returns '' if cap missing/invalid."""
    try:
        mc = float(mkt_cap) if mkt_cap else 0
    except (TypeError, ValueError):
        return ""
    if mc <= 0:           return ""
    if mc >= 200e9:       return "Mega"
    if mc >= 10e9:        return "Large"
    if mc >= 2e9:         return "Mid"
    if mc >= 300e6:       return "Small"
    return "Micro"


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


def _fetch_bonds_forex() -> dict:
    """Fetch bond ETF + forex pair real-time quotes for the Macro tab.

    2026-05-21 · uses EODHD real_time. Bond ETFs (SHY/IEF/TLT/TIP) act as
    yield-curve proxies (inverse to yields: TLT down = long yields up).
    Forex pairs (EURUSD/USDJPY/GBPUSD/USDCNH/USDCAD) for cross-asset risk
    signal. TYX.INDX = 30-year US Treasury yield (the only INDX symbol
    that returns clean data; TNX/FVX both return NA).

    Returns dict shape compatible with macro_signals: {sym: {price, chg_p, name}}.
    Failures are silently dropped (won't break bundle build).
    """
    try:
        import eodhd_client as ec
        symbols = {
            # Yield curve proxies via Treasury ETFs (inverse to yields)
            "SHY":  {"name": "1-3yr Treasury (short duration)", "category": "bond"},
            "IEF":  {"name": "7-10yr Treasury (intermediate)",  "category": "bond"},
            "TLT":  {"name": "20+yr Treasury (long duration)",  "category": "bond"},
            "TIP":  {"name": "TIPS (inflation-protected)",      "category": "bond"},
            # Forex pairs
            "EURUSD.FOREX": {"name": "EUR / USD",  "category": "forex"},
            "USDJPY.FOREX": {"name": "USD / JPY",  "category": "forex"},
            "GBPUSD.FOREX": {"name": "GBP / USD",  "category": "forex"},
            "USDCNH.FOREX": {"name": "USD / CNH",  "category": "forex"},
            "USDCAD.FOREX": {"name": "USD / CAD",  "category": "forex"},
            # 30Y Treasury yield (TYX.INDX is the only Treasury yield index
            # endpoint that returns a usable close; TNX/FVX return NA today).
            "TYX.INDX":     {"name": "US 30Y Treasury Yield (%)", "category": "rate"},
        }
        out = {}
        for sym, meta in symbols.items():
            try:
                r = ec.real_time(sym)
                d = r if isinstance(r, dict) else (r[0] if isinstance(r, list) and r else None)
                if not d:
                    continue
                close = d.get("close")
                chg_p = d.get("change_p")
                # EODHD returns "NA" string when no data — skip
                if close in (None, "NA") or close == "":
                    continue
                try:
                    close = float(close)
                except Exception:
                    continue
                try:
                    chg_p = float(chg_p) if chg_p not in (None, "NA") else None
                except Exception:
                    chg_p = None
                # Sanity guard: bond ETFs / yields / forex never move >15% in a
                # day. EODHD INDX symbols (e.g., TYX.INDX) sometimes return
                # absurd change_p like -90% due to a prev_close computation
                # bug. Null those out so the UI doesn't display garbage.
                if chg_p is not None and abs(chg_p) > 15:
                    chg_p = None
                out[sym] = {
                    "price": close,
                    "change_p": chg_p,
                    "name": meta["name"],
                    "category": meta["category"],
                }
            except Exception:
                continue
        return out
    except Exception:
        return {}


def _load_premarket() -> dict:
    """Read cache/premarket.json written by scripts/premarket_scan.py.
    Returns empty payload if missing (frontend tab falls back to market_movers).
    """
    try:
        from pathlib import Path as _P
        p = _P(__file__).parent.parent / "cache" / "premarket.json"
        if not p.exists():
            return {"_meta": {"session_active": False, "session_status": "not_initialized"}, "gappers_up": [], "gappers_dn": [], "catalysts": {}}
        import json as _j
        return _j.loads(p.read_text())
    except Exception:
        return {"_meta": {"session_active": False, "session_status": "load_error"}, "gappers_up": [], "gappers_dn": [], "catalysts": {}}


def _load_corporate_events() -> dict:
    """Read cache/corporate_events.json written by scripts/fetch_corporate_events.py.

    Returns empty shape if file missing (graceful degrade — tab will show empty
    state rather than break). 2026-05-20.
    """
    try:
        from pathlib import Path as _P
        p = _P(__file__).parent.parent / "cache" / "corporate_events.json"
        if not p.exists():
            return {"_meta": {"generated_at": None, "n_ipos": 0, "n_splits": 0}, "ipos": [], "splits": []}
        import json as _j
        return _j.loads(p.read_text())
    except Exception:
        return {"_meta": {"generated_at": None, "n_ipos": 0, "n_splits": 0}, "ipos": [], "splits": []}


def _fetch_economic_events(days_ahead: int = 30) -> list:
    """Fetch upcoming US economic events from EODHD with impact tier tagging.

    2026-05-20: widened from 14d→30d and added _impact tier (HIGH/MED/LOW) rather
    than dropping non-FOMC events. The Macro tab needs the full calendar
    context, not just rate decisions.
    """
    try:
        import eodhd_client as ec, requests, datetime
        key = ec._load_api_key()
        if not key:
            return []
        today = datetime.date.today().isoformat()
        end   = (datetime.date.today() + datetime.timedelta(days=days_ahead)).isoformat()
        url   = f'https://eodhd.com/api/economic-events?api_token={key}&fmt=json&from={today}&to={end}&limit=80&country=US'
        r = requests.get(url, timeout=8)
        if not r.ok:
            return []
        data = r.json() or []
        high_kw = ['Federal Funds', 'Interest Rate Decision', 'FOMC', 'CPI', 'Non-Farm',
                   'NFP', 'GDP', 'PCE', 'Unemployment Rate', 'Retail Sales']
        med_kw  = ['PMI', 'PPI', 'ISM', 'Initial Jobless', 'Continuing Claims',
                   'Consumer Confidence', 'Housing Starts', 'Building Permits',
                   'Durable Goods', 'Trade Balance', 'Industrial Production',
                   'Existing Home', 'New Home', 'Factory Orders', 'JOLTS']
        for e in data:
            t = e.get('type', '') or ''
            if any(kw in t for kw in high_kw):
                e['_impact'] = 'HIGH'
            elif any(kw in t for kw in med_kw):
                e['_impact'] = 'MED'
            else:
                e['_impact'] = 'LOW'
        filtered = sorted(
            [e for e in data if e.get('_impact') in ('HIGH', 'MED')],
            key=lambda x: x.get('date', '')
        )
        return filtered[:40]
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


def _compute_p0_metrics_safe(r: dict) -> dict:
    """2026-05-13 · P0 metrics for Exec Brief (Sharpe / F-score / Altman Z / ROIC / WACC).

    Reads from r['ohlcv'] (price history) + r['fundamentals'] (EODHD).
    Returns dict with each metric, None where data missing. Never raises.

    Frontend reads these as t.sharpe_1y, t.f_score, t.altman_z, t.roic, t.wacc.
    Missing fields render as "—" in Exec Brief per framework principle 1 (no fabrication).
    """
    out = {
        'sharpe_1y': None, 'sharpe_3y': None, 'volatility_1y': None,
        'max_dd_3y': None, 'calmar': None, 'sortino_1y': None,
        'f_score': None, 'altman_z': None, 'roic': None, 'wacc': None,
        'p0_data_quality': 'PARTIAL'
    }
    try:
        import math
        # ── Price-history-based: Sharpe, volatility, drawdown ─────────
        ohlcv = r.get('ohlcv')
        closes = []
        if isinstance(ohlcv, list) and ohlcv and isinstance(ohlcv[0], dict):
            closes = [float(b.get('Close') or b.get('close') or 0) for b in ohlcv if (b.get('Close') or b.get('close'))]
        elif isinstance(ohlcv, dict):
            c = ohlcv.get('close') or ohlcv.get('Close') or []
            closes = [float(x) for x in c if x]

        if len(closes) >= 60:
            # Daily log returns
            rets = []
            for i in range(1, len(closes)):
                if closes[i-1] > 0:
                    rets.append(math.log(closes[i] / closes[i-1]))
            if rets:
                # 1y window = last 252 returns (or what we have)
                rets_1y = rets[-252:]
                mu_d = sum(rets_1y) / len(rets_1y)
                var_d = sum((x - mu_d) ** 2 for x in rets_1y) / max(1, len(rets_1y) - 1)
                sigma_d = math.sqrt(var_d)
                # Annualize · risk-free ~ 4.4% (current 10Y), so daily Rf = 0.044/252
                rf_d = 0.044 / 252.0
                if sigma_d > 0:
                    sharpe_d = (mu_d - rf_d) / sigma_d
                    out['sharpe_1y'] = round(sharpe_d * math.sqrt(252), 3)
                out['volatility_1y'] = round(sigma_d * math.sqrt(252), 4)
                # Sortino: downside-only volatility
                dn = [r for r in rets_1y if r < 0]
                if dn:
                    sigma_dn = math.sqrt(sum(r ** 2 for r in dn) / len(dn))
                    if sigma_dn > 0:
                        out['sortino_1y'] = round((mu_d * math.sqrt(252) - 0.044) / (sigma_dn * math.sqrt(252)), 3)
                # 3y Sharpe if we have ≥756 days
                if len(rets) >= 600:
                    rets_3y = rets[-756:]
                    mu_3y = sum(rets_3y) / len(rets_3y)
                    var_3y = sum((x - mu_3y) ** 2 for x in rets_3y) / max(1, len(rets_3y) - 1)
                    sigma_3y = math.sqrt(var_3y)
                    if sigma_3y > 0:
                        out['sharpe_3y'] = round((mu_3y - rf_d) / sigma_3y * math.sqrt(252), 3)

            # Max drawdown (3y window)
            window = closes[-756:] if len(closes) >= 756 else closes
            peak = window[0]
            max_dd = 0.0
            for px in window:
                if px > peak: peak = px
                dd = (px - peak) / peak
                if dd < max_dd: max_dd = dd
            out['max_dd_3y'] = round(max_dd, 4)
            # Calmar: annual return / |max DD|
            if out['sharpe_3y'] is not None and out['volatility_1y'] is not None and max_dd < 0:
                ann_ret_3y = out['sharpe_3y'] * out['volatility_1y'] + 0.044
                out['calmar'] = round(ann_ret_3y / abs(max_dd), 3)

        # ── Fundamentals-based: F-score, Altman Z, ROIC, WACC ──────────
        f = r.get('fundamentals') or {}
        # EODHD enrichment may have stored this as compact dict — try both shapes
        details = f.get('details') if isinstance(f, dict) else None
        # Direct access to EODHD raw structure (when full fundamentals fetched)
        bs_q = (((f.get('Financials') or {}).get('Balance_Sheet') or {}).get('quarterly') or {}) if isinstance(f, dict) else {}
        inc_q = (((f.get('Financials') or {}).get('Income_Statement') or {}).get('quarterly') or {}) if isinstance(f, dict) else {}
        cf_q = (((f.get('Financials') or {}).get('Cash_Flow') or {}).get('quarterly') or {}) if isinstance(f, dict) else {}
        hi = f.get('Highlights') or {} if isinstance(f, dict) else {}

        # F-score (9 tests · need current + prior year)
        try:
            bs_keys = sorted(bs_q.keys(), reverse=True) if bs_q else []
            inc_keys = sorted(inc_q.keys(), reverse=True) if inc_q else []
            cf_keys = sorted(cf_q.keys(), reverse=True) if cf_q else []
            if len(bs_keys) >= 5 and len(inc_keys) >= 5:
                cur_bs = bs_q[bs_keys[0]]
                pri_bs = bs_q[bs_keys[4]]  # 4 quarters back ≈ 1 year
                cur_inc = inc_q[inc_keys[0]]
                pri_inc = inc_q[inc_keys[4]]
                cur_cf = cf_q[cf_keys[0]] if cf_keys else {}

                ni_cur = float(cur_inc.get('netIncome') or 0)
                ocf_cur = float(cur_cf.get('totalCashFromOperatingActivities') or 0)
                ta_cur = float(cur_bs.get('totalAssets') or 0)
                ta_pri = float(pri_bs.get('totalAssets') or 0)
                ltd_cur = float(cur_bs.get('longTermDebt') or 0)
                ltd_pri = float(pri_bs.get('longTermDebt') or 0)
                ca_cur = float(cur_bs.get('totalCurrentAssets') or 0)
                cl_cur = float(cur_bs.get('totalCurrentLiabilities') or 0)
                ca_pri = float(pri_bs.get('totalCurrentAssets') or 0)
                cl_pri = float(pri_bs.get('totalCurrentLiabilities') or 0)
                shares_cur = float(cur_bs.get('commonStockSharesOutstanding') or 0)
                shares_pri = float(pri_bs.get('commonStockSharesOutstanding') or 0)
                rev_cur = float(cur_inc.get('totalRevenue') or 0)
                rev_pri = float(pri_inc.get('totalRevenue') or 0)
                gp_cur = float(cur_inc.get('grossProfit') or 0)
                gp_pri = float(pri_inc.get('grossProfit') or 0)
                ni_pri = float(pri_inc.get('netIncome') or 0)

                roa_cur = ni_cur / ta_cur if ta_cur else 0
                roa_pri = ni_pri / ta_pri if ta_pri else 0
                cr_cur = ca_cur / cl_cur if cl_cur else 0
                cr_pri = ca_pri / cl_pri if cl_pri else 0
                gm_cur = gp_cur / rev_cur if rev_cur else 0
                gm_pri = gp_pri / rev_pri if rev_pri else 0
                at_cur = rev_cur / ta_cur if ta_cur else 0
                at_pri = rev_pri / ta_pri if ta_pri else 0
                ltd_ta_cur = ltd_cur / ta_cur if ta_cur else 0
                ltd_ta_pri = ltd_pri / ta_pri if ta_pri else 0

                score = 0
                if ni_cur > 0: score += 1            # 1. Positive NI
                if ocf_cur > 0: score += 1           # 2. Positive OCF
                if roa_cur > roa_pri: score += 1     # 3. ROA increasing
                if ocf_cur > ni_cur: score += 1      # 4. OCF > NI (quality)
                if ltd_ta_cur < ltd_ta_pri: score += 1  # 5. LT debt ratio down
                if cr_cur > cr_pri: score += 1       # 6. Current ratio up
                if shares_cur <= shares_pri * 1.001: score += 1  # 7. No share issuance
                if gm_cur > gm_pri: score += 1       # 8. Gross margin up
                if at_cur > at_pri: score += 1       # 9. Asset turnover up
                out['f_score'] = score
        except Exception:
            pass

        # Altman Z (manufacturing 5-factor)
        try:
            if bs_q and inc_q:
                cur_bs = bs_q[sorted(bs_q.keys(), reverse=True)[0]]
                cur_inc = inc_q[sorted(inc_q.keys(), reverse=True)[0]]
                wc = float(cur_bs.get('totalCurrentAssets') or 0) - float(cur_bs.get('totalCurrentLiabilities') or 0)
                ta = float(cur_bs.get('totalAssets') or 0)
                re = float(cur_bs.get('retainedEarnings') or 0)
                ebit = float(cur_inc.get('ebit') or cur_inc.get('operatingIncome') or 0)
                mcap = float(hi.get('MarketCapitalization') or r.get('market_cap') or 0)
                tl = float(cur_bs.get('totalLiab') or 0)
                rev = float(cur_inc.get('totalRevenue') or 0)
                if ta > 0 and tl > 0:
                    A = wc / ta
                    B = re / ta
                    C = ebit / ta
                    D = mcap / tl
                    E = rev / ta
                    z = 1.2 * A + 1.4 * B + 3.3 * C + 0.6 * D + 1.0 * E
                    out['altman_z'] = round(z, 2)
        except Exception:
            pass

        # ROIC: NOPAT / invested capital
        try:
            if inc_q and bs_q:
                cur_bs = bs_q[sorted(bs_q.keys(), reverse=True)[0]]
                # NOPAT = EBIT × (1 - tax_rate)
                cur_inc = inc_q[sorted(inc_q.keys(), reverse=True)[0]]
                ebit = float(cur_inc.get('ebit') or cur_inc.get('operatingIncome') or 0)
                tax = float(cur_inc.get('incomeTaxExpense') or 0)
                pretax = float(cur_inc.get('incomeBeforeTax') or 0)
                tax_rate = (tax / pretax) if pretax > 0 else 0.21
                nopat = ebit * (1 - tax_rate)
                # Invested capital = total debt + equity − cash
                total_debt = float(cur_bs.get('shortLongTermDebtTotal') or 0) + float(cur_bs.get('longTermDebt') or 0)
                equity = float(cur_bs.get('totalStockholderEquity') or 0)
                cash = float(cur_bs.get('cashAndShortTermInvestments') or cur_bs.get('cash') or 0)
                invested = total_debt + equity - cash
                if invested > 0 and ebit > 0:
                    out['roic'] = round(nopat / invested, 4)
        except Exception:
            pass

        # WACC: weight_e * Re + weight_d * Rd * (1 - tax_rate)
        try:
            beta = float(r.get('beta') or hi.get('Beta') or 1.0)
            mcap = float(hi.get('MarketCapitalization') or r.get('market_cap') or 0)
            if bs_q:
                cur_bs = bs_q[sorted(bs_q.keys(), reverse=True)[0]]
                total_debt = float(cur_bs.get('shortLongTermDebtTotal') or 0) + float(cur_bs.get('longTermDebt') or 0)
            else:
                total_debt = 0
            if mcap > 0:
                # CAPM: Re = Rf + β × ERP
                Rf = 0.044   # current 10Y
                ERP = 0.055  # equity risk premium · long-run avg
                Re = Rf + beta * ERP
                # Cost of debt: estimate ~5% (or interest_expense / debt if available)
                Rd = 0.05
                V = mcap + total_debt
                We = mcap / V
                Wd = total_debt / V
                tax_rate = 0.21
                wacc = We * Re + Wd * Rd * (1 - tax_rate)
                out['wacc'] = round(wacc, 4)
        except Exception:
            pass

        # Data quality flag
        wired = sum(1 for k in ['sharpe_1y','f_score','altman_z','roic','wacc'] if out.get(k) is not None)
        out['p0_data_quality'] = 'FULL' if wired == 5 else ('PARTIAL' if wired >= 3 else 'THIN')
    except Exception:
        pass
    return out


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
    """V-2: Soft regime probabilities P(Bull/Neutral/Bear) from SPY returns. Never raises.
    Routes to HMM (hmmlearn) when config.regime_classifier.use_hmm=True; else Gaussian."""
    try:
        import sys, json
        proj = OUT.parent.parent
        sys.path.insert(0, str(proj))
        import regime_hmm as rh
        import eodhd_client as _e
        from datetime import date, timedelta
        # Recent window for prediction
        rows = _e.eod("SPY", from_date=(date.today() - timedelta(days=60)).isoformat())
        if not rows or len(rows) < 22:
            return {"error": "insufficient SPY history for HMM"}
        closes = [float(r.get("adjusted_close") or r.get("close") or 0) for r in rows]
        # Load config to decide Gaussian vs HMM dispatch
        cfg = {}
        try:
            cfg_path = proj / "config" / "config.json"
            cfg = json.loads(cfg_path.read_text())
        except Exception:
            pass
        # If HMM mode, fetch longer training window
        training_closes = None
        if (cfg.get("regime_classifier") or {}).get("use_hmm"):
            try:
                long_rows = _e.eod("SPY", from_date=(date.today() - timedelta(days=2520)).isoformat())
                if long_rows and len(long_rows) >= 200:
                    training_closes = [float(r.get("adjusted_close") or r.get("close") or 0) for r in long_rows]
            except Exception:
                pass
        return rh.regime_probabilities_dispatch(closes, lookback=21,
                                                  training_closes=training_closes,
                                                  config=cfg)
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


# ────────────────────────────────────────────────────────────────────────
# Project 2 · Milestone 2.2 — Structural-target parallel fields
# ────────────────────────────────────────────────────────────────────────
# These fields are NEW and live ALONGSIDE the legacy ATR-based t1/t2 (NOT
# replacing them). Gated by config.use_structural_targets — off by default.
# When on, compact_row reads cache/target_engine/{TICKER}_{MODE}.json
# (populated by scripts/precompute_targets.py + /v2/trade_engine endpoint)
# and attaches the confluence-scored targets as parallel fields.

_STRUCTURAL_FLAG = None   # tri-state: None=unloaded, True/False=cached

def _structural_flag_enabled() -> bool:
    """Read config.use_structural_targets once · memoised at module scope."""
    global _STRUCTURAL_FLAG
    if _STRUCTURAL_FLAG is not None:
        return _STRUCTURAL_FLAG
    try:
        cfg_path = ROOT / "config" / "config.json"
        with open(cfg_path) as f:
            cfg = json.load(f)
        _STRUCTURAL_FLAG = bool(cfg.get("use_structural_targets", False))
    except Exception:
        _STRUCTURAL_FLAG = False
    return _STRUCTURAL_FLAG


def _structural_target_payload(ticker: str, mode: str):
    """Read cache/target_engine/{TICKER}_{MODE}.json · None on miss/corrupt."""
    if not ticker:
        return None
    try:
        path = ROOT / "cache" / "target_engine" / f"{ticker.upper()}_{mode}.json"
        if not path.exists():
            return None
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def _attach_structural_targets(row: dict, ticker: str) -> dict:
    """Add t1_structural / t2_structural / *_confluence / *_sources / *_behavior /
    *_p_reach as parallel fields. Reads all 3 modes' caches when present —
    swing is primary (matches dashboard Trade tab default).

    Non-destructive: never mutates row['t1'] or row['t2'] (the legacy ATR fields).
    Silent no-op when feature flag is off OR no cache file exists.
    """
    if not _structural_flag_enabled():
        return row

    all_modes: dict = {}
    for mode in ("swing", "position", "invest"):
        p = _structural_target_payload(ticker, mode)
        if p and p.get("decision") != "reject":
            all_modes[mode] = p

    if not all_modes:
        return row

    # Primary = swing (matches dashboard's Trade tab); fall back if absent
    primary_mode = "swing" if "swing" in all_modes else next(iter(all_modes))
    primary = all_modes[primary_mode]

    # target_engine §8 schema: t1 and t2 live at top-level as dicts
    # {price, confluence, sources, behavior, p_reach, r_multiple, distance_pct, action}
    t1 = primary.get("t1") if isinstance(primary.get("t1"), dict) else None
    t2 = primary.get("t2") if isinstance(primary.get("t2"), dict) else None

    def _src_types(src_list):
        """Compact list of {type, price, weight} from a t1/t2 source list."""
        out = []
        for s in (src_list or []):
            if isinstance(s, dict):
                out.append({"type": s.get("type"), "price": s.get("price"),
                            "weight": s.get("weight")})
        return out

    if t1:
        row["t1_structural"] = t1.get("price")
        row["t1_confluence"] = t1.get("confluence")
        row["t1_sources"]    = _src_types(t1.get("sources"))
        row["t1_behavior"]   = t1.get("behavior")
        # p_reach may be a scalar (target_engine §8) or a nested dict
        _pr = t1.get("p_reach")
        row["t1_p_reach"] = _pr.get("p") if isinstance(_pr, dict) else _pr
        row["t1_action"]     = t1.get("action")
        row["t1_r_multiple"] = t1.get("r_multiple")
    if t2:
        row["t2_structural"] = t2.get("price")
        row["t2_confluence"] = t2.get("confluence")
        row["t2_sources"]    = _src_types(t2.get("sources"))
        row["t2_behavior"]   = t2.get("behavior")
        _pr = t2.get("p_reach")
        row["t2_p_reach"] = _pr.get("p") if isinstance(_pr, dict) else _pr
        row["t2_action"]     = t2.get("action")
        row["t2_r_multiple"] = t2.get("r_multiple")

    # Per-mode summary for consumers that want to switch lens (Swing/Position/Invest)
    def _mode_summary(p):
        _t1 = p.get("t1") if isinstance(p.get("t1"), dict) else None
        _t2 = p.get("t2") if isinstance(p.get("t2"), dict) else None
        return {
            "t1": (_t1 or {}).get("price"),
            "t2": (_t2 or {}).get("price"),
            "decision": p.get("decision"),
        }

    row["structural_modes"] = {m: _mode_summary(p) for m, p in all_modes.items()}

    row["_te_mode_primary"] = primary_mode
    row["_te_decision"]     = primary.get("decision")
    row["_te_warnings"]     = primary.get("warnings") or []
    row["_te_cache_status"] = (primary.get("_cache") or {}).get("status")
    return row


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
    _row = {
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
        # earn_days: prefer the post-pass earnings_watchlist stamp on r (added
        # 2026-05-11); falls back to scan-side r["earnings"]["days_until"].
        "earn_days":  r.get("earn_days") if r.get("earn_days") is not None
                     else (earn.get("days_until") if isinstance(earn, dict) else None),
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
        "cap_bucket":   _cap_bucket(r.get("market_cap")),
        "week52_high":  r.get("week52_high"),
        "week52_low":   r.get("week52_low"),
        # 2026-05-25 · conviction_tier now ALWAYS recomputed from the current
        # score so it can't go stale. Previously fell back to nested
        # `conviction.label` from the original pick, which was never re-synced
        # — caused impossible labels (JBL=T2 at score 74, AAPL=WATCH at score 5).
        # Lookup mirrors analysis.py:5473 `assign_conviction_tier` post-2026-05-11
        # (score-band only — no gate dependencies — the verdict field owns gates).
        "conviction_tier": (lambda _s: (
            "T1"    if _s >= 88 else
            "T2"    if _s >= 78 else
            "T3"    if _s >= 70 else
            "WATCH" if _s >= 60 else
            "AVOID"
        ))(r.get("score") or 0),
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
        # Sharpe / Sortino / consistency surfaced for v2 dashboard column (item #2, #8, #12)
        "sharpe_126d":    r.get("sharpe_126d"),
        "sortino_126d":   r.get("sortino_126d"),
        "sharpe_consistency_verdict": (r.get("sharpe_consistency") or {}).get("verdict"),
        "sharpe_consistency_spread":  (r.get("sharpe_consistency") or {}).get("spread"),
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
        # perf_1d: scan returns 0 for pct_chg, so compute from last 2 EOD closes via
        # eodhd_client cache (cache hit — already fetched in scan Step 4). Falls back
        # to scan's pct_chg if cache miss. Added 2026-05-11.
        "perf_1d":        _compute_perf_1d(r.get("ticker") or r.get("symbol")) or r.get("pct_chg") or 0,
        "perf_1w":        (r.get("technicals") or {}).get("perf_week"),
        "insider_recent": ((r.get("insider_data") or {}).get("recent_buys") or 0) - ((r.get("insider_data") or {}).get("recent_sells") or 0),
        "insider_days":   (r.get("insider_data") or {}).get("days_since_last"),
        "short_pct":      r.get("short_float_pct") or (r.get("borrow") or {}).get("short_float_pct") or (r.get("finviz_elite") or {}).get("short_float_pct"),
        "tv_rec_str":     (r.get("tv_rating") or {}).get("recommendation") if isinstance(r.get("tv_rating"), dict) else None,
        # 2026-05-08 — Finviz Elite performance strip + squeeze flag for tile/row UI
        "finviz_elite":   r.get("finviz_elite") or {},
        "squeeze_flag":   r.get("squeeze_flag") or {"level": None, "score": 0},
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
        # 2026-05-23 · Score-modification audit trail — surfaced on detail page
        # Rule Engine sub-tab + Plan sub-tab. Lets users see WHY a score got
        # tilted/multiplied (e.g., entry_quality_score_tilt: MISSED +5 (n=369,
        # PF=1.8, Sharpe=1.5)). Without these, the post-tilt score appears
        # unexplained.
        "score_mult_audit":         r.get("score_mult_audit"),
        "entry_quality_tilt_audit": r.get("entry_quality_tilt_audit"),
        # Scan-over-scan diff (audit log panel)
        "change_log":              _compute_change_log(r, _PREV_BUNDLE_INDEX.get(r.get("ticker"), {}), _PREV_BUNDLE_DATE),
        # 2026-05-17 · SMC engine output (zones · structure · liquidity · multi-TF bars).
        # Wired by analysis.py:attach_smc_data → smc_engine.detect_smc_zones.
        "smc_data":                r.get("smc_data") or {},
        "smc_hit_rates":           r.get("smc_hit_rates") or {},
        # 2026-05-17 · pattern_engine output (Wyckoff · Classical · VP · Fib · Ichimoku · S/R · Trendlines).
        # Wired by analysis.py:attach_pattern_data → pattern_engine.detect_all_patterns.
        "pattern_data":            r.get("pattern_data") or {},
        "pattern_hit_rates":       r.get("pattern_hit_rates") or {},
    }
    # Project 2 · M2.2 — overlay structural targets when feature flag is on.
    # Silent no-op when off; legacy t1/t2 fields above remain untouched.
    return _attach_structural_targets(_row, sym)


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
        # 2026-05-21 · ticker_source from swing_trade.py universe build —
        # which tier added this ticker (sp500 / russell1000 / russell2000 /
        # sp_midcap_400 / sp_smallcap_600 / nasdaq_100 / recent_ipo /
        # post_earnings_mover / insider_cluster / congressional / etf_holding /
        # crypto_adjacent / screener_momentum / signal_200d_new_hi /
        # signal_200d_new_lo / zacks_rank1 / zacks_premium / leveraged / custom).
        "ticker_source": r.get("ticker_source") or "unknown",

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

        # 2026-05-13 · P0 metrics for Exec Brief (round 5).
        # Sharpe / Sortino / Calmar / max-DD from ohlcv history.
        # F-score / Altman Z / ROIC / WACC from EODHD fundamentals.
        # Each field defaults to None when source data is missing; frontend
        # renders "—" per framework principle 1 (no fabrication).
        **_compute_p0_metrics_safe(r),
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
        # 2026-05-11 · surface raw indicator values for Overview decision cards.
        # Previously only above_X booleans were exposed; the actual numbers
        # (ADX 27, EMA8 340.74, ATR 26.38, etc.) lived in technicals.indicators
        # but never reached tickers.json — Overview was forced to show "—".
        "adx":          (techs.get("indicators") or {}).get("adx"),
        "ema8":         (techs.get("indicators") or {}).get("ema8"),
        "ema21":        (techs.get("indicators") or {}).get("ema21"),
        "ema50":        (techs.get("indicators") or {}).get("ema50"),
        "ema200":       (techs.get("indicators") or {}).get("ema200"),
        "sma200":       (techs.get("indicators") or {}).get("sma200") or (techs.get("indicators") or {}).get("ema200"),
        "atr":          (techs.get("indicators") or {}).get("atr"),
        "macd_bullish": (techs.get("indicators") or {}).get("macd_bullish"),
        "macd_hist":    (techs.get("indicators") or {}).get("macd_hist"),
        "week52_high":  (techs.get("indicators") or {}).get("high_52w") or r.get("week52_high"),
        "week52_low":   (techs.get("indicators") or {}).get("low_52w")  or r.get("week52_low"),
        "rs_rank":      (techs.get("indicators") or {}).get("rs_rank") or r.get("rs_rank"),
        "fractal_signal": r.get("fractal_signal"),
        "fractal_high": r.get("fractal_high"),
        "fractal_low":  r.get("fractal_low"),
        "squeeze_on":   r.get("squeeze") if isinstance(r.get("squeeze"), bool) else (r.get("squeeze") or {}).get("on"),
        "squeeze":      r.get("squeeze") if isinstance(r.get("squeeze"), dict) else {"on": bool(r.get("squeeze"))},
        "bars_in_squeeze":   (r.get("indicators") or {}).get("bars_in_squeeze"),
        "squeeze_fired":     (r.get("indicators") or {}).get("squeeze_fired"),
        "squeeze_direction": (r.get("indicators") or {}).get("squeeze_direction"),
        "sqz_series_20":     (r.get("indicators") or {}).get("sqz_series_20"),
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
        "cap_bucket":   _cap_bucket(r.get("market_cap")),
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
        # 2026-05-08 — Finviz Elite enrichment (performance strip, squeeze, quality KPIs)
        "finviz_elite": r.get("finviz_elite") or {},
        "squeeze_flag": r.get("squeeze_flag") or {"level": None, "score": 0},
        # Promote a few Finviz fields to top-level for direct UI access
        "perf_week_pct":    (r.get("finviz_elite") or {}).get("perf_week_pct"),
        "perf_month_pct":   (r.get("finviz_elite") or {}).get("perf_month_pct"),
        "perf_quarter_pct": (r.get("finviz_elite") or {}).get("perf_quarter_pct"),
        "perf_half_pct":    (r.get("finviz_elite") or {}).get("perf_half_pct"),
        "perf_year_pct":    (r.get("finviz_elite") or {}).get("perf_year_pct"),
        "perf_ytd_pct":     (r.get("finviz_elite") or {}).get("perf_ytd_pct"),
        "short_float_pct":  (r.get("finviz_elite") or {}).get("short_float_pct"),
        "short_ratio":      (r.get("finviz_elite") or {}).get("short_ratio"),
        "inst_own_pct":     (r.get("finviz_elite") or {}).get("inst_own_pct") or r.get("inst_own_pct"),
        "insider_own_pct":  (r.get("finviz_elite") or {}).get("insider_own_pct"),
        "fv_roe_pct":       (r.get("finviz_elite") or {}).get("roe_pct"),
        "fv_roa_pct":       (r.get("finviz_elite") or {}).get("roa_pct"),
        "fv_gross_margin":  (r.get("finviz_elite") or {}).get("gross_margin_pct"),
        "fv_oper_margin":   (r.get("finviz_elite") or {}).get("oper_margin_pct"),
        "fv_profit_margin": (r.get("finviz_elite") or {}).get("profit_margin_pct"),
        "fv_current_ratio": (r.get("finviz_elite") or {}).get("current_ratio"),
    })
    # 2026-05-08 — Path C thesis card. Auto-generated structured thesis (4 sections:
    # score breakdown, why bullish, risks, trade plan). LLM narration optional via
    # narrate_thesis.py — pulled in if cache/thesis_narrations.json exists.
    try:
        from build_thesis import build_thesis as _bt
        # 2026-05-08 — keep "thesis" reserved for the legacy trade_thesis STRING
        # (rendered in the Overview bottom strip). The structured thesis card
        # lives on a separate key "thesis_card" so we don't shadow the string.
        base["thesis_card"] = _bt(r)
    except Exception as _bt_err:
        base["thesis_card"] = {"error": str(_bt_err)[:120]}
    return base


def _enrich_cockpit_data(data: dict) -> None:
    """Populate data.json with cockpit-only enrichments (in-place):
      • data['market_news']       — EODHD market-wide news feed (top 20)
      • data['market_movers']     — Schwab live movers across $SPX/$COMPX/$DJI
      • per-ticker news_articles  — populated on top-N scored tickers (EODHD)

    All fetches are isolated in try/except blocks — a failure on any one
    doesn't block the build or other enrichments. Cache TTLs handle re-runs.
    """
    import time

    # ── 1. Market-wide news (EODHD, single call, market feed) ──
    try:
        import eodhd_client as _eod
        rows = _eod.news(query=None, ticker=None, limit=25, cache_ttl=14400) or []
        market_news = []
        for a in rows[:20]:
            sent = a.get("sentiment") or {}
            pol = sent.get("polarity") if isinstance(sent, dict) else None
            label = "neutral"
            if isinstance(pol, (int, float)):
                label = "positive" if pol > 0.15 else ("negative" if pol < -0.15 else "neutral")
            market_news.append({
                "title": a.get("title", "")[:200],
                "source": a.get("source", "")[:60],
                "date": a.get("date", ""),
                "url": a.get("link", ""),
                "symbols": (a.get("symbols") or [])[:5],
                "sentiment": label,
                "polarity": pol,
                "_provider": "eodhd",
            })
        data["market_news"] = market_news
        print(f"  enrich: market_news ← {len(market_news)} EODHD items")
    except Exception as e:
        data["market_news"] = []
        print(f"  enrich: market_news FAILED ({e})")

    # ── 2. Schwab market movers ($SPX / $COMPX / $DJI · up + down) ──
    try:
        import schwab_client as _schwab
        movers = {"gainers": [], "losers": [], "by_index": {}, "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        seen_up = set(); seen_dn = set()
        for idx in ("$SPX", "$COMPX", "$DJI"):
            try:
                ups = _schwab.get_movers(idx, direction="up") or []
                dns = _schwab.get_movers(idx, direction="down") or []
            except Exception as ie:
                print(f"  enrich: schwab movers {idx} failed ({ie})")
                continue
            movers["by_index"][idx] = {"up": len(ups), "down": len(dns)}
            for m in ups:
                sym = m.get("symbol") or m.get("description") or ""
                if not sym or sym in seen_up: continue
                seen_up.add(sym)
                movers["gainers"].append({
                    "ticker": sym,
                    "name": m.get("description", "")[:60],
                    "price": m.get("lastPrice") or m.get("last") or 0,
                    "perf_1d": (m.get("netPercentChange") or m.get("netPercentChangeInDouble") or 0),
                    "volume": m.get("totalVolume") or 0,
                    "index": idx,
                })
            for m in dns:
                sym = m.get("symbol") or m.get("description") or ""
                if not sym or sym in seen_dn: continue
                seen_dn.add(sym)
                movers["losers"].append({
                    "ticker": sym,
                    "name": m.get("description", "")[:60],
                    "price": m.get("lastPrice") or m.get("last") or 0,
                    "perf_1d": (m.get("netPercentChange") or m.get("netPercentChangeInDouble") or 0),
                    "volume": m.get("totalVolume") or 0,
                    "index": idx,
                })
        # Sort and trim to 10 each
        movers["gainers"] = sorted(movers["gainers"], key=lambda x: -(x.get("perf_1d") or 0))[:10]
        movers["losers"]  = sorted(movers["losers"],  key=lambda x:  (x.get("perf_1d") or 0))[:10]
        data["market_movers"] = movers
        print(f"  enrich: market_movers ← {len(movers['gainers'])}G/{len(movers['losers'])}L (Schwab)")
    except Exception as e:
        data["market_movers"] = {"gainers": [], "losers": [], "error": str(e)[:120]}
        print(f"  enrich: market_movers FAILED ({e})")

    # ── 3. Options-flow enrichment: Schwab chains for top UOA tickers ──
    #     Computes per-ticker: live IV (ATM), term structure (IV by expiry),
    #     skew (25Δ put-IV − 25Δ call-IV), GEX per strike + gamma wall,
    #     refined max-pain. Stored at data['options_enriched'][ticker].
    try:
        import schwab_client as _schwab
        import time as _t
        from pathlib import Path as _P
        of = data.get("options_flow_top30") or []
        of_b = data.get("options_flow_top50") or []
        of_union = {x.get("ticker"): x for x in (of + of_b) if x.get("ticker")}
        # Top 30 by call volume — covers entire imbalance table for full IV/skew/gex columns
        top_tickers = sorted(
            list(of_union.keys()),
            key=lambda tk: -of_union[tk].get("call_volume", 0)
        )[:30]
        enriched = {}

        # ── IV history cache (rolling per-ticker per-day) ──
        IV_HIST_PATH = _P("cache/iv_history.json")
        iv_hist: dict = {}
        try:
            if IV_HIST_PATH.exists():
                iv_hist = json.loads(IV_HIST_PATH.read_text())
        except Exception:
            iv_hist = {}
        today = (data.get("run_date") or _t.strftime("%Y-%m-%d"))

        # ── Helper: 30d HV from EODHD close-price history ──
        def _compute_hv30(symbol):
            try:
                import math as _m
                from data_fetcher import fetch_market_data as _fmd
                md = _fmd([symbol], period="2mo")
                df = (md or {}).get(symbol)
                if df is None or len(df) < 22:
                    return None
                closes = list(df["Close"].tail(31).values)
                rets = []
                for i in range(1, len(closes)):
                    if closes[i-1] > 0 and closes[i] > 0:
                        rets.append(_m.log(closes[i] / closes[i-1]))
                if len(rets) < 10:
                    return None
                mean = sum(rets) / len(rets)
                var = sum((r - mean) ** 2 for r in rets) / len(rets)
                hv30 = (var ** 0.5) * (252 ** 0.5)
                return round(hv30, 4)
            except Exception:
                return None

        for tkr in top_tickers:
            try:
                ch = _schwab.get_chains(tkr, contract_type="ALL", strike_count=20, include_underlying=True)
                if not ch:
                    continue
                underlying = ch.get("underlying", {}) or {}
                spot = underlying.get("last") or underlying.get("mark") or underlying.get("regularMarketLastPrice")
                if not spot:
                    continue
                spot = float(spot)
                call_map = ch.get("callExpDateMap", {}) or {}
                put_map = ch.get("putExpDateMap", {}) or {}

                # Per-strike consolidated arrays + per-expiry buckets
                strikes_call: dict = {}   # strike -> {oi, vol, iv, delta, gamma, theta, vega, mark, bid, ask, exp, dte}
                strikes_put: dict = {}
                expiries_seen: dict = {}  # exp_date -> {dte, atm_ivs[], call_oi, put_oi, call_vol, put_vol, prem_call$, prem_put$}
                strike_oi: dict = {}      # combined OI per strike (for max-pain)
                strike_gex: dict = {}     # for gamma exposure
                strike_call_iv: dict = {}; strike_put_iv: dict = {}
                strike_call_delta: dict = {}; strike_put_delta: dict = {}
                atm_calls, atm_puts = [], []
                premium_call_total = 0.0
                premium_put_total = 0.0
                net_dealer_delta = 0.0  # Σ(call_delta × OI − put_delta × OI)

                def _to_iv(v):
                    try:
                        v = float(v)
                        return v / 100.0 if v > 5 else v
                    except Exception:
                        return None

                # Walk calls
                for exp_key, strikes in call_map.items():
                    parts = exp_key.split(":")
                    exp_date = parts[0]
                    try: dte = int(parts[1]) if len(parts) > 1 else 0
                    except Exception: dte = 0
                    exp_bucket = expiries_seen.setdefault(exp_date, {"dte": dte, "atm_ivs": [], "call_oi": 0, "put_oi": 0, "call_vol": 0, "put_vol": 0, "prem_call": 0.0, "prem_put": 0.0})
                    exp_bucket["dte"] = dte
                    for sstr, contracts in strikes.items():
                        try: strike = float(sstr)
                        except Exception: continue
                        for c in contracts:
                            iv = _to_iv(c.get("volatility"))
                            oi = int(c.get("openInterest") or 0)
                            vol = int(c.get("totalVolume") or 0)
                            gamma = float(c.get("gamma") or 0)
                            delta = float(c.get("delta") or 0)
                            theta = float(c.get("theta") or 0)
                            vega  = float(c.get("vega") or 0)
                            mark  = float(c.get("mark") or 0)
                            bid   = float(c.get("bid") or 0)
                            ask   = float(c.get("ask") or 0)
                            mid = mark if mark else ((bid + ask) / 2 if (bid and ask) else 0)
                            # Store per-strike-per-expiry record (nearest expiry wins for the ladder)
                            key = (strike, exp_date)
                            if dte <= 45 or key not in strikes_call:
                                strikes_call[strike] = {
                                    "oi": oi, "vol": vol, "iv": iv, "delta": delta, "gamma": gamma,
                                    "theta": theta, "vega": vega, "mark": mark, "bid": bid, "ask": ask,
                                    "exp": exp_date, "dte": dte,
                                }
                            if iv is not None and 0.95 <= strike/spot <= 1.05:
                                exp_bucket["atm_ivs"].append(iv)
                                if dte <= 7: atm_calls.append(iv)
                            if oi: strike_oi[strike] = strike_oi.get(strike, 0) + oi
                            if gamma and oi:
                                strike_gex[strike] = strike_gex.get(strike, 0) + (gamma * oi)
                            if iv is not None and delta:
                                strike_call_iv[strike] = iv
                                strike_call_delta[strike] = delta
                            net_dealer_delta += delta * oi
                            exp_bucket["call_oi"] += oi
                            exp_bucket["call_vol"] += vol
                            exp_bucket["prem_call"] += vol * mid * 100  # per-contract dollars
                            premium_call_total += vol * mid * 100

                # Walk puts
                for exp_key, strikes in put_map.items():
                    parts = exp_key.split(":")
                    exp_date = parts[0]
                    try: dte = int(parts[1]) if len(parts) > 1 else 0
                    except Exception: dte = 0
                    exp_bucket = expiries_seen.setdefault(exp_date, {"dte": dte, "atm_ivs": [], "call_oi": 0, "put_oi": 0, "call_vol": 0, "put_vol": 0, "prem_call": 0.0, "prem_put": 0.0})
                    for sstr, contracts in strikes.items():
                        try: strike = float(sstr)
                        except Exception: continue
                        for c in contracts:
                            iv = _to_iv(c.get("volatility"))
                            oi = int(c.get("openInterest") or 0)
                            vol = int(c.get("totalVolume") or 0)
                            gamma = float(c.get("gamma") or 0)
                            delta = float(c.get("delta") or 0)
                            theta = float(c.get("theta") or 0)
                            vega  = float(c.get("vega") or 0)
                            mark  = float(c.get("mark") or 0)
                            bid   = float(c.get("bid") or 0)
                            ask   = float(c.get("ask") or 0)
                            mid = mark if mark else ((bid + ask) / 2 if (bid and ask) else 0)
                            if dte <= 45 or strike not in strikes_put:
                                strikes_put[strike] = {
                                    "oi": oi, "vol": vol, "iv": iv, "delta": delta, "gamma": gamma,
                                    "theta": theta, "vega": vega, "mark": mark, "bid": bid, "ask": ask,
                                    "exp": exp_date, "dte": dte,
                                }
                            if iv is not None and 0.95 <= strike/spot <= 1.05 and dte <= 7:
                                atm_puts.append(iv)
                            if oi: strike_oi[strike] = strike_oi.get(strike, 0) + oi
                            if gamma and oi:
                                strike_gex[strike] = strike_gex.get(strike, 0) - (gamma * oi)
                            if iv is not None and delta:
                                strike_put_iv[strike] = iv
                                strike_put_delta[strike] = delta
                            net_dealer_delta -= abs(delta) * oi
                            exp_bucket["put_oi"] += oi
                            exp_bucket["put_vol"] += vol
                            exp_bucket["prem_put"] += vol * mid * 100
                            premium_put_total += vol * mid * 100

                # Term structure (per expiry)
                term = []
                expiries_ladder = []
                for exp_date in sorted(expiries_seen.keys()):
                    eb = expiries_seen[exp_date]
                    atm_avg = round(sum(eb["atm_ivs"]) / len(eb["atm_ivs"]), 4) if eb["atm_ivs"] else None
                    term.append({"expiry": exp_date, "dte": eb["dte"], "avg_iv": atm_avg})
                    expiries_ladder.append({
                        "expiry": exp_date,
                        "dte": eb["dte"],
                        "atm_iv": atm_avg,
                        "call_oi": eb["call_oi"],
                        "put_oi": eb["put_oi"],
                        "call_vol": eb["call_vol"],
                        "put_vol": eb["put_vol"],
                        "premium_call_dollars": round(eb["prem_call"], 0),
                        "premium_put_dollars": round(eb["prem_put"], 0),
                    })

                # Live IV (ATM blended, nearest ≤7d)
                all_atm = atm_calls + atm_puts
                live_iv = round(sum(all_atm)/len(all_atm), 4) if all_atm else None

                # Skew (25Δ)
                call_25d_strike = min(strike_call_delta.keys(), key=lambda k: abs(strike_call_delta[k] - 0.25)) if strike_call_delta else None
                put_25d_strike  = min(strike_put_delta.keys(),  key=lambda k: abs(strike_put_delta[k] - (-0.25))) if strike_put_delta else None
                call_25d_iv = strike_call_iv.get(call_25d_strike) if call_25d_strike else None
                put_25d_iv  = strike_put_iv.get(put_25d_strike) if put_25d_strike else None
                skew_val = (put_25d_iv - call_25d_iv) if (put_25d_iv is not None and call_25d_iv is not None) else None

                # Smile slope index — IV of 10Δ wings vs ATM IV
                wing_call_strike = min(strike_call_delta.keys(), key=lambda k: abs(strike_call_delta[k] - 0.10)) if strike_call_delta else None
                wing_put_strike  = min(strike_put_delta.keys(),  key=lambda k: abs(strike_put_delta[k] - (-0.10))) if strike_put_delta else None
                wing_call_iv = strike_call_iv.get(wing_call_strike) if wing_call_strike else None
                wing_put_iv  = strike_put_iv.get(wing_put_strike) if wing_put_strike else None
                wing_avg_iv = (wing_call_iv + wing_put_iv) / 2 if (wing_call_iv is not None and wing_put_iv is not None) else None
                smile_slope = (wing_avg_iv - live_iv) if (wing_avg_iv is not None and live_iv is not None) else None

                # Backwardation index: (front IV − back IV) / front IV
                term_with_iv = [t for t in term if t["avg_iv"]]
                if len(term_with_iv) >= 2:
                    front_iv = term_with_iv[0]["avg_iv"]
                    back_iv  = term_with_iv[-1]["avg_iv"]
                    backwardation = round((front_iv - back_iv) / front_iv, 4) if front_iv else None
                else:
                    backwardation = None

                # GEX
                gex_by_strike_all = sorted(strike_gex.items(), key=lambda kv: -abs(kv[1]))
                gex_by_strike = gex_by_strike_all[:8]
                wall_strike, wall_gex = (gex_by_strike[0] if gex_by_strike else (None, 0))
                wall_kind = "CALL_WALL" if wall_gex > 0 else "PUT_WALL" if wall_gex < 0 else None
                total_gex = sum(strike_gex.values())

                # Net dealer delta — $ exposure (signed)
                net_dealer_delta_dollars = round(net_dealer_delta * 100 * spot, 0)

                # Max-pain
                max_pain = max(strike_oi.items(), key=lambda kv: kv[1])[0] if strike_oi else None

                # HV-30 + IV/HV ratio
                hv30 = _compute_hv30(tkr)
                iv_hv_ratio = round((live_iv / hv30), 3) if (live_iv and hv30) else None

                # IV history append (rolling)
                if live_iv is not None:
                    hist = iv_hist.setdefault(tkr, [])
                    # remove existing entry for today if present, then append
                    hist = [h for h in hist if h.get("date") != today]
                    hist.append({"date": today, "iv": round(live_iv, 4)})
                    # cap at last 260 entries (~52 weeks of daily)
                    iv_hist[tkr] = hist[-260:]

                # IV rank vs trailing 52w
                iv_rank = None
                iv_history_series = iv_hist.get(tkr, [])
                if len(iv_history_series) >= 5 and live_iv is not None:
                    ivs_hist = [h["iv"] for h in iv_history_series if h.get("iv") is not None]
                    if ivs_hist:
                        below = sum(1 for v in ivs_hist if v <= live_iv)
                        iv_rank = round(below / len(ivs_hist) * 100, 1)

                # ── Item #6 · Charm + Vanna — proper Black-Scholes-style approximations ──
                # Charm = dΔ/dt — daily delta decay. BS: charm ≈ -e^(-qT) [N'(d1)(2(r-q)T - d2*σ√T)/(2T·σ√T) - q*N(d1)]
                # Vanna = dΔ/dσ — delta sensitivity to vol. BS: vanna ≈ -e^(-qT) N'(d1) * d2/σ
                # Practical: derive from existing greeks: vanna ≈ vega * delta / (S·σ·√T·100), charm ≈ -theta * delta / mark
                # Aggregate exposures × OI × 100 multiplier for $ exposure
                import math as _m
                charm_dollar = 0.0   # net charm $ exposure (delta-decay per day, in $ terms)
                vanna_dollar = 0.0   # net vanna $ exposure (delta change per 1% IV move)
                def _greek_exposures(contracts, is_put):
                    nonlocal charm_dollar, vanna_dollar
                    for c in contracts.values():
                        oi = c.get("oi") or 0
                        if oi == 0: continue
                        sigma = c.get("iv")
                        T = c.get("dte", 0) / 365.0
                        delta = c.get("delta", 0)
                        vega = c.get("vega", 0)
                        theta = c.get("theta", 0)
                        if sigma is None or sigma <= 0 or T <= 0: continue
                        # Vanna ≈ vega × delta / (S × σ × √T) — $ delta change per 1% σ move
                        try:
                            vanna_proxy = vega * delta / (spot * sigma * _m.sqrt(T))
                            sign = -1 if is_put else 1
                            vanna_dollar += sign * vanna_proxy * oi * 100 * spot * 0.01
                        except Exception: pass
                        # Charm ≈ theta × delta / mark (delta decay per day, $ per share)
                        mark = c.get("mark") or 0
                        if mark > 0:
                            charm_proxy = theta * delta / mark
                            charm_dollar += charm_proxy * oi * 100

                _greek_exposures(strikes_call, False)
                _greek_exposures(strikes_put, True)

                # ── Item #4 · Earnings IV crush forecast — sector-aware + IV-bucket-aware ──
                # Strategy: combine historical sector volatility with current IV level.
                # Biotech/small-tech crush hardest; large-cap diversified crush least.
                crush_pct_est = None
                # Find ticker sector
                tkr_sec = None
                for src in (of, of_b):
                    for row in src:
                        if row.get("ticker") == tkr:
                            tkr_sec = row.get("sector"); break
                    if tkr_sec: break
                # Sector base crush multipliers (empirical industry averages post-earnings)
                SECTOR_CRUSH = {
                    "Healthcare": 1.35,  # biotech volatility crushes hard
                    "Technology": 1.15,
                    "Consumer Cyclical": 1.10,
                    "Communication Services": 1.05,
                    "Industrials": 1.00,
                    "Energy": 0.95,
                    "Financial Services": 0.85,
                    "Consumer Defensive": 0.80,
                    "Utilities": 0.70,
                    "Real Estate": 0.75,
                    "Basic Materials": 0.95,
                }
                sec_mult = SECTOR_CRUSH.get(tkr_sec, 1.0)
                # IV-level base: rule-of-thumb crushes
                if live_iv is not None:
                    if live_iv > 0.8:     base_crush = 45
                    elif live_iv > 0.6:   base_crush = 38
                    elif live_iv > 0.45:  base_crush = 30
                    elif live_iv > 0.30:  base_crush = 22
                    elif live_iv > 0.20:  base_crush = 16
                    else:                 base_crush = 10
                    # Adjust by backwardation: if front-month IV >> back, earnings is priced in
                    if backwardation is not None and backwardation > 0.10:
                        base_crush = int(base_crush * 1.25)  # more crush expected
                    crush_pct_est = max(5, min(60, int(round(base_crush * sec_mult))))

                # ── Item #10 · Per-expiry smile data for proper smile chart ──
                # Build a strike-IV array for the NEAREST expiry only — gives a clean smile curve
                smile_per_expiry = {}  # exp_date -> [{strike, call_iv, put_iv}]
                for exp_key, strikes in call_map.items():
                    exp_date = exp_key.split(":")[0]
                    if exp_date not in smile_per_expiry:
                        smile_per_expiry[exp_date] = {}
                    for sstr, contracts in strikes.items():
                        try: strike = float(sstr)
                        except Exception: continue
                        for c in contracts:
                            v = _to_iv(c.get("volatility"))
                            if v is not None:
                                if strike not in smile_per_expiry[exp_date]:
                                    smile_per_expiry[exp_date][strike] = {}
                                smile_per_expiry[exp_date][strike]["call_iv"] = v
                for exp_key, strikes in put_map.items():
                    exp_date = exp_key.split(":")[0]
                    if exp_date not in smile_per_expiry: continue
                    for sstr, contracts in strikes.items():
                        try: strike = float(sstr)
                        except Exception: continue
                        for c in contracts:
                            v = _to_iv(c.get("volatility"))
                            if v is not None:
                                if strike not in smile_per_expiry[exp_date]:
                                    smile_per_expiry[exp_date][strike] = {}
                                smile_per_expiry[exp_date][strike]["put_iv"] = v
                # Convert to nearest-expiry sorted strikes array (the smile curve)
                nearest_exp = sorted(expiries_seen.keys())[0] if expiries_seen else None
                smile_curve = []
                if nearest_exp and nearest_exp in smile_per_expiry:
                    for s in sorted(smile_per_expiry[nearest_exp].keys()):
                        ivs = smile_per_expiry[nearest_exp][s]
                        # blend if both exist, else take whichever is present
                        c_iv, p_iv = ivs.get("call_iv"), ivs.get("put_iv")
                        if c_iv is not None and p_iv is not None:
                            blended = (c_iv + p_iv) / 2
                        else:
                            blended = c_iv if c_iv is not None else p_iv
                        if blended is not None:
                            smile_curve.append({"strike": s, "iv": round(blended, 4),
                                                "call_iv": c_iv, "put_iv": p_iv})

                # ── Item #9 · Volatility surface — strike × expiry grid with nearest-neighbor backfill ──
                surface = {"strikes": [], "expiries": [], "grid": []}
                strike_set_all = sorted(set(list(strikes_call.keys()) + list(strikes_put.keys())))
                # Pick strikes within ATM ± 25% for the surface (avoids far-OTM IV outliers)
                strike_set = [s for s in strike_set_all if 0.75 <= s/spot <= 1.25]
                if len(strike_set) < 5:
                    strike_set = strike_set_all  # fallback
                # Cap at 21 strikes centered on ATM
                if len(strike_set) > 21:
                    atm_idx = min(range(len(strike_set)), key=lambda i: abs(strike_set[i] - spot))
                    half = 10
                    lo_i = max(0, atm_idx - half)
                    hi_i = min(len(strike_set), lo_i + 21)
                    lo_i = max(0, hi_i - 21)
                    strike_set = strike_set[lo_i:hi_i]
                exp_set = sorted(expiries_seen.keys())[:6]
                surface["strikes"] = strike_set
                surface["expiries"] = exp_set
                # Walk per-expiry data we already built
                raw_grid = {}
                for exp_date in exp_set:
                    if exp_date not in smile_per_expiry: continue
                    for s, ivs in smile_per_expiry[exp_date].items():
                        c_iv, p_iv = ivs.get("call_iv"), ivs.get("put_iv")
                        blended = ((c_iv or 0) + (p_iv or 0)) / max(1, sum(1 for x in [c_iv, p_iv] if x is not None))
                        if c_iv is None and p_iv is None: continue
                        raw_grid[(s, exp_date)] = blended

                # Nearest-neighbor backfill on the strike axis
                # For each (strike, expiry) cell with no data, find nearest strike in same expiry that has data
                filled_grid = {}
                for s in strike_set:
                    for e in exp_set:
                        if (s, e) in raw_grid:
                            filled_grid[(s, e)] = raw_grid[(s, e)]
                        else:
                            # Find nearest neighbor in same expiry
                            candidates_e = [(abs(s2 - s), v) for (s2, e2), v in raw_grid.items() if e2 == e]
                            if candidates_e:
                                candidates_e.sort()
                                # Use nearest neighbor only if within 15% of strike
                                if candidates_e[0][0] / max(s, 0.01) < 0.15:
                                    filled_grid[(s, e)] = candidates_e[0][1]
                                else:
                                    filled_grid[(s, e)] = None
                            else:
                                filled_grid[(s, e)] = None
                surface["grid"] = [
                    [filled_grid.get((s, e)) for e in exp_set]
                    for s in strike_set
                ]

                # Chain ladder rows — ATM-bias 15 strikes
                ladder_strikes = sorted([s for s in strike_set if 0.85 <= s/spot <= 1.15])
                # If too few, just take all strike_set ±10 around ATM
                if len(ladder_strikes) < 8:
                    ladder_strikes = sorted(strike_set, key=lambda x: abs(x - spot))[:15]
                    ladder_strikes.sort()
                ladder = []
                for s in ladder_strikes:
                    c = strikes_call.get(s, {})
                    p = strikes_put.get(s, {})
                    call_uoa = bool(c.get("oi", 0) > 100 and c.get("vol", 0) > c.get("oi", 0) * 3)
                    put_uoa  = bool(p.get("oi", 0) > 100 and p.get("vol", 0) > p.get("oi", 0) * 3)
                    ladder.append({
                        "strike": s,
                        "atm": abs(s - spot) / spot < 0.025,
                        "call": {"oi": c.get("oi", 0), "vol": c.get("vol", 0), "iv": c.get("iv"), "delta": c.get("delta"), "gamma": c.get("gamma"), "mark": c.get("mark"), "uoa": call_uoa},
                        "put":  {"oi": p.get("oi", 0), "vol": p.get("vol", 0), "iv": p.get("iv"), "delta": p.get("delta"), "gamma": p.get("gamma"), "mark": p.get("mark"), "uoa": put_uoa},
                    })

                # OI profile + volume profile — strike-level summary
                profile = []
                for s in sorted(strike_set):
                    c = strikes_call.get(s, {})
                    p = strikes_put.get(s, {})
                    profile.append({
                        "strike": s,
                        "call_oi": c.get("oi", 0),
                        "put_oi": p.get("oi", 0),
                        "call_vol": c.get("vol", 0),
                        "put_vol": p.get("vol", 0),
                    })

                # Greeks curves — for charting
                greeks_curve = []
                for s in sorted(strike_set):
                    c = strikes_call.get(s, {})
                    p = strikes_put.get(s, {})
                    greeks_curve.append({
                        "strike": s,
                        "call_delta": c.get("delta"),
                        "call_gamma": c.get("gamma"),
                        "call_vega": c.get("vega"),
                        "put_delta": p.get("delta"),
                        "put_gamma": p.get("gamma"),
                        "put_vega": p.get("vega"),
                    })

                enriched[tkr] = {
                    "spot": round(spot, 2),
                    "live_iv": live_iv,
                    "live_iv_pct": round(live_iv * 100, 1) if live_iv else None,
                    "hv30": hv30,
                    "hv30_pct": round(hv30 * 100, 1) if hv30 else None,
                    "iv_hv_ratio": iv_hv_ratio,
                    "iv_rank": iv_rank,
                    "iv_history": iv_history_series,
                    "term_structure": term,
                    "backwardation_index": backwardation,
                    "skew": {
                        "call_25d_iv": call_25d_iv,
                        "put_25d_iv": put_25d_iv,
                        "call_25d_strike": call_25d_strike,
                        "put_25d_strike": put_25d_strike,
                        "value": round(skew_val, 4) if skew_val is not None else None,
                        "smile_slope": round(smile_slope, 4) if smile_slope is not None else None,
                        "wing_call_iv": wing_call_iv,
                        "wing_put_iv": wing_put_iv,
                    },
                    "gex": {
                        "by_strike": [{"strike": s, "gex": round(g * 100 * (spot ** 2) / 1e9, 3)} for s, g in gex_by_strike],
                        "all_strikes": [{"strike": s, "gex": round(g * 100 * (spot ** 2) / 1e9, 3)} for s, g in sorted(gex_by_strike_all, key=lambda kv: kv[0])],
                        "wall_strike": wall_strike,
                        "wall_kind": wall_kind,
                        "total_gex_b": round(total_gex * 100 * (spot ** 2) / 1e9, 3) if total_gex else 0,
                    },
                    "max_pain": max_pain,
                    "net_dealer_delta": net_dealer_delta_dollars,
                    "premium_flow": {
                        "call_dollars": round(premium_call_total, 0),
                        "put_dollars": round(premium_put_total, 0),
                        "net_dollars": round(premium_call_total - premium_put_total, 0),
                    },
                    "ladder": ladder,
                    "profile": profile,
                    "greeks_curve": greeks_curve,
                    "expiries": expiries_ladder,
                    "surface": surface,
                    "smile_curve": smile_curve,      # NEW (#10) — nearest-expiry strike-IV array for clean smile chart
                    "charm_dollar": round(charm_dollar, 0),  # NEW (#6) — $ delta decay per day
                    "vanna_dollar": round(vanna_dollar, 0),  # NEW (#6) — $ delta change per 1% σ
                    "crush_pct_est": crush_pct_est,  # IMPROVED (#4) — sector-aware
                    "fetched_at": _t.strftime("%Y-%m-%dT%H:%M:%S"),
                }
                _t.sleep(0.15)
            except Exception as ie:
                print(f"  enrich: chain({tkr}) failed ({ie})")
                continue
        data["options_enriched"] = enriched

        # Persist IV history cache
        try:
            IV_HIST_PATH.parent.mkdir(parents=True, exist_ok=True)
            IV_HIST_PATH.write_text(json.dumps(iv_hist, separators=(",", ":")))
        except Exception as _ihe:
            print(f"  enrich: iv_history cache write failed ({_ihe})")

        # ── Sector peers — for each enriched ticker, identify same-sector tickers ──
        sector_map: dict = {}
        for tk, e in enriched.items():
            sec = None
            for src in (of, of_b):
                for row in src:
                    if row.get("ticker") == tk:
                        sec = row.get("sector"); break
                if sec: break
            if sec: sector_map.setdefault(sec, []).append(tk)
        for tk, e in enriched.items():
            sec = None
            for src in (of, of_b):
                for row in src:
                    if row.get("ticker") == tk:
                        sec = row.get("sector"); break
                if sec: break
            if not sec: continue
            peers = [p for p in sector_map.get(sec, []) if p != tk][:5]
            e["sector_peers"] = [
                {
                    "ticker": p,
                    "iv_pct": enriched[p].get("live_iv_pct"),
                    "iv_rank": enriched[p].get("iv_rank"),
                    "skew": enriched[p].get("skew", {}).get("value"),
                    "iv_hv": enriched[p].get("iv_hv_ratio"),
                } for p in peers
            ]
            e["sector"] = sec
        print(f"  enrich: options_enriched ← {len(enriched)} tickers (Schwab chains; full vol surface)")

        # Backfill iv_percentile / gamma_net into options_flow_top30 from enriched
        for row in (of + of_b):
            tk = row.get("ticker")
            if tk in enriched:
                e = enriched[tk]
                if row.get("iv_percentile") is None and e.get("live_iv_pct") is not None:
                    row["live_iv_pct"] = e["live_iv_pct"]
                if row.get("gamma_net") is None and e.get("gex", {}).get("total_gex_b") is not None:
                    row["gamma_net"] = e["gex"]["total_gex_b"]
                if e.get("skew", {}).get("value") is not None:
                    row["skew_25d"] = e["skew"]["value"]
    except Exception as e:
        data["options_enriched"] = {}
        print(f"  enrich: options chains FAILED ({e})")

    # ── 4. Per-ticker news on top-N scored tickers (EODHD, 4h cache) ──
    try:
        import data_fetcher as _df
        # Build candidate list: union of top 10 per mode by elite_score
        candidates = set()
        ep = data.get("elite_picks", {}) or {}
        for mode in ("Swing", "Position", "Invest"):
            for stage in ("BUY", "WATCH"):
                arr = (ep.get(mode, {}) or {}).get(stage, []) or []
                for p in sorted(arr, key=lambda x: -(x.get("elite_score") or 0))[:5]:
                    if p.get("ticker"): candidates.add(p["ticker"])
        # Also include top 10 of long_term scan by score
        for t in sorted((data.get("long_term") or []), key=lambda x: -(x.get("score") or 0))[:10]:
            if t.get("ticker"): candidates.add(t["ticker"])
        candidates = sorted(candidates)[:50]  # cap at 50 — covers full top-50 UOA + elite picks

        # Build a per-ticker news map then sprinkle into the section records
        news_by_ticker: dict[str, list] = {}
        for tkr in candidates:
            try:
                arts = _df.get_news_articles(tkr, limit=5) or []
                if arts:
                    news_by_ticker[tkr] = [
                        {
                            "title": a.get("title", "")[:200],
                            "source": a.get("source") or (a.get("publisher", {}) or {}).get("name", ""),
                            "date": a.get("published_utc", ""),
                            "url": a.get("url", ""),
                            "sentiment": (a.get("insights") or [{}])[0].get("sentiment", "neutral"),
                        }
                        for a in arts[:4]
                    ]
            except Exception:
                continue
        # Inject into section records (long/medium/short_term + elite_picks)
        for section_key in ("long_term", "medium_term", "short_term"):
            for r in (data.get(section_key) or []):
                if not isinstance(r, dict): continue
                t = r.get("ticker")
                if t in news_by_ticker:
                    r["news_articles"] = news_by_ticker[t]
        data["_news_top_tickers"] = list(news_by_ticker.keys())
        print(f"  enrich: per-ticker news ← {len(news_by_ticker)} tickers with articles")
    except Exception as e:
        print(f"  enrich: per-ticker news FAILED ({e})")


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

    # Top-N for Scanner tab. Show actionable signals only:
    # BUY (long entry), WATCH (forming setup), SELL/SHORT (bear entry).
    # AVOID/KILLED rows live ONLY in the dedicated Killed tab.
    # Source pool = all_scored UNION near_short_blocked. SHORT signals
    # don't appear in all_scored (separate list from bear-setup detection)
    # and tend to score lower than long WATCH rows, so they'd never make
    # the top-50 by score. Reserve up to 10 slots for SHORT signals, then
    # fill the rest with top-scoring longs (BUY/WATCH).
    _actionable_stages = {"BUY", "WATCH", "WAIT", "ADD", "SELL", "SHORT"}
    _short_pool = b.get("near_short_blocked") or []
    _short_set = {(r.get("ticker") or "") for r in _short_pool}
    _SHORT_SLOT_CAP = 10

    # SHORT slots first
    _shorts_sorted = sorted(_short_pool, key=lambda r: r.get("score", 0) or 0, reverse=True)
    _short_picks = [r for r in _shorts_sorted if r.get("ticker")][:_SHORT_SLOT_CAP]
    _picked_tickers = {r.get("ticker") for r in _short_picks}

    # Remaining slots → top-scoring longs (BUY/WATCH/etc.) from all_scored,
    # excluding any ticker already picked as a SHORT.
    _remaining = 50 - len(_short_picks)
    _longs_sorted = sorted(b.get("all_scored") or [],
                           key=lambda r: r.get("score", 0) or 0, reverse=True)
    _long_picks = []
    for r in _longs_sorted:
        t = r.get("ticker")
        if not t or t in _picked_tickers:
            continue
        if stage_of(r) not in _actionable_stages:
            continue
        _long_picks.append(r)
        _picked_tickers.add(t)
        if len(_long_picks) >= _remaining:
            break

    _scanner_pool = _short_picks + _long_picks
    screener_rows = [compact_row(r) for r in _scanner_pool]
    # Force SELL on near_short tickers (mirror short_term logic above)
    for cr in screener_rows:
        if cr.get("ticker") in _short_set:
            cr["stage"] = "SELL"

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
    # Phase B.1 (2026-05-09): route through state_layer for cache + future Mode 2.
    portfolio = {"positions": [], "closed": [], "equity": None, "cash": None,
                 "monthly_pnl": {}, "equity_curve": []}
    try:
        import sys
        sys.path.insert(0, str(ROOT))
        from state_layer import load_portfolio_state
        ps = load_portfolio_state()
    except Exception:
        ps = json.loads(PORTFOLIO.read_text()) if PORTFOLIO.exists() else {}
    if ps:
        try:
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
    # Phase B.1 (2026-05-09): route through state_layer for cache.
    sl: list = []
    try:
        import sys as _sys
        _sys.path.insert(0, str(ROOT))
        from state_layer import load_signal_log
        sl = load_signal_log()
    except Exception:
        if SIGNAL_LOG.exists():
            try:
                sl = json.loads(SIGNAL_LOG.read_text())
            except Exception:
                sl = []
    if sl:
        try:
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
        # 2026-05-21 · bonds + forex for Macro tab enhancement (yield curve
        # proxies via SHY/IEF/TLT/TIP ETFs + EURUSD/USDJPY/GBPUSD/USDCNH/USDCAD
        # + TYX 30Y yield). Live from EODHD real_time.
        "bonds_forex": _fetch_bonds_forex(),
        # 2026-05-21 · universe composition breakdown by ticker_source —
        # surfaced in System Status tab so user can see which tier added
        # which slice of the scanned universe.
        "universe_composition": (lambda ts: {
            "total": len(ts),
            "by_source": dict(__import__('collections').Counter(ts.values()).most_common()),
            "generated_at": b.get("run_timestamp", ""),
        })(b.get("ticker_sources") or {}),
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
        # Corporate events (IPOs + splits) — populated by scripts/fetch_corporate_events.py
        # which writes cache/corporate_events.json. Read at bundle-build time.
        "corporate_events": _load_corporate_events(),
        # Pre-market scanner output — populated by scripts/premarket_scan.py
        # which runs every 30min during 4am-9:30am ET on weekdays. Out-of-session
        # this returns the last session's data + a session_active=false flag.
        "premarket": _load_premarket(),
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
    # 2026-05-11: bundle is only refreshed during scans (4×/day), but the
    # options-flow scanner runs every 30m in market hours and writes to
    # infra/prototype/options_flow.json independently. Read that file
    # directly so fresh UOA shows up between scans.
    # 2026-05-13: previous len-greater-than check failed when the bundle
    # was empty (0 == 0 stays 0). Now we prefer disk whenever:
    #   (a) bundle is empty, OR
    #   (b) disk has more candidates than bundle, OR
    #   (c) disk has a newer refreshed_at than the bundle's run_timestamp.
    # The QuantOptions dashboard tab ALSO fetches options_flow.json directly
    # client-side, so the dashboard is robust even if this step misfires.
    _of_bundle = b.get("options_flow_top30") or []
    _of_top50_bundle = b.get("options_flow_top50") or []
    _of_refreshed_at = None
    try:
        _of_path = OUT / "options_flow.json"
        if _of_path.exists():
            _of_disk = json.loads(_of_path.read_text())
            _of_top30 = _of_disk.get("top30") or _of_disk.get("candidates") or []
            _of_top50 = _of_disk.get("top50") or _of_top30
            _of_refreshed_at = _of_disk.get("refreshed_at")
            if isinstance(_of_top30, list):
                # Compare disk freshness vs bundle scan timestamp.
                _bundle_ts = (b.get("run_timestamp") or "").strip()
                _disk_newer = bool(_of_refreshed_at and _bundle_ts and _of_refreshed_at > _bundle_ts)
                if len(_of_bundle) == 0 or len(_of_top30) > len(_of_bundle) or _disk_newer:
                    _of_bundle = _of_top30
                    _of_top50_bundle = _of_top50 if isinstance(_of_top50, list) else _of_top30
                    print(f"[options_flow] using standalone file ({len(_of_top30)} candidates, refreshed {_of_refreshed_at or '—'})")
                else:
                    print(f"[options_flow] keeping bundle ({len(_of_bundle)} candidates · disk has {len(_of_top30)})")
    except Exception as _of_err:
        print(f"[options_flow] standalone fallback skipped: {_of_err}")
    data["options_flow_top30"] = _of_bundle
    data["options_flow_top50"] = _of_top50_bundle or _of_bundle or []
    # Propagate the actual refresh timestamp so the dashboard freshness pill
    # reflects the truth (not just the broader scan time).
    if _of_refreshed_at:
        data["options_flow_refreshed_at"] = _of_refreshed_at

    # Crypto scan — bundle.crypto contains BTC/ETH/SOL/etc scored through
    # the same gate cascade. Surface to V2 Crypto tab.
    data["crypto"] = b.get("crypto") or {}

    # Strategies — surface setup-family stats so the Strategies tab can
    # show per-strategy hit rate / which scans are firing today.
    data["strategies"] = {
        "setup_stats": b.get("setup_stats") or {},
        "by_setup_in_scan": _setup_distribution_in_scan(b),
    }

    # 2026-05-09 — research_setup_stats: per-setup historical performance from
    # the most-recent portfolio backtest. Powers the Research tab's rigor +
    # decay sub-tabs on elite-detail (replaces previous hard-coded literals).
    # Source: cache/portfolio_backtest.json (auto-written by backtest.py).
    try:
        import math as _math
        bt_path = ROOT / "cache" / "portfolio_backtest.json"
        if bt_path.exists():
            bt = json.loads(bt_path.read_text())
            trades = bt.get("trades") or []
            # Per-setup aggregate
            from collections import defaultdict as _dd
            by_setup = _dd(list)
            for t in trades:
                s = t.get("setup_type") or "?"
                by_setup[s].append(t)
            setup_metrics = {}
            def _wilson_lb(wins, n, z=1.96):
                if n == 0: return 0.0
                p = wins / n
                denom = 1 + z*z/n
                centre = p + z*z/(2*n)
                spread = z * _math.sqrt((p*(1-p) + z*z/(4*n)) / n)
                return max(0.0, (centre - spread) / denom)
            for setup, items in by_setup.items():
                n = len(items)
                wins = sum(1 for t in items if t.get("win"))
                wr = (wins / n) * 100 if n else 0
                wr_lb = _wilson_lb(wins, n) * 100
                pnls = [t.get("pnl_pct", 0) for t in items]
                avg = sum(pnls) / n if n else 0
                # Quartile WR (chronological partition)
                trades_sorted = sorted(items, key=lambda x: x.get("entry_date", ""))
                q_size = max(1, n // 4)
                q_wrs = []
                for qi in range(4):
                    start = qi * q_size
                    end = start + q_size if qi < 3 else n
                    sub = trades_sorted[start:end]
                    if len(sub) >= 2:
                        q_wins = sum(1 for t in sub if t.get("win"))
                        q_wrs.append({"q": f"Q{qi+1}", "wr": round(q_wins / len(sub) * 100, 1), "n": len(sub)})
                    else:
                        q_wrs.append({"q": f"Q{qi+1}", "wr": None, "n": len(sub)})
                # Verdict
                if wr_lb >= 30 and avg > 0.5:
                    verdict = "real edge (CI > 30%)"
                elif wr_lb >= 15:
                    verdict = "marginal — CI low"
                elif n < 10:
                    verdict = "sample too small"
                elif avg < -0.5:
                    verdict = "killed (negative expectancy)"
                else:
                    verdict = "below edge threshold"
                setup_metrics[setup] = {
                    "n": n,
                    "wr": round(wr, 1),
                    "wr_lb": round(wr_lb, 1),
                    "avg_pnl_pct": round(avg, 2),
                    "verdict": verdict,
                    "quartiles": q_wrs,
                }
            data["research_setup_stats"] = setup_metrics
            data["research_backtest_meta"] = {
                "source": "cache/portfolio_backtest.json",
                "n_trades": len(trades),
                "generated_at": bt.get("generated_at") or "",
                "config": bt.get("config") or {},
            }
    except Exception as _rs_err:
        data["research_setup_stats"] = {}
        data["research_backtest_meta"] = {"error": str(_rs_err)[:200]}

    # Leveraged ETFs — score the watchlist tickers from config that made
    # it through the scan. Surface as a tactical-leverage tab.
    _bundle_cfg = b.get("config") or {}
    _lev_set = set(((_bundle_cfg.get("universe") or {}).get("leveraged_watchlist") or []))
    _lev_picks = []
    for sec_key, sec_val in b.items():
        if not (isinstance(sec_val, list) and sec_val
                and isinstance(sec_val[0], dict) and "ticker" in sec_val[0]):
            continue
        for r in sec_val:
            t = (r.get("ticker") or "").upper()
            if t in _lev_set:
                _lev_picks.append({
                    "ticker":   t,
                    "price":    r.get("price"),
                    "score":    r.get("score") or r.get("composite_score"),
                    # 2026-05-25 · Anti-stale: prefer the freshly-scanned top-level
                    # `verdict`. Only fall back to nested `decision.verdict` when the
                    # top-level field is genuinely missing (legacy rows). `stage` is
                    # a lifecycle marker that may carry over from prior runs — drop it
                    # from the fallback chain.
                    "verdict":  r.get("verdict") or (r.get("decision") or {}).get("verdict"),
                    "setup":    r.get("setup_family") or r.get("setup"),
                    "sector":   r.get("sector"),
                    "rs_rank":  r.get("rs_rank"),
                    "trade_plan": r.get("trade_plan") or {},
                })
    # Dedupe (same ticker may appear in multiple sections)
    _seen = set(); _dedup = []
    for p in sorted(_lev_picks, key=lambda x: -(x.get("score") or 0)):
        if p["ticker"] in _seen: continue
        _seen.add(p["ticker"]); _dedup.append(p)
    data["leveraged"] = {
        "watchlist": sorted(_lev_set),
        "picks":     _dedup,
        "in_scan":   len(_dedup),
        "total":     len(_lev_set),
    }

    # Earnings playbook — 1840+ US tickers reporting in next 10 days.
    # Built daily 5:30am PT by build_earnings_watchlist.py. The dashboard
    # Earnings tab sorts by days_to_earnings; cross-references with the
    # ticker payload (5d runup, sector, in-portfolio flag).
    try:
        _ew_path = Path(__file__).resolve().parent.parent.parent / "data" / "earnings_watchlist.json"
        if _ew_path.exists():
            _ew = json.loads(_ew_path.read_text())
            data["earnings_watchlist"] = _ew.get("watchlist") or []
            data["earnings_watchlist_meta"] = {
                "generated_at": _ew.get("generated_at"),
                "from_date":    _ew.get("from_date"),
                "to_date":      _ew.get("to_date"),
                "total_us":     _ew.get("total_us"),
                "window_days":  _ew.get("window_days"),
            }
            # Earnings outcomes — last 30 days of BEAT/MISS/INLINE
            _eo_path = _ew_path.parent / "earnings_outcomes.jsonl"
            outcomes_recent = []
            if _eo_path.exists():
                from datetime import datetime as _dt, timedelta as _td
                _cutoff = (_dt.now() - _td(days=30)).strftime("%Y-%m-%d")
                for _line in _eo_path.read_text().splitlines():
                    _line = _line.strip()
                    if not _line: continue
                    try:
                        _e = json.loads(_line)
                        if (_e.get("report_date") or "") >= _cutoff:
                            outcomes_recent.append(_e)
                    except Exception:
                        continue
            data["earnings_outcomes_30d"] = outcomes_recent
        else:
            data["earnings_watchlist"] = []
            data["earnings_watchlist_meta"] = {}
            data["earnings_outcomes_30d"] = []
    except Exception as _ew_err:
        print(f"[earnings_watchlist] non-fatal: {_ew_err}")
        data["earnings_watchlist"] = []
        data["earnings_outcomes_30d"] = []

    # Earnings beat predictions (#6 INOD-class) — composite 0-100 score
    # per upcoming-earnings ticker. Built daily by predict_earnings_beats.py.
    try:
        _bp_path = Path(__file__).resolve().parent.parent.parent / "data" / "earnings_beat_predictions.json"
        if _bp_path.exists():
            _bp = json.loads(_bp_path.read_text())
            data["earnings_beat_predictions"] = _bp.get("predictions") or []
            data["earnings_per_tier_calibration"] = _bp.get("per_tier_calibration") or {"tiers": []}
        else:
            data["earnings_beat_predictions"] = []
            data["earnings_per_tier_calibration"] = {"tiers": []}
    except Exception as _bp_err:
        print(f"[earnings_beat_predictions] non-fatal: {_bp_err}")
        data["earnings_beat_predictions"] = []
        data["earnings_per_tier_calibration"] = {"tiers": []}

    # Setup-family stats (Wilson LB, sample size, profit factor, reliability)
    # for Signal Scanner Quant Evidence column (added 2026-05-11).
    # tracker.compute_stats_by_setup returns per-SETUP stats; tickers.json
    # uses FAMILY names — aggregate granular setups up to family level.
    FAMILY_TO_SETUPS = {
        "Trend Continuation": ["Trend Continuation", "EMA21 Pullback", "EMA50 Pullback",
                                "Bounce off Support", "10-Week Pullback"],
        "Breakout Expansion": ["VCP Breakout", "Near-VCP Breakout", "52wk Breakout",
                                "Squeeze Expansion", "Squeeze Breakout", "Pocket Pivot",
                                "Stage 2 Breakout (52w high)"],
        "Impulse Catalyst":   [],
        "Special Situation":  ["Insider Cluster", "RS New High"],
    }
    def _wilson_lb(wins, n, z=1.96):
        if not n or n <= 0: return None
        p = wins / n
        denom = 1 + z*z/n
        center = p + z*z/(2*n)
        margin = z * ((p*(1-p) + z*z/(4*n))/n) ** 0.5
        return max(0.0, (center - margin) / denom)
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
        from tracker import compute_stats_by_setup as _setup_stats_fn
        from math import isfinite
        _stats = _setup_stats_fn() or {}
        def _clean_inf(v):
            try:
                if isinstance(v, (int, float)) and not isfinite(v): return None
            except Exception: pass
            return v
        _by_setup = {}
        for k, vv in (_stats.get("by_setup") or {}).items():
            _by_setup[k] = {kk: _clean_inf(vvv) for kk, vvv in vv.items()}
        # Aggregate granular setups → family-level
        _by_family = {}
        for fam, setups in FAMILY_TO_SETUPS.items():
            total_n = total_wins = 0
            r_sum = pf_num = pf_den = 0.0
            for s in setups:
                row = _by_setup.get(s)
                if not row: continue
                n = row.get("trades") or 0
                w = row.get("wins") or 0
                total_n += n; total_wins += w
                r_sum += (row.get("avg_r") or 0) * n
                pf = row.get("profit_factor")
                if pf and isinstance(pf, (int, float)) and isfinite(pf):
                    pf_num += pf * n; pf_den += n
            if total_n == 0: continue
            wr  = total_wins / total_n
            lb  = _wilson_lb(total_wins, total_n)
            avg_r = (r_sum / total_n) if total_n else 0
            pf_avg = (pf_num / pf_den) if pf_den else None
            reli = 'medium' if total_n >= 30 else ('low' if total_n >= 10 else 'thin')
            _by_family[fam] = {
                "trades": total_n, "wins": total_wins,
                "win_rate": round(wr, 4),
                "wr_low_95": round(lb, 4) if lb is not None else None,
                "avg_r": round(avg_r, 2),
                "profit_factor": round(pf_avg, 2) if pf_avg is not None else None,
                "reliability": reli,
            }
        _by_setup.update(_by_family)
        data["setup_family_stats"] = _by_setup
    except Exception as _ss_err:
        print(f"[setup_family_stats] non-fatal: {_ss_err}")
        data["setup_family_stats"] = {}

    # MECHANISM hypothesis + FALSIFICATION rule per setup family
    # (CLAUDE.md principle 2 + 15 — required before promoting any signal).
    # Static map — derived from the setup playbook docs.
    data["setup_mechanisms"] = {
        "Trend Continuation":    "Institutional re-add at the rising EMA21/EMA50 pullback · trend uninterrupted · low-stress entry.",
        "Breakout Expansion":    "Supply absorbed during the base · the lid breaks · momentum continues until volume fades.",
        "VCP Breakout":          "Volatility Contraction Pattern · tightening price action precedes expansion · classic Minervini setup.",
        "Near-VCP Breakout":     "Pre-VCP — base forming but pivot not yet broken · early-entry on tightening volume.",
        "52wk Breakout":         "Price clears 52-week high on volume · attention vacuum + breakout-buyer demand drives continuation.",
        "Stage 2 Breakout (52w high)": "Stage 2 trend with 52w high break · institutional uptrend confirmation.",
        "EMA21 Pullback":        "Trend pulls back to rising 21EMA · institutional re-add at moving-average support.",
        "EMA50 Pullback":        "Trend pulls back to rising 50EMA · deeper institutional re-add point.",
        "Squeeze Breakout":      "Bollinger Band squeeze releases · volatility-compression breakout · expanding range.",
        "Squeeze Expansion":     "Post-squeeze expansion · momentum follows the compression release.",
        "Pocket Pivot":          "O'Neil pocket pivot · volume cluster above 10-day price during base · institutional accumulation.",
        "Bounce off Support":    "Mean-reversion off prior support · oversold reading + reclaim.",
        "Impulse Catalyst":      "News-driven gap on attention vacuum · post-event drift in direction of surprise (PEAD).",
        "Special Situation":     "Forced supply imbalance — short squeeze, float rotation, or insider cluster · asymmetric upside.",
        "Breakdown":             "Trend break to the downside · short setup · breakdown-seller demand drives continuation.",
        "Insider Cluster":       "≥3 insider buys within 30 days · informed-buyer signal · alpha-bearing event.",
        "RS New High":           "Relative-strength line makes a new high before price · leadership reveal.",
        "10-Week Pullback":      "Pullback to the 10-week (50d) moving average within a Stage 2 trend.",
    }
    data["setup_falsifications"] = {
        "Trend Continuation":    "Close below the 21EMA on volume — institutions stop defending the pullback.",
        "Breakout Expansion":    "Close back inside the base on volume — failed breakout, supply re-emerges.",
        "VCP Breakout":          "Volume breakout fails to hold above pivot for 2 closes — no follow-through demand.",
        "Near-VCP Breakout":     "Pivot fails on first attempt with high volume — base is wider than tradeable.",
        "52wk Breakout":         "Daily close back below the 52w high pivot on volume — breakout failure / bull trap.",
        "Stage 2 Breakout (52w high)": "Two consecutive closes below the 50-day moving average — stage 2 broken.",
        "EMA21 Pullback":        "Daily close below the 21EMA AND below the prior swing low.",
        "EMA50 Pullback":        "Daily close below the 50EMA AND below the prior swing low.",
        "Squeeze Breakout":      "Bands re-contract within 5 days of the breakout — failed expansion.",
        "Squeeze Expansion":     "Price re-enters the squeeze range on falling volume.",
        "Pocket Pivot":          "Volume fails to follow through in the next 3 sessions — no institutional support.",
        "Bounce off Support":    "Support breaks on close with above-average volume — no buying demand.",
        "Impulse Catalyst":      "Gap fills within 3 days OR catalyst is denied/walked back officially.",
        "Special Situation":     "Catalyst is denied, hedge unwound, or float-rotation reverses on volume.",
        "Breakdown":             "Close back above prior support level — failed breakdown, short squeeze risk.",
        "Insider Cluster":       "Follow-on insider sells within 14 days — cluster invalidated.",
        "RS New High":           "RS-line rolls over within 5 days while price still rising — divergence.",
        "10-Week Pullback":      "Close below the 10-week moving average on volume.",
    }

    # Drift alert — if model_drift_alert.py wrote a recent flag (last 24h),
    # surface it. If file absent, derive "low reliability" badges from setup_family_stats.
    try:
        from datetime import datetime as _dt, timezone as _tz
        _drift_path = Path(__file__).resolve().parent.parent.parent / "cache" / "drift_alerts.json"
        if _drift_path.exists():
            _drift = json.loads(_drift_path.read_text())
            data["setup_drift_alerts"] = _drift.get("alerts") or _drift
        else:
            # Fallback: setup with sample n<10 AND wr<0.40 + reliability=low → "drift-watch"
            _watch = []
            for k, v in (data["setup_family_stats"] or {}).items():
                if v.get("reliability") == "low" and (v.get("win_rate") or 0) < 0.40 and (v.get("trades") or 0) >= 5:
                    _watch.append({"setup": k, "reason": "low reliability + low WR", "n": v.get("trades"), "wr": v.get("win_rate")})
            data["setup_drift_alerts"] = _watch
    except Exception as _de:
        print(f"[setup_drift_alerts] non-fatal: {_de}")
        data["setup_drift_alerts"] = []

    # Pre-earnings BUY badge (#3) — for each ticker, attach earnings_in_Nd
    # if it appears in the earnings_watchlist within 10 days. Surfaces in
    # elite-detail and audit trail as a "🎯 EARN+5D" tag.
    _ew_by_t = {x["ticker"]: x for x in (data.get("earnings_watchlist") or []) if isinstance(x, dict)}
    for _section_key in ("short_term", "medium_term", "long_term"):
        _section = data.get(_section_key) or []
        if not isinstance(_section, list): continue
        for _r in _section:
            if not isinstance(_r, dict): continue
            _t = _r.get("ticker")
            _ew_e = _ew_by_t.get(_t)
            if _ew_e:
                _r["earnings_in_days"] = _ew_e.get("days_to_earnings")
                _r["earnings_report_date"] = _ew_e.get("report_date")
                _r["earnings_when"] = _ew_e.get("before_after_market")
                # Stamp earn_days back onto the ticker row when the scan's
                # earnings dict didn't carry it (added 2026-05-11). Surfaces in
                # Signal Scanner, Detail panel, and V2 earnings widget.
                if _r.get("earn_days") in (None, 0) and _ew_e.get("days_to_earnings") is not None:
                    _r["earn_days"] = _ew_e.get("days_to_earnings")

    # ── Cockpit enrichment: market news (EODHD), market movers (Schwab),
    #    per-ticker news for top-N picks (EODHD primary, yfinance fallback).
    #    All wrapped in try/except so a single API failure doesn't block the build.
    _enrich_cockpit_data(data)

    # ── 2026-05-19 · Schwab session-context enrichment ─────────────────
    # Merge live Schwab quote fields (security_status, today's OHLC, NBBO depth,
    # mark vs last, HV, asset-type, dividend calendar) into every ticker payload
    # so the kairos.html SESSION CONTEXT section + halt chip light up.
    # ONE batched Schwab API call (up to 500 syms) — cheap.
    try:
        import schwab_client as _schwab
        # Collect unique tickers from all signal lists + portfolio
        _tkrs = set()
        for _bucket in ("short_term", "medium_term", "long_term", "watchlist", "killed"):
            for _r in (data.get(_bucket) or []):
                if isinstance(_r, dict) and _r.get("ticker"):
                    _tkrs.add(_r["ticker"].upper())
        for _p in (data.get("portfolio", {}).get("positions") or []):
            if _p.get("ticker"):
                _tkrs.add(_p["ticker"].upper())
        _tkrs.discard("")
        _tkr_list = sorted(_tkrs)[:500]  # Schwab batch cap

        if _tkr_list:
            print(f"  enrich: schwab session-context for {len(_tkr_list)} tickers...")
            _blobs = _schwab.get_quotes_batch(_tkr_list) or {}
            _sess_by_tkr: dict = {}
            for _sym, _blob in _blobs.items():
                try:
                    _info = _schwab.translate_quote_to_stock_info(_sym, _blob)
                    _sess_by_tkr[_sym.upper()] = {
                        # Halt status
                        "security_status":   _info.get("security_status"),
                        "is_halted":         _info.get("is_halted"),
                        # Today's intraday context
                        "today_open":        _info.get("today_open"),
                        "today_high":        _info.get("today_high"),
                        "today_low":         _info.get("today_low"),
                        "day_change_pct":    _info.get("today_net_pct"),
                        "day_change_dollar": _info.get("today_net_change"),
                        # Post-market move (separate)
                        "postmarket_pct":    _info.get("kpi_post_market_pct"),
                        # NBBO depth + microstructure
                        "bid_size":          _info.get("bid_size"),
                        "ask_size":          _info.get("ask_size"),
                        "bid_ask_imbalance": _info.get("bid_ask_imbalance"),
                        "spread_bp":         _info.get("kpi_spread_bp"),
                        "quote_age_s":       _info.get("kpi_quote_age_s"),
                        # Mark price (cleaner for after-hours)
                        "mark":              _info.get("mark"),
                        "mark_pct_change":   _info.get("mark_pct_change"),
                        # Historical volatility (when available)
                        "hist_volatility":   _info.get("hist_volatility"),
                        # Asset classification (replaces hardcoded ETF lists)
                        "asset_main_type":   _info.get("asset_main_type"),
                        "asset_sub_type":    _info.get("asset_sub_type"),
                        "is_etf":            _info.get("is_etf"),
                        "leverage_factor":   _info.get("kpi_leverage_factor"),
                        # Dividend calendar (avoid ex-div surprises)
                        "next_div_ex_date":  _info.get("next_div_ex_date"),
                        "days_to_ex_div":    _info.get("days_to_ex_div"),
                        # 52-week context
                        "dist_from_52w_high_pct": _info.get("kpi_dist_from_52wk_high_pct"),
                        "dist_from_52w_low_pct":  _info.get("kpi_dist_from_52wk_low_pct"),
                    }
                except Exception:
                    continue

            # Merge into every ticker payload across buckets
            for _bucket in ("short_term", "medium_term", "long_term", "watchlist", "killed"):
                for _r in (data.get(_bucket) or []):
                    if isinstance(_r, dict) and _r.get("ticker"):
                        _sess = _sess_by_tkr.get(_r["ticker"].upper())
                        if _sess:
                            _r.update(_sess)
                            _r["session_context"] = _sess  # nested copy too
            for _p in (data.get("portfolio", {}).get("positions") or []):
                _sess = _sess_by_tkr.get((_p.get("ticker") or "").upper())
                if _sess:
                    _p["session_context"] = _sess
                    if _sess.get("is_halted"):
                        _p["is_halted"] = True
            print(f"  enrich: schwab session-context merged into {len(_sess_by_tkr)} tickers")
    except Exception as _se:
        print(f"  enrich: schwab session-context FAILED ({type(_se).__name__}: {_se})")

    data = _clean(data)
    DATA.write_text(json.dumps(data, default=str, indent=0, allow_nan=False))
    print(f"wrote {DATA} ({DATA.stat().st_size:,} bytes)")

    # PERF-7 + PERF-7b: emit critical + 7 deferred chunks for lazy dashboard
    # loading. Cuts cold-load payload by ~4.7 MB (~89% reduction). Lazy splits:
    #   data_perf.json        (1.7 MB) → Performance tab
    #   data_killed.json      (1.1 MB) → Killed tab
    #   data_signals_ext.json (1.0 MB) → Position/Invest scanner modes (mt+lt)
    #   data_earnings.json    (430 KB) → Earnings tab + beat predictions
    #   data_screener.json    (255 KB) → Screener tab
    #   data_crypto.json      (132 KB) → Crypto tab
    #   data_misc.json         (65 KB) → strategies + zacks_* (Strategies/Settings)
    # Critical bundle keeps small stubs matching each chunk's shape so
    # boot-time render() and sidebar counts continue to work — chunks overlay
    # the stubs when they arrive on tab activation.
    _PERF_KEYS         = ("performance",)
    _KILLED_KEYS       = ("killed",)
    _EARNINGS_KEYS     = ("earnings_beat_predictions", "earnings_outcomes_30d",
                          "earnings_watchlist", "earnings_watchlist_meta",
                          "earnings_per_tier_calibration")
    _SCREENER_KEYS     = ("screener",)
    _CRYPTO_KEYS       = ("crypto",)
    _SIGNALS_EXT_KEYS  = ("medium_term", "long_term")
    _MISC_KEYS         = ("strategies", "zacks_premium_services", "zacks_email_digest")
    _LAZY_KEYS = (set(_PERF_KEYS) | set(_KILLED_KEYS) | set(_EARNINGS_KEYS)
                  | set(_SCREENER_KEYS) | set(_CRYPTO_KEYS)
                  | set(_SIGNALS_EXT_KEYS) | set(_MISC_KEYS))

    _critical = {k: v for k, v in data.items() if k not in _LAZY_KEYS}
    # Stubs — match the SHAPE of the real chunk so renderers using `?.` / `||`
    # guards don't crash before the chunk arrives. killed/screener/medium_term/
    # long_term are lists; crypto/strategies/zacks_* are dicts; performance is
    # a dict with `.total` exposed for the sidebar count.
    _critical["killed"] = []
    _critical["screener"] = []
    _critical["crypto"] = {}
    _critical["medium_term"] = []
    _critical["long_term"]   = []
    _critical["strategies"]            = {}
    _critical["zacks_premium_services"] = {}
    _critical["zacks_email_digest"]    = {}
    _perf_total = (data.get("performance") or {}).get("total")
    if _perf_total is not None:
        _critical["performance"] = {"total": _perf_total}
    # Pre-computed counts so sidebar/floor strip can render real numbers at
    # boot without waiting for chunks. Read by dashboard.html boot path.
    _critical["_chunk_counts"] = {
        "screener":     len(data.get("screener") or []),
        "crypto":       len((data.get("crypto") or {}).get("top_picks") or []),
        "killed":       len(data.get("killed") or []),
        "medium_term":  len(data.get("medium_term") or []),
        "long_term":    len(data.get("long_term") or []),
    }

    _chunks = {
        "perf":        {k: data[k] for k in _PERF_KEYS        if k in data},
        "killed":      {k: data[k] for k in _KILLED_KEYS      if k in data},
        "earnings":    {k: data[k] for k in _EARNINGS_KEYS    if k in data},
        "screener":    {k: data[k] for k in _SCREENER_KEYS    if k in data},
        "crypto":      {k: data[k] for k in _CRYPTO_KEYS      if k in data},
        "signals_ext": {k: data[k] for k in _SIGNALS_EXT_KEYS if k in data},
        "misc":        {k: data[k] for k in _MISC_KEYS        if k in data},
    }

    _crit_path = OUT / "data.critical.json"
    _crit_path.write_text(json.dumps(_critical, default=str, indent=0, allow_nan=False))
    print(f"wrote {_crit_path.name} ({_crit_path.stat().st_size:,} bytes)")
    for _name, _chunk in _chunks.items():
        _path = OUT / f"data_{_name}.json"
        _path.write_text(json.dumps(_chunk, default=str, indent=0, allow_nan=False))
        print(f"wrote {_path.name} ({_path.stat().st_size:,} bytes)")

    # Tickers — rich payload for elite-detail page
    # Pre-build earn_days lookup from the loaded earnings_watchlist so we can
    # stamp it onto each src row BEFORE rich_row() rebuilds the output dict
    # (2026-05-11 fix — scan's r["earnings"] is null but watchlist has the data).
    _ew_lookup = {x["ticker"]: x.get("days_to_earnings")
                  for x in (data.get("earnings_watchlist") or [])
                  if isinstance(x, dict) and x.get("ticker") and x.get("days_to_earnings") is not None}
    # Build mode lookup from st_rows / mt_rows / invest_rows so each ticker
    # carries its source horizon (swing / position / invest) — added 2026-05-11
    # for Signal Scanner horizon-filter chips.
    _mode_lookup = {}
    for r in st_rows: _mode_lookup[r.get("ticker")] = 'swing'
    for r in mt_rows: _mode_lookup.setdefault(r.get("ticker"), 'position')
    for r in invest_rows: _mode_lookup.setdefault(r.get("ticker"), 'invest')
    # Setup-family stats + mechanism + falsification lookups — keyed by setup_family
    _sf_stats = data.get("setup_family_stats") or {}
    _sf_mech  = data.get("setup_mechanisms") or {}
    _sf_fals  = data.get("setup_falsifications") or {}
    _sf_drift = {(d.get("setup") if isinstance(d, dict) else None) for d in (data.get("setup_drift_alerts") or [])}
    _sf_drift.discard(None)
    # Build a unified ticker→rich-source lookup covering ALL five list types
    # (short / medium / long / screener / killed) so the detail-view fast-path
    # at server.py:/api/elite/<TICKER> hits for every ticker shown anywhere on
    # the dashboard. Previously this loop iterated only st_rows + mt_rows,
    # leaving long_term + screener + killed tickers absent from tickers.json
    # — clicks on those fell through to slow on-demand run_quick_dive and the
    # page rendered with empty options_kpis (misleading "Schwab token expired"
    # fallback). killed coverage added 2026-05-11 so the user can investigate
    # "why was X rejected" without a 15-25s re-scan.
    _all_scored_by_t = {r.get("ticker"): r for r in (b.get("all_scored") or []) if r.get("ticker")}
    _st_by_t      = {r.get("ticker"): r for r in st_rows if r.get("ticker")}
    _mt_by_t      = {r.get("ticker"): r for r in mt_rows if r.get("ticker")}
    _killed_by_t  = {r.get("ticker"): r for r in (b.get("killed") or []) if isinstance(r, dict) and r.get("ticker")}
    killed_set    = set(_killed_by_t.keys())

    # Preserve original iteration order so existing short_term-first dedupe
    # semantics still hold; layer long_term + screener next; killed last (so
    # actionable tickers always take precedence on the dedupe seen-set).
    _ordered_targets: list[str] = []
    _seen: set = set()
    for r in (st_rows + mt_rows + long_term + screener_rows):
        t = r.get("ticker")
        if t and t not in _seen:
            _seen.add(t); _ordered_targets.append(t)
    for t in _killed_by_t:
        if t and t not in _seen:
            _seen.add(t); _ordered_targets.append(t)

    all_rich = {}
    _rich_failures: list[tuple[str, str]] = []
    for t in _ordered_targets:
        src = (_st_by_t.get(t) or _mt_by_t.get(t)
               or _all_scored_by_t.get(t) or _killed_by_t.get(t))
        if not src: continue
        if src.get("earn_days") in (None, 0) and t in _ew_lookup:
            src["earn_days"] = _ew_lookup[t]
        # Per-ticker try/except — without this, one malformed row (missing
        # nested key in _compute_mode_verdicts, type mismatch in fund_real,
        # div-by-zero on a no-fundamentals stock) would halt the whole build.
        # Failures logged below and reported on stdout so they're visible
        # without burying the rest of the run.
        try:
            all_rich[t] = rich_row(src, b)
        except Exception as _e:
            _rich_failures.append((t, type(_e).__name__ + ": " + str(_e)[:120]))
            continue
        all_rich[t]["_mode"] = _mode_lookup.get(t, 'swing')
        # Stamp setup-family stats + mechanism + falsification per ticker so
        # the Scanner UI can render Wilson LB / n / mechanism without
        # cross-referencing data.setup_family_stats on every row.
        _fam = src.get("setup_family") or all_rich[t].get("setup_family")
        if _fam:
            _s = _sf_stats.get(_fam) or {}
            all_rich[t]["_setup_wr"]          = _s.get("win_rate")
            all_rich[t]["_setup_wilson_lb"]   = _s.get("wr_low_95")
            all_rich[t]["_setup_wilson_hi"]   = _s.get("wr_high_95")
            all_rich[t]["_setup_n"]           = _s.get("trades")
            all_rich[t]["_setup_pf"]          = _s.get("profit_factor")
            all_rich[t]["_setup_avg_r"]       = _s.get("avg_r")
            all_rich[t]["_setup_reliability"] = _s.get("reliability")
            all_rich[t]["_mechanism"]         = _sf_mech.get(_fam) or ""
            all_rich[t]["_falsification"]     = _sf_fals.get(_fam) or ""
            all_rich[t]["_setup_drift"]       = _fam in _sf_drift
        if t in short_set:
            all_rich[t]["stage"] = "SELL"
            all_rich[t]["verdict"] = "SELL"
        elif t in killed_set:
            # Stamp killed tickers with explicit stage so the detail view
            # renders an honest "AVOID" badge instead of pretending it's a
            # WATCH candidate. reject_reason already lives on the source row
            # (set by decision_engine path) — surface it under both names so
            # downstream UI code can reference either.
            all_rich[t]["stage"] = "KILLED"
            all_rich[t]["verdict"] = "AVOID"
            # Boolean flag for frontend filtering (Signal Scanner default
            # 'all' view excludes killed via `!t.killed`). Without this
            # explicit True, the field defaults to None/falsy and 263 killed
            # tickers leak into the 'all' view as AVOID badges.
            all_rich[t]["killed"] = True
            kr = src.get("reject_reason") or src.get("kill_reason") or ""
            if kr:
                all_rich[t]["kill_reason"]   = kr
                all_rich[t]["reject_reason"] = kr
    if _rich_failures:
        print(f"rich_row failures: {len(_rich_failures)} tickers skipped")
        for _t, _err in _rich_failures[:10]:
            print(f"  {_t}: {_err}")

    # Per-ticker earnings prediction join — surfaces 4Q pattern + revision
    # trend + implied move + Kelly-lite + PEAD + macro overlap + sector cohort
    # to the detail tabs (Plan / Fundamentals / Options) without duplication.
    _ebp_by_t = {p["ticker"]: p for p in (data.get("earnings_beat_predictions") or [])
                 if isinstance(p, dict) and p.get("ticker")}
    for t, rec in all_rich.items():
        if t in _ebp_by_t:
            rec["earnings_beat_prediction"] = _ebp_by_t[t]

    # ── Bug 4 fix (2026-05-25): Backfill earnings-only tickers ──
    # Watchlist tickers that never appeared in scan output (e.g. OOMA reports
    # tomorrow but didn't pass the scan filters) were missing from tickers.json
    # entirely, leaving the Earnings tab "Days to Report" blank. Add a stub
    # row carrying earn_days + report_date so the tab populates.
    _ew_full = {x["ticker"]: x for x in (data.get("earnings_watchlist") or [])
                if isinstance(x, dict) and x.get("ticker")}
    _backfilled = 0
    for t, ew in _ew_full.items():
        if t in all_rich: continue
        days = ew.get("days_to_earnings")
        if days is None: continue
        all_rich[t] = {
            "ticker": t,
            "earn_days": days,
            "earnings_date": ew.get("report_date") or ew.get("earnings_date"),
            "earnings_estimate": ew.get("estimate") or ew.get("eps_estimate"),
            "_mode": "earnings_only",
            "stage": "EARNINGS_WATCH",
            "name": ew.get("name"),
            "sector": ew.get("sector"),
            "price": ew.get("price"),
            "_data_completeness": "lite",
            "_lite_sources": ["earnings"],
        }
        if t in _ebp_by_t:
            all_rich[t]["earnings_beat_prediction"] = _ebp_by_t[t]
        _backfilled += 1
    if _backfilled:
        print(f"  earnings-watchlist backfill: {_backfilled} tickers added")

    # ─── Option B (2026-05-23): Unified ticker universe ───────────────
    # Augment tickers.json with ML / Earnings / Options-only tickers that
    # weren't in the main scan. Each gets OHLCV + name + sector + last price
    # via EODHD (24h cached). The detail page works for every clicked ticker
    # because every ticker has at least lite-quality data.
    #
    # Tag with _data_completeness: 'full' (main-scan) vs 'lite' (extras).
    for t, rec in all_rich.items():
        rec.setdefault("_data_completeness", "full")
    try:
        _augment_with_lite_universe(all_rich, b, data)
    except Exception as e:
        print(f"  ⚠ lite-universe augmentation failed: {e}")

    all_rich = _clean(all_rich)
    TICKS.write_text(json.dumps(all_rich, default=str, allow_nan=False))
    print(f"wrote {TICKS} (n={len(all_rich)} tickers, {TICKS.stat().st_size:,} bytes)")


# ════ Lite-universe augmentation · Option B · 2026-05-23 ═════════════════
def _augment_with_lite_universe(all_rich: dict, bundle: dict, data: dict) -> None:
    """In-place augment all_rich with tickers from ML cache / earnings watchlist
    / options flow that aren't already present. Each extra gets:
      - OHLCV (last 90 bars, via EODHD eod() — 24h cached)
      - name + sector + industry (via bulk_fundamentals — 24h cached)
      - last close as price
      - _data_completeness='lite' flag (frontend can show "limited data" banner)
      - _lite_sources list ('ml','earnings','options')
    The frontend _tickerMap[symbol] lookup now succeeds for every clicked
    ticker; QuantDetail's chart sub-tab + header always have data.
    """
    from pathlib import Path as _P
    import datetime as _dt, json as _json

    extras: dict[str, list[str]] = {}  # ticker → list of sources
    def _add(t, src):
        t = (t or "").upper().strip()
        if not t or t in all_rich: return
        extras.setdefault(t, []).append(src)

    # 1. ML Edge predictions (cache/ml_edge_predictions.json)
    ml_p = _P("cache/ml_edge_predictions.json")
    if ml_p.exists():
        try:
            ml = _json.loads(ml_p.read_text())
            for mode in ("swing", "position", "invest"):
                pool = ((ml.get("predictions") or {}).get(mode) or {})
                for t in pool.keys(): _add(t, "ml")
        except Exception as e:
            print(f"  lite-aug: ML cache read failed — {e}")

    # 2. Earnings watchlist (data/earnings_watchlist.json or bundle)
    ew = data.get("earnings_watchlist") or bundle.get("earnings_watchlist") or []
    for e in ew:
        if isinstance(e, dict): _add(e.get("ticker"), "earnings")

    # 3. Options flow (cache/options_flow.json if exists)
    opt_p = _P("cache/options_flow.json")
    if opt_p.exists():
        try:
            opt = _json.loads(opt_p.read_text())
            rows = opt.get("flows") if isinstance(opt, dict) else opt
            for o in (rows or []):
                if isinstance(o, dict): _add(o.get("ticker"), "options")
        except Exception:
            pass

    if not extras:
        print("  lite-universe: no extras to add (all sources covered by main scan)")
        return

    print(f"  lite-universe: {len(extras)} extras to lite-score (ML/Earnings/Options-only tickers)")

    # Bulk-fundamentals fetch (24h cached) — name + sector + industry
    fund_cache: dict[str, dict] = {}
    try:
        import eodhd_client as _eod
        syms = list(extras.keys())
        for i in range(0, len(syms), 100):
            batch = syms[i:i+100]
            try:
                bulk = _eod.bulk_fundamentals(batch) or {}
                for sym, f in bulk.items():
                    if isinstance(f, dict): fund_cache[sym.upper().split(".")[0]] = f
            except Exception as e:
                print(f"  lite-aug: bulk_fundamentals batch {i}-{i+100} failed — {e}")
    except ImportError:
        print("  lite-aug: eodhd_client not importable — skipping fundamentals")

    # Per-ticker OHLCV (24h cached) — fetch 120 days, keep last 90 bars
    try:
        import eodhd_client as _eod
        today = _dt.date.today()
        from_d = (today - _dt.timedelta(days=120)).strftime("%Y-%m-%d")
        to_d = today.strftime("%Y-%m-%d")
    except ImportError:
        print("  lite-aug: eodhd_client not importable — skipping OHLCV")
        return

    n_ok, n_skip = 0, 0
    for t, sources in extras.items():
        try:
            bars = _eod.eod(t, from_date=from_d, to_date=to_d, period="d") or []
            if not bars or len(bars) < 5:
                n_skip += 1
                continue

            # Normalize to compact bar shape {d,o,h,l,c,v} matching main rows
            ohlcv = []
            for bar in bars[-90:]:
                if not isinstance(bar, dict): continue
                ohlcv.append({
                    "d": bar.get("date"),
                    "o": bar.get("open"),
                    "h": bar.get("high"),
                    "l": bar.get("low"),
                    "c": bar.get("close"),
                    "v": bar.get("volume"),
                })

            fund = fund_cache.get(t) or {}
            general    = (fund.get("General") or {})   if isinstance(fund, dict) else {}
            highlights = (fund.get("Highlights") or {}) if isinstance(fund, dict) else {}

            last_close = (bars[-1] or {}).get("close") if bars else None

            all_rich[t] = {
                "ticker":           t,
                "symbol":           t,
                "name":             general.get("Name") or t,
                "sector":           general.get("Sector"),
                "industry":         general.get("Industry"),
                "price":            last_close,
                "ohlcv":            ohlcv,
                # Lite scoring — fields exist but are null so frontend renders
                # "not scored in today's scan" state rather than crashing.
                "verdict":          None,
                "score":            None,
                "rs_rank":          None,
                "rvol":             None,
                "rsi":              None,
                "atr":              None,
                "setup_family":     None,
                "setup_type":       None,
                "conviction_tier":  None,
                "rr_ratio":         None,
                "entry_low":        None,
                "entry_high":       None,
                "stop":             None,
                "target1":          None,
                "target2":          None,
                "earn_days":        None,
                "catalyst_tier":    None,
                "ticker_source":    sources[0] + "_extra",  # ml_extra / earnings_extra / options_extra
                "market_cap":       highlights.get("MarketCapitalization"),
                "fund_real":        {
                    "name":     general.get("Name") or t,
                    "sector":   general.get("Sector"),
                    "industry": general.get("Industry"),
                    "exchange": general.get("Exchange"),
                    "country":  general.get("Country"),
                    "market_cap": highlights.get("MarketCapitalization"),
                },
                # Provenance — frontend reads this to show banners
                "_data_completeness": "lite",
                "_lite_sources":      sources,
            }
            n_ok += 1
        except Exception as e:
            n_skip += 1
            if n_skip < 5:
                print(f"  lite-aug {t}: {type(e).__name__}: {str(e)[:80]}")

    print(f"  lite-universe: scored {n_ok}/{len(extras)} extras ({n_skip} skipped)")


if __name__ == "__main__":
    main()
