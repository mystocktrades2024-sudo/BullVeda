"""
Trade tracking and performance stats for SwingTrade.
Append-only history with auto-evaluation of past picks.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

from data_fetcher import yf  # _YfStub: empty no-op (yfinance removed 2026-04-25)

log = logging.getLogger("swingtrade.tracker")

BASE_DIR = Path(__file__).parent
HISTORY_PATH = BASE_DIR / "cache" / "picks_history.json"


def _load_history() -> dict:
    if HISTORY_PATH.exists():
        with open(HISTORY_PATH) as f:
            return json.load(f)
    return {"runs": [], "trades": []}


def _save_history(data: dict):
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(HISTORY_PATH, "w") as f:
        json.dump(data, f, indent=2, default=str)


def record_run(picks: list[dict], run_date: str | None = None,
               regime_name: str | None = None,
               # AI-15: full-context market snapshot for per-trade attribution
               vix: float | None = None,
               breadth_pct_50d: float | None = None,
               regime4: str | None = None,
               spy_price: float | None = None,
               spy_1m_ret: float | None = None,
               distribution_days: int | None = None):
    """
    Append a screener run keyed by run_date + run_time.
    Every execution is preserved — multiple runs per day are kept separately.
    Saves BUY, WATCH, and SHORT picks (AVOID skipped).

    AI-15: captures full per-pick context (rs_rank, rvol, catalyst_tags,
    weekly_bull, entry/stop/T1/T2) + market snapshot (VIX, breadth,
    regime4) for per-setup WR attribution and drift analysis.
    """
    history = _load_history()
    now = datetime.now()
    run_date = run_date or now.strftime("%Y-%m-%d")
    run_time = now.strftime("%H:%M")
    regime_name = (regime_name or "unknown").lower()

    saved_picks = []
    for p in picks:
        verdict = p["decision"]["verdict"]
        # Track all actionable signals — BUY, WATCH, SHORT
        # AVOID is skipped (no entry considered)
        if verdict == "AVOID":
            continue
        _ind = p.get("technicals", {}).get("indicators", {}) or {}
        _plan = p.get("trade_plan") or {}
        saved_picks.append({
            "ticker":          p["ticker"],
            "direction":       p.get("direction", "long"),
            "entry_price":     p["price"],
            "score":           p["score"],
            "verdict":         verdict,
            "setup_type":      _plan.get("setup_type", ""),
            "regime":          regime_name,
            "rr_ratio":        _plan.get("rr_ratio"),
            "bear_score":      p.get("bear_setup", {}).get("score"),
            # Phase 9 attribution fields
            "setup_family":    p.get("setup_family", ""),
            "catalyst_tier":   p.get("catalyst_tier", 3),
            "entry_quality":   p.get("entry_quality", ""),
            "entry_subtype":   p.get("entry_subtype", ""),
            "regime4":         p.get("regime4", regime4 or regime_name),
            "sector":          p.get("sector", ""),
            "industry":        p.get("industry", ""),
            "conviction_tier": p.get("conviction", {}).get("label", ""),
            # AI-15: full trade-journal context
            "stop":            _plan.get("stop"),
            "target1":         _plan.get("target1"),
            "target2":         _plan.get("target2"),
            "rs_rank":         p.get("rs_rank") if p.get("rs_rank") is not None else _ind.get("rs_rank"),
            "rvol":            _ind.get("rvol"),
            "rsi":             _ind.get("rsi"),
            "adx":             _ind.get("adx"),
            "weekly_bull":     bool(_ind.get("weekly_ema_bullish")),
            "catalyst_tags":   p.get("catalyst_tags") or [],
            "market_vix":      vix,
            "market_breadth":  breadth_pct_50d,
            "market_spy":      spy_price,
            "market_spy_1m":   spy_1m_ret,
            "market_dist_days": distribution_days,
            # Audit ranking flaw #16/#17: per-pillar breakdown
            "scoring_breakdown": p.get("scoring_breakdown", {}) or {},
        })

    run = {
        "run_date":   run_date,
        "run_time":   run_time,
        "regime":     regime_name,
        "num_picks":  len(saved_picks),
        "picks":      saved_picks,
        "evaluated":  False,
    }

    # Dedup update-in-place: if a ticker was already recorded today, UPDATE its
    # existing entry with the latest verdict/score/plan rather than dropping it.
    # This preserves the earliest run_date/run_time while letting later BUY/SELL
    # signals override stale AM WATCH/AVOID verdicts.
    #
    # Backward-compat: older picks without `updated_count` / `last_updated_time`
    # still load fine — we simply seed those fields when first touched.
    existing_index: dict[str, tuple[dict, dict]] = {}
    for r in history["runs"]:
        if r["run_date"] == run_date:
            for pk in r["picks"]:
                # Last-write-wins across runs today (so we update the most recent copy)
                existing_index[pk["ticker"]] = (r, pk)

    fresh_picks = []
    for np_ in saved_picks:
        tk = np_["ticker"]
        if tk in existing_index:
            _run_ref, old = existing_index[tk]
            old_verdict = old.get("verdict")
            old_score   = old.get("score")
            new_verdict = np_.get("verdict")
            new_score   = np_.get("score")
            if old_verdict == new_verdict and old_score == new_score:
                # Nothing materially changed — bump updated_count and timestamp only
                old["updated_count"] = int(old.get("updated_count", 1)) + 1
                old["last_updated_time"] = run_time
                continue
            # Update-in-place: overwrite fields with the fresh values
            preserved_run_date = old.get("run_date") or _run_ref.get("run_date")
            preserved_first_time = old.get("first_seen_time") or _run_ref.get("run_time")
            old.update(np_)
            # Preserve earliest run_date and first-seen time
            if preserved_run_date:
                old["run_date"] = preserved_run_date
            old["first_seen_time"] = preserved_first_time
            old["last_updated_time"] = run_time
            old["updated_count"] = int(old.get("updated_count", 1)) + 1
            log.info(
                f"Updated pick {tk}: verdict {old_verdict} → {new_verdict}, "
                f"score {old_score} → {new_score}"
            )
        else:
            # Seed tracking fields on first insertion
            np_["first_seen_time"] = run_time
            np_["last_updated_time"] = run_time
            np_["updated_count"] = 1
            fresh_picks.append(np_)

    run["picks"] = fresh_picks
    run["num_picks"] = len(fresh_picks)

    # Append run only if there are genuinely new tickers; updates above
    # already mutated existing run entries in history["runs"].
    if fresh_picks:
        history["runs"].append(run)

    _save_history(history)
    # Counts reflect the full scan result (including updated-in-place picks), not just new rows
    buys  = sum(1 for p in saved_picks if p["verdict"] == "BUY")
    watch = sum(1 for p in saved_picks if p["verdict"] == "WATCH")
    short = sum(1 for p in saved_picks if p["verdict"] == "SHORT")
    log.info(
        f"Recorded run {run_date} {run_time}: {buys} BUY, {watch} WATCH, {short} SHORT "
        f"({len(fresh_picks)} new, {len(saved_picks) - len(fresh_picks)} updated)"
    )

    # ── WATCH trigger list ────────────────────────────────────────────────────
    history = _load_history()
    watch_triggers = history.get("watch_triggers", [])
    # Remove any existing entries for tickers in this run (refresh them)
    run_tickers = {r["ticker"] for r in picks}
    watch_triggers = [w for w in watch_triggers if w["ticker"] not in run_tickers]
    # Add new WATCH picks with trigger prices
    for r in picks:
        if r.get("verdict") == "WATCH":
            plan = r.get("trade_plan", {})
            trigger = plan.get("entry_low") or plan.get("entry") or r.get("price")
            if trigger:
                watch_triggers.append({
                    "ticker":         r["ticker"],
                    "trigger_price":  float(trigger),
                    "score":          r.get("score", 0),
                    "run_date":       run_date,
                    "setup":          r.get("setup_type", ""),
                })
    # Keep only last 30 days of watches
    cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    watch_triggers = [w for w in watch_triggers if w.get("run_date", "") >= cutoff]
    history["watch_triggers"] = watch_triggers
    _save_history(history)


def check_watch_triggers(current_prices: dict) -> list[dict]:
    """
    Check which WATCH picks have crossed their trigger price.
    Returns list of triggered items: [{ticker, trigger_price, current_price, score, setup}]
    """
    history = _load_history()
    watch_triggers = history.get("watch_triggers", [])
    triggered = []
    for w in watch_triggers:
        ticker = w["ticker"]
        cur = current_prices.get(ticker)
        if cur is None:
            continue
        trigger = w["trigger_price"]
        # Triggered when price moves within 1% of trigger (approaching entry zone)
        if cur >= trigger * 0.99:
            pct = round((cur - trigger) / trigger * 100, 2)
            hit = {
                "ticker":           ticker,
                "trigger_price":    trigger,
                "current_price":    round(float(cur), 2),
                "score":            w.get("score", 0),
                "setup":            w.get("setup", ""),
                "run_date":         w.get("run_date", ""),
                "pct_from_trigger": pct,
                # Promote to BUY if within entry zone (within 1% of trigger — tighter threshold)
                "promoted_buy":     pct <= 1.0,
                "promotion_reason": "Price entered entry zone" if pct <= 1.0 else "",
                "action":           "BUY NOW — WATCH trigger fired" if pct <= 1.0 else "ENTERING zone — monitor closely",
            }
            triggered.append(hit)
            # Fire alert for promoted picks
            if hit["promoted_buy"]:
                try:
                    from alerts import send_watch_promotion
                    send_watch_promotion(
                        ticker=ticker,
                        score=w.get("score", 0),
                        setup=w.get("setup", ""),
                        rr=w.get("rr_ratio", 3.0),
                    )
                except Exception:
                    pass
            # Sidecar: log every watch trigger fire to JSONL (folded to Supabase nightly)
            try:
                import json as _wjson, hashlib as _whash
                from datetime import datetime as _wdt, timezone as _wtz
                from pathlib import Path as _wpath
                _wlog = _wpath(__file__).parent / "cache" / "watch_triggers.jsonl"
                _wlog.parent.mkdir(parents=True, exist_ok=True)
                _wts = _wdt.now(_wtz.utc).isoformat()
                with _wlog.open("a") as _wf:
                    _wf.write(_wjson.dumps({
                        "triggered_at": _wts,
                        "ticker": ticker,
                        "trigger_price": trigger,
                        "current_price": float(cur),
                        "score": w.get("score", 0),
                        "setup": w.get("setup", ""),
                        "run_date": w.get("run_date", ""),
                        "pct_from_trigger": pct,
                        "promoted_buy": bool(hit.get("promoted_buy")),
                        "sync_key": _whash.sha1(f"{_wts}|{ticker}".encode()).hexdigest()[:32],
                    }, default=str) + "\n")
            except Exception:
                pass
    return triggered


def update_score_history(results: list, run_date: str) -> None:
    """Track score history per ticker for momentum ranking (last 14 runs)."""
    import json as _json
    score_path = Path(__file__).parent / "cache" / "score_history.json"
    try:
        history = _json.loads(score_path.read_text()) if score_path.exists() else {}
    except Exception:
        history = {}
    for r in results:
        ticker = r.get("ticker", "")
        if not ticker:
            continue
        entry = {"date": run_date, "score": r.get("score", 0), "verdict": r.get("verdict", "")}
        if ticker not in history:
            history[ticker] = []
        history[ticker].append(entry)
        # Keep only last 14 entries per ticker
        history[ticker] = history[ticker][-14:]
    try:
        score_path.write_text(_json.dumps(history))
    except Exception as e:
        log.warning(f"Score history write failed: {e}")


def get_score_trend(ticker: str) -> dict:
    """Return score trend for a ticker: up/down/flat + delta over last 3 runs."""
    import json as _json
    score_path = Path(__file__).parent / "cache" / "score_history.json"
    try:
        history = _json.loads(score_path.read_text()) if score_path.exists() else {}
    except Exception:
        return {"trend": "flat", "delta_3d": 0.0, "history": []}
    entries = history.get(ticker, [])
    if len(entries) < 2:
        return {"trend": "flat", "delta_3d": 0.0, "history": [e["score"] for e in entries]}
    scores = [e["score"] for e in entries]
    delta = scores[-1] - scores[max(0, len(scores) - 4)]  # last 3 data points
    trend = "up" if delta >= 3 else "down" if delta <= -3 else "flat"
    return {"trend": trend, "delta_3d": round(delta, 1), "history": scores[-7:]}


def evaluate_pending(hold_days: int = 5) -> int:
    """Evaluate picks older than hold_days. Returns count evaluated."""
    history = _load_history()
    cutoff = datetime.now() - timedelta(days=hold_days)
    evaluated = 0

    for run in history["runs"]:
        if run["evaluated"]:
            continue

        run_date = datetime.strptime(run["run_date"], "%Y-%m-%d")
        if run_date > cutoff:
            continue

        for pick in run["picks"]:
            try:
                ticker = pick["ticker"]
                # Schwab/Polygon/archive → yfinance fallback
                data = None
                try:
                    from data_archive import load_ticker as _alt
                    _df = _alt(ticker)
                    if _df is not None and not _df.empty:
                        if _df.index.tz is not None:
                            _df.index = _df.index.tz_localize(None)
                        import pandas as _pd
                        _start = _pd.Timestamp(run["run_date"])
                        data = _df[_df.index >= _start].head(hold_days + 2)
                except Exception:
                    pass
                if data is None or data.empty or len(data) < 2:
                    data = yf.download(ticker, start=run["run_date"],
                                       period=f"{hold_days + 2}d",
                                       progress=False)
                if data is None or data.empty or len(data) < 2:
                    continue

                entry = pick["entry_price"]
                close_vals = data["Close"].values.flatten()
                exit_price = float(close_vals[min(hold_days, len(close_vals) - 1)])

                if pick["direction"] == "long":
                    pct_chg = ((exit_price - entry) / entry) * 100
                else:
                    pct_chg = ((entry - exit_price) / entry) * 100

                # CTRA-class data hygiene (2026-05-11): pct_chg > 100% in
                # a 5-10d swing window is essentially always a data bug —
                # unadjusted stock split, ticker re-use, or bad bar from
                # the data source. Same class as the CAR target-spike issue.
                # Skip the trade outright (don't record poisoned outcomes
                # into picks_history.json — they'd corrupt setup-family
                # WR multipliers and entry_quality stratified analysis).
                if abs(pct_chg) > 100:
                    log.warning(
                        f"Skipping outlier trade for {pick.get('ticker')}: "
                        f"pct_chg={pct_chg:.2f}% (entry={entry:.2f}, "
                        f"exit={exit_price:.2f}) — likely split/data bug, "
                        f"verify ticker history before re-recording"
                    )
                    continue

                # MFE/MAE: max favorable / adverse excursion during hold period
                high_vals = data["High"].values.flatten() if "High" in data else close_vals
                low_vals  = data["Low"].values.flatten()  if "Low"  in data else close_vals
                period_slice = slice(0, min(hold_days + 1, len(close_vals)))
                if pick["direction"] == "long":
                    mfe = round((max(high_vals[period_slice]) - entry) / entry * 100, 2)
                    mae = round((min(low_vals[period_slice])  - entry) / entry * 100, 2)
                else:
                    mfe = round((entry - min(low_vals[period_slice]))  / entry * 100, 2)
                    mae = round((entry - max(high_vals[period_slice])) / entry * 100, 2)

                # Fix #31: Compute realized_R and slippage_pct
                # realized_R = actual gain/loss divided by planned risk (stop distance)
                _planned_risk = abs(entry - float(pick.get("stop", entry * 0.98) or entry * 0.98))
                if _planned_risk > 0:
                    if pick["direction"] == "long":
                        realized_r = round((exit_price - entry) / _planned_risk, 2)
                    else:
                        realized_r = round((entry - exit_price) / _planned_risk, 2)
                else:
                    realized_r = 0.0

                # slippage_pct = difference between planned entry and actual fill
                # In tracker context, entry_price IS the planned price from the signal;
                # actual fill would come from broker data. We record 0.0 as placeholder
                # until broker integration provides actual fill prices.
                slippage_pct = 0.0

                # Compute exit_date (entry_date + hold_days business days) for
                # Phase-9-compatible schema consumers (MAE/MFE re-compute etc.)
                from datetime import datetime as _dt, timedelta as _td
                _e_dt = _dt.strptime(run["run_date"], "%Y-%m-%d")
                _x_dt = _e_dt
                _added = 0
                while _added < hold_days:
                    _x_dt += _td(days=1)
                    if _x_dt.weekday() < 5:
                        _added += 1

                trade = {
                    "run_date":        run["run_date"],
                    "run_time":        run.get("run_time", ""),
                    "entry_date":      run["run_date"],
                    "exit_date":       _x_dt.strftime("%Y-%m-%d"),
                    "ticker":          ticker,
                    "direction":       pick["direction"],
                    "verdict":         pick.get("verdict", "BUY"),
                    "setup_type":      pick.get("setup_type", ""),
                    "regime":          pick.get("regime", run.get("regime", "unknown")),
                    "entry_price":     entry,
                    "exit_price":      round(exit_price, 2),
                    "pct_chg":         round(pct_chg, 2),
                    "pnl_pct":         round(pct_chg, 2),
                    "win":             pct_chg > 0,
                    "score":           pick["score"],
                    "rr_ratio":        pick.get("rr_ratio"),
                    "hold_days":       hold_days,
                    "mfe":             mfe,
                    "mae":             mae,
                    "mfe_pct":         mfe,
                    "mae_pct":         mae,
                    # Fix #31: realized R-multiple and slippage tracking
                    "realized_r":      realized_r,
                    "slippage_pct":    slippage_pct,
                    "planned_risk":    round(_planned_risk, 2),
                    # Phase 9 attribution fields
                    "setup_family":    pick.get("setup_family", ""),
                    "catalyst_tier":   pick.get("catalyst_tier", 3),
                    "entry_quality":   pick.get("entry_quality", ""),
                    "entry_subtype":   pick.get("entry_subtype", ""),
                    "regime4":         pick.get("regime4", pick.get("regime", "unknown")),
                    "sector":          pick.get("sector", ""),
                    "industry":        pick.get("industry", ""),
                    "conviction_tier": pick.get("conviction_tier", ""),
                    # AI-15: market context snapshot at entry
                    "market_vix":      pick.get("market_vix"),
                    "market_breadth":  pick.get("market_breadth"),
                    "market_spy":      pick.get("market_spy"),
                    "market_spy_1m":   pick.get("market_spy_1m"),
                    "market_dist_days": pick.get("market_dist_days"),
                    # Audit ranking flaw #16/#17: per-pillar breakdown
                    "tech_score":    (pick.get("scoring_breakdown") or {}).get("tech_score"),
                    "cat_score":     (pick.get("scoring_breakdown") or {}).get("cat_score"),
                    "rs_score":      (pick.get("scoring_breakdown") or {}).get("rs_score"),
                    "sm_score":      (pick.get("scoring_breakdown") or {}).get("sm_score"),
                    "qg_score":      (pick.get("scoring_breakdown") or {}).get("qg_score"),
                    "raw_total":     (pick.get("scoring_breakdown") or {}).get("raw_total"),
                    "wr_multiplier": (pick.get("scoring_breakdown") or {}).get("wr_multiplier"),
                    "bonus_total":   (pick.get("scoring_breakdown") or {}).get("bonus_total"),
                }
                history["trades"].append(trade)
                evaluated += 1

            except Exception as e:
                log.warning(f"Failed to evaluate {pick.get('ticker')}: {e}")

        run["evaluated"] = True

    _save_history(history)
    # Invalidate setup stats cache since new completed trades were added
    if evaluated > 0:
        global _stats_by_setup_cache
        _stats_by_setup_cache = None
    return evaluated


def backfill_trade_attribution() -> dict:
    """
    One-time helper for Bug D/E: enrich existing closed trades in
    cache/picks_history.json with Phase 9 attribution fields that were
    dropped at promotion time (before evaluate_pending copied them).

    Matches closed trades to their source pick by (ticker, run_date) and
    copies setup_family, regime, regime4, catalyst_tier, entry_quality,
    entry_subtype, sector, industry, conviction_tier, and the market_* snapshot
    fields. Only fills missing/empty/unknown values — never overwrites good
    data. Returns a summary dict of counts before/after.
    """
    ATTR_FIELDS = [
        "setup_family", "regime", "regime4", "catalyst_tier",
        "entry_quality", "entry_subtype", "sector", "industry",
        "conviction_tier",
        "market_vix", "market_breadth", "market_spy",
        "market_spy_1m", "market_dist_days",
    ]

    history = _load_history()
    trades = history.get("trades", [])
    runs = history.get("runs", [])

    # Build lookup: (run_date, ticker) -> pick dict (merged across run_time
    # variants for that date; last-write wins so we prefer later richer data).
    pick_index: dict[tuple[str, str], dict] = {}
    for r in runs:
        rd = r.get("run_date")
        for p in r.get("picks", []):
            key = (rd, p.get("ticker"))
            if key in pick_index:
                # Merge: prefer non-empty values
                merged = dict(pick_index[key])
                for k, v in p.items():
                    if v not in (None, "", "unknown") or k not in merged:
                        merged[k] = v
                pick_index[key] = merged
            else:
                pick_index[key] = dict(p)

    def _is_empty(v) -> bool:
        if v is None:
            return True
        if isinstance(v, str) and v.strip() in ("", "unknown"):
            return True
        return False

    before = {f: sum(1 for t in trades if not _is_empty(t.get(f))) for f in ATTR_FIELDS}
    enriched = 0
    unmatched: list[tuple[str, str]] = []

    for t in trades:
        key = (t.get("run_date"), t.get("ticker"))
        src = pick_index.get(key)
        if not src:
            unmatched.append(key)
            continue
        touched = False
        for f in ATTR_FIELDS:
            cur = t.get(f)
            new = src.get(f)
            if _is_empty(cur) and not _is_empty(new):
                t[f] = new
                touched = True
            elif f not in t:
                # Ensure key exists for downstream analytics
                t[f] = new if new is not None else ("" if f != "catalyst_tier" else 3)
                touched = True
        # Fallback defaults so downstream code never hits None where a string
        # or int is expected. Normalize None/missing -> default.
        _defaults = {
            "setup_family": "", "regime": "unknown",
            "regime4": t.get("regime") or "unknown",
            "catalyst_tier": 3, "entry_quality": "",
            "entry_subtype": "", "sector": "", "industry": "",
            "conviction_tier": "",
        }
        for _k, _dv in _defaults.items():
            if t.get(_k) in (None, ""):
                if _k == "catalyst_tier" and t.get(_k) is not None:
                    continue
                t[_k] = _dv
        if touched:
            enriched += 1

    after = {f: sum(1 for t in trades if not _is_empty(t.get(f))) for f in ATTR_FIELDS}

    _save_history(history)
    return {
        "total_trades": len(trades),
        "enriched": enriched,
        "unmatched": unmatched,
        "before": before,
        "after": after,
    }


def compute_stats(min_trades: int = 5) -> dict:
    """Compute performance statistics from trade history."""
    history = _load_history()
    trades = history.get("trades", [])

    if len(trades) < min_trades:
        return {
            "sufficient_data": False,
            "total_trades": len(trades),
            "min_required": min_trades
        }

    wins = [t for t in trades if t["win"]]
    losses = [t for t in trades if not t["win"]]

    win_pcts = [t["pct_chg"] for t in wins]
    loss_pcts = [t["pct_chg"] for t in losses]

    avg_win = sum(win_pcts) / len(win_pcts) if win_pcts else 0
    avg_loss = sum(loss_pcts) / len(loss_pcts) if loss_pcts else 0

    gross_wins = sum(win_pcts)
    gross_losses = abs(sum(loss_pcts))
    profit_factor = gross_wins / gross_losses if gross_losses > 0 else float("inf")

    # Best streak
    streak, best_streak = 0, 0
    for t in trades:
        if t["win"]:
            streak += 1
            best_streak = max(best_streak, streak)
        else:
            streak = 0

    best_trade = max(trades, key=lambda t: t["pct_chg"]) if trades else None
    worst_trade = min(trades, key=lambda t: t["pct_chg"]) if trades else None

    # Vinod expert review: separate long vs short P&L tracking
    def _direction_stats(subset: list[dict]) -> dict:
        if not subset:
            return {"trades": 0, "wins": 0, "win_rate": 0.0, "avg_win": 0.0,
                    "avg_loss": 0.0, "profit_factor": 0.0, "gross_pnl": 0.0}
        _w = [t for t in subset if t["win"]]
        _l = [t for t in subset if not t["win"]]
        _wp = [t["pct_chg"] for t in _w]
        _lp = [t["pct_chg"] for t in _l]
        _gw = sum(_wp); _gl = abs(sum(_lp))
        return {
            "trades": len(subset),
            "wins": len(_w),
            "losses": len(_l),
            "win_rate": round(len(_w) / len(subset) * 100, 1),
            "avg_win": round(sum(_wp)/len(_wp), 2) if _wp else 0.0,
            "avg_loss": round(sum(_lp)/len(_lp), 2) if _lp else 0.0,
            "profit_factor": round(_gw/_gl, 2) if _gl > 0 else float("inf"),
            "gross_pnl": round(_gw - _gl, 2),
        }

    longs  = [t for t in trades if str(t.get("direction", "long")).lower() == "long"]
    shorts = [t for t in trades if str(t.get("direction", "long")).lower() == "short"]

    return {
        "sufficient_data": True,
        "total_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(trades) * 100, 1),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "profit_factor": round(profit_factor, 2),
        "gross_pnl": round(gross_wins - gross_losses, 2),
        "best_streak": best_streak,
        "best_trade": best_trade,
        "worst_trade": worst_trade,
        "by_direction": {
            "long":  _direction_stats(longs),
            "short": _direction_stats(shorts),
        },
    }


# ---------------------------------------------------------------------------
# Win-rate feedback loop — per setup / regime breakdown
# ---------------------------------------------------------------------------

# Module-level cache so we don't re-read disk on every analyze_ticker call
_stats_by_setup_cache: dict | None = None


# ---------------------------------------------------------------------------
# Audit #8 — Wilson-score confidence intervals for win-rate reporting
# ---------------------------------------------------------------------------

def wilson_ci(wins: int, total: int, confidence: float = 0.95) -> tuple[float, float]:
    """Wilson score interval for WR. Returns (lo, hi) as decimals."""
    import math
    if total == 0:
        return (0.0, 1.0)
    z_map = {0.90: 1.645, 0.95: 1.96, 0.99: 2.576}
    z = z_map.get(confidence, 1.96)
    phat = wins / total
    denom = 1 + z * z / total
    center = (phat + z * z / (2 * total)) / denom
    spread = z * math.sqrt((phat * (1 - phat) + z * z / (4 * total)) / total) / denom
    return (max(0.0, center - spread), min(1.0, center + spread))


def ci_width_pct(wins: int, total: int, confidence: float = 0.95) -> float:
    """Width of CI in percentage points (hi - lo)."""
    lo, hi = wilson_ci(wins, total, confidence)
    return round((hi - lo) * 100, 1)


def _reliability_label(n: int, ci_width_pp: float) -> str:
    """Classify a WR bucket's statistical reliability."""
    if n >= 100 and ci_width_pp < 10:
        return "high"
    if n >= 30:
        return "medium"
    return "low"


def _group_stats(completed: list[dict]) -> dict:
    """
    Given a list of completed trade dicts (each must have 'win', 'pct_chg',
    'setup_type', 'regime'), return a stats summary dict keyed by an arbitrary
    group key.  Returns a dict mapping key → stats sub-dict.
    """
    from collections import defaultdict

    groups: dict[str, list] = defaultdict(list)
    for t in completed:
        yield_key = t.get("_group_key", "unknown")
        groups[yield_key].append(t)

    result = {}
    for key, items in groups.items():
        wins   = [i for i in items if i["win"]]
        losses = [i for i in items if not i["win"]]
        # R-multiple: use pct_chg as a proxy (no per-trade stop stored)
        win_pcts  = [i["pct_chg"] for i in wins  if i.get("pct_chg") is not None and not _is_nan(i["pct_chg"])]
        loss_pcts = [i["pct_chg"] for i in losses if i.get("pct_chg") is not None and not _is_nan(i["pct_chg"])]
        avg_r     = round(sum(win_pcts + loss_pcts) / len(win_pcts + loss_pcts), 2) if (win_pcts or loss_pcts) else 0.0
        gross_w   = sum(win_pcts)
        gross_l   = abs(sum(loss_pcts))
        pf        = round(gross_w / gross_l, 2) if gross_l > 0 else (float("inf") if gross_w > 0 else 0.0)
        n_items = len(items)
        n_wins  = len(wins)
        wr_lo, wr_hi = wilson_ci(n_wins, n_items, 0.95)
        ci_width = round((wr_hi - wr_lo) * 100, 1)
        result[key] = {
            "trades":        n_items,
            "wins":          n_wins,
            "win_rate":      round(n_wins / n_items, 4) if items else 0.0,
            "avg_r":         avg_r,
            "profit_factor": pf,
            # Audit #8 — statistical confidence fields (backward-compatible additions)
            "wr_low_95":     round(wr_lo, 4),
            "wr_high_95":    round(wr_hi, 4),
            "ci_width_pp":   ci_width,
            "reliability":   _reliability_label(n_items, ci_width),
        }
    return result


def _is_nan(v) -> bool:
    """Return True if v is float NaN (avoids importing math at module level)."""
    try:
        return v != v  # NaN is the only float where self != self
    except Exception:
        return False


def compute_stats_by_setup(history: list[dict] | None = None) -> dict:
    """
    Break down win rate and avg return by setup type AND market regime.

    Returns:
        {
            "by_setup": {
                "VCP": {"trades": 5, "wins": 3, "win_rate": 0.60, "avg_r": 1.8, "profit_factor": 2.1},
                ...
            },
            "by_regime": {
                "bull":    {"trades": 20, "wins": 14, "win_rate": 0.70, "avg_r": 2.2, ...},
                "neutral": {...},
                "bear":    {...},
            },
            "by_setup_regime": {
                "VCP_bull": {"trades": 3, "wins": 2, "win_rate": 0.67, "avg_r": 2.0, ...},
                ...
            },
            "best_setups":  [{"setup": "VCP", "regime": "bull", "win_rate": 0.67, ...}, ...],
            "worst_setups": [...],
            "display_rows": [...],  # formatted for HTML History tab
            "total_trades": int,
            "enough_data":  bool,  # True if >= 20 completed trades
        }
    """
    global _stats_by_setup_cache

    # Use cached result if already computed this process lifetime
    if _stats_by_setup_cache is not None:
        return _stats_by_setup_cache

    raw_history = _load_history()

    # Build a lookup: (run_date, ticker) → pick metadata (setup_type, regime, verdict)
    # 2026-05-11 (TRACKER-BUY-FILTER): also track verdict so we can exclude
    # WATCH-stage outcomes from per-setup stats. WATCH picks get tracked but
    # never traded — their outcomes shouldn't bias setup_score_multiplier
    # decisions. Per OPERATING MINDSET principle 16 (per-substrategy attribution).
    pick_meta: dict[tuple, dict] = {}
    for run in raw_history.get("runs", []):
        run_regime = run.get("regime", "unknown")
        for pick in run.get("picks", []):
            key = (run["run_date"], pick["ticker"])
            pick_meta[key] = {
                "setup_type": pick.get("setup_type", "unknown") or "unknown",
                "regime":     (pick.get("regime") or run_regime or "unknown").lower(),
                "verdict":    (pick.get("verdict") or "").upper(),
            }

    # Filter to completed trades only (have a real exit_price that is not NaN).
    # 2026-05-11: ALSO filter to verdict=BUY (or SHORT for shorts). WATCH
    # picks are tracked-but-never-traded; including their outcomes biases
    # setup multipliers. Audit (n=763) showed signal_log includes WATCH at
    # ~45% of records — same bias here.
    raw_trades = raw_history.get("trades", [])
    completed: list[dict] = []
    n_excluded_watch = 0
    for t in raw_trades:
        ep = t.get("exit_price")
        pc = t.get("pct_chg")
        if ep is None or _is_nan(ep) or pc is None or _is_nan(pc):
            continue  # not yet evaluated or bad data
        key = (t.get("run_date", ""), t.get("ticker", ""))
        meta = pick_meta.get(key, {})
        # TRACKER-BUY-FILTER (2026-05-11): drop WATCH-stage outcomes.
        # Trades with no meta (older runs predating verdict field) are kept
        # for back-compat. SHORT trades kept for short attribution.
        verdict = meta.get("verdict", "")
        if verdict and verdict not in ("BUY", "SHORT"):
            n_excluded_watch += 1
            continue
        completed.append({
            **t,
            "setup_type": meta.get("setup_type", "unknown") or "unknown",
            "regime":     meta.get("regime", "unknown"),
            "verdict":    verdict or "BUY",  # back-compat: default to BUY for old trades
        })
    if n_excluded_watch:
        log.debug(f"compute_stats_by_setup: excluded {n_excluded_watch} WATCH-stage outcomes")

    total = len(completed)
    enough_data = total >= 20

    # ── by_setup ─────────────────────────────────────────────────────────────
    for t in completed:
        t["_group_key"] = t["setup_type"]
    by_setup = _group_stats(completed)

    # ── by_regime ────────────────────────────────────────────────────────────
    for t in completed:
        t["_group_key"] = t["regime"]
    by_regime = _group_stats(completed)

    # ── by_setup_regime ──────────────────────────────────────────────────────
    for t in completed:
        t["_group_key"] = f"{t['setup_type']}_{t['regime']}"
    by_setup_regime = _group_stats(completed)

    # ── by_setup_family (Phase 9) ────────────────────────────────────────────
    for t in completed:
        t["_group_key"] = t.get("setup_family") or "Unknown"
    by_setup_family = _group_stats(completed)

    # ── by_catalyst_tier ─────────────────────────────────────────────────────
    for t in completed:
        t["_group_key"] = f"T{t.get('catalyst_tier', 3)}"
    by_catalyst_tier = _group_stats(completed)

    # ── by_entry_quality ─────────────────────────────────────────────────────
    for t in completed:
        t["_group_key"] = t.get("entry_quality") or "Unknown"
    by_entry_quality = _group_stats(completed)

    # ── by_conviction_tier ───────────────────────────────────────────────────
    for t in completed:
        t["_group_key"] = t.get("conviction_tier") or "Unknown"
    by_conviction_tier = _group_stats(completed)

    # ── by_regime4 ───────────────────────────────────────────────────────────
    for t in completed:
        t["_group_key"] = t.get("regime4") or t.get("regime") or "unknown"
    by_regime4 = _group_stats(completed)

    # ── by_sector ────────────────────────────────────────────────────────────
    for t in completed:
        t["_group_key"] = t.get("sector") or "Unknown"
    by_sector = _group_stats(completed)

    # Clean up temporary key
    for t in completed:
        t.pop("_group_key", None)

    # ── best / worst setups (min 3 trades, sorted by win_rate) ───────────────
    combo_list = []
    for combo_key, stats in by_setup_regime.items():
        if stats["trades"] < 3:
            continue
        parts = combo_key.rsplit("_", 1)
        setup_name = parts[0] if len(parts) == 2 else combo_key
        regime_name = parts[1] if len(parts) == 2 else "unknown"
        combo_list.append({
            "setup":      setup_name,
            "regime":     regime_name,
            "win_rate":   stats["win_rate"],
            "avg_r":      stats["avg_r"],
            "trades":     stats["trades"],
            "profit_factor": stats["profit_factor"],
        })

    combo_list_sorted = sorted(combo_list, key=lambda x: x["win_rate"], reverse=True)
    best_setups  = combo_list_sorted[:3]
    worst_setups = list(reversed(combo_list_sorted))[:3]

    # ── display_rows (for HTML History tab) ──────────────────────────────────
    display_rows = []
    for setup_key, stats in sorted(by_setup.items(), key=lambda x: -x[1]["trades"]):
        wr = stats["win_rate"]
        if wr > 0.55:
            edge = "positive"
        elif wr >= 0.45:
            edge = "neutral"
        else:
            edge = "negative"
        display_rows.append({
            "setup":         setup_key,
            "regime":        "all",
            "trades":        stats["trades"],
            "win_rate_pct":  f"{round(wr * 100):.0f}%",
            "avg_r":         f"{stats['avg_r']:.1f}R",
            "profit_factor": f"{stats['profit_factor']:.1f}x" if stats["profit_factor"] != float("inf") else "inf",
            "edge":          edge,
        })

    result = {
        "by_setup":          by_setup,
        "by_regime":         by_regime,
        "by_setup_regime":   by_setup_regime,
        "by_setup_family":   by_setup_family,
        "by_catalyst_tier":  by_catalyst_tier,
        "by_entry_quality":  by_entry_quality,
        "by_conviction_tier":by_conviction_tier,
        "by_regime4":        by_regime4,
        "by_sector":         by_sector,
        "best_setups":       best_setups,
        "worst_setups":      worst_setups,
        "display_rows":      display_rows,
        "total_trades":      total,
        "enough_data":       enough_data,
    }

    _stats_by_setup_cache = result
    return result


def get_setup_weight_multiplier(setup_type: str, regime: str) -> float:
    """
    Return a **sizing** weight multiplier (0.7–1.3) based on historical win rate
    for this setup + regime combination.

    Semantics (after 2026-04-15 hardening, checklist 7.3):
      - This multiplier is SIZING-ONLY. It does NOT affect score or threshold.
      - Consumers: compute_position_size / result['sizing_multiplier'].
      - The backtest `_score_as_of` path still calls apply_setup_wr_multiplier
        for historical parity with pre-hardening data; live scoring does not.

    Thresholds (require >= 5 trades to adjust, 3–4 trades for neutral):
      win_rate >= 70% AND >= 5 trades → 1.3x
      win_rate >= 60% AND >= 5 trades → 1.1x
      win_rate  50–60%                → 1.0x (neutral)
      win_rate  40–50%                → 0.9x
      win_rate  < 40% AND >= 5 trades → 0.7x
      < 3 trades OR not enough global data → 1.0x
    """
    stats = compute_stats_by_setup()

    # Not enough global data — no adjustment
    if not stats["enough_data"]:
        return 1.0

    regime_clean = (regime or "unknown").lower()
    setup_clean  = (setup_type or "unknown").strip()

    # Prefer the specific setup+regime combo; fall back to setup-only stats
    combo_key = f"{setup_clean}_{regime_clean}"
    combo     = stats["by_setup_regime"].get(combo_key)
    setup_only = stats["by_setup"].get(setup_clean)

    # Pick the most specific bucket with enough trades
    target = None
    if combo and combo["trades"] >= 3:
        target = combo
    elif setup_only and setup_only["trades"] >= 3:
        target = setup_only

    if target is None:
        return 1.0

    wr     = target["win_rate"]
    n      = target["trades"]
    min5   = n >= 5

    if wr >= 0.70 and min5:
        return 1.3
    if wr >= 0.60 and min5:
        return 1.1
    if wr >= 0.50:
        return 1.0
    if wr >= 0.40:
        return 0.9
    if wr < 0.40 and min5:
        return 0.7
    return 1.0


def get_recent_picks(n: int = 10) -> list[dict]:
    """Return the most recent N picks across all runs."""
    history = _load_history()
    all_picks = []
    for run in reversed(history.get("runs", [])):
        for pick in run["picks"]:
            pick["run_date"] = run["run_date"]
            pick["run_time"] = run.get("run_time", "")
            all_picks.append(pick)
            if len(all_picks) >= n:
                return all_picks
    return all_picks


def mark_to_market() -> list[dict]:
    """
    Compute live multi-period returns for ALL picks (not just evaluated ones).
    Returns a list of dicts, one per pick, with D1–D5, W1, W2, Month columns.
    Downloads current prices in one batch for speed.
    """
    history = _load_history()
    all_picks = []
    for run in history.get("runs", []):
        for p in run.get("picks", []):
            all_picks.append({**p, "run_date": run["run_date"],
                                    "run_time": run.get("run_time", "")})

    if not all_picks:
        return []

    # Collect unique tickers + run_dates
    tickers = list({p["ticker"] for p in all_picks})

    # Load from data archive (instant) instead of Yahoo (rate-limited)
    import pandas as _pd
    try:
        from data_archive import load_ticker as _archive_load
        all_frames = {}
        for t in tickers:
            df = _archive_load(t)
            if df is not None and "Close" in df.columns:
                c = df["Close"].squeeze().copy()
                # Strip timezone so comparisons with tz-naive dates work
                if c.index.tz is not None:
                    c.index = c.index.tz_localize(None)
                all_frames[t] = c
        if not all_frames:
            log.warning("mark_to_market: no data from archive")
            return []
        closes = _pd.DataFrame(all_frames)
    except Exception as e:
        log.warning(f"mark_to_market archive load failed: {e}, falling back to Yahoo")
        # Fallback to Yahoo
        earliest = min(p["run_date"] for p in all_picks)
        try:
            raw = yf.download(tickers[:50], start=earliest, progress=False, auto_adjust=True)
            if isinstance(raw.columns, _pd.MultiIndex):
                closes = raw["Close"]
            else:
                closes = raw[["Close"]]
        except Exception:
            return []
    closes = closes.loc[:, ~closes.columns.duplicated()]

    # Fetch LIVE current prices so "today" bar fills even when archive is stale.
    # Use the proper vendor-failover chain (Polygon primary → archive → yfinance last).
    # Falls back to raw yfinance if data_fetcher unavailable (e.g., in tests).
    live_prices: dict = {}
    try:
        import pandas as _pd
        try:
            from data_fetcher import fetch_ohlcv_with_failover
            for t in tickers[:100]:
                try:
                    df_live, _tier = fetch_ohlcv_with_failover(t, days=2)
                    if df_live is not None and "Close" in df_live.columns and not df_live.empty:
                        last_idx = df_live.index[-1]
                        if hasattr(last_idx, "tz") and last_idx.tz is not None:
                            last_idx = last_idx.tz_localize(None)
                        live_prices[t] = (last_idx, float(df_live["Close"].iloc[-1]))
                except Exception:
                    continue
        except ImportError:
            # Fallback: EODHD batch real-time quotes (15-min delayed)
            try:
                import eodhd_client as _eod
                rt = _eod.real_time(tickers[:500])
                rows = rt if isinstance(rt, list) else ([rt] if isinstance(rt, dict) else [])
                for q in rows:
                    code = (q.get("code") or "").split(".")[0].upper()
                    px = q.get("close") or q.get("previousClose")
                    if code and px and px != "NA":
                        try:
                            live_prices[code] = (_pd.Timestamp.now().normalize(), float(px))
                        except (ValueError, TypeError):
                            pass
            except Exception:
                pass
    except Exception as _live_err:
        log.warning(f"mark_to_market live-fetch failed (archive-only mode): {_live_err}")

    # Compute returns at each period
    # D1 = same-day close (offset 0) — entry is from morning scan, D1 shows EOD return
    # D2 = next trading day close, etc.
    PERIODS = [
        ("D1", 0), ("D2", 1), ("D3", 2), ("D4", 3), ("D5", 4),
        ("W1", 4), ("W2", 9), ("M1", 20),
    ]

    results = []
    for p in all_picks:
        ticker = p["ticker"]
        run_date = p["run_date"]
        entry = p["entry_price"]
        direction = p.get("direction", "long")
        verdict = p.get("verdict", "?")
        score = p.get("score", 0)

        import pandas as _pd

        # Base row — always created even if no archive data
        row = {
            "ticker": ticker, "run_date": run_date,
            "run_time": p.get("run_time", ""),
            "entry": entry,
            "direction": direction, "verdict": verdict, "score": score,
            "setup": p.get("setup_type", ""),
            "setup_family": p.get("setup_family", ""),
            "conviction_tier": p.get("conviction_tier", ""),
        }

        # Days since entry
        today = _pd.Timestamp.now().normalize()
        entry_ts = _pd.Timestamp(run_date)
        row["age_days"] = (today - entry_ts).days

        if ticker not in closes.columns:
            # No archive data — use live price for current_pct only, D1-M1 = None
            live_px = live_prices.get(ticker, (None, None))[1] if ticker in live_prices else None
            if live_px and entry:
                if direction == "long":
                    row["current_pct"] = round((live_px - entry) / entry * 100, 2)
                else:
                    row["current_pct"] = round((entry - live_px) / entry * 100, 2)
                row["current_price"] = round(live_px, 2)
            else:
                row["current_pct"] = 0.0
                row["current_price"] = entry
            for label, _ in PERIODS:
                row[label] = None
            results.append(row)
            continue

        col = closes[ticker].dropna()

        # Splice live price onto archive FIRST so run_date==today resolves correctly
        live_ts, live_px = (None, None)
        if ticker in live_prices:
            live_ts, live_px = live_prices[ticker]
        if live_ts is not None and len(col) > 0 and live_ts > col.index[-1]:
            col = _pd.concat([col, _pd.Series([live_px], index=[_pd.Timestamp(live_ts)])])

        # Find entry index on the spliced series: last trading day ≤ run_date.
        try:
            ts = _pd.Timestamp(run_date)
            bwd_mask = col.index <= ts
            if bwd_mask.any():
                entry_idx = col.index.get_loc(col.index[bwd_mask][-1])
            else:
                for label, _ in PERIODS:
                    row[label] = None
                row["current_pct"] = 0.0
                row["current_price"] = entry
                results.append(row)
                continue
        except Exception:
            for label, _ in PERIODS:
                row[label] = None
            row["current_pct"] = 0.0
            row["current_price"] = entry
            results.append(row)
            continue

        # Current price (prefer live)
        cur_price = float(col.iloc[-1])
        if direction == "long":
            row["current_pct"] = round((cur_price - entry) / entry * 100, 2)
        else:
            row["current_pct"] = round((entry - cur_price) / entry * 100, 2)
        row["current_price"] = round(cur_price, 2)

        # Multi-period returns
        for label, days in PERIODS:
            idx = entry_idx + days
            if idx < len(col):
                px = float(col.iloc[idx])
                if direction == "long":
                    ret = round((px - entry) / entry * 100, 2)
                else:
                    ret = round((entry - px) / entry * 100, 2)
                row[label] = ret
            else:
                row[label] = None  # not enough data yet

        results.append(row)

    # Sort: newest first, then by score desc
    results.sort(key=lambda r: (r["run_date"], -r["score"]), reverse=True)
    return results


def get_full_history() -> dict:
    """Return the full run + trade history for dashboard display."""
    history = _load_history()
    runs    = list(reversed(history.get("runs",   [])))  # newest first
    trades  = history.get("trades", [])

    # Build a lookup: (run_date, ticker) → evaluated trade outcome
    outcome_map: dict[tuple, dict] = {}
    for t in trades:
        outcome_map[(t["run_date"], t["ticker"])] = t

    # Annotate each pick with its outcome (if evaluated)
    enriched_runs = []
    for run in runs:
        picks = []
        for p in run.get("picks", []):
            outcome = outcome_map.get((run["run_date"], p["ticker"]))
            picks.append({**p, "outcome": outcome})
        enriched_runs.append({
            "run_date":  run["run_date"],
            "run_time":  run.get("run_time", ""),
            "evaluated": run.get("evaluated", False),
            "num_picks": run.get("num_picks", len(picks)),
            "picks":     picks,
        })

    return {
        "runs":   enriched_runs,
        "trades": trades,
    }


# ---------------------------------------------------------------------------
# Dedup analytics (HARDENING 3.5)
# ---------------------------------------------------------------------------

def get_new_buy_count(days: int = 7) -> dict:
    """Count first-time BUYs (dedup'd) vs raw BUY count over the last `days`.

    Reads from the signal_log (which now carries `is_new_buy`), plus
    decision_log as a fallback if a caller wants broader verdict-level stats.

    Returns:
        {
          "window_days": int,
          "raw_total": int,    # all BUYs logged in window
          "new_total": int,    # where is_new_buy == True
          "dedup_ratio": float # new_total / raw_total (0..1); 0 if raw_total=0
        }
    """
    try:
        import signal_tracker as _st
        entries = _st._load_log()
    except Exception as exc:
        log.warning(f"get_new_buy_count: cannot load signal log: {exc}")
        entries = []

    today = datetime.now().date()
    cutoff = today - timedelta(days=max(days - 1, 0))

    raw_total = 0
    new_total = 0
    for e in entries:
        try:
            d = datetime.strptime(e.get("date", ""), "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue
        if d < cutoff:
            continue
        raw_total += 1
        if e.get("is_new_buy") is True:
            new_total += 1

    dedup_ratio = round(new_total / raw_total, 4) if raw_total else 0.0
    return {
        "window_days": days,
        "raw_total": raw_total,
        "new_total": new_total,
        "dedup_ratio": dedup_ratio,
    }
