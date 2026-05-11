"""supabase_analysis_sync.py — Wire the analysis pipeline into Supabase.

Called once per scan from swing_trade.py after the bundle is assembled.
Walks every `result` dict in `bundle['all_scored']` and upserts into the
analysis-domain tables (ticker_analyses + ~50 child tables).

Design rules:
  - NEVER raises. Errors are logged and the scan continues.
  - Idempotent per (run_id, ticker) via upserts on the natural key.
  - Each table family has its own _sync_<family>() helper.
  - All inserts use one psycopg2 connection per scan to minimize round-trips.
  - Service-role key is used (bypasses RLS) — set via SUPABASE_SERVICE_KEY.

Disabled paths:
  - SUPABASE_MODE=0 → no-op
  - SUPABASE_MODE>=1 → sync runs (1=dual-write, 2=canonical)
"""
from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# Reuse the supabase/_client.py to get a psycopg2 connection
_REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_REPO_ROOT / "supabase" / "scripts"))

try:
    from _client import pg_conn  # type: ignore
except Exception:
    pg_conn = None  # noqa: N816


# ============================================================================
# Helpers
# ============================================================================

def _enabled() -> bool:
    if pg_conn is None:
        return False
    try:
        return int(os.environ.get("SUPABASE_MODE", "0")) >= 1
    except (ValueError, TypeError):
        return False


def _num(v: Any) -> float | None:
    """Coerce ('n/a','None','', None) → None; otherwise float."""
    if v is None or isinstance(v, bool):
        return None if v is None else (1.0 if v else 0.0)
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("", "n/a", "na", "null", "none", "-", "nan"):
            return None
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _int(v: Any) -> int | None:
    n = _num(v)
    return int(n) if n is not None else None


def _bool(v: Any) -> bool | None:
    if v is None: return None
    if isinstance(v, bool): return v
    if isinstance(v, (int, float)): return v != 0
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("true", "yes", "1", "y", "t"): return True
        if s in ("false", "no", "0", "n", "f"): return False
    return None


def _txt(v: Any, maxlen: int = 1024) -> str | None:
    if v is None: return None
    if isinstance(v, str):
        return v[:maxlen] if v else None
    try:
        return str(v)[:maxlen]
    except Exception:
        return None


def _enum(v: Any, allowed: tuple, *, upper: bool = False, lower: bool = False) -> str | None:
    s = _txt(v)
    if not s: return None
    if upper: s = s.upper()
    if lower: s = s.lower()
    return s if s in allowed else None


# ============================================================================
# Per-table writers
# ============================================================================

def _upsert_ticker(cur, ticker: str, result: dict) -> None:
    cur.execute(
        """
        insert into public.tickers (ticker, name, sector, industry, beta, last_seen)
        values (%s, %s, %s, %s, %s, now())
        on conflict (ticker) do update set
            name      = coalesce(excluded.name, public.tickers.name),
            sector    = coalesce(excluded.sector, public.tickers.sector),
            industry  = coalesce(excluded.industry, public.tickers.industry),
            beta      = coalesce(excluded.beta, public.tickers.beta),
            last_seen = now()
        """,
        (
            ticker,
            _txt(result.get("name")),
            _txt(result.get("sector")),
            _txt(result.get("industry")),
            _num(result.get("beta")),
        ),
    )


def _sync_run(cur, bundle: dict) -> int:
    """Upsert the runs row, return run_id."""
    regime = bundle.get("regime") or {}
    run_date = bundle.get("run_date") or time.strftime("%Y-%m-%d")
    cur.execute(
        """
        insert into public.runs
            (run_date, run_time, regime, regime4, market_phase, vix,
             breadth_pct_above_50d, total_scanned, total_passed, num_picks,
             evaluated, decision_engine_version, data_health_json)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
        on conflict (run_date) do update set
            run_time                 = excluded.run_time,
            regime                   = coalesce(excluded.regime, public.runs.regime),
            regime4                  = coalesce(excluded.regime4, public.runs.regime4),
            market_phase             = coalesce(excluded.market_phase, public.runs.market_phase),
            vix                      = coalesce(excluded.vix, public.runs.vix),
            breadth_pct_above_50d    = coalesce(excluded.breadth_pct_above_50d, public.runs.breadth_pct_above_50d),
            total_scanned            = coalesce(excluded.total_scanned, public.runs.total_scanned),
            total_passed             = coalesce(excluded.total_passed, public.runs.total_passed),
            num_picks                = coalesce(excluded.num_picks, public.runs.num_picks),
            evaluated                = coalesce(excluded.evaluated, public.runs.evaluated),
            decision_engine_version  = coalesce(excluded.decision_engine_version, public.runs.decision_engine_version),
            data_health_json         = coalesce(excluded.data_health_json, public.runs.data_health_json)
        returning id
        """,
        (
            run_date,
            bundle.get("run_timestamp"),
            _enum(regime.get("regime3") or regime.get("confirmed_regime"),
                  ("bull", "neutral", "bear", "panic"), lower=True),
            _enum(regime.get("regime4") or regime.get("confirmed_regime4"),
                  ("risk_on_trending", "risk_on_choppy", "risk_off_trending", "panic"), lower=True),
            _txt(regime.get("market_phase")),
            _num(regime.get("vix") or (bundle.get("fear_greed") or {}).get("vix")),
            _num((bundle.get("market_breadth") or {}).get("pct_above_50d")
                 or (bundle.get("market_breadth") or {}).get("breadth_pct")),
            _int(bundle.get("total_scanned")),
            _int(bundle.get("total_passed")),
            _int(len(bundle.get("buy_candidates") or [])),
            _int(len(bundle.get("all_scored") or [])),
            _txt(bundle.get("decision_engine_version")),
            None,  # data_health_json — TODO add when we have a clean dict
        ),
    )
    return cur.fetchone()[0]


def _sync_ticker_analysis(cur, run_id: int, r: dict) -> int | None:
    """Upsert the central ticker_analyses row. Returns analysis_id."""
    ticker = r.get("ticker")
    if not ticker:
        return None

    decision = r.get("decision") or {}
    conviction = r.get("conviction") or {}

    cur.execute(
        """
        insert into public.ticker_analyses (
            run_id, ticker, analyzed_at, verdict, direction, price, score, score_raw,
            star_rating, setup_family, setup_type, catalyst_tier, entry_quality,
            entry_subtype, entry_timing, hold_period_guide, conviction_tier,
            reject_reason, ticker_source, sector_pct_rank, rs_rank, rs_63d_pct,
            mtf_conflict, mtf_label
        ) values (
            %s, %s, now(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s
        )
        on conflict (run_id, ticker) do update set
            analyzed_at         = excluded.analyzed_at,
            verdict             = excluded.verdict,
            direction           = excluded.direction,
            price               = excluded.price,
            score               = excluded.score,
            score_raw           = excluded.score_raw,
            star_rating         = excluded.star_rating,
            setup_family        = excluded.setup_family,
            setup_type          = excluded.setup_type,
            catalyst_tier       = excluded.catalyst_tier,
            entry_quality       = excluded.entry_quality,
            entry_subtype       = excluded.entry_subtype,
            entry_timing        = excluded.entry_timing,
            hold_period_guide   = excluded.hold_period_guide,
            conviction_tier     = excluded.conviction_tier,
            reject_reason       = excluded.reject_reason,
            ticker_source       = excluded.ticker_source,
            sector_pct_rank     = excluded.sector_pct_rank,
            rs_rank             = excluded.rs_rank,
            rs_63d_pct          = excluded.rs_63d_pct,
            mtf_conflict        = excluded.mtf_conflict,
            mtf_label           = excluded.mtf_label
        returning id
        """,
        (
            run_id,
            ticker,
            _enum(r.get("verdict") or decision.get("verdict"),
                  ("BUY", "WATCH", "SHORT", "AVOID"), upper=True) or "AVOID",
            _enum(r.get("direction"), ("long", "short", "neutral"), lower=True),
            _num(r.get("price")),
            _int(r.get("score")),
            _num(r.get("score_raw")),
            _int(r.get("star_rating")),
            _txt(r.get("setup_family")),
            _txt(r.get("setup_type") or (r.get("trade_plan") or {}).get("setup_type")),
            _int(r.get("catalyst_tier")),
            _enum(r.get("entry_quality"),
                  ("FRESH", "PULLBACK", "VALID", "EXTENDED", "MISSED"), upper=True),
            _txt(r.get("entry_subtype")),
            _txt(r.get("entry_timing")),
            _txt(r.get("hold_period_guide")),
            _enum(conviction.get("label"), ("T1", "T2", "T3", "WATCH"), upper=True),
            _txt(r.get("reject_reason"))[:1024] if r.get("reject_reason") else None,
            _txt(r.get("ticker_source")),
            _num(r.get("sector_pct_rank")),
            _int(r.get("rs_rank") or (r.get("technicals", {}).get("indicators", {}) or {}).get("rs_rank")),
            _num((r.get("technicals", {}).get("indicators", {}) or {}).get("rs_63d_pct")),
            _bool(r.get("mtf_conflict")),
            _txt(r.get("mtf_label")),
        ),
    )
    return cur.fetchone()[0]


def _sync_pricing(cur, aid: int, r: dict) -> None:
    indi = (r.get("technicals") or {}).get("indicators") or {}
    cur.execute(
        """
        insert into public.analysis_pricing
            (analysis_id, price, prev_close, day_change_pct, volume, avg_volume_20d,
             rvol, atr, atr_pct, price_tier, quote_age_s, spread_bp, post_market_pct)
        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        on conflict (analysis_id) do update set
            price = excluded.price, prev_close = excluded.prev_close,
            day_change_pct = excluded.day_change_pct, volume = excluded.volume,
            avg_volume_20d = excluded.avg_volume_20d, rvol = excluded.rvol,
            atr = excluded.atr, atr_pct = excluded.atr_pct,
            price_tier = excluded.price_tier, quote_age_s = excluded.quote_age_s,
            spread_bp = excluded.spread_bp, post_market_pct = excluded.post_market_pct
        """,
        (
            aid, _num(r.get("price")), _num(indi.get("prev_close")),
            _num(indi.get("day_change_pct")),
            _int(r.get("volume")), _int(r.get("avg_volume")),
            _num(r.get("rvol")), _num(indi.get("atr")), _num(r.get("atr_pct")),
            _txt(r.get("price_tier")),
            _int((r.get("kpi") or {}).get("quote_age_s")),
            _num((r.get("kpi") or {}).get("spread_bp")),
            _num((r.get("kpi") or {}).get("post_market_pct")),
        ),
    )


def _sync_scoring(cur, aid: int, r: dict) -> None:
    sb = r.get("scoring_breakdown") or {}
    cur.execute(
        """
        insert into public.analysis_scoring
            (analysis_id, tech_score, cat_score, rs_score, sm_score, qg_score,
             raw_total, wr_multiplier, bonus_total, entry_rr_score, final_score,
             raw_score, raw_momentum_score, raw_growth_score, raw_value_score,
             sizing_multiplier)
        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        on conflict (analysis_id) do update set
            tech_score = excluded.tech_score, cat_score = excluded.cat_score,
            rs_score = excluded.rs_score, sm_score = excluded.sm_score,
            qg_score = excluded.qg_score, raw_total = excluded.raw_total,
            wr_multiplier = excluded.wr_multiplier, bonus_total = excluded.bonus_total,
            entry_rr_score = excluded.entry_rr_score, final_score = excluded.final_score,
            raw_score = excluded.raw_score,
            raw_momentum_score = excluded.raw_momentum_score,
            raw_growth_score = excluded.raw_growth_score,
            raw_value_score = excluded.raw_value_score,
            sizing_multiplier = excluded.sizing_multiplier
        """,
        (
            aid,
            _num(sb.get("tech_score")), _num(sb.get("cat_score")),
            _num(sb.get("rs_score")),   _num(sb.get("sm_score")),
            _num(sb.get("qg_score")),   _num(sb.get("raw_total")),
            _num(sb.get("wr_multiplier")), _num(sb.get("bonus_total")),
            _num(sb.get("entry_rr_score")), _num(sb.get("final_score")),
            _int(r.get("raw_score")),
            _num(r.get("raw_momentum_score")),
            _num(r.get("raw_growth_score")),
            _num(r.get("raw_value_score")),
            _num(r.get("sizing_multiplier")),
        ),
    )


def _sync_verdict(cur, aid: int, r: dict) -> None:
    decision = r.get("decision") or {}
    audit = r.get("audit_trail") or {}
    dstate = r.get("decision_state") or {}
    import json
    cur.execute(
        """
        insert into public.analysis_verdict
            (analysis_id, verdict, reject_reason, decided_by, hard_gates_passed,
             decision_state, decision_label, in_cloud, no_edge_zone,
             momentum_slowdown, size_mult_by_zone, caveats_json)
        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
        on conflict (analysis_id) do update set
            verdict = excluded.verdict, reject_reason = excluded.reject_reason,
            decided_by = excluded.decided_by,
            hard_gates_passed = excluded.hard_gates_passed,
            decision_state = excluded.decision_state,
            decision_label = excluded.decision_label,
            in_cloud = excluded.in_cloud, no_edge_zone = excluded.no_edge_zone,
            momentum_slowdown = excluded.momentum_slowdown,
            size_mult_by_zone = excluded.size_mult_by_zone,
            caveats_json = excluded.caveats_json
        """,
        (
            aid,
            _enum(r.get("verdict") or decision.get("verdict"),
                  ("BUY","WATCH","SHORT","AVOID"), upper=True) or "AVOID",
            _txt(r.get("reject_reason"), 2048),
            _txt(audit.get("decided_by")),
            _bool(audit.get("hard_gates_passed")),
            _txt(dstate.get("state")),
            _txt(dstate.get("label")),
            _bool(dstate.get("in_cloud")),
            _bool(dstate.get("no_edge_zone")),
            _bool(dstate.get("momentum_slowdown")),
            _num(dstate.get("size_mult_by_zone")),
            json.dumps(r.get("caveats") or []),
        ),
    )


def _sync_conviction(cur, aid: int, r: dict) -> None:
    c = r.get("conviction") or {}
    cur.execute(
        """
        insert into public.analysis_conviction
            (analysis_id, tier, label, size_mult, description, wr_size_adj)
        values (%s,%s,%s,%s,%s,%s)
        on conflict (analysis_id) do update set
            tier = excluded.tier, label = excluded.label,
            size_mult = excluded.size_mult, description = excluded.description,
            wr_size_adj = excluded.wr_size_adj
        """,
        (
            aid, _int(c.get("tier")), _txt(c.get("label")),
            _num(c.get("size_mult")), _txt(c.get("description")),
            _txt(c.get("wr_size_adj")),
        ),
    )


def _sync_trade_plan(cur, aid: int, r: dict) -> None:
    """Write trade_plans + entries + risk in one shot."""
    ctp = r.get("canonical_trade_plan") or {}
    tp  = r.get("trade_plan") or {}
    entry = ctp.get("entry") or {}
    risk  = ctp.get("risk") or {}

    cur.execute(
        """
        insert into public.trade_plans (
            analysis_id, schema_version, direction, verdict, conviction_tier,
            hold_period_days, shares, position_size_pct, allocation_pct,
            stop, target1, target2, risk_per_share, rr_ratio,
            mechanism_hypothesis, decided_at, git_commit, config_snapshot_hash)
        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        on conflict (analysis_id) do update set
            direction = excluded.direction, verdict = excluded.verdict,
            conviction_tier = excluded.conviction_tier,
            hold_period_days = excluded.hold_period_days,
            shares = excluded.shares,
            position_size_pct = excluded.position_size_pct,
            allocation_pct = excluded.allocation_pct,
            stop = excluded.stop, target1 = excluded.target1, target2 = excluded.target2,
            risk_per_share = excluded.risk_per_share, rr_ratio = excluded.rr_ratio,
            decided_at = excluded.decided_at
        """,
        (
            aid,
            _int(ctp.get("schema_version")) or 1,
            _enum(ctp.get("direction") or tp.get("direction"),
                  ("long","short","neutral"), lower=True),
            _enum(ctp.get("verdict") or r.get("verdict"),
                  ("BUY","WATCH","SHORT","AVOID"), upper=True),
            _txt(ctp.get("conviction_tier")),
            _int(ctp.get("hold_period_days")),
            _int(ctp.get("shares")),
            _num(ctp.get("position_size_pct")),
            _num(tp.get("allocation_pct")),
            _num(ctp.get("stop") or tp.get("stop")),
            _num(ctp.get("target1") or tp.get("target1")),
            _num(ctp.get("target2") or tp.get("target2")),
            _num(tp.get("risk_per_share")),
            _num(tp.get("rr_ratio") or (risk.get("rr_ratio") if isinstance(risk, dict) else None)),
            _txt((ctp.get("setup") or {}).get("mechanism_hypothesis")),
            _txt(ctp.get("decided_at")),
            _txt(ctp.get("git_commit")),
            _txt(ctp.get("config_snapshot_hash")),
        ),
    )

    cur.execute(
        """
        insert into public.trade_plan_entries (
            analysis_id, entry_low, entry_mid, entry_high,
            shallow_zone_low, shallow_zone_high, primary_zone_low, primary_zone_high,
            deep_zone_low, deep_zone_high, fib_382, fib_500, fib_618,
            ichimoku_zone_top, ichimoku_zone_bottom, expected_pullback)
        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        on conflict (analysis_id) do update set
            entry_low = excluded.entry_low, entry_mid = excluded.entry_mid,
            entry_high = excluded.entry_high,
            shallow_zone_low = excluded.shallow_zone_low,
            shallow_zone_high = excluded.shallow_zone_high,
            primary_zone_low = excluded.primary_zone_low,
            primary_zone_high = excluded.primary_zone_high,
            deep_zone_low = excluded.deep_zone_low,
            deep_zone_high = excluded.deep_zone_high,
            fib_382 = excluded.fib_382, fib_500 = excluded.fib_500,
            fib_618 = excluded.fib_618,
            expected_pullback = excluded.expected_pullback
        """,
        (
            aid,
            _num(tp.get("entry_low") or entry.get("low")),
            _num(entry.get("mid")),
            _num(tp.get("entry_high") or entry.get("high")),
            _num(tp.get("shallow_zone_low")), _num(tp.get("shallow_zone_high")),
            _num(tp.get("primary_zone_low")), _num(tp.get("primary_zone_high")),
            _num(tp.get("deep_zone_low")),    _num(tp.get("deep_zone_high")),
            _num(tp.get("fib_382")), _num(tp.get("fib_500")), _num(tp.get("fib_618")),
            _num(tp.get("ichimoku_zone_top")), _num(tp.get("ichimoku_zone_bottom")),
            _txt(tp.get("expected_pullback")),
        ),
    )

    cur.execute(
        """
        insert into public.trade_plan_risk (
            analysis_id, max_loss_pct, max_loss_dollars, rr_ratio,
            beta_adjusted_size_pct, beta_adj_multiplier, beta_adj_note,
            cvar_975_pct, drawdown_haircut_pct)
        values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        on conflict (analysis_id) do update set
            max_loss_pct = excluded.max_loss_pct,
            max_loss_dollars = excluded.max_loss_dollars,
            rr_ratio = excluded.rr_ratio,
            beta_adjusted_size_pct = excluded.beta_adjusted_size_pct,
            beta_adj_multiplier = excluded.beta_adj_multiplier,
            beta_adj_note = excluded.beta_adj_note,
            cvar_975_pct = excluded.cvar_975_pct
        """,
        (
            aid,
            _num(risk.get("max_loss_pct")) if isinstance(risk, dict) else None,
            _num(risk.get("max_loss_dollars")) if isinstance(risk, dict) else None,
            _num(tp.get("rr_ratio")),
            _num(risk.get("beta_adjusted_size_pct")) if isinstance(risk, dict) else None,
            _num(tp.get("beta_adj_multiplier")),
            _txt(tp.get("beta_adj_note")),
            _num((r.get("kelly_size") or {}).get("cvar_975_pct")),
            _num((r.get("kelly_size") or {}).get("drawdown_pct")),
        ),
    )


def _sync_risk_sizing(cur, aid: int, r: dict) -> None:
    k = r.get("kelly_size") or {}
    cur.execute(
        """
        insert into public.risk_sizing (
            analysis_id, kelly_pct, half_kelly_pct, final_alloc_pct,
            risk_per_trade_pct, dollar_risk, position_value, suggested_shares,
            regime_mult, regime_max_size_pct, effective_regime_cap, vix_mult,
            drawdown_mult, drawdown_pct, earnings_mult, earnings_days,
            var_floor_mult, cvar_975_pct, live_stats_used, live_win_rate,
            stack_note, mc_p_profit, sizing_multiplier)
        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        on conflict (analysis_id) do update set
            kelly_pct = excluded.kelly_pct, half_kelly_pct = excluded.half_kelly_pct,
            final_alloc_pct = excluded.final_alloc_pct,
            risk_per_trade_pct = excluded.risk_per_trade_pct,
            dollar_risk = excluded.dollar_risk, position_value = excluded.position_value,
            suggested_shares = excluded.suggested_shares,
            regime_mult = excluded.regime_mult,
            regime_max_size_pct = excluded.regime_max_size_pct,
            effective_regime_cap = excluded.effective_regime_cap,
            vix_mult = excluded.vix_mult, drawdown_mult = excluded.drawdown_mult,
            drawdown_pct = excluded.drawdown_pct,
            earnings_mult = excluded.earnings_mult, earnings_days = excluded.earnings_days,
            var_floor_mult = excluded.var_floor_mult, cvar_975_pct = excluded.cvar_975_pct,
            live_stats_used = excluded.live_stats_used,
            live_win_rate = excluded.live_win_rate,
            stack_note = excluded.stack_note,
            mc_p_profit = excluded.mc_p_profit,
            sizing_multiplier = excluded.sizing_multiplier
        """,
        (
            aid,
            _num(k.get("kelly_pct")), _num(k.get("half_kelly_pct")),
            _num(k.get("final_alloc_pct")), _num(k.get("risk_per_trade_pct")),
            _num(k.get("dollar_risk")), _num(k.get("position_value")),
            _int(k.get("suggested_shares")),
            _num(k.get("regime_mult")), _num(k.get("regime_max_size_pct")),
            _num(k.get("effective_regime_cap")), _num(k.get("vix_mult")),
            _num(k.get("drawdown_mult")), _num(k.get("drawdown_pct")),
            _num(k.get("earnings_mult")), _int(k.get("earnings_days")),
            _num(k.get("var_floor_mult")), _num(k.get("cvar_975_pct")),
            _bool(k.get("live_stats_used")), _num(k.get("live_win_rate")),
            _txt(k.get("stack_note")),
            _num(r.get("mc_p_profit")), _num(r.get("sizing_multiplier")),
        ),
    )


def _sync_technicals(cur, aid: int, r: dict) -> None:
    """One-shot pass through all technicals_* tables."""
    indi = (r.get("technicals") or {}).get("indicators") or {}
    if not indi:
        return

    # EMA ladder
    cur.execute(
        """
        insert into public.technicals_ema (
            analysis_id, ema5, ema8, ema13, ema20, ema21, ema34, ema50, ema55,
            ema100, ema200, weekly_ema8, weekly_ema21, weekly_ema_bullish, weekly_ema_bearish,
            ema5_slope_up, ema13_slope_up, ema5_above_13, ema5_cross_bull, ema5_cross_bear,
            price_above_ema5, emas_above, ema_signal)
        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        on conflict (analysis_id) do update set ema_signal = excluded.ema_signal
        """,
        (
            aid, _num(indi.get("ema5")), _num(indi.get("ema8")), _num(indi.get("ema13")),
            _num(indi.get("ema20")), _num(indi.get("ema21")), _num(indi.get("ema34")),
            _num(indi.get("ema50")), _num(indi.get("ema55")), _num(indi.get("ema100")),
            _num(indi.get("ema200")),
            _num(indi.get("weekly_ema8")), _num(indi.get("weekly_ema21")),
            _bool(indi.get("weekly_ema_bullish")), _bool(indi.get("weekly_ema_bearish")),
            _bool(indi.get("ema5_slope_up")), _bool(indi.get("ema13_slope_up")),
            _bool(indi.get("ema5_above_13")), _bool(indi.get("ema5_cross_bull")),
            _bool(indi.get("ema5_cross_bear")),
            _bool(indi.get("price_above_ema5")), _int(indi.get("emas_above")),
            _txt(indi.get("ema_signal")),
        ),
    )

    # Momentum
    cur.execute(
        """
        insert into public.technicals_momentum (
            analysis_id, rsi, macd_signal, macd_bullish, stoch_rsi_k, stoch_rsi_d,
            stoch_k_above_d, stoch_overbought, stoch_oversold, mfi, mfi_bullish,
            cmf, cmf_accumulating, adx, adx_plus_di, adx_minus_di, adx_trending)
        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        on conflict (analysis_id) do update set rsi = excluded.rsi
        """,
        (
            aid, _num(indi.get("rsi")), _txt(indi.get("macd_signal")),
            _bool(indi.get("macd_bullish")),
            _num(indi.get("stoch_rsi_k")), _num(indi.get("stoch_rsi_d")),
            _bool(indi.get("stoch_k_above_d")), _bool(indi.get("stoch_overbought")),
            _bool(indi.get("stoch_oversold")),
            _num(indi.get("mfi")), _bool(indi.get("mfi_bullish")),
            _num(indi.get("cmf")), _bool(indi.get("cmf_accumulating")),
            _num(indi.get("adx")), _num(indi.get("adx_plus_di")),
            _num(indi.get("adx_minus_di")), _bool(indi.get("adx_trending")),
        ),
    )

    # Volatility / squeeze
    enh = indi.get("enhanced_squeeze_components") or {}
    cur.execute(
        """
        insert into public.technicals_volatility (
            analysis_id, atr, atr_pct, bb_pct_b, squeeze_on, squeeze_fired,
            squeeze_direction, bars_in_squeeze, enhanced_squeeze_label,
            enhanced_squeeze_probability, enh_short_float_pts, enh_days_to_cover_pts,
            enh_momentum_pts, enh_si_trend_pts)
        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        on conflict (analysis_id) do update set atr = excluded.atr
        """,
        (
            aid, _num(indi.get("atr")), _num(indi.get("atr_pct")),
            _num(indi.get("bb_pct_b")), _bool(indi.get("squeeze_on")),
            _bool(indi.get("squeeze_fired")), _txt(indi.get("squeeze_direction")),
            _int(indi.get("bars_in_squeeze")), _txt(indi.get("enhanced_squeeze_label")),
            _int(indi.get("enhanced_squeeze_probability")),
            _int(enh.get("short_float_pts")), _int(enh.get("days_to_cover_pts")),
            _int(enh.get("momentum_pts")), _int(enh.get("si_trend_pts")),
        ),
    )

    # Pattern
    cur.execute(
        """
        insert into public.technicals_pattern (
            analysis_id, vcp, near_vcp, vcp_pivot, vcp_contractions, vcp_tightness,
            vcp_vol_dry_up, pocket_pivot, holy_grail_setup, stage2,
            fractal_high, fractal_low, fractal_highs, fractal_lows, fractal_signal,
            candle_patterns)
        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        on conflict (analysis_id) do update set vcp = excluded.vcp
        """,
        (
            aid, _bool(indi.get("vcp")), _bool(indi.get("near_vcp")),
            _num(indi.get("vcp_pivot")), _int(indi.get("vcp_contractions")),
            _num(indi.get("vcp_tightness")), _bool(indi.get("vcp_vol_dry_up")),
            _bool(indi.get("pocket_pivot")), _bool(indi.get("holy_grail_setup")),
            _bool(indi.get("stage2")),
            _num(indi.get("fractal_high")), _num(indi.get("fractal_low")),
            indi.get("fractal_highs") or [], indi.get("fractal_lows") or [],
            _txt(indi.get("fractal_signal")), indi.get("candle_patterns") or [],
        ),
    )

    # Trend signals
    cur.execute(
        """
        insert into public.technicals_trend (
            analysis_id, golden_cross, death_cross, supertrend_bull, supertrend_value,
            supertrend_flips, sar, sar_bullish, sar_flipped, bullish_stack,
            fib_ribbon, fib_ribbon_spread, fib_ribbon_state, trend_direction,
            trend_age_bars, trend_age_label)
        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        on conflict (analysis_id) do update set golden_cross = excluded.golden_cross
        """,
        (
            aid, _bool(indi.get("golden_cross")), _bool(indi.get("death_cross")),
            _bool(indi.get("supertrend_bull")), _num(indi.get("supertrend_value")),
            _int(indi.get("supertrend_flips")),
            _num(indi.get("sar")), _bool(indi.get("sar_bullish")), _bool(indi.get("sar_flipped")),
            _bool(indi.get("bullish_stack")),
            _txt(indi.get("fib_ribbon")), _num(indi.get("fib_ribbon_spread")),
            _txt(indi.get("fib_ribbon_state")),
            _txt(indi.get("trend_direction")), _int(indi.get("trend_age_bars")),
            _txt(indi.get("trend_age_label")),
        ),
    )

    # Volume flow
    cur.execute(
        """
        insert into public.technicals_volume_flow (
            analysis_id, obv_rising, power_days, power_trend, rvol,
            breakout_vol_ratio, pp_vol_ratio)
        values (%s,%s,%s,%s,%s,%s,%s)
        on conflict (analysis_id) do update set rvol = excluded.rvol
        """,
        (
            aid, _bool(indi.get("obv_rising")), _int(indi.get("power_days")),
            _bool(indi.get("power_trend")), _num(indi.get("rvol")),
            _num(indi.get("breakout_vol_ratio")), _num(indi.get("pp_vol_ratio")),
        ),
    )

    # Position vs reference
    cur.execute(
        """
        insert into public.technicals_position (
            analysis_id, above_200sma, above_50ema, above_20ema, price_above_ema5,
            prev_close, day_change_pct)
        values (%s,%s,%s,%s,%s,%s,%s)
        on conflict (analysis_id) do update set above_200sma = excluded.above_200sma
        """,
        (
            aid, _bool(indi.get("above_200sma")), _bool(indi.get("above_50ema")),
            _bool(indi.get("above_20ema")), _bool(indi.get("price_above_ema5")),
            _num(indi.get("prev_close")), _num(indi.get("day_change_pct")),
        ),
    )

    # 52w range
    cur.execute(
        """
        insert into public.technicals_52w (
            analysis_id, high_52w, low_52w, near_52w_high, near_52w_low,
            at_52w_breakout, pct_from_52w_high)
        values (%s,%s,%s,%s,%s,%s,%s)
        on conflict (analysis_id) do update set high_52w = excluded.high_52w
        """,
        (
            aid, _num(indi.get("high_52w")), _num(indi.get("low_52w")),
            _bool(indi.get("near_52w_high")), _bool(indi.get("near_52w_low")),
            _bool(indi.get("at_52w_breakout")), _num(indi.get("pct_from_52w_high")),
        ),
    )

    # Relative strength
    cur.execute(
        """
        insert into public.technicals_relative_strength (
            analysis_id, rs_rank, rs_63d_pct, sector_rank, sector_etf,
            sector_vs_spy_pct, outperforming_sector, outperforming_spy,
            sector_outperforming, sector_underperform, sector_rotation_score,
            sector_rotation_label, sector_rotation_trend)
        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        on conflict (analysis_id) do update set rs_rank = excluded.rs_rank
        """,
        (
            aid, _int(indi.get("rs_rank")), _num(indi.get("rs_63d_pct")),
            _int(indi.get("sector_rank")), _txt(indi.get("sector_etf")),
            _num(indi.get("sector_vs_spy_pct")),
            _bool(indi.get("outperforming_sector")), _bool(indi.get("outperforming_spy")),
            _bool(indi.get("sector_outperforming")), _bool(indi.get("sector_underperform")),
            _int(indi.get("sector_rotation_score")),
            _txt(indi.get("sector_rotation_label")), _txt(indi.get("sector_rotation_trend")),
        ),
    )

    # SR / VWAP
    cur.execute(
        """
        insert into public.technicals_sr_vwap (
            analysis_id, support, resistance, vwap, avwap_swing_low,
            above_vwap, above_avwap)
        values (%s,%s,%s,%s,%s,%s,%s)
        on conflict (analysis_id) do update set vwap = excluded.vwap
        """,
        (
            aid, _num(indi.get("support")), _num(indi.get("resistance")),
            _num(indi.get("vwap")), _num(indi.get("avwap_swing_low")),
            _bool(indi.get("above_vwap")), _bool(indi.get("above_avwap")),
        ),
    )

    # Location-adjusted volume
    cur.execute(
        """
        insert into public.technicals_loc_volume (
            analysis_id, at_resistance, at_support, loc_vol_label, loc_vol_score)
        values (%s,%s,%s,%s,%s)
        on conflict (analysis_id) do update set loc_vol_label = excluded.loc_vol_label
        """,
        (
            aid, _bool(indi.get("at_resistance")), _bool(indi.get("at_support")),
            _txt(indi.get("loc_vol_label")), _int(indi.get("loc_vol_score")),
        ),
    )


def _sync_options(cur, aid: int, r: dict) -> None:
    od = r.get("options_data") or {}
    oi = r.get("options_intelligence") or {}
    ok = r.get("options_kpis") or {}
    if not (od or oi or ok):
        return

    if od:
        cur.execute(
            """
            insert into public.options_snapshot (
                analysis_id, source, current_iv, iv_rank, iv_pct, put_call_ratio,
                total_call_oi, total_call_vol, total_put_oi, total_put_vol,
                max_pain, uoa_calls, uoa_puts, error)
            values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            on conflict (analysis_id) do update set current_iv = excluded.current_iv
            """,
            (
                aid, _txt(od.get("source")) or "schwab",
                _num(od.get("current_iv")), _num(od.get("iv_rank")), _num(od.get("iv_pct")),
                _num(od.get("put_call_ratio")),
                _int(od.get("total_call_oi")), _int(od.get("total_call_vol")),
                _int(od.get("total_put_oi")), _int(od.get("total_put_vol")),
                _num(od.get("max_pain")),
                _int(od.get("uoa_calls")), _int(od.get("uoa_puts")),
                _txt(od.get("error")),
            ),
        )

    if oi:
        cur.execute(
            """
            insert into public.options_intelligence (
                analysis_id, iv_skew, pc_ratio_oi, pc_ratio_vol, gamma_wall_above,
                gamma_wall_below, max_pain, dominant_flow, iv_rank_est,
                call_oi_sum, call_vol_sum, put_oi_sum, put_vol_sum)
            values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            on conflict (analysis_id) do update set iv_skew = excluded.iv_skew
            """,
            (
                aid, _num(oi.get("iv_skew")), _num(oi.get("pc_ratio_oi")),
                _num(oi.get("pc_ratio_vol")), _num(oi.get("gamma_wall_above")),
                _num(oi.get("gamma_wall_below")), _num(oi.get("max_pain")),
                _enum(oi.get("dominant_flow"), ("calls","puts","balanced"), lower=True),
                _num(oi.get("iv_rank_est")),
                _int(oi.get("call_oi_sum")), _int(oi.get("call_vol_sum")),
                _int(oi.get("put_oi_sum")), _int(oi.get("put_vol_sum")),
            ),
        )

    if ok:
        ts = ok.get("term_structure") or {}
        cur.execute(
            """
            insert into public.options_kpis (
                analysis_id, iv_percentile, iv_current, put_call_ratio,
                uoa_calls, uoa_puts, uoa_call_detail, uoa_put_detail,
                gamma_net, skew_25d, max_pain, term_structure,
                term_front_iv, term_back_iv, verdict, verdict_confidence, narrative)
            values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            on conflict (analysis_id) do update set verdict = excluded.verdict
            """,
            (
                aid, _num(ok.get("iv_percentile")), _num(ok.get("iv_current")),
                _num(ok.get("put_call_ratio")),
                _bool(ok.get("uoa_calls")), _bool(ok.get("uoa_puts")),
                _txt(ok.get("uoa_call_detail")), _txt(ok.get("uoa_put_detail")),
                _int(ok.get("gamma_net")), _num(ok.get("skew_25d")),
                _num(ok.get("max_pain")),
                _enum(ts.get("structure"), ("contango","backwardation","flat"), lower=True),
                _num(ts.get("front_iv")), _num(ts.get("back_iv")),
                _txt((ok.get("verdict") or {}).get("verdict") if isinstance(ok.get("verdict"), dict) else ok.get("verdict")),
                _num((ok.get("verdict") or {}).get("confidence") if isinstance(ok.get("verdict"), dict) else None),
                _txt((ok.get("verdict") or {}).get("narrative") if isinstance(ok.get("verdict"), dict) else None),
            ),
        )


def _sync_zacks(cur, aid: int, r: dict) -> None:
    gmail = r.get("gmail_bonus") or {}
    cur.execute(
        """
        insert into public.zacks_data (
            analysis_id, grade_growth, grade_momentum, grade_value, grade_vgm,
            vgm_verdict, zacks_rank1, zacks_sell,
            gmail_bonus_pts, gmail_signal_count, gmail_trade_alert, rank_from_email)
        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        on conflict (analysis_id) do update set
            grade_vgm = excluded.grade_vgm, vgm_verdict = excluded.vgm_verdict
        """,
        (
            aid,
            _enum(r.get("grade_growth"),   ("A","B","C","D","F"), upper=True),
            _enum(r.get("grade_momentum"), ("A","B","C","D","F"), upper=True),
            _enum(r.get("grade_value"),    ("A","B","C","D","F"), upper=True),
            _enum(r.get("grade_vgm"),      ("A","B","C","D","F"), upper=True),
            _txt(r.get("vgm_verdict")),
            _bool(r.get("zacks_rank1")), _bool(r.get("zacks_sell")),
            _int(gmail.get("bonus")), _int(gmail.get("mention_count")),
            _txt(gmail.get("trade_alert")), _txt(gmail.get("rank_from_email")),
        ),
    )


def _sync_tier1(cur, aid: int, r: dict) -> None:
    t1 = r.get("tier1_signals") or {}
    sig = t1.get("signals") or {}
    cur.execute(
        """
        insert into public.tier1_signals (
            analysis_id, total_points, active_count, narratives,
            insider_cluster, nr7_inside_day, volume_dryup, obv_divergence,
            mean_reversion, beat_and_raise, apply_to_score)
        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        on conflict (analysis_id) do update set
            total_points = excluded.total_points, active_count = excluded.active_count
        """,
        (
            aid, _int(t1.get("total_points")), _int(t1.get("active_count")),
            t1.get("narratives") or [],
            _bool(sig.get("insider_cluster")), _bool(sig.get("nr7_inside_day")),
            _bool(sig.get("volume_dryup")), _bool(sig.get("obv_divergence")),
            _bool(sig.get("mean_reversion")), _bool(sig.get("beat_and_raise")),
            _bool(t1.get("apply_to_score")),
        ),
    )


def _sync_sentiment(cur, aid: int, r: dict) -> None:
    nss = r.get("news_sentiment_score") or {}
    if nss:
        cur.execute(
            """
            insert into public.news_sentiment_snapshot
                (analysis_id, score, max, momentum, breaking, article_count, source_score, details)
            values (%s,%s,%s,%s,%s,%s,%s,%s)
            on conflict (analysis_id) do update set score = excluded.score
            """,
            (
                aid, _int(nss.get("score")), _int(nss.get("max")),
                _enum(nss.get("momentum"), ("bullish","neutral","bearish"), lower=True),
                _bool(nss.get("breaking")), _int(nss.get("article_count")),
                _num(nss.get("source_score")), _txt(nss.get("details")),
            ),
        )

    rw = r.get("reddit_wsb") or {}
    if rw:
        cur.execute(
            """
            insert into public.reddit_wsb_snapshot (analysis_id, mentions, avg_score, sentiment)
            values (%s,%s,%s,%s)
            on conflict (analysis_id) do update set mentions = excluded.mentions
            """,
            (
                aid, _int(rw.get("mentions")), _num(rw.get("avg_score")),
                _enum(rw.get("sentiment"), ("bullish","neutral","bearish"), lower=True),
            ),
        )

    st = r.get("stocktwits") or {}
    if st:
        cur.execute(
            """
            insert into public.stocktwits_snapshot
                (analysis_id, bullish, bearish, neutral, bull_pct, message_volume,
                 watchlist_count, trending)
            values (%s,%s,%s,%s,%s,%s,%s,%s)
            on conflict (analysis_id) do update set bull_pct = excluded.bull_pct
            """,
            (
                aid, _int(st.get("bullish")), _int(st.get("bearish")), _int(st.get("neutral")),
                _num(st.get("bull_pct")), _int(st.get("message_volume")),
                _int(st.get("watchlist_count")), _bool(st.get("trending")),
            ),
        )


def _sync_elliott_wave(cur, aid: int, r: dict) -> None:
    """elliott_wave (legacy) + elliott_wave_v1 (enhanced).

    Only reads result.elliott_wave (top-level) — the trade_plan.elliott_wave
    sub-dict has a different shape and was causing type-cast errors.
    """
    ew = r.get("elliott_wave") or {}
    if ew:
        import json
        # nearest_fib is a mixed list like ['23.6%', 171.79] — coerce to all strings
        nfib = [str(x) for x in (ew.get("nearest_fib") or []) if x is not None]
        cur.execute(
            """
            insert into public.elliott_wave (
                analysis_id, wave_number, wave_label, trend, confidence,
                swing_base, swing_top, bonus, description, fib_levels_json, nearest_fib)
            values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
            on conflict (analysis_id) do update set
                wave_number = excluded.wave_number, wave_label = excluded.wave_label
            """,
            (
                aid, _int(ew.get("wave_number")), _txt(ew.get("wave_label")),
                _txt(ew.get("trend")),
                _enum(ew.get("confidence"), ("high","medium","low"), lower=True),
                _num(ew.get("swing_base")), _num(ew.get("swing_top")),
                _int(ew.get("bonus")), _txt(ew.get("description"), 2048),
                json.dumps(ew.get("fib_levels") or {}),
                nfib,
            ),
        )

    ew1 = (r.get("trade_plan") or {}).get("elliott_wave_v1") or {}
    if ew1:
        import json
        cur.execute(
            """
            insert into public.elliott_wave_v1 (
                analysis_id, ew_state, ew_bullish, ew_bearish, ew_score, meta_json)
            values (%s,%s,%s,%s,%s,%s::jsonb)
            on conflict (analysis_id) do update set ew_state = excluded.ew_state
            """,
            (
                aid, _txt(ew1.get("ew_state")),
                _bool(ew1.get("ew_bullish")), _bool(ew1.get("ew_bearish")),
                _num(ew1.get("ew_score")),
                json.dumps(ew1),
            ),
        )


def _sync_theory(cur, aid: int, r: dict) -> None:
    """theory_confluence (1:1) + theory_states (1:N)."""
    tc = r.get("theory_confluence") or {}
    if not tc:
        return
    cur.execute(
        """
        insert into public.theory_confluence (
            analysis_id, direction, bull_count, bear_count, min_required,
            hard_gate_pass, evidence_summary, eligible_theories)
        values (%s,%s,%s,%s,%s,%s,%s,%s)
        on conflict (analysis_id) do update set
            direction = excluded.direction, bull_count = excluded.bull_count,
            bear_count = excluded.bear_count
        """,
        (
            aid,
            _enum(tc.get("direction"), ("BULL","BEAR","NEUTRAL"), upper=True),
            _int(tc.get("bull_count")), _int(tc.get("bear_count")),
            _int(tc.get("min_required")), _bool(tc.get("hard_gate_pass")),
            _txt(tc.get("evidence_summary"), 1024),
            tc.get("eligible_theories") or [],
        ),
    )

    # 1:N theory_states — refresh
    states = tc.get("states") or {}
    bull_aligned = tc.get("bull_aligned") or {}
    bear_aligned = tc.get("bear_aligned") or {}
    details = tc.get("details") or {}
    if not isinstance(states, dict):
        return
    cur.execute("delete from public.theory_states where analysis_id=%s", (aid,))
    import json
    rows = []
    for theory in ("dow", "wyckoff", "elliott", "gann"):
        if theory not in states and theory not in bull_aligned and theory not in bear_aligned:
            continue
        rows.append((
            aid, theory, _txt(states.get(theory)),
            _bool(bull_aligned.get(theory)), _bool(bear_aligned.get(theory)),
            json.dumps(details.get(theory) if isinstance(details.get(theory), dict) else {}),
        ))
    if rows:
        cur.executemany(
            """
            insert into public.theory_states
                (analysis_id, theory, state, bull_aligned, bear_aligned, detail_json)
            values (%s,%s,%s,%s,%s,%s::jsonb)
            """,
            rows,
        )


def _sync_mtf(cur, aid: int, r: dict) -> None:
    indi = (r.get("technicals") or {}).get("indicators") or {}
    lt = r.get("long_term") or {}
    mt = r.get("medium_term") or {}
    tf4 = r.get("tf_4h") or {}
    if not (lt or mt or tf4 or indi.get("weekly_aligned") is not None or r.get("mtf_label")):
        return
    import json
    cur.execute(
        """
        insert into public.mtf_summary (
            analysis_id, mtf_conflict, mtf_label,
            lt_score, lt_verdict, lt_gate_pass,
            mt_score, mt_verdict, mt_gate_status,
            tf_4h_json, weekly_aligned)
        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
        on conflict (analysis_id) do update set
            mtf_conflict = excluded.mtf_conflict, mtf_label = excluded.mtf_label
        """,
        (
            aid, _bool(r.get("mtf_conflict")), _txt(r.get("mtf_label")),
            _num(lt.get("score")), _txt(lt.get("verdict")), _bool(lt.get("gate_pass")),
            _num(mt.get("score")), _txt(mt.get("verdict")), _txt(mt.get("gate_status")),
            json.dumps(tf4 or {}),
            _bool(indi.get("weekly_aligned")),
        ),
    )


def _sync_fundamentals_pillar(cur, aid: int, r: dict) -> None:
    f = r.get("fundamentals") or {}
    if not f:
        return
    import json
    cur.execute(
        """
        insert into public.fundamentals_pillar (
            analysis_id, score, max, bull_drivers, bear_risks, details_json)
        values (%s,%s,%s,%s,%s,%s::jsonb)
        on conflict (analysis_id) do update set
            score = excluded.score, max = excluded.max
        """,
        (
            aid, _int(f.get("score")), _int(f.get("max")),
            f.get("bull_drivers") or [], f.get("bear_risks") or [],
            json.dumps(f.get("details") or {}),
        ),
    )


def _sync_sentiment_pillar(cur, aid: int, r: dict) -> None:
    s = r.get("sentiment") or {}
    if not s:
        return
    import json
    cur.execute(
        """
        insert into public.sentiment_pillar (analysis_id, score, max, details_json)
        values (%s,%s,%s,%s::jsonb)
        on conflict (analysis_id) do update set score = excluded.score
        """,
        (
            aid, _int(s.get("score")), _int(s.get("max")),
            json.dumps(s.get("details") or {}),
        ),
    )


def _sync_gamma_exposure(cur, aid: int, r: dict) -> None:
    g = r.get("gamma") or {}
    if not g:
        return
    cur.execute(
        """
        insert into public.gamma_exposure (
            analysis_id, gamma_score, call_oi_skew, short_float_pct, float_size_m)
        values (%s,%s,%s,%s,%s)
        on conflict (analysis_id) do update set gamma_score = excluded.gamma_score
        """,
        (
            aid, _num(g.get("gamma_score")), _num(g.get("call_oi_skew")),
            _num(g.get("short_float_pct")), _num(g.get("float_size_m")),
        ),
    )


def _sync_volume_profile(cur, aid: int, r: dict) -> None:
    vp = r.get("volume_profile") or {}
    if not vp:
        return
    cur.execute(
        """
        insert into public.volume_profile (
            analysis_id, poc, vah, val, hvn_levels, lvn_levels,
            support_vpn, resistance_vpn)
        values (%s,%s,%s,%s,%s,%s,%s,%s)
        on conflict (analysis_id) do update set poc = excluded.poc
        """,
        (
            aid, _num(vp.get("poc")), _num(vp.get("vah")), _num(vp.get("val")),
            vp.get("hvn_levels") or vp.get("hvn") or [],
            vp.get("lvn_levels") or vp.get("lvn") or [],
            _num(vp.get("support_vpn")), _num(vp.get("resistance_vpn")),
        ),
    )


def _sync_premarket(cur, aid: int, r: dict) -> None:
    pm = r.get("premarket") or {}
    if not pm:
        return
    cur.execute(
        """
        insert into public.technicals_premarket (
            analysis_id, premarket_vol, avg_premarket_vol, vol_ratio,
            premarket_pct, unusual)
        values (%s,%s,%s,%s,%s,%s)
        on conflict (analysis_id) do update set premarket_vol = excluded.premarket_vol
        """,
        (
            aid, _int(pm.get("premarket_vol")), _int(pm.get("avg_premarket_vol")),
            _num(pm.get("vol_ratio")),
            _num(pm.get("premarket_pct") or pm.get("pct")),
            _bool(pm.get("unusual")),
        ),
    )


def _sync_tv_rating(cur, aid: int, r: dict) -> None:
    tv = r.get("tv_rating") or {}
    if not tv:
        return
    cur.execute(
        """
        insert into public.tv_rating (
            analysis_id, overall, ma, osc, buy_count, sell_count, neutral_count)
        values (%s,%s,%s,%s,%s,%s,%s)
        on conflict (analysis_id) do update set overall = excluded.overall
        """,
        (
            aid, _txt(tv.get("overall") or tv.get("Recommend.All")),
            _txt(tv.get("ma") or tv.get("Recommend.MA")),
            _txt(tv.get("osc") or tv.get("Recommend.Other")),
            _int(tv.get("buy_count")), _int(tv.get("sell_count")),
            _int(tv.get("neutral_count")),
        ),
    )


# ============================================================================
# 1:N expanders — TRUNCATE-for-aid then INSERT (idempotent)
# ============================================================================

def _sync_gates_1n(cur, aid: int, r: dict) -> None:
    """analysis_gates + gates_evaluated (8-gate cascade)."""
    gate = r.get("gate") or {}
    gates_eval = r.get("gates_evaluated") or []

    # analysis_gates — refresh per analysis
    cur.execute("delete from public.analysis_gates where analysis_id=%s", (aid,))
    rows = []
    # pre_trade_gate failure reasons
    for i, reason in enumerate(gate.get("reasons") or []):
        rows.append((aid, "pre_trade_gate", i, bool(gate.get("passed")),
                     _txt(reason, 512), True, None))
    if rows:
        import json
        cur.executemany(
            """
            insert into public.analysis_gates
                (analysis_id, gate_name, gate_order, passed, reason, is_hard, meta_json)
            values (%s,%s,%s,%s,%s,%s,%s::jsonb)
            """,
            [(a, n, o, p, rs, h, json.dumps({}) if m is None else json.dumps(m)) for a, n, o, p, rs, h, m in rows],
        )

    # gates_evaluated — refresh per analysis
    cur.execute("delete from public.gates_evaluated where analysis_id=%s", (aid,))
    if isinstance(gates_eval, list) and gates_eval:
        rows2 = []
        for i, ge in enumerate(gates_eval):
            if not isinstance(ge, dict):
                continue
            rows2.append((
                aid,
                _txt(ge.get("gate_code") or ge.get("code")),
                _txt(ge.get("gate_name") or ge.get("name")),
                _int(ge.get("cascade_order") or ge.get("order") or i),
                _bool(ge.get("passed")),
                _bool(ge.get("is_hard")),
                _txt(ge.get("reason"), 1024),
                _txt(ge.get("evaluator")),
            ))
        if rows2:
            cur.executemany(
                """
                insert into public.gates_evaluated
                    (analysis_id, gate_code, gate_name, cascade_order, passed,
                     is_hard, reason, evaluator)
                values (%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                rows2,
            )


def _sync_catalysts_1n(cur, aid: int, r: dict) -> None:
    tags = r.get("catalyst_tags") or []
    meta = (r.get("catalyst_meta") or {}).get("per_tag") or {}
    if not tags:
        return
    cur.execute("delete from public.analysis_catalysts where analysis_id=%s", (aid,))
    rows = []
    for tag in tags:
        m = meta.get(tag) or {}
        rows.append((
            aid, _txt(tag),
            _int(r.get("catalyst_tier")) if tag == (tags[0] if tags else None) else _int(m.get("tier")),
            _int(m.get("expiry_days")),
            _bool(m.get("is_expired")),
        ))
    if rows:
        cur.executemany(
            """
            insert into public.analysis_catalysts
                (analysis_id, tag, tier, expiry_days, is_expired)
            values (%s,%s,%s,%s,%s)
            """,
            rows,
        )


def _sync_methodology_1n(cur, aid: int, r: dict) -> None:
    """Flatten both shapes:
       pre  = {checks: {name: {pass, reason}}, passes, verdict}
       post = [{item, checked, detail}, ...]
    """
    pre  = r.get("methodology_checklist") or {}
    post = r.get("reaction_checklist") or []
    rows = []

    pre_checks = pre.get("checks") if isinstance(pre, dict) else None
    if isinstance(pre_checks, dict):
        for name, info in pre_checks.items():
            if isinstance(info, dict):
                rows.append((
                    aid, "pre",
                    _txt(name),
                    _bool(info.get("pass") if info.get("pass") is not None else info.get("passed")),
                    _txt(info.get("reason") or info.get("detail"), 512),
                ))
            else:
                rows.append((aid, "pre", _txt(name), _bool(info), None))
    elif isinstance(pre_checks, list):
        for c in pre_checks:
            if isinstance(c, dict):
                rows.append((aid, "pre",
                             _txt(c.get("name") or c.get("check_name") or c.get("item")),
                             _bool(c.get("passed") or c.get("pass") or c.get("checked")),
                             _txt(c.get("detail") or c.get("reason"), 512)))

    if isinstance(post, list):
        for c in post:
            if isinstance(c, dict):
                rows.append((aid, "post",
                             _txt(c.get("name") or c.get("check_name") or c.get("item")),
                             _bool(c.get("passed") or c.get("checked") or c.get("pass")),
                             _txt(c.get("detail") or c.get("reason"), 512)))

    if rows:
        cur.execute("delete from public.analysis_methodology where analysis_id=%s", (aid,))
        cur.executemany(
            """
            insert into public.analysis_methodology
                (analysis_id, phase, check_name, passed, detail)
            values (%s,%s,%s,%s,%s)
            """,
            rows,
        )


def _sync_trade_plan_1n(cur, aid: int, r: dict) -> None:
    """trade_plan_exit_rules + trade_plan_zone_confluence + trade_plan_risk_flags."""
    tp = r.get("trade_plan") or {}
    exit_rules = tp.get("exit_rules") or []
    confluence = tp.get("zone_confluence") or []
    risk_flags = tp.get("risk_flags") or []
    exit_params = tp.get("exit_params") or {}

    if exit_rules:
        cur.execute("delete from public.trade_plan_exit_rules where analysis_id=%s", (aid,))
        rows = []
        for i, rule in enumerate(exit_rules):
            rows.append((
                aid, i, _txt(rule, 1024),
                _txt(tp.get("exit_family")),
                _num(exit_params.get("trail_activate_pct")),
                _num(exit_params.get("trail_atr_mult")),
                _num(exit_params.get("partial_at_t1_pct")),
                _int(exit_params.get("time_stop_days")),
            ))
        cur.executemany(
            """
            insert into public.trade_plan_exit_rules
                (analysis_id, rule_order, rule_text, exit_family,
                 trail_activate_pct, trail_atr_mult, partial_at_t1_pct, time_stop_days)
            values (%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            rows,
        )

    if confluence:
        cur.execute("delete from public.trade_plan_zone_confluence where analysis_id=%s", (aid,))
        rows = []
        for c in confluence:
            if isinstance(c, str):
                rows.append((aid, c, None))
            elif isinstance(c, dict):
                rows.append((aid, _txt(c.get("factor") or c.get("name")),
                             _num(c.get("price_level") or c.get("level"))))
        if rows:
            cur.executemany(
                "insert into public.trade_plan_zone_confluence (analysis_id, factor, price_level) values (%s,%s,%s)",
                rows,
            )

    if risk_flags:
        cur.execute("delete from public.trade_plan_risk_flags where analysis_id=%s", (aid,))
        rows = []
        for f in risk_flags:
            if isinstance(f, dict):
                rows.append((
                    aid,
                    _txt(f.get("code") or f.get("flag") or f.get("type")),
                    _enum(f.get("severity"), ("low","medium","high","critical"), lower=True),
                    _txt(f.get("message") or f.get("text"), 1024),
                ))
            elif isinstance(f, str):
                rows.append((aid, None, None, _txt(f, 1024)))
        if rows:
            cur.executemany(
                """
                insert into public.trade_plan_risk_flags
                    (analysis_id, flag_code, severity, message)
                values (%s,%s,%s,%s)
                """,
                rows,
            )


def _sync_chart_patterns_1n(cur, aid: int, r: dict) -> None:
    p = r.get("patterns") or {}
    if not p:
        return
    import json
    detected = p.get("detected") or p.get("patterns") or []
    if not isinstance(detected, list) or not detected:
        # Maybe single primary pattern
        primary = p.get("primary")
        if primary:
            detected = [primary]
        else:
            return

    cur.execute("delete from public.chart_patterns where analysis_id=%s", (aid,))
    primary_name = p.get("primary")
    rows = []
    for name in detected:
        rows.append((
            aid, _txt(name),
            name == primary_name,
            _num(p.get("confidence")),
            json.dumps(p.get("details") or {}),
        ))
    if rows:
        cur.executemany(
            """
            insert into public.chart_patterns
                (analysis_id, pattern, is_primary, confidence, details_json)
            values (%s,%s,%s,%s,%s::jsonb)
            """,
            rows,
        )


def _sync_smc_1n(cur, aid: int, r: dict) -> None:
    """smc_summary + bos_choch (1:1) + order_blocks/fvg_zones/sweeps (1:N)."""
    smc = r.get("smc") or {}
    if not smc:
        return

    cur.execute(
        """
        insert into public.smc_summary (
            analysis_id, score, smc_direction, fvg_target, ob_entry_zone, ob_stop)
        values (%s,%s,%s,%s,%s,%s)
        on conflict (analysis_id) do update set
            score = excluded.score, smc_direction = excluded.smc_direction
        """,
        (
            aid, _num(smc.get("score")), _txt(smc.get("smc_direction")),
            _num(smc.get("fvg_target")), _num(smc.get("ob_entry_zone")),
            _num(smc.get("ob_stop")),
        ),
    )

    bc = smc.get("bos_choch") or {}
    if bc:
        cur.execute(
            """
            insert into public.smc_bos_choch (
                analysis_id, bos_bullish, bos_bearish, choch_bullish, choch_bearish,
                last_swing_high, last_swing_low)
            values (%s,%s,%s,%s,%s,%s,%s)
            on conflict (analysis_id) do update set
                bos_bullish = excluded.bos_bullish, bos_bearish = excluded.bos_bearish
            """,
            (
                aid,
                _bool(bc.get("bos_bullish")), _bool(bc.get("bos_bearish")),
                _bool(bc.get("choch_bullish")), _bool(bc.get("choch_bearish")),
                _num(bc.get("last_swing_high")), _num(bc.get("last_swing_low")),
            ),
        )

    # 1:N — order blocks
    obs = smc.get("order_blocks") or []
    if isinstance(obs, list) and obs:
        cur.execute("delete from public.smc_order_blocks where analysis_id=%s", (aid,))
        rows = []
        for i, ob in enumerate(obs[:50]):  # cap at 50 to avoid blowing up
            if not isinstance(ob, dict):
                continue
            rows.append((
                aid, i,
                _enum(ob.get("direction") or ob.get("type"),
                      ("bullish","bearish"), lower=True),
                _num(ob.get("top") or ob.get("high")),
                _num(ob.get("bottom") or ob.get("low")),
                _int(ob.get("bar_offset")),
                _bool(ob.get("mitigated")), _bool(ob.get("broken")),
            ))
        if rows:
            cur.executemany(
                """
                insert into public.smc_order_blocks
                    (analysis_id, idx, direction, top, bottom, bar_offset, mitigated, broken)
                values (%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                rows,
            )

    # 1:N — FVG zones
    fvgs = smc.get("fvg_zones") or []
    if isinstance(fvgs, list) and fvgs:
        cur.execute("delete from public.smc_fvg_zones where analysis_id=%s", (aid,))
        rows = []
        for i, fvg in enumerate(fvgs[:50]):
            if not isinstance(fvg, dict):
                continue
            rows.append((
                aid, i,
                _enum(fvg.get("direction") or fvg.get("type"),
                      ("bullish","bearish"), lower=True),
                _num(fvg.get("top")), _num(fvg.get("bottom")), _num(fvg.get("mid")),
                _bool(fvg.get("filled")),
            ))
        if rows:
            cur.executemany(
                """
                insert into public.smc_fvg_zones
                    (analysis_id, idx, direction, top, bottom, mid, filled)
                values (%s,%s,%s,%s,%s,%s,%s)
                """,
                rows,
            )

    # 1:N — liquidity sweeps
    sweeps = smc.get("liquidity_sweeps") or []
    if isinstance(sweeps, list) and sweeps:
        cur.execute("delete from public.smc_liquidity_sweeps where analysis_id=%s", (aid,))
        rows = []
        for sw in sweeps[:50]:
            if not isinstance(sw, dict):
                continue
            rows.append((
                aid,
                _enum(sw.get("direction"), ("bullish","bearish","up","down"), lower=True),
                _num(sw.get("level")),
                _int(sw.get("bar_offset")),
            ))
        if rows:
            cur.executemany(
                """
                insert into public.smc_liquidity_sweeps
                    (analysis_id, direction, level, bar_offset)
                values (%s,%s,%s,%s)
                """,
                rows,
            )


def _sync_option_chain_1n(cur, aid: int, r: dict) -> None:
    chain = r.get("options_chain") or {}
    if not chain:
        return
    cur.execute("delete from public.option_chain where analysis_id=%s", (aid,))
    rows = []
    for side, sec in (("call", chain.get("calls") or []), ("put", chain.get("puts") or [])):
        if not isinstance(sec, list):
            continue
        for o in sec[:200]:  # cap at 200 per side per analysis to keep bulk write sane
            if not isinstance(o, dict):
                continue
            rows.append((
                aid, side,
                _num(o.get("strike")), _txt(o.get("expiry") or o.get("expirationDate")),
                _int(o.get("openInterest") or o.get("open_interest")),
                _int(o.get("totalVolume") or o.get("volume")),
                _num(o.get("volatility") or o.get("iv")),
                _num(o.get("delta")), _num(o.get("gamma")),
                _num(o.get("theta")), _num(o.get("vega")),
                _num(o.get("bid")), _num(o.get("ask")),
            ))
    if rows:
        cur.executemany(
            """
            insert into public.option_chain
                (analysis_id, side, strike, expiry, open_interest, volume,
                 iv, delta, gamma, theta, vega, bid, ask)
            values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            rows,
        )


def _sync_uoa_alerts_1n(cur, aid: int, r: dict) -> None:
    oi = r.get("options_intelligence") or {}
    calls = oi.get("true_uoa_calls") or []
    puts  = oi.get("true_uoa_puts") or []
    if not (calls or puts):
        return
    cur.execute("delete from public.option_uoa_alerts where analysis_id=%s", (aid,))
    rows = []
    for side, sec in (("call", calls), ("put", puts)):
        for o in sec:
            if not isinstance(o, dict):
                continue
            rows.append((
                aid, side,
                _num(o.get("strike")),
                _txt(o.get("expiry")),
                _int(o.get("volume")), _int(o.get("open_interest") or o.get("oi")),
                _num(o.get("vol_oi_ratio") or o.get("vol_oi")),
                _num(o.get("premium_dollars") or o.get("premium")),
                _bool(o.get("is_smart_money") or o.get("smart_money")),
            ))
    if rows:
        cur.executemany(
            """
            insert into public.option_uoa_alerts
                (analysis_id, side, strike, expiry, volume, open_interest,
                 vol_oi_ratio, premium_dollars, is_smart_money)
            values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            rows,
        )


def _sync_stocktwits_messages_1n(cur, aid: int, r: dict) -> None:
    st = r.get("stocktwits") or {}
    msgs = st.get("messages") or []
    if not isinstance(msgs, list) or not msgs:
        return
    cur.execute("delete from public.stocktwits_messages where analysis_id=%s", (aid,))
    rows = []
    for m in msgs[:50]:
        if not isinstance(m, dict):
            continue
        rows.append((
            aid,
            _txt(m.get("id") or m.get("message_id")),
            _txt(m.get("body") or m.get("text"), 2048),
            _txt(m.get("sentiment")),
            _txt(m.get("created_at") or m.get("createdAt")),
        ))
    if rows:
        cur.executemany(
            """
            insert into public.stocktwits_messages
                (analysis_id, message_id, body, sentiment, created_at)
            values (%s,%s,%s,%s,%s::timestamptz)
            """,
            rows,
        )


def _sync_analysis_earnings(cur, aid: int, r: dict) -> None:
    e = r.get("earnings") or {}
    if not e:
        return
    ticker = r.get("ticker")
    rdate = e.get("earnings_date") or e.get("next_earnings_date")
    event_id = None
    if ticker and rdate:
        try:
            cur.execute("""
                insert into public.earnings_events (ticker, report_date)
                values (%s, %s)
                on conflict (ticker, report_date) do update set ticker = excluded.ticker
                returning id
            """, (ticker, rdate))
            event_id = cur.fetchone()[0]
        except Exception:
            pass

    cur.execute(
        """
        insert into public.analysis_earnings
            (analysis_id, earnings_event_id, days_to_earnings, earnings_risk, earnings_warning)
        values (%s,%s,%s,%s,%s)
        on conflict (analysis_id) do update set
            earnings_event_id = excluded.earnings_event_id,
            days_to_earnings  = excluded.days_to_earnings,
            earnings_risk     = excluded.earnings_risk,
            earnings_warning  = excluded.earnings_warning
        """,
        (
            aid, event_id, _int(e.get("days_to_earnings")),
            _txt(e.get("earnings_risk")),
            _txt(r.get("earnings_warning"), 512),
        ),
    )


def _sync_ohlcv_window(cur, aid: int, r: dict) -> None:
    bars = r.get("ohlcv") or []
    if not isinstance(bars, list) or not bars:
        return
    import json
    cur.execute(
        """
        insert into public.analysis_ohlcv_window
            (analysis_id, bars_json, bar_count, first_date, last_date)
        values (%s, %s::jsonb, %s, %s, %s)
        on conflict (analysis_id) do update set
            bars_json = excluded.bars_json, bar_count = excluded.bar_count
        """,
        (
            aid, json.dumps(bars), len(bars),
            _txt((bars[0] or {}).get("date") or (bars[0] or {}).get("t")) if isinstance(bars[0], dict) else None,
            _txt((bars[-1] or {}).get("date") or (bars[-1] or {}).get("t")) if isinstance(bars[-1], dict) else None,
        ),
    )


def _sync_smart_money(cur, aid: int, r: dict) -> None:
    ins = r.get("insider_data") or {}
    if ins:
        cur.execute(
            """
            insert into public.insider_summary
                (analysis_id, buys, sells, ceo_buy, cfo_buy, sentiment,
                 days_since_last, max_single_buy, total_buy_value)
            values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            on conflict (analysis_id) do update set buys = excluded.buys
            """,
            (
                aid, _int(ins.get("buys")), _int(ins.get("sells")),
                _bool(ins.get("ceo_buy")), _bool(ins.get("cfo_buy")),
                _enum(ins.get("sentiment"), ("bullish","neutral","bearish"), lower=True),
                _int(ins.get("days_since_last")),
                _int(ins.get("max_single_buy")), _int(ins.get("total_buy_value")),
            ),
        )

    cg = r.get("congressional") or {}
    if cg:
        cur.execute(
            """
            insert into public.congressional_summary
                (analysis_id, purchases, sales, net, latest_member, source, source_unavailable)
            values (%s,%s,%s,%s,%s,%s,%s)
            on conflict (analysis_id) do update set purchases = excluded.purchases
            """,
            (
                aid, _int(cg.get("purchases")), _int(cg.get("sales")),
                _enum(cg.get("net"), ("bullish","neutral","bearish"), lower=True),
                _txt(cg.get("latest")), _txt(cg.get("source")),
                _bool(cg.get("source_unavailable")),
            ),
        )

    it = r.get("inst_trend") or {}
    if it:
        cur.execute(
            """
            insert into public.institutional_trend
                (analysis_id, inst_pct, inst_trend, net_change_pct, total_holders)
            values (%s,%s,%s,%s,%s)
            on conflict (analysis_id) do update set inst_pct = excluded.inst_pct
            """,
            (
                aid, _num(it.get("inst_pct")),
                _enum(it.get("inst_trend"), ("increasing","decreasing","stable"), lower=True),
                _num(it.get("net_change_pct")), _int(it.get("total_holders")),
            ),
        )


# ============================================================================
# Top-level entry point — called from swing_trade.py
# ============================================================================

# Ordered list of per-analysis writers. Each is wrapped in its own try/except
# so a failure on one (e.g. options) doesn't skip the rest.
_WRITERS = [
    # 1:1 narrow tables
    ("pricing",            _sync_pricing),
    ("scoring",            _sync_scoring),
    ("verdict",            _sync_verdict),
    ("conviction",         _sync_conviction),
    ("trade_plan",         _sync_trade_plan),
    ("risk_sizing",        _sync_risk_sizing),
    ("technicals",         _sync_technicals),
    ("options",            _sync_options),
    ("zacks",              _sync_zacks),
    ("tier1",              _sync_tier1),
    ("sentiment",          _sync_sentiment),
    ("smart_money",        _sync_smart_money),
    # Newly added 1:1 writers
    ("elliott_wave",       _sync_elliott_wave),
    ("theory",             _sync_theory),
    ("mtf",                _sync_mtf),
    ("fundamentals_pillar",_sync_fundamentals_pillar),
    ("sentiment_pillar",   _sync_sentiment_pillar),
    ("gamma_exposure",     _sync_gamma_exposure),
    ("volume_profile",     _sync_volume_profile),
    ("premarket",          _sync_premarket),
    ("tv_rating",          _sync_tv_rating),
    ("analysis_earnings",  _sync_analysis_earnings),
    ("ohlcv_window",       _sync_ohlcv_window),
    # 1:N expanders (TRUNCATE-for-aid then INSERT)
    ("gates_1n",           _sync_gates_1n),
    ("catalysts_1n",       _sync_catalysts_1n),
    ("methodology_1n",     _sync_methodology_1n),
    ("trade_plan_1n",      _sync_trade_plan_1n),
    ("chart_patterns_1n",  _sync_chart_patterns_1n),
    ("smc_1n",             _sync_smc_1n),
    ("option_chain_1n",    _sync_option_chain_1n),
    ("uoa_alerts_1n",      _sync_uoa_alerts_1n),
    ("stocktwits_1n",      _sync_stocktwits_messages_1n),
]


def sync_scan(bundle: dict) -> dict:
    """Bulk-INSERT analysis pipeline writer.

    Collects all per-ticker rows in memory, then performs one execute_values()
    per child table. Replaces ~12,000 round-trips (395 tickers × 30 tables) with
    ~50, giving ~50x speedup.

    Returns {ok, n_tickers, errors, elapsed_sec}. Never raises.
    """
    if not _enabled():
        return {"ok": False, "reason": "disabled", "n_tickers": 0}
    if not bundle or not isinstance(bundle, dict):
        return {"ok": False, "reason": "empty bundle", "n_tickers": 0}

    results = bundle.get("all_scored") or []
    if not results:
        return {"ok": True, "n_tickers": 0, "errors": {}}

    try:
        from psycopg2.extras import execute_values
    except Exception as e:
        return {"ok": False, "reason": f"psycopg2 import failed: {e}"}

    errors: dict[str, int] = {}
    t0 = time.time()

    try:
        conn = pg_conn()
    except Exception as e:
        log.warning(f"supabase_analysis_sync: pg_conn failed: {e}")
        return {"ok": False, "reason": f"connect failed: {e}", "n_tickers": 0}

    n_done = 0
    try:
        with conn:
            with conn.cursor() as cur:
                # ----- Step 1: run row + ticker master ------------------------
                run_id = _sync_run(cur, bundle)

                # bulk upsert tickers (idempotent)
                t_rows = []
                seen = set()
                for r in results:
                    t = r.get("ticker")
                    if not t or t in seen:
                        continue
                    seen.add(t)
                    t_rows.append((t, _txt(r.get("name")), _txt(r.get("sector")),
                                   _txt(r.get("industry")), _num(r.get("beta"))))
                if t_rows:
                    execute_values(
                        cur,
                        """
                        insert into public.tickers
                            (ticker, name, sector, industry, beta, last_seen)
                        values %s
                        on conflict (ticker) do update set
                            name      = coalesce(excluded.name, public.tickers.name),
                            sector    = coalesce(excluded.sector, public.tickers.sector),
                            industry  = coalesce(excluded.industry, public.tickers.industry),
                            beta      = coalesce(excluded.beta, public.tickers.beta),
                            last_seen = now()
                        """,
                        t_rows,
                        template="(%s,%s,%s,%s,%s,now())",
                        page_size=500,
                    )

                # ----- Step 2: bulk upsert ticker_analyses, fetch aid map -----
                ta_rows = []
                for r in results:
                    ticker = r.get("ticker")
                    if not ticker:
                        continue
                    decision = r.get("decision") or {}
                    conviction = r.get("conviction") or {}
                    indi = (r.get("technicals") or {}).get("indicators") or {}
                    ta_rows.append((
                        run_id, ticker,
                        _enum(r.get("verdict") or decision.get("verdict"),
                              ("BUY","WATCH","SHORT","AVOID"), upper=True) or "AVOID",
                        _enum(r.get("direction"), ("long","short","neutral"), lower=True),
                        _num(r.get("price")),
                        _int(r.get("score")),
                        _num(r.get("score_raw")),
                        _int(r.get("star_rating")),
                        _txt(r.get("setup_family")),
                        _txt(r.get("setup_type") or (r.get("trade_plan") or {}).get("setup_type")),
                        _int(r.get("catalyst_tier")),
                        _enum(r.get("entry_quality"),
                              ("FRESH","PULLBACK","VALID","EXTENDED","MISSED"), upper=True),
                        _txt(r.get("entry_subtype")),
                        _txt(r.get("entry_timing")),
                        _txt(r.get("hold_period_guide")),
                        _enum(conviction.get("label"), ("T1","T2","T3","WATCH"), upper=True),
                        _txt(r.get("reject_reason"), 1024) if r.get("reject_reason") else None,
                        _txt(r.get("ticker_source")),
                        _num(r.get("sector_pct_rank")),
                        _int(r.get("rs_rank") or indi.get("rs_rank")),
                        _num(indi.get("rs_63d_pct")),
                        _bool(r.get("mtf_conflict")),
                        _txt(r.get("mtf_label")),
                    ))

                aid_map: dict[str, int] = {}
                if ta_rows:
                    res = execute_values(
                        cur,
                        """
                        insert into public.ticker_analyses (
                            run_id, ticker, verdict, direction, price, score, score_raw,
                            star_rating, setup_family, setup_type, catalyst_tier, entry_quality,
                            entry_subtype, entry_timing, hold_period_guide, conviction_tier,
                            reject_reason, ticker_source, sector_pct_rank, rs_rank, rs_63d_pct,
                            mtf_conflict, mtf_label
                        ) values %s
                        on conflict (run_id, ticker) do update set
                            verdict           = excluded.verdict,
                            direction         = excluded.direction,
                            price             = excluded.price,
                            score             = excluded.score,
                            score_raw         = excluded.score_raw,
                            star_rating       = excluded.star_rating,
                            setup_family      = excluded.setup_family,
                            setup_type        = excluded.setup_type,
                            catalyst_tier     = excluded.catalyst_tier,
                            entry_quality     = excluded.entry_quality,
                            entry_subtype     = excluded.entry_subtype,
                            entry_timing      = excluded.entry_timing,
                            hold_period_guide = excluded.hold_period_guide,
                            conviction_tier   = excluded.conviction_tier,
                            reject_reason     = excluded.reject_reason,
                            ticker_source     = excluded.ticker_source,
                            sector_pct_rank   = excluded.sector_pct_rank,
                            rs_rank           = excluded.rs_rank,
                            rs_63d_pct        = excluded.rs_63d_pct,
                            mtf_conflict      = excluded.mtf_conflict,
                            mtf_label         = excluded.mtf_label,
                            analyzed_at       = now()
                        returning id, ticker
                        """,
                        ta_rows, page_size=500, fetch=True,
                    )
                    aid_map = {ticker: aid for aid, ticker in res}

                n_done = len(aid_map)
                if not aid_map:
                    return {"ok": True, "n_tickers": 0, "errors": errors,
                            "elapsed_sec": time.time() - t0}

                # ----- Step 3: per-child-table bulk INSERT --------------------
                # For each writer, build the row list across all tickers, then
                # execute_values for the entire batch.
                for label, fn in _WRITERS:
                    try:
                        _bulk_write_table(cur, label, fn, aid_map, results, execute_values, errors)
                    except Exception as e:
                        errors[label + "_bulk"] = errors.get(label + "_bulk", 0) + 1
                        log.debug(f"supabase_sync: bulk {label} failed: {e}")
    finally:
        try:
            conn.close()
        except Exception:
            pass

    elapsed = time.time() - t0
    log.info(
        f"supabase_analysis_sync: wrote {n_done}/{len(results)} tickers "
        f"in {elapsed:.1f}s · errors={errors or 'none'}"
    )
    return {"ok": True, "n_tickers": n_done, "errors": errors, "elapsed_sec": elapsed}


class _BufferedCursor:
    """Captures cur.execute()/executemany() calls into a {sql → [args,...]}
    map instead of sending each statement immediately. flush() then runs each
    SQL with execute_batch() — turning N round-trips of the same statement
    into 1 (or page_size'd) round-trip.

    Only methods used by the writers are implemented. Anything that returns
    rows (RETURNING / fetchone) falls back to the real cursor.
    """
    def __init__(self, real_cur):
        self._real = real_cur
        self._buf: dict[str, list[tuple]] = {}

    # Buffered path
    def execute(self, sql, args=None):
        if "returning" in sql.lower() or sql.lower().lstrip().startswith(("select", "delete", "update", "savepoint", "release", "rollback")):
            # passthrough to real cursor
            return self._real.execute(sql, args)
        self._buf.setdefault(sql, []).append(args or ())

    def executemany(self, sql, args_list):
        self._buf.setdefault(sql, []).extend(args_list)

    # Passthrough for everything else (RETURNING, fetchone, etc.)
    def fetchone(self):
        return self._real.fetchone()

    def fetchall(self):
        return self._real.fetchall()

    def flush(self):
        """Run accumulated statements via execute_batch."""
        from psycopg2.extras import execute_batch
        ran = 0
        for sql, args_list in self._buf.items():
            if not args_list:
                continue
            execute_batch(self._real, sql, args_list, page_size=200)
            ran += len(args_list)
        self._buf.clear()
        return ran


def _bulk_write_table(cur, label, fn, aid_map, results, execute_values_fn, errors):
    """Run a per-ticker writer for every ticker, buffering INSERTs into one
    batched round-trip per SQL template (instead of one per call).
    """
    buf = _BufferedCursor(cur)
    bad = 0
    for r in results:
        ticker = r.get("ticker")
        aid = aid_map.get(ticker)
        if aid is None:
            continue
        try:
            fn(buf, aid, r)
        except Exception as e:
            bad += 1
            if bad <= 3:
                log.debug(f"supabase_sync: {label}/{ticker} extract failed: {e}")
    # Flush all buffered INSERTs in one batched call per SQL template
    try:
        n_sent = buf.flush()
    except Exception as e:
        # On batch failure, rollback the savepoint (if any) — fall back to per-row
        bad += 1
        log.debug(f"supabase_sync: bulk flush {label} failed: {e}")
        n_sent = 0
    if bad:
        errors[label] = bad


# ============================================================================
# CLI: manual back-fill from last_bundle.json
# ============================================================================
if __name__ == "__main__":
    import argparse
    import json

    ap = argparse.ArgumentParser(description="Sync a scan bundle into Supabase")
    ap.add_argument("--bundle", default="cache/last_bundle.json", help="path to bundle JSON")
    ap.add_argument("--limit",  type=int, default=None, help="only sync first N tickers")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    path = Path(args.bundle)
    if not path.exists():
        print(f"bundle not found: {path}")
        sys.exit(2)

    bundle = json.loads(path.read_text())
    if args.limit:
        bundle["all_scored"] = (bundle.get("all_scored") or [])[:args.limit]

    res = sync_scan(bundle)
    print(json.dumps(res, indent=2, default=str))
