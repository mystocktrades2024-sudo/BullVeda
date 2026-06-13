"""
SwingTrade — Rules-Based Swing Trading Agent
Main orchestrator: runs the full pipeline from universe building to HTML output.

Usage:
    python3 swing_trade.py                    # Full daily scan
    python3 swing_trade.py deep NVDA          # Deep dive on one ticker
    python3 swing_trade.py history             # Show performance stats
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as _FutureTimeout
from datetime import datetime, date
from pathlib import Path

import pandas as pd
from data_fetcher import yf  # _YfStub: empty no-op (yfinance removed 2026-04-25)

# Silence yfinance's HTTP-retry noise.  After the Schwab/Polygon/Finviz
# migration (2026-04-24) yfinance is only a last-resort fallback; its
# internal retry flow still logs 401 "Invalid Crumb" errors even when the
# retry succeeds, which spams the scan log with ~1,000 lines per run.
# Raise the library's logger to CRITICAL so only fatal issues surface;
# our own log.info/warn messages are unaffected.
logging.getLogger("yfinance").setLevel(logging.CRITICAL)

# Suppress the yfinance DeprecationWarning flood. After EODHD's fundamentals
# endpoint started returning empty (mass failover seen 2026-05-11), every
# ticker triggers yfinance's deprecated Ticker.earnings code path, producing
# ~50 warning lines per ticker × 600 tickers = 30k+ lines drowning out the
# real progress log. The warnings reach stderr via warnings.warn(), bypassing
# the yfinance logger above, so we must use the warnings module to silence them.
import warnings as _warnings
_warnings.filterwarnings("ignore", category=DeprecationWarning, module="yfinance")
_warnings.filterwarnings("ignore", category=FutureWarning, module="yfinance")

from social_signals import get_social_signals
from data_fetcher import (
    load_config, get_sp500, get_russell1000, fetch_all_zacks_data,
    fetch_market_data, get_stock_info, get_stock_info_batch,
    get_market_regime, compute_sector_dispersion, get_earnings_date, get_news_sentiment,
    get_insider_activity, get_analyst_data, get_tv_ratings_batch,
    get_stocktwits_data, get_sector_etf_data, get_weekly_data,
    get_options_iv_data, get_earnings_beat_rate,
    get_macro_signals, get_market_breadth, get_extra_fundamentals,
    get_fundamentals_rich,
    get_fear_greed, get_congressional_trades, get_reddit_wsb,
    get_live_price, get_unusual_options, get_borrow_rate,
    get_quarterly_revenue_growth,
    get_finnhub_data, get_fmp_data, get_fundamentals, get_sec_filings,
    get_premarket_volume, get_institutional_trend,
    get_gamma_squeeze_data, get_earnings_estimate_trend,
    get_finviz_bulk, get_finviz_news,
    get_news_articles,
    _TV_EXCHANGE_MAP,
)
# Backward-compat aliases for any in-file refs still using old names
get_schwab_fundamentals = get_fundamentals
get_news_articles        = get_news_articles

def get_schwab_options(ticker: str, expiry: Optional[str] = None) -> dict:
    """Fetch a Schwab option chain for one expiry. Returns {calls:[...], puts:[...]} or {}.
    Schwab's response uses callExpDateMap[date]: {strike: [contract,...]} — we flatten.

    Schwab is the authorized options provider. Returns {} if credentials missing
    or refresh fails (caller handles missing data gracefully)."""
    try:
        import schwab_client as _sc
    except Exception:
        return {}
    try:
        raw = _sc.get_chains(ticker, contract_type="ALL", strike_count=10,
                             from_date=expiry, to_date=expiry)
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict = {"calls": [], "puts": []}
    for side, key in (("calls", "callExpDateMap"), ("puts", "putExpDateMap")):
        date_map = raw.get(key) or {}
        for _, strike_map in date_map.items():
            for _, contracts in (strike_map or {}).items():
                for c in (contracts or []):
                    if not isinstance(c, dict):
                        continue
                    out[side].append({
                        "strike": c.get("strikePrice"),
                        "iv": c.get("volatility"),
                        "oi": c.get("openInterest"),
                        "volume": c.get("totalVolume"),
                        "bid": c.get("bid"),
                        "ask": c.get("ask"),
                        "delta": c.get("delta"),
                    })
    return out
from analysis import analyze_ticker, raw_value_score, raw_growth_score, raw_momentum_score
# Phase B (2026-05-08): html_generator.build_dashboard import removed. The
# legacy single-page HTML dashboard generator is no longer called from any
# live code path. Source preserved in _legacy/html_generator.py if needed.
from tracker import (record_run, evaluate_pending, compute_stats, get_full_history,
                     mark_to_market, compute_stats_by_setup)
from portfolio_tracker import refresh_prices, get_portfolio_summary
from gmail_zacks import fetch_zacks_emails, get_zacks_email_bonus
from alerts import send_scan_alerts
# Phase B (2026-05-08): email_report.send_dashboard_email retired —
# depended on cache/dashboard.html (legacy single-page dump) which is no
# longer generated. Slack alerts via alerts.send_alert cover the use case.
# Source preserved at email_report.py if you want to revive for V2.
from crypto_screener import run_crypto_scan

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("swingtrade")

BASE_DIR = Path(__file__).parent


def _check_connectivity() -> tuple[bool, list[str]]:
    """Verify critical endpoints resolve before scan starts.

    Returns (all_ok, failure_messages). Does NOT abort on failure — caller
    decides whether to enable degraded mode. Uses a 3-second DNS timeout
    per host so total wall-clock stays < 10s even if all fail.
    """
    import socket
    endpoints = [
        ("eodhd.com", 443),
    ]
    failures: list[str] = []
    _prev_timeout = socket.getdefaulttimeout()
    try:
        socket.setdefaulttimeout(3)
        for host, _port in endpoints:
            try:
                socket.gethostbyname(host)
            except socket.gaierror as e:
                failures.append(f"{host} DNS: {e}")
            except Exception as e:
                failures.append(f"{host}: {e}")
    finally:
        socket.setdefaulttimeout(_prev_timeout)
    return (len(failures) == 0, failures)


def _compute_portfolio_risk(results: list, market_data: dict, spy_close) -> dict:
    """
    Compute portfolio-level risk metrics from the scored results universe.

    Metrics:
    - sector_concentration: top-3 sectors by count + pct of total
    - beta_exposure: avg beta across BUY candidates (beta-adjusted net long exposure)
    - correlation_matrix: pairwise return correlations for BUY candidates (max 10)
    - max_drawdown_flags: any BUY candidates with >40% drawdown from ATH
    - gap_risk_flags: any BUY candidates with high gap risk
    """
    import numpy as np

    buy_results = [r for r in results if r.get("decision", {}).get("verdict") == "BUY"]

    # Sector concentration across all scored results (passed gate)
    sector_counts: dict[str, int] = {}
    for r in results:
        s = r.get("sector", "Unknown")
        sector_counts[s] = sector_counts.get(s, 0) + 1
    total = len(results) or 1
    sector_concentration = sorted(
        [{"sector": k, "count": v, "pct": round(v / total * 100, 1)}
         for k, v in sector_counts.items() if k and k != "Unknown"],
        key=lambda x: x["count"], reverse=True
    )

    # Beta-adjusted exposure for BUY candidates
    betas = []
    for r in buy_results:
        b = r.get("beta")
        try:
            betas.append(float(b))
        except (TypeError, ValueError):
            betas.append(1.0)  # assume market beta if unknown
    avg_beta = round(sum(betas) / len(betas), 2) if betas else None

    # Return correlations for BUY candidates (up to 10)
    correlation_matrix = []
    corr_tickers = [r["ticker"] for r in buy_results[:10] if r["ticker"] in market_data]
    if len(corr_tickers) >= 2 and spy_close is not None:
        try:
            returns = {}
            for t in corr_tickers:
                c = market_data[t]["Close"].squeeze()
                c.index = pd.to_datetime(c.index)
                spy_aligned = spy_close.reindex(c.index, method="nearest")
                # Use last 60 days
                rets = c.pct_change().tail(60).dropna()
                if len(rets) >= 20:
                    returns[t] = rets
            if len(returns) >= 2:
                df_ret = pd.DataFrame(returns).dropna(how="any")
                corr = df_ret.corr().round(2)
                # Convert to list of {t1, t2, corr} pairs (upper triangle only)
                tks = list(corr.columns)
                for i in range(len(tks)):
                    for j in range(i + 1, len(tks)):
                        v = float(corr.iloc[i, j])
                        if not np.isnan(v):
                            correlation_matrix.append({
                                "t1": tks[i], "t2": tks[j], "corr": v,
                                "level": "high" if v > 0.7 else ("med" if v > 0.4 else "low"),
                            })
                correlation_matrix.sort(key=lambda x: abs(x["corr"]), reverse=True)
        except Exception as e:
            log.debug(f"Correlation matrix computation failed: {e}")

    # Flag BUY candidates with high drawdown or gap risk
    drawdown_flags = []
    gap_flags = []
    for r in buy_results:
        dd = r.get("gate", {}).get("drawdown_from_ath")
        if dd is not None and dd > 40:
            drawdown_flags.append({"ticker": r["ticker"], "drawdown_pct": dd})
        gr = r.get("gate", {}).get("gap_risk", {})
        if gr.get("level") == "high":
            gap_flags.append({
                "ticker": r["ticker"],
                "large_gaps_20d": gr.get("large_gaps_20d"),
                "avg_gap_pct": gr.get("avg_gap_pct"),
            })

    return {
        "sector_concentration": sector_concentration[:10],
        "avg_beta": avg_beta,
        "beta_count": len(betas),
        "correlation_matrix": correlation_matrix[:20],
        "drawdown_flags": drawdown_flags,
        "gap_flags": gap_flags,
    }


def _vgm_verdict(score: float, rr: float, vgm: str, growth: str) -> str:
    """Derive VGM verdict from score + grades."""
    if vgm == "A" and score >= 75 and rr >= 3.0:
        return "Strong Buy"
    elif vgm in ("A", "B") and score >= 65 and rr >= 3.0:
        return "Buy"
    elif vgm in ("A", "B") and score >= 55:
        return "Watch"
    elif vgm == "C" and score >= 60:
        return "Watch"
    elif vgm in ("D", "F") or score < 50:
        return "Avoid"
    else:
        return "Watch"


def assign_vgm_grades(results: list[dict]) -> list[dict]:
    """Percentile-rank V/G/M scores across scanned universe. Assigns letter grades + VGM composite."""
    import numpy as np

    def percentile_grade(score, all_scores):
        if not all_scores or score is None:
            return "N/A"
        arr = np.array([s for s in all_scores if s is not None])
        if len(arr) == 0:
            return "N/A"
        pct = float(np.sum(arr <= score)) / len(arr) * 100
        if pct >= 80: return "A"
        elif pct >= 60: return "B"
        elif pct >= 40: return "C"
        elif pct >= 20: return "D"
        else: return "F"

    v_scores = [r.get("raw_value_score") for r in results if r.get("raw_value_score") is not None]
    g_scores = [r.get("raw_growth_score") for r in results if r.get("raw_growth_score") is not None]
    m_scores = [r.get("raw_momentum_score") for r in results if r.get("raw_momentum_score") is not None]

    # Pre-compute VGM composite raw scores for all tickers (needed for percentile ranking)
    all_vgm_raws = []
    for r in results:
        c2 = []
        tw2 = 0.0
        if r.get("raw_value_score") is not None:
            c2.append(r["raw_value_score"] * 0.30); tw2 += 0.30
        if r.get("raw_growth_score") is not None:
            c2.append(r["raw_growth_score"] * 0.40); tw2 += 0.40
        if r.get("raw_momentum_score") is not None:
            c2.append(r["raw_momentum_score"] * 0.30); tw2 += 0.30
        all_vgm_raws.append(sum(c2) / tw2 if tw2 > 0 else None)

    for i, r in enumerate(results):
        v_raw = r.get("raw_value_score")
        g_raw = r.get("raw_growth_score")
        m_raw = r.get("raw_momentum_score")

        r["grade_value"]    = percentile_grade(v_raw, v_scores)
        r["grade_growth"]   = percentile_grade(g_raw, g_scores)
        r["grade_momentum"] = percentile_grade(m_raw, m_scores)

        vgm_raw = all_vgm_raws[i]
        if vgm_raw is not None:
            r["grade_vgm"] = percentile_grade(vgm_raw, [x for x in all_vgm_raws if x is not None])
        else:
            r["grade_vgm"] = "N/A"

        # VGM verdict
        score = r.get("score", 0)
        rr = r.get("plan", {}).get("rr_ratio", 0) if isinstance(r.get("plan"), dict) else 0
        # Also try trade_plan key (used in analyze_ticker result dict)
        if rr == 0:
            rr = r.get("trade_plan", {}).get("rr_ratio", 0) if isinstance(r.get("trade_plan"), dict) else 0
        r["vgm_verdict"] = _vgm_verdict(score, rr, r["grade_vgm"], r.get("grade_growth", "N/A"))

    return results


# Code defaults for fallback detection — keep in sync with analysis/config defaults.
_BANNER_CODE_DEFAULTS = {
    "buy_min_score":            65,
    "watch_min_score":          50,
    "rs_min":                   70,
    "rr_min":                   2.5,
    "weekly_bull_required":     True,
    "catalyst_override_offset": 15,
}


def print_active_config_banner(config: dict, regime4: str | None = None) -> None:
    """Log a startup banner echoing the resolved active config.

    Surfaces the thresholds actually in effect (regime + regime4) so silent
    fallbacks to code defaults are visible. Call once at scan start before
    the main scan loop. Read-only — does not mutate config.
    """
    try:
        # --- Resolve active profile name ---
        profile_name = (
            config.get("_profile_name")
            or config.get("_meta", {}).get("profile")
            or config.get("_meta", {}).get("_profile_name")
        )
        if not profile_name:
            try:
                ptr = BASE_DIR / "config" / "history" / "active_profile.txt"
                if ptr.exists():
                    profile_name = ptr.read_text().strip() or None
            except Exception:
                profile_name = None
        profile_name = profile_name or "unknown"

        # --- Resolve regime buckets ---
        regime_name = "bull"
        try:
            regime_name = (config.get("_active_regime")
                           or config.get("_meta", {}).get("active_regime")
                           or "bull")
        except Exception:
            pass

        regime_thresholds = config.get("regime_thresholds", {}) or {}
        regime4_thresholds = config.get("regime4_thresholds", {}) or {}
        r_block = regime_thresholds.get(regime_name, {}) or {}
        r4_block = regime4_thresholds.get(regime4 or "", {}) or {}

        warnings: list[str] = []

        def _resolve(key: str, primary: dict, secondary: dict | None = None):
            """Return (value, source). Source: 'regime'/'regime4'/'default'."""
            if key in primary:
                return primary[key], "regime"
            if secondary and key in secondary:
                return secondary[key], "regime4"
            warnings.append(f"{key} fell back to code default "
                            f"({_BANNER_CODE_DEFAULTS.get(key, '?')})")
            return _BANNER_CODE_DEFAULTS.get(key), "default"

        buy_min,    _src_buy   = _resolve("buy_min_score",   r_block, r4_block)
        watch_min,  _src_watch = _resolve("watch_min_score", r_block, r4_block)
        rs_min,     _src_rs    = _resolve("rs_min",          r_block, r4_block)
        rr_min,     _src_rr    = _resolve("rr_min",          r_block, r4_block)
        wbr = r_block.get("weekly_bull_required",
                          config.get("weekly_bull_required", False))

        # catalyst_override_offset: check decisions, top-level, gates, scoring
        catalyst_offset = None
        for _parent in (config.get("decisions", {}),
                        config,
                        config.get("gates", {}),
                        config.get("scoring", {})):
            if isinstance(_parent, dict) and _parent.get("catalyst_override_offset") is not None:
                catalyst_offset = _parent["catalyst_override_offset"]
                break
        if catalyst_offset is None:
            catalyst_offset = _BANNER_CODE_DEFAULTS["catalyst_override_offset"]
            warnings.append(f"catalyst_override_offset fell back to code default "
                            f"({_BANNER_CODE_DEFAULTS['catalyst_override_offset']})")
            catalyst_source = "default (code)"
        else:
            catalyst_source = "config"

        # setup_gates presence + non-default listing
        setup_gates = config.get("setup_gates", {}) or {}
        default_gate = setup_gates.get("default", {})
        non_default_setups = []
        for setup_name, gate in setup_gates.items():
            if setup_name == "default" or not isinstance(gate, dict):
                continue
            if gate != default_gate:
                non_default_setups.append(setup_name)

        # regime4 max_size_pct
        max_size_pct = r4_block.get("max_size_pct", "—")

        # --- Print banner ---
        bar = "═" * 60
        log.info(bar)
        log.info(f" SwingTrade Active Config — Profile: {profile_name}")
        log.info(bar)
        log.info(f"   Regime: {regime_name} (regime4: {regime4 or 'unknown'})")
        log.info(f"   buy_min_score:    {buy_min}")
        log.info(f"   watch_min_score:  {watch_min}")
        log.info(f"   rs_min:           {rs_min}")
        log.info(f"   rr_min:           {rr_min}")
        log.info(f"   weekly_bull_required: {str(bool(wbr)).lower()}")
        log.info(f"   catalyst_override_offset: {catalyst_offset}  "
                 f"(code default: {_BANNER_CODE_DEFAULTS['catalyst_override_offset']}, source: {catalyst_source})")
        log.info(f"   setup_gates: {len(setup_gates)} setups configured"
                 + (f" (non-default: {', '.join(non_default_setups)})" if non_default_setups else ""))
        log.info(f"   max_size_pct:     {max_size_pct} (regime4)")
        if warnings:
            for w in warnings:
                log.warning(f"   ⚠ FALLBACK: {w}")
        log.info(bar)
    except Exception as e:
        log.warning(f"print_active_config_banner failed: {e}")


def _circuit_breaker_review_reminder(cfg):
    """If the drawdown breaker is disabled, ping Slack every 90 days to re-evaluate.
    Self-rolling: posts when today >= review_date, then advances review_date +90d."""
    try:
        cb = (cfg.get("circuit_breaker") or {})
        if not cb.get("disabled"):
            return
        from datetime import date, timedelta
        rd = cb.get("review_date")
        if not rd or date.today() < date.fromisoformat(str(rd)):
            return
        # fire the reminder
        try:
            import os, json as _json
            url = os.environ.get("SLACK_WEBHOOK_URL", "")
            if url:
                import urllib.request
                msg = (f"⏰ *Circuit breaker review* — the drawdown circuit breaker has been "
                       f"DISABLED (paper-trading mode) since the last review. It's been ~90 days. "
                       f"Re-evaluate whether to keep it off, and *re-enable it before any LIVE trading* "
                       f"(`config/config.json` → `circuit_breaker.disabled = false`).")
                req = urllib.request.Request(url, data=_json.dumps({"text": msg}).encode(),
                                             headers={"Content-Type": "application/json"})
                urllib.request.urlopen(req, timeout=8)
                log.info("  Circuit-breaker 90-day review reminder posted to Slack.")
        except Exception as _se:
            log.warning(f"  CB review reminder Slack post failed: {_se}")
        # advance the review date +90 days in config.json (idempotent — won't re-fire today)
        try:
            from pathlib import Path as _P
            import json as _json
            cpath = _P(__file__).resolve().parent / "config" / "config.json"
            full = _json.loads(cpath.read_text())
            full.setdefault("circuit_breaker", {})["review_date"] = (date.fromisoformat(str(rd)) + timedelta(days=90)).isoformat()
            cpath.write_text(_json.dumps(full, indent=2))
        except Exception as _ce:
            log.warning(f"  CB review_date advance failed: {_ce}")
    except Exception:
        pass


def run_daily_scan(force_fresh: bool = False):
    """Full daily scan pipeline."""
    cfg = load_config()
    run_date      = datetime.now().strftime("%Y-%m-%d")
    run_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    log.info(f"=== SwingTrade Daily Scan — {run_timestamp} ===")
    _circuit_breaker_review_reminder(cfg)

    # ── EODHD quota preflight (2026-06-02) ──────────────────────────────────
    # Reconcile the daily counter to EODHD's AUTHORITATIVE billed-unit usage,
    # then throttle/abort if near the limit. Root cause being fixed: the local
    # counter bumped +1/request while EODHD bills weighted units (fundamentals
    # =10, intraday=5, bulk=100) → it read 18K while real usage was ~100K, so
    # the budget guard never fired and stacked scans + the 3500-name nightly
    # enrich blew through 100K silently (2026-06-02). Now: sync to truth, then
    #   ≥ throttle_pct → light mode (skip deep fundamentals — the 10× driver)
    #   ≥ abort_pct    → skip this scan (don't burn the last calls on a run that
    #                    would degrade to Yahoo-fallback anyway). Resets 00:00 UTC.
    try:
        import eodhd_client as _ecq
        _ecq.sync_quota_from_server()                # reconcile to real usage (1 unit)
        _qs   = _ecq.eodhd_quota_status()
        _used = int(_qs.get("count", 0)); _cap = int(_qs.get("daily_limit", 100000) or 100000)
        _pct  = (_used / _cap * 100) if _cap else 0.0
        _qcfg = cfg.get("eodhd_quota", {}) or {}
        _throttle_pct = float(_qcfg.get("throttle_pct", 85))
        _abort_pct    = float(_qcfg.get("abort_pct", 97))
        log.info(f"  EODHD budget: {_used:,}/{_cap:,} ({_pct:.0f}%) billed units used today "
                 f"(throttle ≥{_throttle_pct:.0f}% · abort ≥{_abort_pct:.0f}%)")
        if _pct >= _abort_pct:
            log.warning(f"🔴 EODHD quota at {_pct:.0f}% (≥{_abort_pct:.0f}%) — SKIPPING scan to avoid "
                        f"burning the last calls on a degraded run. Budget resets 00:00 UTC.")
            return
        if _pct >= _throttle_pct and os.environ.get("SCAN_MODE", "").lower() != "light":
            os.environ["SCAN_MODE"] = "light"
            log.warning(f"🟡 EODHD quota at {_pct:.0f}% (≥{_throttle_pct:.0f}%) — THROTTLING to light "
                        f"mode (shrink deep-enrich tier, skip most fundamentals) to protect the budget.")
    except Exception as _qe:
        log.debug(f"EODHD quota preflight skipped (non-fatal): {_qe}")

    # ── 2026-05-22: Schwab refresh-token health probe ──
    # Refresh tokens have a 7-day lifetime; if the scanner stops for >7d (or
    # the rotated token wasn't written back), Schwab calls fail with HTTP 400
    # and IV Rank goes to 0/N silently. Surface the failure at scan start.
    try:
        from schwab_auth import check_token_health as _schwab_health
        _h = _schwab_health()
        if _h["status"] == "dead":
            log.warning("🔴 SCHWAB TOKEN DEAD — IV Rank / Schwab options data will be empty this scan")
            log.warning(f"   {_h['message']}")
        elif _h["status"] == "warn":
            log.warning(f"🟡 SCHWAB TOKEN AGING — {_h['message']}")
        elif _h["status"] == "ok":
            log.info(f"  Schwab refresh token OK (age {_h['days_since_saved']}d)")
        # 'unknown' (pre-2026-05-22 install, no saved_at) is silent
    except Exception as e:
        log.debug(f"Schwab health probe failed (non-fatal): {e}")

    # ── P0-1 (2026-05-10): refresh prices THEN compute drawdown ──
    # refresh_prices() now appends/updates today's equity_curve point so
    # compute_current_drawdown_pct sees a fresh mark-to-market. Previously
    # the curve only updated on close_position, leaving drawdown_mult stale.
    try:
        from portfolio_tracker import refresh_prices as _refresh_prices_early
        _refresh_prices_early()
    except Exception as e:
        log.debug(f"Early price refresh failed (non-fatal): {e}")

    # ── P0-1: inject current drawdown_pct into vol-targeting config ──
    # kelly_position_size reads cfg.portfolio_vol_targeting._runtime_drawdown_pct
    # to scale position size during drawdowns. Without this injection it's a no-op.
    try:
        from portfolio_tracker import compute_current_drawdown_pct
        _dd = compute_current_drawdown_pct(lookback_days=90)
        if _dd and _dd.get("drawdown_pct") is not None:
            _vol = cfg.setdefault("portfolio_vol_targeting", {})
            _vol["_runtime_drawdown_pct"] = float(_dd["drawdown_pct"])
            _vol["_runtime_peak_equity"] = _dd.get("peak_equity")
            _vol["_runtime_current_equity"] = _dd.get("current_equity")
            log.info(
                f"Drawdown sizing wired: {_dd['drawdown_pct']:.2f}% below peak "
                f"(${_dd.get('peak_equity')} → ${_dd.get('current_equity')}, "
                f"peak {_dd.get('peak_date')}, n={_dd.get('n_points')})"
            )
    except Exception as e:
        log.debug(f"Drawdown injection failed (non-fatal): {e}")

    # Log rotation — compress >30d logs, delete >90d archives
    try:
        from log_rotation import rotate_logs
        rotate_logs()
    except Exception as e:
        log.debug(f"Log rotation failed: {e}")

    # Daily state backup — snapshot critical JSON state files (idempotent)
    try:
        from state_backup import backup_state
        backup_state()
    except Exception as e:
        log.debug(f"State backup failed: {e}")

    # Pre-scan connectivity check — detect DNS/network outages before they
    # silently kill ~35% of the universe. If any critical endpoint fails to
    # resolve, enable archive-first degraded mode (Fix #1 + #5).
    try:
        _conn_ok, _conn_issues = _check_connectivity()
        if not _conn_ok:
            log.error("Network connectivity check FAILED — scan may produce incomplete results:")
            for _issue in _conn_issues:
                log.error(f"   {_issue}")
            log.warning("Proceeding with DEGRADED MODE (archive-first failover). "
                        "Expect elevated killed-ticker count.")
            try:
                from data_fetcher import enable_degraded_mode as _edm
                _edm()
            except Exception as _edm_e:
                log.debug(f"Could not enable degraded mode: {_edm_e}")
            # Loud alert via Slack/Mac so operator sees it immediately
            try:
                from alerts import send_alert
                send_alert(
                    level="WARN",
                    title="Network connectivity degraded",
                    body=f"DNS/endpoint checks failed: {'; '.join(_conn_issues)}. "
                         f"Scan running in archive-first degraded mode.",
                )
            except Exception:
                pass
        else:
            log.info("  Connectivity check: all endpoints resolve ✓")
    except Exception as _conn_e:
        log.debug(f"Connectivity check skipped: {_conn_e}")

    # Auto-update data archive before scan (ensures D1-D5 columns populate)
    try:
        from data_archive import delta_update as _da_update
        log.info("  Updating data archive...")
        _da_update()
        log.info("  Archive updated ✓")
    except Exception as _da_e:
        log.warning(f"  Archive update failed (scan continues with stale data): {_da_e}")

    # Startup config validator — surface issues early, fail-fast on 🔴 critical
    try:
        from config_validator import validate_config
        _cfg_issues = validate_config()
        if _cfg_issues:
            for _i in _cfg_issues:
                if _i.startswith("🔴"):
                    log.error(f"  Config: {_i}")
                else:
                    log.warning(f"  Config: {_i}")
    except Exception as _cve:
        log.debug(f"Config validation skipped: {_cve}")

    # Data freshness guard — SPY bar age (market hours check removed with Schwab decommission)
    try:
        _market_open = None  # Could be derived from PST time if needed; for now scan runs whenever
        from data_fetcher import fetch_market_data as _fmd
        _spy_check = _fmd(["SPY"])
        _spy_df_check = _spy_check.get("SPY") if isinstance(_spy_check, dict) else None
        if _spy_df_check is not None and not _spy_df_check.empty:
            _last_bar = _spy_df_check.index[-1]
            _hours_stale = (datetime.now(_last_bar.tz) - _last_bar).total_seconds() / 3600 if getattr(_last_bar, "tz", None) else (datetime.now() - _last_bar.to_pydatetime()).total_seconds() / 3600
            _wd = datetime.now().weekday()  # 0=Mon..6=Sun
            # Max acceptable staleness: weekends/Mon allow 96h (Fri close → Mon pre-market)
            _max_stale = 96 if _wd in (0, 5, 6) else (96 if _market_open is False else 48)
            if _hours_stale > _max_stale:
                log.error(f"  🔴 DATA FRESHNESS: SPY last bar is {_hours_stale:.0f}h old (max {_max_stale}h) — aborting scan, check Polygon")
                raise RuntimeError(f"Data >{_max_stale}h stale")
            else:
                log.info(f"  Data freshness: SPY last bar {_hours_stale:.1f}h old ✓")
    except RuntimeError:
        raise
    except Exception as _dfe:
        log.debug(f"Data freshness check skipped: {_dfe}")

    # Step 0: Evaluate any pending trades from prior runs
    evaluated = evaluate_pending(hold_days=5)
    if evaluated:
        log.info(f"Auto-evaluated {evaluated} pending trades")

    # Step 0: Pre-scan cache clear — read previous Data Health and clear FAIL sources
    try:
        _prev_bundle = Path(cache_dir / "last_bundle.json")
        if _prev_bundle.exists():
            import glob as _gl0
            _prev = json.loads(_prev_bundle.read_text(errors="replace").encode("utf-8", errors="replace").decode("utf-8"))
            _prev_dh = _prev.get("data_health", {}).get("checks", [])
            _cache_map = {
                "IV Rank": "cache/_cache_options_*",
                "Beat Rate": "cache/_cache_finnhub_*",
                "Analyst Revisions": "cache/_cache_finnhub_*",
                "Insider Activity": "cache/_cache_insider_*",
                "Polygon News NLP": "cache/_cache_polygon_news_*",
                "Beta": "cache/_cache_finviz_*",
                "Valuation (PEG)": "cache/_cache_finviz_*",
            }
            _pre_cleared = 0
            _pre_patterns = set()
            for c in _prev_dh:
                if c.get("status") in ("fail", "warn"):
                    pattern = _cache_map.get(c["label"])
                    if pattern and pattern not in _pre_patterns:
                        for f in _gl0.glob(str(BASE_DIR / pattern)):
                            try:
                                os.remove(f)
                                _pre_cleared += 1
                            except Exception:
                                pass
                        _pre_patterns.add(pattern)
            if _pre_cleared:
                log.info(f"Step 0: Pre-scan cache clear — {_pre_cleared} stale files for FAIL/WARN sources")
    except Exception as _e0:
        log.debug(f"Pre-scan cache clear failed: {_e0}")

    # Step 0b: Sync Alpaca paper account state into local stores (ALPACA-SYNC,
    # commit 2026-05-10). Best-effort — failures (auth missing, network) log
    # but don't block the scan. Output feeds portfolio dashboard + kelly_size
    # drawdown_haircut + future tracker pick attribution.
    try:
        from alpaca_sync import sync_alpaca_to_local
        _sync = sync_alpaca_to_local(verbose=False)
        if _sync.get("ok"):
            log.info(
                f"Step 0b: Alpaca sync OK — equity=${_sync['equity']:,.2f} "
                f"positions(alpaca={_sync.get('alpaca_position_count',0)}) "
                f"+{len(_sync.get('inserted') or [])} ~{len(_sync.get('updated') or [])} "
                f"-{len(_sync.get('closed') or [])} new_closed_trades={_sync.get('new_closed_trades',0)}"
            )
        elif _sync.get("skipped"):
            log.debug(f"Step 0b: Alpaca sync rate-limited ({_sync['skipped']})")
        else:
            log.warning(f"Step 0b: Alpaca sync failed: {_sync.get('error')}")
    except Exception as _e0b:
        log.warning(f"Step 0b: Alpaca sync skipped (best-effort): {_e0b}")

    # Step 1: Build universe + fetch all Zacks premium data in one browser session
    log.info("Step 1: Building universe + fetching Zacks premium data...")
    sp500 = get_sp500()
    log.info(f"  S&P 500: {len(sp500)} tickers")
    if len(sp500) < 200:
        log.error(f"S&P 500 returned only {len(sp500)} tickers — universe too small, aborting scan")
        return

    universe_cfg = cfg.get("universe", {})
    include_r1000 = universe_cfg.get("include_russell1000", False)
    russell1000 = []
    if include_r1000:
        russell1000 = get_russell1000()
        log.info(f"  Russell 1000: {len(russell1000)} tickers")
    russell2000 = []
    try:
        from data_fetcher import get_russell2000
        russell2000 = get_russell2000()
        log.info(f"  Russell 2000: {len(russell2000)} tickers")
    except Exception as _r2e:
        log.debug(f"Russell 2000 fetch: {_r2e}")

    # 2026-06-09 · Russell 3000 (RUA.INDX) — authoritative completeness only.
    # R3000 ≈ R1000 ∪ R2000 (both already fetched above), so this is largely
    # redundant; default OFF. Flag: universe.include_russell3000.
    russell3000 = []
    if universe_cfg.get("include_russell3000", False):
        try:
            from data_fetcher import get_russell3000
            russell3000 = get_russell3000()
            log.info(f"  Russell 3000: {len(russell3000)} tickers (authoritative; ≈R1000∪R2000)")
        except Exception as _r3e:
            log.debug(f"Russell 3000 fetch: {_r3e}")

    # 2026-05-21 · Tier-1 universe expansion · S&P MidCap 400 + S&P SmallCap 600 + NASDAQ-100
    sp_mid400, sp_small600, nasdaq100 = [], [], []
    try:
        from data_fetcher import get_sp_midcap_400, get_sp_smallcap_600, get_nasdaq_100
        sp_mid400 = get_sp_midcap_400()
        log.info(f"  S&P MidCap 400: {len(sp_mid400)} tickers")
        sp_small600 = get_sp_smallcap_600()
        log.info(f"  S&P SmallCap 600: {len(sp_small600)} tickers")
        nasdaq100 = get_nasdaq_100()
        log.info(f"  NASDAQ-100: {len(nasdaq100)} tickers")
    except Exception as _t1e:
        log.debug(f"Tier-1 universe expansion fetch: {_t1e}")

    # 2026-05-30 · Full NASDAQ exchange (opt-in) — all NASDAQ common stocks so the
    # scanner ranks the whole exchange, not just NDX-100. Net-new = non-Russell
    # small/micro-caps. Enrichment stays capped (max_enrichment_tickers).
    nasdaq_all = []
    try:
        if (cfg.get("universe") or {}).get("include_nasdaq_all"):
            from data_fetcher import get_nasdaq_all
            _u = cfg.get("universe") or {}
            _topn = int(_u.get("nasdaq_all_top_n", 1000))
            _mindv = float(_u.get("nasdaq_all_min_dollar_vol", 10_000_000))
            nasdaq_all = get_nasdaq_all(top_n=_topn, min_dollar_vol=_mindv)
            log.info(f"  NASDAQ {_topn if _topn > 0 else 'all'} (top liquid · >=${_mindv/1e6:.0f}M $vol): {len(nasdaq_all)} tickers")
    except Exception as _nae:
        log.warning(f"  NASDAQ full-exchange fetch failed: {_nae}")

    # 2026-05-21 · Tier-2 universe extras · recent IPOs + post-earnings movers
    recent_ipos, pead_movers = [], []
    try:
        _ue_path = BASE_DIR / "cache" / "universe_extras.json"
        if _ue_path.exists():
            _ue = json.loads(_ue_path.read_text())
            recent_ipos = _ue.get("recent_ipos") or []
            pead_movers = _ue.get("post_earnings_movers") or []
            log.info(f"  Recent IPOs (>$300M, 21d-400d): {len(recent_ipos)} tickers")
            log.info(f"  Post-earnings movers (5d, >5% surprise): {len(pead_movers)} tickers")
        else:
            log.debug(f"universe_extras.json not found — run scripts/build_universe_extras.py")
    except Exception as _t2e:
        log.debug(f"Tier-2 universe extras read: {_t2e}")

    # 2026-05-21 · Tier-3a · Insider cluster (Bettis-Coles edge)
    # Read from cache/insider_cluster.json populated by
    # scripts/build_universe_insider_cluster.py (runs weekly via launchd).
    # Adds names with >=3 insiders buying >=$200K each in last 30d.
    insider_cluster_tickers = []
    try:
        _ic_path = BASE_DIR / "cache" / "insider_cluster.json"
        if _ic_path.exists():
            _ic = json.loads(_ic_path.read_text())
            insider_cluster_tickers = _ic.get("tickers") or []
            log.info(f"  Insider cluster (>=3 insiders, >=$200K, 30d): {len(insider_cluster_tickers)} tickers")
    except Exception as _t3a_e:
        log.debug(f"Tier-3a insider cluster read: {_t3a_e}")

    # 2026-05-21 · Tier-3b · Congressional trading universe
    congressional_tickers = []
    try:
        _cg_path = BASE_DIR / "cache" / "congressional_picks.json"
        if _cg_path.exists():
            _cg = json.loads(_cg_path.read_text())
            congressional_tickers = _cg.get("tickers") or []
            log.info(f"  Congressional picks (90d): {len(congressional_tickers)} tickers")
    except Exception as _t3b_e:
        log.debug(f"Tier-3b congressional read: {_t3b_e}")

    # 2026-05-21 · Tier-4 · Thematic universe layers
    # Read from cache/universe_thematic.json populated by
    # scripts/build_universe_thematic.py (runs daily). Three sub-sources:
    #   - etf_holdings_union: holdings of 22 curated sector/thematic ETFs
    #     (XLK/XBI/ARKK/SMH/KRE/etc.) — captures names that overflow the
    #     cap-weighted S&P/Russell base (esp. biotech via XBI)
    #   - crypto_adjacent: hardcoded ~20 crypto-exposure equities
    #     (COIN/MSTR/MARA/IBIT/...) — ensures coverage even pre-rebalance
    #   - screener_momentum: EODHD screener API for US >$500M cap +
    #     >500K avg vol + >+3% 5d return (top 200 hits, refreshed daily)
    etf_holdings_tickers, crypto_tickers, screener_tickers = [], [], []
    new_highs_200d, new_lows_200d = [], []
    try:
        _th_path = BASE_DIR / "cache" / "universe_thematic.json"
        if _th_path.exists():
            _th = json.loads(_th_path.read_text())
            etf_holdings_tickers = _th.get("etf_holdings_union") or []
            crypto_tickers = _th.get("crypto_adjacent") or []
            screener_tickers = _th.get("screener_momentum") or []
            new_highs_200d = _th.get("new_highs_200d") or []
            new_lows_200d  = _th.get("new_lows_200d") or []
            log.info(f"  ETF holdings union (22 ETFs): {len(etf_holdings_tickers)} tickers")
            log.info(f"  Crypto-adjacent equities: {len(crypto_tickers)} tickers")
            log.info(f"  Screener momentum (+3% 5d, $500M+ cap): {len(screener_tickers)} tickers")
            log.info(f"  EODHD signal · 200d new highs: {len(new_highs_200d)} tickers")
            log.info(f"  EODHD signal · 200d new lows: {len(new_lows_200d)} tickers")
    except Exception as _t4_e:
        log.debug(f"Tier-4 thematic read: {_t4_e}")

    # 2026-06-09 · Phase 3b · Finviz Elite per-sleeve CANDIDATE GENERATION
    # ─────────────────────────────────────────────────────────────────────────
    # The untapped lever from docs/data_loading_diagram.html Tab ⑤ section A:
    # one Finviz Elite screener export call per sleeve hands us that sleeve's
    # actual daily movers — INCLUDING off-index small-caps the index-member base
    # misses — off EODHD's meter entirely.
    #
    # CRITICAL — Open Risk #7 (un-backtestable snapshot data):
    #   These ONLY ADD candidate tickers to the scan universe. A Finviz preset
    #   must NEVER gate or decide a trade by itself — it is a CURRENT snapshot
    #   (look-ahead risk, no point-in-time history, can't be backtested). The
    #   scan's existing 5-pillar scoring + the sleeve detectors still confirm
    #   every signal on EODHD BARS. Finviz only widens the funnel; it never
    #   closes it. Candidates feed the enrich-cap guaranteed set (so they get
    #   SCORED, like other curated sources) — that is the entire extent of their
    #   influence. No code path lets a `finviz_<sleeve>` source tag promote a
    #   verdict.
    #
    # Gated by universe.finviz_candidate_gen (default FALSE → scan path unchanged).
    finviz_candidate_map: dict[str, str] = {}   # ticker → finviz_<sleeve> source tag
    if universe_cfg.get("finviz_candidate_gen", False):
        try:
            try:
                import scripts.finviz_candidates as _fc
            except ImportError:
                # Fallback: ensure scripts/ is importable regardless of cwd
                import sys as _sys
                _scripts_dir = str(BASE_DIR / "scripts")
                if _scripts_dir not in _sys.path:
                    _sys.path.insert(0, _scripts_dir)
                import finviz_candidates as _fc  # type: ignore
            _fc_results = _fc.all_candidates()
            for _sleeve, _tks in _fc_results.items():
                _tag = f"finviz_{_sleeve}"
                for _t in _tks:
                    _tu = _t.upper().strip()
                    # first-sleeve-wins for source tagging (informational only)
                    finviz_candidate_map.setdefault(_tu, _tag)
            log.info("  Finviz candidate gen (FLAG ON): "
                     + ", ".join(f"{_s}={len(_t)}" for _s, _t in _fc_results.items())
                     + f" → {len(finviz_candidate_map)} distinct candidate tickers "
                     "(ADDED to scan only; signal still confirmed on EODHD bars)")
        except Exception as _fc_e:
            log.warning(f"  Finviz candidate gen failed (continuing without): {_fc_e}")
    finviz_candidate_set = set(finviz_candidate_map.keys())

    creds_path = cfg.get("zacks_credentials", "")
    full_creds = str(BASE_DIR / creds_path) if not Path(creds_path).is_absolute() else creds_path
    zacks_data = fetch_all_zacks_data(full_creds, force_fresh=force_fresh)
    if zacks_data.get("error"):
        log.warning(f"  Zacks premium: {zacks_data['error']}")
    zacks_r1        = zacks_data.get("zacks_r1", [])
    zacks_r1_scores = zacks_data.get("zacks_r1_scores", {})
    ultimate_data = {
        "overview":      zacks_data.get("ultimate_overview", {}),
        "all_trades":    zacks_data.get("ultimate_all_trades", []),
        "commentary":    zacks_data.get("ultimate_commentary", []),
        "special_reports": zacks_data.get("ultimate_special_reports", []),
        "confidential_commentary": zacks_data.get("confidential_commentary", []),
        "confidential_overview": zacks_data.get("confidential_overview", {}),
        "error":         zacks_data.get("error"),
    }
    tazr_data = {
        "trades":          zacks_data.get("tazr_trades", []),
        "portfolio_stats": zacks_data.get("tazr_portfolio_stats", {}),
        "commentary":      zacks_data.get("tazr_commentary", []),
        "error":           zacks_data.get("error"),
    }

    # Build premium portfolio dicts — all share same structure
    def _build_port(prefix):
        return {
            "trades":          zacks_data.get(f"{prefix}_trades", []),
            "portfolio_stats": zacks_data.get(f"{prefix}_portfolio_stats", {}),
            "commentary":      zacks_data.get(f"{prefix}_commentary", []),
            "error":           zacks_data.get("error"),
        }
    bbt_data          = _build_port("bbt")
    cs_data           = _build_port("counterstrike")
    ht_data           = _build_port("headlinetrader")
    alt_energy_data   = _build_port("alt_energy")
    blockchain_data   = _build_port("blockchain")
    tech_innov_data   = _build_port("tech_innovators")
    # Phase 2 — 5 new services (Surprise, Insider, Value, Home Run, Income)
    surprise_data     = _build_port("surprise_trader")
    insider_t_data    = _build_port("insider_trader")
    value_inv_data    = _build_port("value_investor")
    homerun_data      = _build_port("home_run_investor")
    income_inv_data   = _build_port("income_investor")
    # Phase 1 — per-ticker enrichment (Industry Rank, ESP, Revisions, Surprise History, Broker Recs)
    zacks_per_ticker_map = zacks_data.get("zacks_per_ticker") or {}

    log.info(f"  Zacks #1: {len(zacks_r1)} tickers | "
             f"Ultimate: {len(ultimate_data['all_trades'])} open trades | "
             f"Confidential: {len(ultimate_data['confidential_commentary'])} articles")

    # ── ALWAYS-INCLUDE coverage set ────────────────────────────────────────
    # Mandatory: a name someone BOUGHT or that the system ever PICKED must keep
    # getting scored every day, even after it falls out of the ranked universe —
    # otherwise a holder gets no stop/target/exit read on a live position. These
    # bypass the price/volume/liquidity filter AND the enrichment cap below.
    #   held      = current open positions (Alpaca paper book / portfolio_state)
    #   past_pick = every historical pick the system issued + closed trades
    held_syms: set[str] = set()
    pastpick_syms: set[str] = set()
    try:
        import json as _json
        from pathlib import Path as _Path
        _ps = _Path("data/portfolio_state.json")
        if _ps.exists():
            _pd = _json.loads(_ps.read_text())
            for _p in (_pd.get("positions") or []):
                _t = (_p.get("ticker") or _p.get("symbol") or "").upper()
                if _t:
                    held_syms.add(_t)
            for _c in (_pd.get("closed_trades") or _pd.get("closed") or []):
                _t = (_c.get("ticker") or _c.get("symbol") or "").upper()
                if _t:
                    pastpick_syms.add(_t)
        _ph = _Path("cache/picks_history.json")
        if _ph.exists():
            _phd = _json.loads(_ph.read_text())
            for _key in ("trades", "TRADES", "watch_triggers", "WATCH_TRIGGERS"):
                for _r in (_phd.get(_key) or []):
                    if isinstance(_r, dict):
                        _t = (_r.get("ticker") or _r.get("symbol") or _r.get("sym") or "").upper()
                        if _t:
                            pastpick_syms.add(_t)
            # 2026-06-03: ALSO pull every ticker EVER in runs[].picks — many historical
            # picks never became `trades`/`watch_triggers` (88 names were missed). A name
            # the system ever PICKED must keep getting re-scored/ranked. This closes the gap.
            for _run in (_phd.get("runs") or []):
                if isinstance(_run, dict):
                    for _p in (_run.get("picks") or []):
                        if isinstance(_p, dict):
                            _t = (_p.get("ticker") or _p.get("symbol") or _p.get("sym") or "").upper()
                            if _t:
                                pastpick_syms.add(_t)
        # 2026-06-09 · Track-record guarantee (Open Risk #1): audit_ledger.json is
        # the CANONICAL superset — picks_history ∪ signal_log with resolved returns
        # (~842 distinct tickers vs ~500 from picks_history/portfolio alone). Many
        # names were signaled only in signal_log (or only survive in the resolved
        # ledger) and never landed in picks_history's trades/watch_triggers/runs.
        # Union them so EVERY ticker we've ever signaled or held stays in scan +
        # bypasses the enrichment cap forever. signal_log is fully subsumed by the
        # ledger (verified delta = 0), so we don't read it separately. Delisted
        # tombstones are still excluded downstream by the _skip prune, so dead
        # names are NOT re-added. Flag: universe.track_record_from_audit_ledger.
        if universe_cfg.get("track_record_from_audit_ledger", True):
            _al = _Path("cache/audit_ledger.json")
            if _al.exists():
                _before_al = len(pastpick_syms)
                _ald = _json.loads(_al.read_text())
                for _r in (_ald.get("records") or []):
                    if isinstance(_r, dict):
                        _t = (_r.get("ticker") or "").upper().strip()
                        if _t:
                            pastpick_syms.add(_t)
                log.info(f"  Track-record (audit_ledger): {len(_ald.get('records') or [])} records "
                         f"→ +{len(pastpick_syms) - _before_al} new track-record tickers "
                         f"(canonical superset; tombstoned dead names excluded downstream)")
    except Exception as _e:
        log.warning(f"  always-include set build failed (continuing): {_e}")
    # held names are never merely "past_pick"
    pastpick_syms -= held_syms
    always_include = held_syms | pastpick_syms
    log.info(f"  Always-include coverage: {len(held_syms)} held + {len(pastpick_syms)} past-pick = "
             f"{len(always_include)} force-scanned (bypass filter + enrichment cap)")

    # Build universe
    custom = universe_cfg.get("custom_watchlist", [])
    zacks_rank1_only = universe_cfg.get("zacks_rank1_only", False)
    sp500_set    = set(sp500)
    r1000_set    = set(russell1000)
    zacks_r1_set = set(zacks_r1)
    zacks_sell_set = {
        (t["ticker"] if isinstance(t, dict) else t).upper()
        for t in zacks_data.get("zacks_sell_list", [])
        if t
    }
    log.info(f"  Zacks Sell List: {len(zacks_sell_set)} tickers tagged for SHORT priority")

    # Fix #17: Track source for each ticker (first source wins for overlaps)
    ticker_sources: dict[str, str] = {}
    leveraged_set = set(universe_cfg.get("leveraged_watchlist", []))

    if zacks_rank1_only and zacks_r1:
        # Narrow/fast mode: Zacks Rank #1 + custom watchlist
        # Russell 1000 Rank #1 stocks are already inside zacks_r1_set (Zacks ranks all US stocks)
        universe = list(zacks_r1_set | set(custom) | always_include | finviz_candidate_set)
        for t in zacks_r1_set:
            ticker_sources[t] = "zacks_rank1"
        for t in custom:
            ticker_sources.setdefault(t, "custom")
        # Finviz candidates (flag-gated) — provenance tag only, never gates a trade
        for t, _ftag in finviz_candidate_map.items():
            ticker_sources.setdefault(t, _ftag)
        for t in held_syms:
            ticker_sources.setdefault(t, "held")
        for t in pastpick_syms:
            ticker_sources.setdefault(t, "past_pick")
        log.info(f"  Universe (Zacks #1 mode): {len(universe)} "
                 f"(Zacks #1={len(zacks_r1)}, Russell 1000 R#1 included above, custom={len(custom)}, "
                 f"always-include={len(always_include)})")
    else:
        # Full mode union of all sources (indices + extras + info-edge + thematic)
        r2000_set    = set(russell2000)
        r3000_set    = set(russell3000)  # default empty unless include_russell3000
        mid400_set   = set(sp_mid400)
        sml600_set   = set(sp_small600)
        ndx_set      = set(nasdaq100)
        ipo_set      = set(t.upper() for t in recent_ipos)
        pead_set     = set(t.upper() for t in pead_movers)
        insider_set  = set(t.upper() for t in insider_cluster_tickers)
        congress_set = set(t.upper() for t in congressional_tickers)
        etf_set      = set(t.upper() for t in etf_holdings_tickers)
        crypto_set   = set(t.upper() for t in crypto_tickers)
        screen_set   = set(t.upper() for t in screener_tickers)
        newhi_set    = set(t.upper() for t in new_highs_200d)
        newlo_set    = set(t.upper() for t in new_lows_200d)
        ndxall_set   = set(t.upper() for t in nasdaq_all)
        base_set = (sp500_set | r1000_set | r2000_set | r3000_set | mid400_set | sml600_set
                    | ndx_set | ndxall_set | ipo_set | pead_set | insider_set | congress_set
                    | etf_set | crypto_set | screen_set | newhi_set | newlo_set
                    | zacks_r1_set | set(custom) | always_include | finviz_candidate_set)
        universe = list(base_set)
        # Source tagging — first-source-wins. Most curated → least curated.
        for t in sp500_set:    ticker_sources[t] = "sp500"
        for t in r1000_set:    ticker_sources.setdefault(t, "russell1000")
        for t in mid400_set:   ticker_sources.setdefault(t, "sp_midcap_400")
        for t in sml600_set:   ticker_sources.setdefault(t, "sp_smallcap_600")
        for t in r2000_set:    ticker_sources.setdefault(t, "russell2000")
        for t in r3000_set:    ticker_sources.setdefault(t, "russell3000")
        for t in ndx_set:      ticker_sources.setdefault(t, "nasdaq_100")
        for t in ndxall_set:   ticker_sources.setdefault(t, "nasdaq_exchange")
        for t in ipo_set:      ticker_sources.setdefault(t, "recent_ipo")
        for t in pead_set:     ticker_sources.setdefault(t, "post_earnings_mover")
        for t in insider_set:  ticker_sources.setdefault(t, "insider_cluster")
        for t in congress_set: ticker_sources.setdefault(t, "congressional")
        for t in etf_set:      ticker_sources.setdefault(t, "etf_holding")
        for t in crypto_set:   ticker_sources.setdefault(t, "crypto_adjacent")
        for t in screen_set:   ticker_sources.setdefault(t, "screener_momentum")
        for t in newhi_set:    ticker_sources.setdefault(t, "signal_200d_new_hi")
        for t in newlo_set:    ticker_sources.setdefault(t, "signal_200d_new_lo")
        # Finviz candidate tags (finviz_<sleeve>) — informational source label.
        # Tagged AFTER curated/index sources so off-index Finviz-only names get
        # the finviz_<sleeve> tag; names already in an index keep that tag. The
        # tag NEVER influences scoring/verdict — it only marks provenance and
        # routes the name into the curated guaranteed enrich set below.
        for t, _ftag in finviz_candidate_map.items():
            ticker_sources.setdefault(t, _ftag)
        for t in zacks_r1_set: ticker_sources.setdefault(t, "zacks_rank1")
        for t in custom:       ticker_sources.setdefault(t, "custom")
        for t in held_syms:    ticker_sources.setdefault(t, "held")
        for t in pastpick_syms: ticker_sources.setdefault(t, "past_pick")
        log.info(f"  Universe: {len(universe)} "
                 f"(S&P 500={len(sp500)}, R1000={len(russell1000)}, "
                 f"R2000={len(russell2000)}, R3000={len(russell3000)}, MID400={len(sp_mid400)}, "
                 f"SML600={len(sp_small600)}, NDX100={len(nasdaq100)}, NDXall={len(nasdaq_all)}, "
                 f"IPOs={len(recent_ipos)}, PEAD={len(pead_movers)}, "
                 f"insider={len(insider_cluster_tickers)}, "
                 f"congress={len(congressional_tickers)}, "
                 f"ETF={len(etf_holdings_tickers)}, "
                 f"crypto={len(crypto_tickers)}, "
                 f"screener={len(screener_tickers)}, "
                 f"newHi={len(new_highs_200d)}, newLo={len(new_lows_200d)}, "
                 f"Zacks #1={len(zacks_r1)}, custom={len(custom)})")

    # Add Zacks premium service tickers to universe
    universe_set = set(universe)
    for svc_data in [tazr_data, bbt_data, cs_data, ht_data, alt_energy_data, blockchain_data, tech_innov_data]:
        for trade in svc_data.get("trades", []):
            t = trade.get("ticker", "").upper().strip()
            if t and t not in universe_set:
                universe.append(t)
                universe_set.add(t)
                ticker_sources[t] = "zacks_premium"

    # Tag leveraged ETFs
    for t in leveraged_set:
        ticker_sources[t] = "leveraged"

    universe = list(dict.fromkeys(universe))  # Dedupe

    # Prune tickers known to fail yfinance/Polygon lookups.
    # Index synthetics (SPX) and leveraged single-stock ETFs (TNA/TECL/SPXL/BULZ/UPRO/UDOW/WEBL)
    # do not have fundamentals endpoints; crypto pairs (HYPE-USD) and delisted symbols (BITF)
    # return 404 from yfinance quoteSummary.
    _DEAD_TICKERS = {
        "SPX", "BITF", "HYPE-USD", "WEBL",
        "TNA", "TECL", "SPXL", "BULZ", "UPRO", "UDOW",
    }
    # Open Risk #9(a): merge the dynamic delisting tombstone registry into the
    # static dead-ticker prune. A name the track-record guarantee force-includes
    # (always_include) but which has failed every failover tier N cycles running
    # is genuinely delisted — skip re-fetching it so it stops burning cycles. Its
    # historical record (picks_history/signal_log/audit_ledger) is UNTOUCHED.
    # Auto-revives after the retry window; manual revive via
    # `python3 delisted_registry.py revive TICKER`.
    _tombstoned: set[str] = set()
    try:
        import delisted_registry as _dr
        _tombstoned = {t.upper() for t in _dr.tombstoned_set()}
    except Exception as _e:
        log.debug(f"  tombstone registry unavailable (continuing): {_e}")
    _skip = _DEAD_TICKERS | _tombstoned
    _before = len(universe)
    universe = [t for t in universe if t.upper() not in _skip]
    _pruned = _before - len(universe)
    if _pruned:
        log.info(f"  Universe pruned: {_pruned} known-dead/unsupported tickers removed"
                 + (f" ({len(_tombstoned)} delisting-tombstoned, history retained)"
                    if _tombstoned else ""))

    # Step 1.4 + 1.5 (optional): expand universe + Screener API pre-filter.
    # Both gated by config flags so default behavior is unchanged.
    _gates_cfg = (cfg or {}).get("gates", {}) if isinstance(cfg, dict) else {}

    # 1.4 — full US exchange universe (~52K tickers). Use only with screener on.
    if _gates_cfg.get("use_full_exchange_universe", False):
        try:
            import eodhd_client as _ec
            _exch_rows = _ec.exchange_symbol_list("US") or []
            _full_set = {(r.get("Code") or r.get("code") or "").upper().split(".")[0]
                         for r in _exch_rows if isinstance(r, dict) and (r.get("Type") or r.get("type") or "").lower() in ("common stock", "etf", "stock")}
            if _full_set:
                _ub = len(universe)
                _custom_keep = {t for t in universe if ticker_sources.get(t) in ("custom", "zacks_premium", "leveraged")}
                universe = list(_custom_keep | _full_set)
                log.info(f"  Full-exchange universe: {_ub} → {len(universe)} (Screener pre-filter required to keep latency sane)")
        except Exception as e:
            log.warning(f"  Full-exchange universe expand failed: {e}")

    # 1.5 — EODHD Screener API pre-filter
    _screener_cfg = _gates_cfg
    if _screener_cfg.get("use_screener_prefilter", False):
        try:
            import eodhd_client as _ec
            _scr_filters = [
                ["market_capitalization", ">", float(_screener_cfg.get("screener_min_mcap", 1e9))],
                ["avgvol_200d", ">", float(_screener_cfg.get("screener_min_adv", 500000))],
                ["adjusted_close", ">", float(_screener_cfg.get("min_price", 5))],
                ["adjusted_close", "<", float(_screener_cfg.get("max_price", 500))],
            ]
            _scr_resp = _ec.screener(filters=_scr_filters, limit=2000) or {}
            _scr_rows = _scr_resp.get("data") or _scr_resp if isinstance(_scr_resp, list) else []
            _scr_set = {(r.get("code") or r.get("Code") or "").upper().split(".")[0]
                        for r in _scr_rows if isinstance(r, dict)}
            if _scr_set:
                _ub = len(universe)
                universe = [t for t in universe if t.upper() in _scr_set or ticker_sources.get(t) in ("custom", "leveraged") or t.upper() in always_include]
                log.info(f"  Screener pre-filter: {_ub} → {len(universe)} ({_ub - len(universe)} below mcap/ADV/price floors)")
        except Exception as e:
            log.warning(f"  Screener pre-filter failed (continuing without): {e}")

    # ── Step 1.9: Bulk price/volume pre-filter (Phase 2 optimization) ─────
    # Use EODHD bulk_eod (one call returns all US last-day OHLCV) to drop
    # tickers that can't possibly qualify on price + ADV, BEFORE we pay the
    # cost of fetching 1y history for them. Drops the history-fetch universe
    # from ~3000 → ~1800, cutting EODHD quota usage 40%+ per scan.
    _prefilter_pre = len(universe)
    try:
        _min_price = float(cfg.get("filters", {}).get("min_price", 5))
        _max_price = float(cfg.get("filters", {}).get("max_price", 500))
        _min_dv    = float(cfg.get("filters", {}).get("min_avg_daily_dollar_vol", 5_000_000))

        from data_fetcher import _eodhd_bulk_eod_layer as _bulk_layer
        _snap_map, _ = _bulk_layer(universe)
        if _snap_map:
            _kept: list[str] = []
            _ts_keep: dict = {}
            for _t in universe:
                _rec = _snap_map.get(_t)
                if not _rec:
                    # No bulk snapshot for this ticker — keep it (custom, foreign listing, etc.)
                    _kept.append(_t)
                    if _t in ticker_sources:
                        _ts_keep[_t] = ticker_sources[_t]
                    continue
                _close = float(_rec.get("close") or _rec.get("adjusted_close") or 0)
                _vol   = float(_rec.get("volume") or 0)
                _dv    = _close * _vol
                # ALWAYS keep custom + leveraged + Zacks #1 + held/past-pick even if out of range
                if ticker_sources.get(_t) in ("custom", "leveraged", "zacks_r1") or _t.upper() in always_include:
                    _kept.append(_t)
                    _ts_keep[_t] = ticker_sources.get(_t, "held" if _t.upper() in held_syms else "past_pick")
                    continue
                if _min_price <= _close <= _max_price and _dv >= _min_dv:
                    _kept.append(_t)
                    if _t in ticker_sources:
                        _ts_keep[_t] = ticker_sources[_t]
            _saved = _prefilter_pre - len(_kept)
            if _saved > 0:
                log.info(
                    f"  Phase-2 prefilter: {_prefilter_pre} → {len(_kept)} "
                    f"({_saved} dropped on bulk price/volume) · saves ~{_saved} EODHD history calls"
                )
                universe = _kept
                ticker_sources = _ts_keep if _ts_keep else ticker_sources
    except Exception as _e:
        log.debug(f"Phase-2 bulk prefilter skipped: {_e}")

    # Step 2: Fetch market data + macro context
    log.info("Step 2: Fetching market data...")
    market_data = fetch_market_data(universe, period="1y")
    fill_rate = len(market_data) / len(universe) if universe else 0
    log.info(f"  Got data for {len(market_data)} tickers ({fill_rate:.0%} fill rate)")
    if fill_rate < 0.5:
        log.error(f"Market data fill rate critical ({fill_rate:.0%}) — aborting scan to avoid garbage results")
        return
    if fill_rate < 0.7:
        log.warning(f"Market data fill rate low ({fill_rate:.0%}) — results may be incomplete")

    # ── Step 2.5: Bulk EODHD live quotes for KPI chips ────────────────
    # EODHD batch real-time gives delayed (15-min) prices for all tickers in 1 call.
    # Stored in _live_kpi_map and used to inject today's bar during market hours.
    _live_kpi_map: dict = {}
    try:
        import eodhd_client as _eod_bulk
        _bulk_tickers = list(market_data.keys())
        if _bulk_tickers:
            _t0 = __import__("time").time()
            # EODHD real_time accepts up to ~50 symbols per batched call; chunk for safety
            for _i in range(0, len(_bulk_tickers), 50):
                _chunk = _bulk_tickers[_i:_i+50]
                _rt = _eod_bulk.real_time(_chunk)
                _rows = _rt if isinstance(_rt, list) else ([_rt] if isinstance(_rt, dict) else [])
                for _q in _rows:
                    _code = (_q.get("code") or "").split(".")[0].upper()
                    _px = _q.get("close") or _q.get("previousClose")
                    if _code and _px and _px != "NA":
                        try:
                            _live_kpi_map[_code] = {"_last_price": float(_px),
                                                     "_volume": _q.get("volume") or 0}
                        except (ValueError, TypeError):
                            pass
            log.info(f"  EODHD bulk quotes: {len(_live_kpi_map)}/{len(_bulk_tickers)} "
                     f"in {__import__('time').time()-_t0:.1f}s")
    except Exception as _eq_err:
        log.debug(f"EODHD bulk quotes skipped: {_eq_err}")

    # Keep legacy alias for downstream code that reads _schwab_kpi_map
    _schwab_kpi_map = _live_kpi_map

    # ── Step 2.6: Inject live EODHD prices into OHLCV DataFrames during market hours ──
    _live_bars_injected = 0
    try:
        from zoneinfo import ZoneInfo as _ZI26
        _now_et_26 = datetime.now(_ZI26("America/New_York"))
    except ImportError:
        import pytz as _pytz26
        _now_et_26 = datetime.now(_pytz26.timezone("America/New_York"))
    _mkt_open_26 = (_now_et_26.weekday() < 5 and
                    (9 * 60 + 30) <= (_now_et_26.hour * 60 + _now_et_26.minute) <= (16 * 60))
    if _mkt_open_26 and _live_kpi_map:
        _today_ts = pd.Timestamp(_now_et_26.date())
        for _sym, _kpi in _live_kpi_map.items():
            if _sym not in market_data:
                continue
            _lp = _kpi.get("_last_price")
            if not _lp or _lp <= 0:
                continue
            _df = market_data[_sym]
            _last_idx = _df.index[-1] if not _df.empty else None
            if _last_idx is not None:
                _last_naive = _last_idx.tz_localize(None) if _last_idx.tzinfo else _last_idx
                if _last_naive >= _today_ts:
                    continue
            _vol = _kpi.get("_volume") or 0
            _new_bar = pd.DataFrame(
                {"Open": [_lp], "High": [_lp], "Low": [_lp],
                 "Close": [_lp], "Volume": [float(_vol)]},
                index=pd.DatetimeIndex([_today_ts]),
            )
            market_data[_sym] = pd.concat([_df, _new_bar])
            _live_bars_injected += 1
        if _live_bars_injected:
            log.info(f"  Live price injection: {_live_bars_injected} tickers updated via EODHD")
    elif not _mkt_open_26:
        log.debug("  Live price injection skipped (market closed)")

    # Market breadth (uses already-downloaded market_data — no extra download).
    # 2026-05-10: restrict to S&P 500 constituents so live breadth definition
    # matches the V4 regime classifier validation (backtest/regime_backtest.py
    # used `get_sp500()` only). Without this filter, breadth was computed over
    # SP500 ∪ R1000 ∪ custom (~1000 names) and read ~13pp higher than backtest
    # breadth (today: 64.0 vs 50.9), causing the V4 thresholds to fire
    # differently in production than in validation.
    try:
        _sp500_set = set(get_sp500())
    except Exception:
        _sp500_set = None  # fall back to legacy (full-universe) breadth on fetch failure
    market_breadth = get_market_breadth(market_data, universe_filter=_sp500_set)
    log.info(f"  Market breadth (SP500-filtered): {market_breadth['pct_above_50d']:.0f}% above 50d "
             f"({market_breadth['label_50']}) | "
             f"{market_breadth['pct_above_100d']:.0f}% above 100d ({market_breadth['label_100']})"
             f" | n={market_breadth.get('total','?')}")

    # Get SPY data for relative strength — EODHD primary via failover wrapper
    from data_fetcher import fetch_ohlcv_with_failover
    spy_data, _spy_src = fetch_ohlcv_with_failover("SPY", days=365)
    spy_close = spy_data["Close"].squeeze().dropna() if spy_data is not None and not spy_data.empty else None
    if spy_close is None or len(spy_close) == 0:
        log.warning("  SPY data unavailable — relative strength scores will default to neutral (50)")
        spy_close = None

    # Get market regime (includes VIX + 4-regime classification)
    regime = get_market_regime(breadth=market_breadth)
    vix = regime.get("vix", {})
    vix_cur = regime.get("vix_current", vix.get("vix_current", 20))
    regime4 = regime.get("regime4", "unknown")
    log.info(f"  Market regime: {regime['regime'].upper()} | Regime4: {regime4} | "
             f"(SPY ${regime['spy_price']}) | "
             f"VIX {vix_cur} ({vix.get('regime','?')}) | "
             f"Breadth: {regime.get('breadth_pct_50d', 50):.0f}% above 50d | "
             f"Cycle: {regime.get('market_cycle','?')} | "
             f"SPY today: {regime.get('spy_daily_chg', 0):+.1f}% | "
             f"Dist days: {regime.get('distribution_days', 0)}")

    # Active-config startup banner — echo resolved thresholds so silent fallbacks
    # to code defaults are visible before the main scan loop starts (HARDENING 2.2).
    try:
        # Hint the banner about active regime without mutating cfg for downstream code.
        cfg.setdefault("_active_regime", regime.get("regime", "bull"))
        print_active_config_banner(cfg, regime4=regime4)
    except Exception as _banner_e:
        log.debug(f"Config banner skipped: {_banner_e}")

    # Regime transition auto-exit (Risk Controls A+): shrink exposure when regime
    # flips to risk-off/panic. Done before scan to influence sizing this run.
    try:
        import json as _json_rae
        from pathlib import Path as _Path_rae
        _rae_fp = BASE_DIR / "cache" / "regime_last_seen.json"
        _prev_r4 = None
        if _rae_fp.exists():
            _prev_r4 = _json_rae.loads(_rae_fp.read_text()).get("regime4")
        _risk_off_regimes = ("risk_off_trending", "panic")
        # Flipping INTO risk-off: reduce all open position sizes
        if _prev_r4 and _prev_r4 not in _risk_off_regimes and regime4 in _risk_off_regimes:
            from portfolio_tracker import runner_protection_trim, flat_position_exits
            _forced_trims = runner_protection_trim(max_position_pct=10.0, trim_to_pct=5.0)
            if _forced_trims:
                log.warning(f"  🔴 REGIME AUTO-EXIT: risk-off flip ({_prev_r4} → {regime4}) — {len(_forced_trims)} positions flagged for forced trim")
                for _t in _forced_trims:
                    log.warning(f"    TRIM {_t['ticker']}: {_t['current_pct']}% → {_t['target_pct']}% ({_t['shares_to_trim']} shares)")
    except Exception as _rae_e:
        log.debug(f"Regime auto-exit check failed (non-fatal): {_rae_e}")

    # Fix #27: Regime transition alert — diff against last persisted regime
    try:
        import json as _json_rt
        from pathlib import Path as _Path_rt
        _rt_fp = BASE_DIR / "cache" / "regime_last_seen.json"
        _prev_r = None
        _prev_r4 = None
        if _rt_fp.exists():
            _prev = _json_rt.loads(_rt_fp.read_text())
            _prev_r = _prev.get("regime")
            _prev_r4 = _prev.get("regime4")
        _cur_r = regime.get("regime", "unknown")
        if _prev_r and _prev_r != _cur_r:
            _msg = f"REGIME TRANSITION: {_prev_r.upper()} -> {_cur_r.upper()} (regime4: {_prev_r4} -> {regime4})"
            log.warning(_msg)
            try:
                import subprocess as _sp_rt
                _sp_rt.run(["osascript", "-e",
                            f'display notification "{_msg}" with title "SwingTrade Regime Change"'],
                           check=False, timeout=5)
            except Exception:
                pass
        elif _prev_r4 and _prev_r4 != regime4:
            _msg = f"Regime4 shift: {_prev_r4} -> {regime4} (top-level regime unchanged: {_cur_r})"
            log.info(_msg)
        _rt_fp.parent.mkdir(parents=True, exist_ok=True)
        _rt_fp.write_text(_json_rt.dumps({
            "regime": _cur_r, "regime4": regime4, "as_of": str(run_date) if "run_date" in dir() else None,
        }))
    except Exception as _rt_e:
        log.debug(f"Regime transition check failed: {_rt_e}")

    # AI-11: unified VIX mode resolver (single source of truth for tighten/kill/sizing)
    _vix_kill_active = False
    _vix_tighten_active = False
    _vix_mode_info = None
    try:
        from data_fetcher import yf as _yf, fetch_ohlcv_with_failover as _foh
        from analysis import resolve_vix_mode as _resolve_vix
        # EODHD primary (post-2026-04-25): VIX via failover chain, yfinance fallback
        _vix_hist, _ = _foh("VIX", days=10)
        if _vix_hist is None or _vix_hist.empty or len(_vix_hist) < 6:
            _vix_hist = _yf.download("^VIX", period="10d", interval="1d", progress=False, auto_adjust=True)
        _vix_today = None
        _vix_5d_avg = None
        if _vix_hist is not None and not _vix_hist.empty and len(_vix_hist) >= 6:
            _vix_series = _vix_hist["Close"].squeeze().dropna()
            _vix_today = float(_vix_series.iloc[-1])
            _vix_5d_avg = float(_vix_series.iloc[-6:-1].mean())
        _vix_mode_info = _resolve_vix(_vix_today or vix_cur, _vix_5d_avg, cfg)
        if _vix_mode_info["mode"] == "kill":
            _vix_kill_active = True
            log.warning(f"  VIX SPIKE KILL SWITCH: {_vix_mode_info['note']}")
        elif _vix_mode_info["mode"] == "tighten":
            _vix_tighten_active = True
            log.warning(f"  VIX TIGHTEN: {_vix_mode_info['note']}")
        else:
            log.info(f"  VIX mode: {_vix_mode_info['note']}")
    except Exception as _ve:
        log.debug(f"  VIX mode resolver failed (non-fatal): {_ve}")

    # Sector ETF rotation + macro signals (parallel)
    log.info("  Fetching sector ETF rotation + macro signals...")
    with ThreadPoolExecutor(max_workers=3) as _pool:
        _sector_fut  = _pool.submit(get_sector_etf_data, 63)
        _macro_fut   = _pool.submit(get_macro_signals)
        _fg_fut      = _pool.submit(get_fear_greed)
        sector_etf_data = _sector_fut.result()
        macro_signals   = _macro_fut.result()
        fear_greed_data = _fg_fut.result()
    log.info(f"  Fear & Greed: {fear_greed_data.get('value','?')} ({fear_greed_data.get('label','?')}) | "
             f"Yield curve: {macro_signals.get('yield_curve',{}).get('spread','?')} "
             f"({'inverted' if macro_signals.get('yield_curve',{}).get('inverted') else 'normal'})")
    if sector_etf_data:
        leaders = [(e, d["vs_spy_pct"]) for e, d in sector_etf_data.items()
                   if e != "SPY" and d.get("vs_spy_pct", 0) > 0]
        leaders.sort(key=lambda x: x[1], reverse=True)
        log.info(f"  Sector leaders: {', '.join(e for e, _ in leaders[:3])}")

    # Sector dispersion regime enhancement (2026-05-11) — narrow leadership
    # is a fragile-bull signal that breadth/VIX/EMA gates miss. Merge the
    # dispersion stats into the regime dict and downgrade risk_on_trending
    # to risk_on_choppy when leadership is narrow OR rotation is defensive.
    # 2026-05-13 KILLSWITCH: gated by regime_classifier.gate_sector_dispersion_enabled
    _gate_sd_on = bool((cfg.get("regime_classifier") or {}).get("gate_sector_dispersion_enabled", True))
    _disp = compute_sector_dispersion(sector_etf_data) if sector_etf_data else {}
    if _disp and not _disp.get("_error"):
        regime["sector_dispersion"] = _disp
        if _gate_sd_on and _disp.get("downgrade_regime") and regime.get("regime4") == "risk_on_trending":
            _orig = regime["regime4"]
            regime["regime4_pre_dispersion"] = _orig
            regime["regime4"] = "risk_on_choppy"
            regime["max_size_pct"] = 70  # match risk_on_choppy sizing
            log.info(
                f"  Regime DOWNGRADED: {_orig} → risk_on_choppy "
                f"(leadership={_disp.get('leadership_breadth')}, "
                f"rotation={_disp.get('rotation_signal')}, "
                f"tech_only={_disp.get('is_tech_only')})"
            )
        log.info(
            f"  Sector dispersion: leadership={_disp.get('leadership_breadth')} "
            f"({_disp.get('sectors_outperforming_spy')}/{_disp.get('sectors_total')} "
            f"out-SPY) · rotation={_disp.get('rotation_signal')} · "
            f"stdev={_disp.get('dispersion_stdev')}pp"
        )

    log.info(f"  Macro risk: {macro_signals.get('risk_signal', '?')} | "
             f"HYG {macro_signals.get('hyg', {}).get('trend', '?')} | "
             f"DXY {macro_signals.get('dxy', {}).get('trend', '?')}")

    # Credit-spread regime gate (audit gap #2, 2026-05-11) — HYG/LQD ratio
    # captures credit stress separate from duration risk. State levels:
    #   healthy: no action
    #   stress:  risk_on_trending → risk_on_choppy
    #   panic:   risk_on_choppy → risk_off_trending
    # Reference: S&P credit research 2002-2022 — HYG/LQD chg20 < -2%
    # preceded 60% of 5%+ SPX corrections within 4 weeks.
    # 2026-05-13 KILLSWITCH: gated by regime_classifier.gate_credit_spreads_enabled
    _gate_credit_on = bool((cfg.get("regime_classifier") or {}).get("gate_credit_spreads_enabled", True))
    _credit = (macro_signals or {}).get("credit") or {}
    _credit_state = _credit.get("state", "unknown")
    if _gate_credit_on and _credit_state and _credit_state not in ("unknown", "healthy"):
        regime["credit_state"] = _credit_state
        regime["credit_chg20"] = _credit.get("hyg_lqd_chg20")
        _orig_regime4 = regime.get("regime4")
        if _credit_state == "panic" and _orig_regime4 in ("risk_on_trending", "risk_on_choppy"):
            regime["regime4_pre_credit"] = _orig_regime4
            regime["regime4"] = "risk_off_trending"
            regime["max_size_pct"] = 35
            log.info(
                f"  Regime DOWNGRADED by credit panic: {_orig_regime4} → risk_off_trending "
                f"(HYG/LQD chg20={_credit.get('hyg_lqd_chg20')}%, "
                f"chg5={_credit.get('hyg_lqd_chg5')}%)"
            )
        elif _credit_state == "stress" and _orig_regime4 == "risk_on_trending":
            regime["regime4_pre_credit"] = _orig_regime4
            regime["regime4"] = "risk_on_choppy"
            regime["max_size_pct"] = 70
            log.info(
                f"  Regime DOWNGRADED by credit stress: {_orig_regime4} → risk_on_choppy "
                f"(HYG/LQD chg5={_credit.get('hyg_lqd_chg5')}%, "
                f"chg20={_credit.get('hyg_lqd_chg20')}%)"
            )
    else:
        regime["credit_state"] = _credit_state
        regime["credit_chg20"] = _credit.get("hyg_lqd_chg20")
    log.info(f"  Credit state: {regime.get('credit_state')} | "
             f"HYG/LQD chg5={_credit.get('hyg_lqd_chg5')}% chg20={_credit.get('hyg_lqd_chg20')}%")

    # Step 3: Price/Volume filter
    log.info("Step 3: Applying price/volume filters...")
    min_price = cfg.get("filters", {}).get("min_price", 5)
    max_price = cfg.get("filters", {}).get("max_price", 100)
    min_dv = cfg.get("filters", {}).get("min_daily_dollar_volume", 10_000_000)

    qualified = {}
    # Track why each Zacks #1 ticker was excluded from analysis
    zacks_r1_missing: dict[str, str] = {}

    # Mark Zacks #1 tickers that got no market data at all
    for t in zacks_r1:
        if t not in market_data:
            zacks_r1_missing[t] = "No market data (Yahoo + tvDatafeed both failed)"

    # Detect if market is currently open (NYSE: Mon-Fri 9:30–16:00 ET)
    try:
        from zoneinfo import ZoneInfo
        _now_et = datetime.now(ZoneInfo("America/New_York"))
    except ImportError:
        import pytz
        _now_et = datetime.now(pytz.timezone("America/New_York"))
    _market_open = (_now_et.weekday() < 5 and
                    (9 * 60 + 30) <= (_now_et.hour * 60 + _now_et.minute) <= (16 * 60))

    # Pre-fetch live prices only for Zacks #1 tickers (high-value subset, not all 705)
    # Avoids 700+ serial yfinance calls during market hours
    # 2026-04-27: switched from per-ticker get_live_price (200 EODHD calls) to
    # a single batched real_time() call covering all Zacks #1 tickers (1 call).
    _live_prices: dict[str, float] = {}
    if _market_open and zacks_r1_set:
        _live_targets = list(zacks_r1_set & set(market_data.keys()))
        if _live_targets:
            try:
                import eodhd_client as _eod
                # Batch in chunks of 50 to keep URL length reasonable
                for _chunk_start in range(0, len(_live_targets), 50):
                    _chunk = _live_targets[_chunk_start:_chunk_start + 50]
                    rows = _eod.real_time(_chunk) or []
                    if isinstance(rows, dict):
                        rows = [rows]
                    for _row in rows or []:
                        if not isinstance(_row, dict):
                            continue
                        _code = (_row.get("code") or "").upper().split(".")[0]
                        _close = _row.get("close") or _row.get("previousClose")
                        try:
                            _p = float(_close) if _close not in (None, "NA") else None
                        except (TypeError, ValueError):
                            _p = None
                        if _code and _p:
                            _live_prices[_code] = _p
            except Exception as _lpe:
                log.debug(f"Batched live price fetch failed: {_lpe}")

    for ticker, df in market_data.items():
        try:
            # Use last non-NaN close — intraday sessions leave today's close as NaN
            close_series = df["Close"].dropna()
            if close_series.empty:
                if ticker in zacks_r1_set:
                    zacks_r1_missing[ticker] = "No valid close price data"
                continue
            price = float(close_series.iloc[-1])
            # During market hours: use pre-fetched live quote for Zacks #1 tickers
            if _market_open and ticker in _live_prices:
                live = _live_prices[ticker]
                if abs(live - price) / price < 0.10:  # sanity: within 10%
                    price = live
            # Use last available volume (may include today's partial volume)
            vol_series = df["Volume"].dropna()
            vol = float(vol_series.iloc[-1]) if not vol_series.empty else 0.0
            avg_vol = float(df["Volume"].rolling(20).mean().dropna().iloc[-1]) if len(df) >= 20 else vol
            daily_dv = avg_vol * price

            # Always-include (held + past-pick) bypass the price/volume gate — a name
            # someone holds must be scored for exit management even if it now trades
            # below the liquidity/price floor or has fallen out of range.
            if (min_price <= price <= max_price and daily_dv >= min_dv) or ticker.upper() in always_include:
                qualified[ticker] = df
            elif ticker in zacks_r1_set:
                # Record why this Zacks #1 stock was filtered out
                if price < min_price or price > max_price:
                    zacks_r1_missing[ticker] = f"Price ${price:.2f} outside ${min_price}–${max_price} range"
                else:
                    zacks_r1_missing[ticker] = (
                        f"Volume ${daily_dv/1e6:.1f}M/day below ${min_dv/1e6:.0f}M minimum"
                    )
        except Exception:
            if ticker in zacks_r1_set and ticker not in zacks_r1_missing:
                zacks_r1_missing[ticker] = "Data parse error"

    log.info(f"  Qualified: {len(qualified)} tickers")
    log.info(f"  Zacks #1 excluded before analysis: {len(zacks_r1_missing)}")
    total_scanned = len(market_data)

    # Step 3.5: Fast OHLCV pre-screen — reduce enrichment universe before any API calls
    # Scores every qualified ticker using only in-memory price/volume data (zero HTTP requests).
    # Keeps top N by score + all Zacks #1 tickers unconditionally.
    #
    # 2026-06-02 · prescreen v2 (config performance.prescreen_v2, default ON):
    # the v1 score was pure trend-momentum, which (a) under-ranked RS leaders in a
    # flat tape, (b) scored coiled pre-breakout (VCP/squeeze) names ~0, (c) actively
    # PENALIZED pullbacks — cutting the exact entries the Mean-Reversion + EMA-pullback
    # sleeves buy. v2 adds RS-vs-SPY, a liquidity tilt, a volatility-contraction bonus,
    # and replaces the blanket pullback penalty with an oversold-above-200EMA credit.
    # Flip to false to revert to v1 momentum-only ranking.
    _prescreen_v2 = bool(cfg.get("performance", {}).get("prescreen_v2", True))
    # SPY benchmark returns for the RS term — computed ONCE, not per-ticker.
    _spy_ret5 = _spy_ret21 = None
    if spy_close is not None and len(spy_close) >= 23:
        try:
            _spy_ret5  = (float(spy_close.iloc[-1]) / float(spy_close.iloc[-6])  - 1) * 100
            _spy_ret21 = (float(spy_close.iloc[-1]) / float(spy_close.iloc[-22]) - 1) * 100
        except Exception:
            _spy_ret5 = _spy_ret21 = None

    def _fast_prescreen_score(df: pd.DataFrame) -> float:
        try:
            close = df["Close"].dropna()
            if len(close) < 50:
                return 0.0
            vol = df["Volume"].dropna()
            price = float(close.iloc[-1])

            e8  = float(close.ewm(span=8,  adjust=False).mean().iloc[-1])
            e21 = float(close.ewm(span=21, adjust=False).mean().iloc[-1])
            e200 = float(close.ewm(span=200, adjust=False).mean().iloc[-1]) if len(close) >= 200 else None
            e50 = float(close.ewm(span=50, adjust=False).mean().iloc[-1])

            score = 0.0

            # EMA stack: cleanly trending vs partial vs weak
            # Also detect pullbacks to rising 50 SMA (high RS stocks pulling back)
            sma50_10d = float(close.iloc[-60:-50].mean()) if len(close) >= 60 else e50
            sma50_rising = e50 > sma50_10d * 1.001

            if price > e8 > e21 > e50:
                score += 4.0
            elif price > e21 > e50:
                score += 2.0
            elif price > e50:
                score += 1.0
            elif price > e50 * 0.97 and sma50_rising:
                score += 2.5  # Pullback to rising 50 SMA — valid setup, don't cut
            elif price > e50 * 0.95 and sma50_rising:
                score += 1.5  # Deeper pullback but 50 SMA still rising

            # RSI: want 50-70 (bullish momentum, not extended)
            delta = close.diff()
            gain = delta.where(delta > 0, 0.0).ewm(com=13, adjust=False).mean()
            loss = (-delta.where(delta < 0, 0.0)).ewm(com=13, adjust=False).mean()
            loss_val = float(loss.iloc[-1])
            rsi = float(100 - 100 / (1 + float(gain.iloc[-1]) / loss_val)) if loss_val > 0 else 50.0
            if   50 <= rsi <= 70: score += 3.0
            elif 45 <= rsi <  50: score += 1.0
            elif rsi > 70:        score += 1.0  # extended — partial credit

            # Relative volume: accumulation signal
            if len(vol) >= 20:
                avg_vol = float(vol.rolling(20).mean().iloc[-1])
                rvol = float(vol.iloc[-1]) / max(avg_vol, 1)
                if   rvol >= 2.0: score += 2.0
                elif rvol >= 1.5: score += 1.0

            # 5-day momentum (thrust credit kept in both v1 and v2)
            ret5 = ret21 = None
            if len(close) >= 6:
                ret5 = (float(close.iloc[-1]) / float(close.iloc[-6]) - 1) * 100
                if ret5 >= 3.0:
                    score += 1.0
            if len(close) >= 22:
                ret21 = (float(close.iloc[-1]) / float(close.iloc[-22]) - 1) * 100

            if not _prescreen_v2:
                # v1 behavior: blanket penalty on any 5d dump
                if ret5 is not None and ret5 <= -5.0:
                    score -= 2.0
                return round(min(10.0, max(0.0, score)), 1)

            # ── prescreen v2 additions ────────────────────────────────────────
            # GAP #4 — don't penalize a pullback inside an uptrend; only penalize a
            # true breakdown (5d dump AND price below EMA50). Reward oversold dips
            # that hold above the 200EMA — the Mean-Reversion / EMA-pullback entry.
            if ret5 is not None and ret5 <= -5.0 and price < e50:
                score -= 1.5                                  # breakdown, not pullback
            if rsi < 35 and e200 is not None and price > e200:
                score += 2.0                                  # oversold-in-uptrend (mean-rev setup)
            elif 35 <= rsi < 45 and price > e21:
                score += 0.75                                 # shallow pullback holding EMA21

            # GAP #2 — relative strength vs SPY (regime-aware ranking). Uses the
            # longer 21d window primarily, 5d as a tiebreak.
            if ret21 is not None and _spy_ret21 is not None:
                rs21 = ret21 - _spy_ret21
                if   rs21 >= 5.0: score += 2.0
                elif rs21 >= 2.0: score += 1.25
                elif rs21 >= 0.0: score += 0.5
                elif rs21 <= -8.0: score -= 1.0               # severe laggard
            if ret5 is not None and _spy_ret5 is not None and (ret5 - _spy_ret5) >= 2.0:
                score += 0.5

            # GAP #1 — liquidity tilt (all qualified already clear the $10M ADV floor;
            # this biases the ranking toward deeper, lower-slippage names).
            if len(vol) >= 20:
                avg_vol = float(vol.rolling(20).mean().iloc[-1])
                dollar_vol = price * avg_vol
                if   dollar_vol >= 50e6: score += 1.0
                elif dollar_vol >= 20e6: score += 0.5

            # GAP #3 — volatility contraction (VCP / squeeze): recent realized vol
            # collapsing while price coils near its 20d high = pre-breakout energy
            # that pure-trend scoring misses entirely.
            if len(close) >= 30:
                rets = close.pct_change().dropna()
                vol_recent = float(rets.iloc[-10:].std())
                vol_prior  = float(rets.iloc[-30:-10].std())
                hi20 = float(close.iloc[-20:].max())
                if vol_prior > 0 and vol_recent < 0.70 * vol_prior and price >= 0.95 * hi20:
                    score += 2.0                              # tight coil near highs
                elif vol_prior > 0 and vol_recent < 0.80 * vol_prior and price >= 0.90 * hi20:
                    score += 1.0

            return round(min(16.0, max(0.0, score)), 1)
        except Exception:
            return 0.0

    # MAX_ENRICHMENT_OVERRIDE: nightly full-universe enrich batch sets this (e.g. 3500)
    # to deep-enrich ALL ranked tickers off-hours (throttle-paced, alone -> no per-minute
    # burst), pre-populating every ticker detail for /api/ticker. Daily scan leaves unset.
    _max_enrich = int(os.environ.get("MAX_ENRICHMENT_OVERRIDE") or
                      cfg.get("performance", {}).get("max_enrichment_tickers", 350))

    # Earnings-window guarantee (2026-05-08 — INOD-class fix).
    # Any ticker reporting earnings in the next 10 days gets GUARANTEED
    # inclusion in the prescreen, regardless of momentum score. Catches
    # consolidating names with a known catalyst that the score-based
    # filter would otherwise cut. Watchlist refreshed daily 5:30am PT
    # by build_earnings_watchlist.py → data/earnings_watchlist.json.
    _earnings_guaranteed: set = set()
    try:
        _ew_path = BASE_DIR / "data" / "earnings_watchlist.json"
        if _ew_path.exists():
            import json as _json_ew
            _ew = _json_ew.loads(_ew_path.read_text())
            _earnings_guaranteed = {x["ticker"] for x in (_ew.get("watchlist") or [])
                                     if isinstance(x, dict) and x.get("ticker")}
            log.info(f"  Earnings watchlist loaded: {len(_earnings_guaranteed)} tickers reporting in next 10d")
    except Exception as _ew_err:
        log.debug(f"earnings_watchlist load skipped: {_ew_err}")

    # PEAD-window guarantee (2026-05-14): tickers that REPORTED in the last 7 days
    # must reach the enrichment universe so the PEAD sleeve has signals to fire on.
    # Without this, FOXA / CEG / ZBRA (textbook PEAD setups) were filtered out by
    # the OHLCV pre-screen score because their recent gap-down→bounce gave them
    # weak short-term momentum scores.
    _pead_guaranteed: set = set()
    try:
        from data_fetcher import _load_recent_earnings_surprises_global as _lp
        _pead_idx = _lp()
        if _pead_idx:
            # Filter to high-quality post-report names (≥ +3% EPS surprise AND ≥ +2% gap)
            for t, d in _pead_idx.items():
                eps = d.get("eps_surprise_pct") or 0
                gap = d.get("post_report_gap_pct") or 0
                days = d.get("days_since_earnings", 99)
                if eps >= 3 and gap >= 2 and days <= 5:
                    _pead_guaranteed.add(t)
            log.info(f"  PEAD watchlist loaded: {len(_pead_guaranteed)} tickers reported in last 5d with EPS+3% gap+2%")
    except Exception as _pe_err:
        log.debug(f"pead_guaranteed load skipped: {_pe_err}")

    if len(qualified) > _max_enrich:
        _prescores      = {t: _fast_prescreen_score(df) for t, df in qualified.items()}
        _zr1_qualified  = [t for t in qualified if t in zacks_r1_set]
        # P1.5-bridge fix (2026-04-30): GUARANTEE S&P 500 inclusion in qualified
        # set so quality compounders (AAPL/MSFT/GOOG/etc.) reach Invest scoring
        # even when their short-term pre-screen score is low. Without this, they
        # never appear in `all_scored` and Long-term picks miss the obvious names.
        _sp500_in_qualified = [t for t in qualified if t in sp500_set and t not in zacks_r1_set]
        # NASDAQ-100 guarantee (2026-06-02): SYMMETRIC with the S&P 500 guarantee
        # above. The major NASDAQ index names (AAPL/NVDA/MSFT/AMD/etc.) must reach
        # scoring regardless of short-term momentum prescore — same as S&P 500.
        # Without this, pure-NASDAQ names had to EARN their 1500-slot on momentum
        # while every S&P 500 name was free → NASDAQ was under-represented (only
        # ~34% of top-liquid NASDAQ scored). nasdaq100 is always populated (full
        # + zacks mode). Net-new is small (most NDX100 ⊂ S&P 500) but closes the
        # asymmetry for the NASDAQ-only flagship names.
        _ndx100_set = set(nasdaq100) if nasdaq100 else set()
        _ndx_in_qualified = [t for t in qualified if t in _ndx100_set and t not in zacks_r1_set and t not in sp500_set]
        # Earnings-window guarantee — overlap with qualified universe
        _earnings_in_qualified = [t for t in qualified if t in _earnings_guaranteed]
        # PEAD-window guarantee — post-report PEAD candidates
        _pead_in_qualified = [t for t in qualified if t in _pead_guaranteed]

        # 2026-05-22 · Tier-2/3/4 curated-source guarantees · fixes the
        # "0 of 79 IPOs scored" problem flagged in 2026-05-21 scan output.
        # Without these guarantees, SP500's 474 names + earnings 54 saturate the
        # 500-slot cap and IPO/screener/insider/etc. compete for ~zero slots.
        # Now: guarantee every curated SMALL-tier source ticker (IPO, PEAD list,
        # insider cluster, congressional, 200d new-high/low, crypto-adjacent).
        # SKIPPED here: ETF holdings (660), screener momentum (200) — too wide,
        # let them compete on prescore. Net new guaranteed: ~188 today.
        _curated_sources = {
            'recent_ipo', 'post_earnings_mover',
            'insider_cluster', 'congressional',
            'signal_200d_new_hi', 'signal_200d_new_lo',
            'crypto_adjacent',
        }
        _curated_qualified = [t for t in qualified
                              if ticker_sources.get(t) in _curated_sources]

        # Phase 3b — Finviz candidate guarantee (flag-gated, Open Risk #7).
        # When finviz_candidate_gen is ON, guarantee the focused per-sleeve
        # candidates a scoring slot (like other curated sources) so the sleeve
        # detectors actually get to CONFIRM-or-reject them on EODHD bars. This
        # only ADDS them to the scored pool; the verdict is still decided by
        # scoring + detectors on bars, never by the Finviz preset alone.
        _finviz_qualified = [t for t in qualified
                             if str(ticker_sources.get(t, "")).startswith("finviz_")]

        # Always-include (held + past-pick) — never cut by the enrichment cap.
        # A held/previously-picked name MUST be deep-scored every scan so the
        # holder gets a current stop/target/exit read, not stale coverage.
        _alwaysinc_qualified = [t for t in qualified if t.upper() in always_include]

        _guaranteed = (set(_zr1_qualified) | set(_sp500_in_qualified)
                       | set(_ndx_in_qualified)
                       | set(_earnings_in_qualified) | set(_pead_in_qualified)
                       | set(_curated_qualified) | set(_alwaysinc_qualified)
                       | set(_finviz_qualified))
        _non_guaranteed_sorted = sorted(
            [(t, s) for t, s in _prescores.items() if t not in _guaranteed],
            key=lambda x: x[1], reverse=True
        )
        _slots          = max(0, _max_enrich - len(_guaranteed))
        _selected       = _guaranteed | {t for t, _ in _non_guaranteed_sorted[:_slots]}
        qualified       = {t: df for t, df in qualified.items() if t in _selected}
        log.info(f"  Pre-screen: {len(_prescores)} → {len(qualified)} tickers "
                 f"({len(_zr1_qualified)} Zacks #1 + "
                 f"{len(_sp500_in_qualified)} S&P 500 + "
                 f"{len(_ndx_in_qualified)} NASDAQ-100 + "
                 f"{len(_earnings_in_qualified)} pre-earnings + "
                 f"{len(_pead_in_qualified)} PEAD post-report + "
                 f"{len(_curated_qualified)} curated-source guaranteed + "
                 f"{len(_finviz_qualified)} finviz-candidate guaranteed + "
                 f"{len(_selected) - len(_guaranteed)} top-ranked OHLCV)")
    else:
        log.info(f"  Pre-screen: {len(qualified)} tickers (under {_max_enrich} threshold, no cut)")

    # Step 4: Fetch fundamentals + enrichment for qualified tickers
    log.info("Step 4: Fetching fundamentals & enrichment...")
    tickers_to_analyze = list(qualified.keys())

    # ── Phase 5: two-stage conditional enrichment ─────────────────────────
    # Split qualified into a "deep" tier (full enrichment) and a "light" tier
    # (only cheap EODHD-backed endpoints). Expensive per-ticker endpoints
    # (options chain, UOA, gamma, congressional, WSB, gamma squeeze) only fire
    # for the deep tier. Light-tier tickers can still produce a verdict from
    # OHLCV + cheap signals but won't get BUY upgrades (only WATCH at best).
    _tier1_n   = int(cfg.get("performance", {}).get("deep_enrichment_top_n", 200))
    # DEEP_ENRICHMENT_OVERRIDE: lift the deep (options/UOA/gamma/news) tier for the
    # weekly Saturday-evening full refresh — deep-enrich the WHOLE universe, not just
    # the top-N. Set by scripts/weekly_full_enrich.sh. (2026-06-03)
    _deep_override = os.environ.get("DEEP_ENRICHMENT_OVERRIDE")
    if _deep_override:
        try:
            _tier1_n = max(_tier1_n, int(_deep_override))
            log.info(f"  DEEP_ENRICHMENT_OVERRIDE={_tier1_n} → deep-enrich tier lifted (weekly full refresh)")
        except Exception:
            pass
    # 2026-05-28: LIGHT intraday mode. The heavy deep-enrich runs ONCE at 06:00
    # (warms the 7-day fundamentals cache + does full options/UOA on top 1,500).
    # The 5 intraday scans (07:00/11:00/13:30/15:00) run with SCAN_MODE=light:
    # they still re-rank ALL tickers (cheap — OHLCV + warm-cached fundamentals),
    # but shrink the expensive-endpoint tier (options/UOA/SEC/inst) to the top
    # ~150 so each intraday scan finishes fast and stays well under quota.
    _scan_mode = os.environ.get("SCAN_MODE", "").lower()
    if _scan_mode == "light":
        _tier1_n = min(_tier1_n, int(cfg.get("performance", {}).get("light_deep_enrichment_top_n", 150)))
        log.info(f"  SCAN_MODE=light → deep-enrich tier shrunk to {_tier1_n} (intraday: re-rank all, deep-enrich top {_tier1_n})")
    _zr1_set   = set(zacks_r1_set) if "zacks_r1_set" in dir() else set()
    _eg_set    = _earnings_guaranteed if "_earnings_guaranteed" in dir() else set()
    _custom_set = {t for t, src in ticker_sources.items() if src in ("custom", "leveraged")}
    _alwaysinc_set = {t for t in qualified if t.upper() in always_include}
    # Score all qualifying tickers cheaply (reuse the local pre-screen helper)
    _all_scores = {t: _fast_prescreen_score(df) for t, df in qualified.items()}
    # Tier-1 = (guaranteed sets) + (top-N by score until we hit _tier1_n)
    _t1_guaranteed = _zr1_set | _eg_set | _custom_set | _alwaysinc_set
    _t1_guaranteed &= set(qualified.keys())
    _sorted = sorted(
        [(t, s) for t, s in _all_scores.items() if t not in _t1_guaranteed],
        key=lambda x: x[1], reverse=True,
    )
    _t1_slots = max(0, _tier1_n - len(_t1_guaranteed))
    tier1_tickers: set = _t1_guaranteed | {t for t, _ in _sorted[:_t1_slots]}
    tier2_tickers: set = set(qualified.keys()) - tier1_tickers
    log.info(
        f"  Phase-5 tier split: tier1={len(tier1_tickers)} "
        f"(deep: options/UOA/gamma/WSB/congressional), "
        f"tier2={len(tier2_tickers)} (light: cheap EODHD only)"
    )
    # Surface the tier split so downstream code can gate BUY verdicts
    _tier1_set = tier1_tickers
    _tier2_set = tier2_tickers

    # Phase 3: pre-fetch bulk calendar/trends so get_earnings_estimate_trend()
    # hits an in-memory cache instead of falling through to deprecated yfinance.
    # Cuts ~650 yfinance calls (with 50+ DeprecationWarnings each) to ~6-7 bulk
    # EODHD calls per scan.
    try:
        from data_fetcher import prewarm_calendar_trends_bulk
        _pw = prewarm_calendar_trends_bulk(tickers_to_analyze)
        if _pw.get("ok"):
            log.info(
                f"  [Phase-3 prewarm] calendar/trends: warmed {_pw['tickers_warmed']}/"
                f"{len(tickers_to_analyze)} tickers in {_pw['eodhd_calls']} EODHD calls "
                f"({_pw['elapsed_sec']}s)"
            )
    except Exception as _pe:
        log.debug(f"Phase-3 prewarm skipped: {_pe}")

    # Fetch info in parallel
    infos = get_stock_info_batch(tickers_to_analyze, max_workers=16)

    # Merge Schwab bulk KPI data into info dicts (Step 2.5 output)
    if _schwab_kpi_map:
        _kpi_merged = 0
        for t in tickers_to_analyze:
            if t in _schwab_kpi_map and t in infos:
                kpi_info = _schwab_kpi_map[t]
                for k in ("kpi_quote_age_s", "kpi_spread_bp", "kpi_post_market_pct",
                           "kpi_dist_from_52wk_high_pct", "kpi_dist_from_52wk_low_pct",
                           "kpi_days_since_earnings", "kpi_leverage_factor"):
                    if kpi_info.get(k) is not None:
                        infos[t][k] = kpi_info[k]
                _kpi_merged += 1
        log.info(f"  KPI data merged into {_kpi_merged} info dicts")

    # Lazy weekly fetch: only needed for weekly EMA alignment (±2 pt bonus).
    # Pre-screen with a fast EMA trend check — skip tickers in clear downtrends.
    def _quick_is_trending(df):
        try:
            c = df["Close"].squeeze()
            if len(c) < 50:
                return False
            e21 = float(c.ewm(span=21, adjust=False).mean().iloc[-1])
            e50 = float(c.ewm(span=50, adjust=False).mean().iloc[-1])
            return float(c.iloc[-1]) > e50 and e21 > e50
        except Exception:
            return False

    weekly_candidates = [t for t in tickers_to_analyze if _quick_is_trending(qualified[t])]
    log.info(f"  Fetching weekly OHLCV (lazy: {len(weekly_candidates)}/{len(tickers_to_analyze)} trending)...")
    weekly_data = get_weekly_data(weekly_candidates)
    log.info(f"  Weekly data: {len(weekly_data)} tickers")

    # Fetch earnings, news, insider, analyst, StockTwits, options IV, beat rate,
    # congressional trades, and Reddit WSB all in parallel (congressional/WSB moved
    # out of per-ticker analysis thread to avoid N×serial API calls)
    earnings_data       = {}
    news_data           = {}
    insider_data        = {}
    analyst_data        = {}
    stocktwits_data     = {}
    options_iv_data     = {}
    beat_rate_data      = {}
    extra_fund_data     = {}
    rich_fund_data      = {}  # 2026-05-27 · EODHD holders + insider tx + 5y fins
    congressional_data  = {}
    reddit_wsb_data     = {}
    uoa_data            = {}
    borrow_data         = {}
    finnhub_data        = {}
    fmp_data            = {}
    sec_data            = {}
    premarket_data      = {}
    inst_trend_data     = {}
    gamma_data          = {}
    eps_trend_data      = {}

    # FINVIZ bulk + Polygon snapshot decommissioned 2026-04-25 (EODHD-only).
    # Stubbed callers return empty dicts; downstream code handles None gracefully.
    # FINVIZ bulk (#b): whole-universe breadth in ~5 calls (short-float/ownership/SMA/
    # rel-vol/perf/valuation/margins/beta) — was dormant ({}); the scoring engine already
    # consumes finviz_bulk. Populating it gives those fields to ALL tickers + offloads EODHD.
    finviz_bulk      = {}
    try:
        finviz_bulk = get_finviz_bulk() or {}
        log.info(f"  Finviz bulk: {len(finviz_bulk)} tickers (breadth/ownership/short/SMA — whole-universe, offloads EODHD per-ticker)")
    except Exception as _fve:
        log.warning(f"  Finviz bulk fetch failed (non-fatal): {_fve}")
    finviz_news_list = []

    # 2026-05-28 · Level-1 quote snapshot (bid/ask/last/sizes/volume) from
    # Schwab Market Data /quotes — batched at 500 symbols/call so the full
    # universe costs ~2-4 calls. Gives the dashboard live marks for P&L + exit
    # alerts across ALL modes (swing/position/invest). Previously stubbed {}
    # → quote_snapshot data-health was 0/N. Schwab Market Data scope only —
    # no Trader-API / account access needed.
    quote_snapshot = {}
    try:
        import schwab_client as _sc
        _raw_q = _sc.get_quotes_batch(tickers_to_analyze)
        for _sym, _blob in (_raw_q or {}).items():
            _q = (_blob or {}).get("quote") or {}
            if not _q:
                continue
            quote_snapshot[_sym.upper()] = {
                "bid":        _q.get("bidPrice"),
                "ask":        _q.get("askPrice"),
                "last":       _q.get("lastPrice"),
                "bid_size":   _q.get("bidSize"),
                "ask_size":   _q.get("askSize"),
                "last_size":  _q.get("lastSize"),
                "volume":     _q.get("totalVolume"),
                "mark":       _q.get("mark"),
                "quote_time": _q.get("quoteTime"),
                "trade_time": _q.get("tradeTime"),
                "spread_pct": (round((_q["askPrice"] - _q["bidPrice"]) / _q["bidPrice"] * 100, 3)
                               if _q.get("askPrice") and _q.get("bidPrice") and _q["bidPrice"] > 0 else None),
                "_source": "schwab_l1",
            }
        log.info(f"  Schwab L1 quote snapshot: {len(quote_snapshot)}/{len(tickers_to_analyze)} tickers")
    except Exception as _q_err:
        log.warning(f"  Schwab quote snapshot failed (non-fatal): {_q_err}")

    news_articles_data = {}
    options_chain_data = {}

    # Enrichment-pool config (bounds API blast radius + skips dead/low-signal calls)
    enr_cfg = (cfg.get("enrichment") or {})
    # Workers bumped 12 → 14 (2026-05-11) to match EODHD per-sec rate limit exactly;
    # the limiter at eodhd_client.py:_RATE_PER_SEC=14 still gates if 14 workers
    # ever issue >14 calls in a second, so this is safe. 12 left 2 slots idle.
    pool_workers   = int(enr_cfg.get("pool_workers", 14))
    skip_low_signal = bool(enr_cfg.get("skip_low_signal", True))  # drop social + decommissioned calls
    skip_options    = bool(enr_cfg.get("skip_options",    True))  # options data removed in EODHD migration
    # Hang guards (2026-06-09): a single worker blocked on a no-timeout social/web
    # scrape froze the whole scan for ~11min. per_ticker_timeout_s abandons any
    # single future that won't return; phase_max_seconds is the overall Step-4
    # wall-clock kill-switch so the scan ALWAYS reaches scoring.
    per_ticker_timeout_s = float(enr_cfg.get("per_ticker_timeout_s", 90))
    phase_max_seconds    = float(enr_cfg.get("phase_max_seconds", 900))

    log.info(f"  Enrichment pool: workers={pool_workers}, skip_low_signal={skip_low_signal}, skip_options={skip_options}")
    log.info(f"  Enrichment hang guards: per_ticker_timeout={per_ticker_timeout_s:.0f}s, phase_deadline={phase_max_seconds:.0f}s")
    log.info(f"  Tickers: {len(tickers_to_analyze)} × ~14 endpoints ≈ {len(tickers_to_analyze)*14} EODHD calls (cache hits skip the network)")

    # Heartbeat helper — surfaces enrichment progress so log doesn't go silent
    # for 1–2 hours when EODHD failover triggers mass yfinance fallback.
    _enrich_t0 = time.time()
    _enrich_total = len(tickers_to_analyze)
    def _heartbeat(loop_name: str, completed: int) -> None:
        if _enrich_total <= 0:
            return
        step = max(50, _enrich_total // 10)
        if completed == _enrich_total or completed % step == 0:
            elapsed = time.time() - _enrich_t0
            log.info(f"  [enrich] {loop_name}: {completed}/{_enrich_total} ({elapsed:.0f}s)")
    # When skip_low_signal/skip_options=True we leave stocktwits_data, reddit_wsb_data,
    # congressional_data, gamma_data, polygon_opts_data as their original {} init from
    # earlier in this function — downstream code uses .get(t, {}) so empty is safe.

    # Phase 5 tier helpers: cheap endpoints fire for ALL qualified tickers;
    # expensive endpoints fire ONLY for tier-1 (deep_enrichment_top_n) to bound spend.
    _t1 = [t for t in tickers_to_analyze if t in _tier1_set]

    # ── 2026-05-28: fundamentals freshness strategy ──────────────────────────
    # EODHD bulk-fundamentals is a separate paid add-on (403 on our All-In-One
    # plan), so we CANNOT collapse per-ticker calls via bulk. Instead the win is
    # the 7-day cache TTL on fundamentals() (eodhd_client): the weekly cold scan
    # fetches per-ticker once, then every scan for the next 7 days hits the warm
    # disk cache (0 network calls). Across 42 scans/week only 1 is cold.
    # calendar-trends bulk IS attempted (cheap, fails gracefully if unavailable).
    try:
        import eodhd_client as _ec
        if hasattr(_ec, "prewarm_calendar_trends"):
            _ct = _ec.prewarm_calendar_trends(tickers_to_analyze)
            if _ct.get("calls"):
                log.info(f"  Bulk prewarm · calendar-trends: {_ct.get('ok',0)} cached in {_ct.get('calls',0)} bulk calls")
    except Exception as _cte:
        log.debug(f"calendar-trends prewarm skipped: {_cte}")

    with ThreadPoolExecutor(max_workers=pool_workers) as pool:
        # ── CHEAP endpoints (all qualified tickers) — EODHD bulk-able or cached
        earn_futures        = {pool.submit(get_earnings_date,       t): t for t in tickers_to_analyze}
        news_futures        = {pool.submit(get_news_sentiment,      t): t for t in tickers_to_analyze}
        insider_futures     = {pool.submit(get_insider_activity,    t): t for t in tickers_to_analyze}
        analyst_futures     = {pool.submit(get_analyst_data,        t): t for t in tickers_to_analyze}
        extra_fund_futures  = {pool.submit(get_extra_fundamentals,  t): t for t in tickers_to_analyze}
        rich_fund_futures   = {pool.submit(get_fundamentals_rich,   t): t for t in tickers_to_analyze}
        schwab_fund_futures = {pool.submit(get_schwab_fundamentals, t): t for t in tickers_to_analyze}
        eps_trend_futures   = {pool.submit(get_earnings_estimate_trend, t): t for t in tickers_to_analyze}
        news_articles_futures = {pool.submit(get_news_articles, t, 8): t for t in tickers_to_analyze}

        # ── EXPENSIVE endpoints (tier-1 only) — Schwab options chain, UOA, etc.
        options_futures     = {pool.submit(get_options_iv_data,     t): t for t in _t1}
        beat_futures        = {pool.submit(get_earnings_beat_rate,  t): t for t in _t1}
        uoa_futures         = {pool.submit(get_unusual_options,     t): t for t in _t1}
        borrow_futures      = {pool.submit(get_borrow_rate,         t): t for t in _t1}
        sec_futures         = {pool.submit(get_sec_filings,         t): t for t in _t1}
        premarket_futures   = {pool.submit(get_premarket_volume,    t): t for t in _t1}
        inst_trend_futures  = {pool.submit(get_institutional_trend, t): t for t in _t1}

        # Optional / low-signal — tier-1 ONLY when not skipped
        if skip_low_signal:
            stocktwits_futures = {}
            wsb_futures        = {}
            cong_futures       = {}
            gamma_futures      = {}
        else:
            stocktwits_futures  = {pool.submit(get_stocktwits_data,     t): t for t in _t1}
            wsb_futures         = {pool.submit(get_reddit_wsb,          t): t for t in _t1}
            cong_futures        = {pool.submit(get_congressional_trades, t): t for t in _t1}
            gamma_futures       = {pool.submit(get_gamma_squeeze_data,   t): t for t in _t1}

        # Options chain — Schwab is the canonical provider (post-2026-04-25
        # Polygon decommissioning). Variable renamed 2026-05-15 from the
        # legacy `poly_opts_futures` to clarify provider in code reads.
        if skip_options:
            schwab_opts_futures = {}
        else:
            from datetime import date as _date, timedelta as _td
            _today = _date.today()
            _days_ahead = (4 - _today.weekday()) % 7 or 7
            _nearest_expiry = (_today + _td(days=_days_ahead)).isoformat()
            schwab_opts_futures = {pool.submit(get_schwab_options, t, _nearest_expiry): t for t in tickers_to_analyze}

        # ── Hang-guard drainer (2026-06-09) ──────────────────────────────────
        # Replaces the bare `for fut in as_completed(futures)` pattern. Three
        # layers of protection so one hung worker can never freeze the scan:
        #   1. per-future timeout — fut.result(timeout=per_ticker_timeout_s);
        #      a single stuck call is abandoned (default filled), pool continues.
        #   2. wall-clock deadline — as_completed(timeout=remaining_budget);
        #      once phase_max_seconds elapses we stop waiting on the rest.
        #   3. graceful fill — every un-drained ticker gets `default` so
        #      downstream .get(t, {}) consumers see a complete map and scoring
        #      always proceeds.
        _phase_deadline = time.time() + phase_max_seconds
        _drain_stats = {"timed_out_futures": 0, "deadline_hit_loops": 0}

        def _drain(futures, sink, default, label, on_item=None):
            """Drain a {future: ticker} map into `sink` with hang guards."""
            if not futures:
                return
            pending = dict(futures)  # future -> ticker still to collect
            try:
                remaining = max(1.0, _phase_deadline - time.time())
                for fut in as_completed(futures, timeout=remaining):
                    t = pending.pop(fut, None)
                    if t is None:
                        continue
                    try:
                        sink[t] = fut.result(timeout=per_ticker_timeout_s)
                    except _FutureTimeout:
                        _drain_stats["timed_out_futures"] += 1
                        log.warning(f"  [enrich] {label}: per-ticker timeout "
                                    f"({per_ticker_timeout_s:.0f}s) on {t} — abandoning, using default")
                        fut.cancel()
                        sink[t] = default() if callable(default) else default
                    except Exception:
                        sink[t] = default() if callable(default) else default
                    if on_item is not None:
                        on_item(t)
            except _FutureTimeout:
                # Wall-clock deadline reached — stop waiting on the remainder.
                _drain_stats["deadline_hit_loops"] += 1
                log.warning(f"  [enrich] {label}: phase deadline ({phase_max_seconds:.0f}s) "
                            f"hit — proceeding with {len(futures) - len(pending)}/{len(futures)} "
                            f"enriched, {len(pending)} defaulted")
            # Fill defaults for anything still pending (deadline or stray).
            for fut, t in pending.items():
                if t not in sink:
                    fut.cancel()
                    sink[t] = default() if callable(default) else default

        _drain(earn_futures, earnings_data,
               lambda: {"earnings_date": None, "days_to_earnings": None, "earnings_risk": False},
               "earnings_date")

        _drain(news_futures, news_data,
               lambda: {"score": 0, "bias": "neutral"}, "news_sentiment")
        _drain(insider_futures, insider_data,
               lambda: {"buys": 0, "sells": 0, "sentiment": "neutral"}, "insider")
        _drain(analyst_futures, analyst_data, dict, "analyst")
        _drain(stocktwits_futures, stocktwits_data, dict, "stocktwits")
        _drain(options_futures, options_iv_data, dict, "options_iv")
        _drain(beat_futures, beat_rate_data, dict, "beat_rate")

        _n_extra = 0
        def _on_extra(_t):
            nonlocal _n_extra
            _n_extra += 1
            _heartbeat("extra_fund", _n_extra)
        _drain(extra_fund_futures, extra_fund_data, dict, "extra_fund", on_item=_on_extra)

        # 2026-05-27 · Rich fundamentals (holders + insider tx + 5y fins +
        # earnings history + analyst revision trend). Cached 24h via the
        # underlying eodhd_client.fundamentals call, so most hit cache here.
        _n_rich = 0
        def _on_rich(_t):
            nonlocal _n_rich
            _n_rich += 1
            _heartbeat("rich_fund", _n_rich)
        _drain(rich_fund_futures, rich_fund_data, dict, "rich_fund", on_item=_on_rich)

        _drain(cong_futures, congressional_data, dict, "congressional")
        _drain(wsb_futures, reddit_wsb_data, dict, "reddit_wsb")
        _drain(uoa_futures, uoa_data, dict, "unusual_options")
        _drain(borrow_futures, borrow_data, dict, "borrow_rate")

        # Drain Schwab fundamentals (populates the shared memcache). After this
        # loop, both get_finnhub_data() and get_fmp_data() below are O(1).
        # Sink is a throwaway dict — we only care about the cache side effect.
        _n_schwab = 0
        def _on_schwab(_t):
            nonlocal _n_schwab
            _n_schwab += 1
            _heartbeat("schwab_fund", _n_schwab)
        _drain(schwab_fund_futures, {}, dict, "schwab_fund", on_item=_on_schwab)
        for t in tickers_to_analyze:
            finnhub_data[t] = get_finnhub_data(t)   # shim — reads Schwab memcache
            fmp_data[t]     = get_fmp_data(t)       # shim — reads Schwab memcache

        _drain(sec_futures, sec_data, dict, "sec_filings")
        _drain(premarket_futures, premarket_data, dict, "premarket")
        _drain(inst_trend_futures, inst_trend_data, dict, "inst_trend")
        _drain(gamma_futures, gamma_data, dict, "gamma")

        _n_eps = 0
        def _on_eps(_t):
            nonlocal _n_eps
            _n_eps += 1
            _heartbeat("eps_trend", _n_eps)
        _drain(eps_trend_futures, eps_trend_data, dict, "eps_trend", on_item=_on_eps)

        _n_news = 0
        def _on_news(_t):
            nonlocal _n_news
            _n_news += 1
            _heartbeat("news_articles", _n_news)
        _drain(news_articles_futures, news_articles_data, list, "news_articles", on_item=_on_news)

        _drain(schwab_opts_futures, options_chain_data, dict, "schwab_options")

        if _drain_stats["timed_out_futures"] or _drain_stats["deadline_hit_loops"]:
            log.warning(
                f"  [enrich] hang guards engaged: "
                f"{_drain_stats['timed_out_futures']} per-ticker timeout(s), "
                f"{_drain_stats['deadline_hit_loops']} phase-deadline hit(s) — "
                f"scan continued to scoring with partial enrichment"
            )

    log.info(f"  Enriched {len(infos)} tickers (EODHD + Schwab + SEC EDGAR + FINVIZ scrape + congressional + WSB + UOA + borrow + pre-mkt + gamma)")
    # Surface yfinance circuit-breaker stats so a tripped breaker is visible.
    try:
        from data_fetcher import yf_circuit_stats
        _cs = yf_circuit_stats()
        if _cs["total_calls"] > 0:
            state = "OPEN (yf fallback disabled mid-scan)" if _cs["open"] else "closed"
            log.info(
                f"  [yfinance circuit] {state} · calls={_cs['total_calls']} "
                f"slow={_cs['slow_calls']} failed={_cs['failed_calls']} "
                f"(trips on {_cs['trip_after']}+ slow calls)"
            )
    except Exception:
        pass

    # Backfill missing earnings dates from FINVIZ bulk
    _earn_patched = 0
    if finviz_bulk:
        for t in tickers_to_analyze:
            ed = earnings_data.get(t, {})
            if ed.get("earnings_date") is not None:
                continue
            fv = finviz_bulk.get(t, {})
            fv_ed = fv.get("earnings_date")
            if fv_ed:
                try:
                    import pandas as _pd_earn
                    parsed = _pd_earn.to_datetime(fv_ed, utc=True)
                    now = _pd_earn.Timestamp.now(tz="UTC")
                    days = (parsed - now).days
                    earnings_data[t] = {
                        "earnings_date": str(parsed.date()),
                        "days_to_earnings": max(0, days),
                        "earnings_risk": 0 <= days <= 5,
                        "_source": "finviz",
                    }
                    _earn_patched += 1
                except Exception:
                    pass
    if _earn_patched:
        log.info(f"  Earnings date backfill from FINVIZ: {_earn_patched} tickers")

    # EODHD-first backfill (2026-05-08): EODHD's get_fundamentals returns
    # beta + sector + industry from Technicals + General blocks. Calling it
    # here is cheap (7-day cache hit on second use). Runs BEFORE Finviz so
    # EODHD wins; Finviz becomes pure cleanup for what EODHD missed.
    _eodhd_patched = 0
    try:
        from data_fetcher import get_fundamentals as _get_eodhd_fund
        for t in tickers_to_analyze:
            info_d = infos.get(t, {})
            need_any = (info_d.get("beta") is None or
                        info_d.get("short_pct") is None or
                        info_d.get("sector") in (None, "Unknown", "") or
                        info_d.get("industry") in (None, "Unknown", ""))
            if not need_any:
                continue
            ef = _get_eodhd_fund(t)  # cached 7d
            if not isinstance(ef, dict):
                continue
            patched = False
            if info_d.get("beta") is None and ef.get("beta") is not None:
                info_d["beta"] = ef["beta"]; patched = True
            if info_d.get("short_pct") is None and ef.get("short_pct") is not None:
                info_d["short_pct"] = ef["short_pct"]; patched = True
            if info_d.get("sector") in (None, "Unknown", "") and ef.get("sector"):
                info_d["sector"] = ef["sector"]; patched = True
            if info_d.get("industry") in (None, "Unknown", "") and ef.get("industry"):
                info_d["industry"] = ef["industry"]; patched = True
            if patched:
                infos[t] = info_d
                _eodhd_patched += 1
    except Exception as _ee:
        log.debug(f"EODHD backfill skipped: {_ee}")
    if _eodhd_patched:
        log.info(f"  EODHD backfill: patched {_eodhd_patched} info dicts (beta/sector/industry)")

    # Finviz fallback — only fills what EODHD didn't have. Free public
    # scraping; fragile but covers gaps when EODHD returns null. Memory:
    # feedback_data_source_priority.md (Finviz Elite paid was decommissioned;
    # this is the free-scrape supplement).
    _fv_patched = 0
    if finviz_bulk:
        for t in tickers_to_analyze:
            fv = finviz_bulk.get(t)
            if not fv:
                continue
            info_d = infos.get(t, {})
            patched = False
            if info_d.get("beta") is None and fv.get("beta") is not None:
                info_d["beta"] = fv["beta"]
                patched = True
            if info_d.get("short_pct") is None and fv.get("short_float_pct") is not None:
                info_d["short_pct"] = fv["short_float_pct"] / 100.0 if fv["short_float_pct"] > 1 else fv["short_float_pct"]
                patched = True
            if info_d.get("sector") in (None, "Unknown", "") and fv.get("sector"):
                info_d["sector"] = fv["sector"]
                patched = True
            if info_d.get("industry") in (None, "Unknown", "") and fv.get("industry"):
                info_d["industry"] = fv["industry"]
                patched = True
            if patched:
                infos[t] = info_d
                _fv_patched += 1
        log.info(f"  Finviz backfill (post-EODHD residual): patched {_fv_patched} info dicts")

    # ── Sector fallback: Finnhub /stock/profile2 for tickers still missing sector ──
    _fh_sector_patched = 0
    for t in tickers_to_analyze:
        info_d = infos.get(t, {})
        if info_d.get("sector") not in (None, "Unknown", ""):
            continue
        fh = finnhub_data.get(t, {})
        fh_sector = fh.get("sector")
        if fh_sector:
            info_d["sector"] = fh_sector
            if info_d.get("industry") in (None, "Unknown", ""):
                info_d["industry"] = fh.get("industry") or fh_sector
            infos[t] = info_d
            _fh_sector_patched += 1
    if _fh_sector_patched:
        log.info(f"  Sector backfill from Finnhub: {_fh_sector_patched} tickers")

    # ── Multi-Source Fallback Chain: Beat Rate ──
    # Schwab earnings → Finnhub surprises → FMP earnings
    _br_patched = 0
    for t in tickers_to_analyze:
        if beat_rate_data.get(t) and beat_rate_data[t].get("beat_rate") is not None:
            continue

        # Layer 1: Finnhub earnings surprises
        fh = finnhub_data.get(t, {})
        es = fh.get("earnings_surprises", [])
        if es and len(es) >= 2:
            beats = sum(1 for e in es if (e.get("actual") or 0) > (e.get("estimate") or 0))
            beat_rate_data[t] = {
                "beat_rate": beats / len(es),
                "beats": beats,
                "misses": len(es) - beats,
                "quarters": len(es),
                "_source": "finnhub",
            }
            _br_patched += 1
            continue

        # Layer 2: FMP earnings data
        fm = fmp_data.get(t, {})
        fm_eps_hist = fm.get("eps_history", [])
        if fm_eps_hist and len(fm_eps_hist) >= 2:
            beats = sum(1 for e in fm_eps_hist if (e.get("actual") or 0) > (e.get("estimate") or 0))
            beat_rate_data[t] = {
                "beat_rate": beats / len(fm_eps_hist),
                "beats": beats,
                "misses": len(fm_eps_hist) - beats,
                "quarters": len(fm_eps_hist),
                "_source": "fmp",
            }
            _br_patched += 1
            continue

        # Layer 3: Derive from Finviz EPS growth (proxy — if growth is consistently positive, likely beating)
        fv = finviz_bulk.get(t, {})
        _fv_this = fv.get("eps_growth_this_yr")
        _fv_next = fv.get("eps_growth_next_yr")
        if _fv_this is not None and _fv_this > 10:
            beat_rate_data[t] = {
                "beat_rate": 0.75 if _fv_this > 20 else 0.60,
                "beats": 3 if _fv_this > 20 else 2,
                "misses": 1 if _fv_this > 20 else 2,
                "quarters": 4,
                "_source": "finviz_proxy",
            }
            _br_patched += 1
    if _br_patched:
        log.info(f"  Beat rate backfill: {_br_patched} tickers (Finnhub + FMP + Finviz proxy)")

    # ── Multi-Source Fallback Chain: Analyst ──
    # Finnhub recs → FMP consensus → Finviz-derived
    _ad_patched = 0
    for t in tickers_to_analyze:
        ad = analyst_data.get(t, {})
        if ad.get("total_analysts", 0) > 0:
            continue

        # Layer 1: Finnhub recommendations
        fh = finnhub_data.get(t, {})
        fh_buy = fh.get("analyst_buy", 0)
        fh_hold = fh.get("analyst_hold", 0)
        fh_sell = fh.get("analyst_sell", 0)
        fh_total = fh_buy + fh_hold + fh_sell

        # Layer 2: FMP analyst data
        if fh_total == 0:
            fm = fmp_data.get(t, {})
            fm_consensus = fm.get("consensus")
            fm_analysts = fm.get("num_analysts", 0)
            if fm_consensus and fm_analysts > 0:
                _fm_map = {"Strong Buy": (fm_analysts, 0, 0), "Buy": (int(fm_analysts*0.7), int(fm_analysts*0.3), 0),
                           "Hold": (0, fm_analysts, 0), "Sell": (0, 0, fm_analysts)}
                fh_buy, fh_hold, fh_sell = _fm_map.get(fm_consensus, (0, fm_analysts, 0))
                fh_total = fh_buy + fh_hold + fh_sell

        # Layer 3: Finviz EPS growth as proxy (strong growth = analysts likely bullish)
        if fh_total == 0:
            fv = finviz_bulk.get(t, {})
            _fv_eps_next = fv.get("eps_growth_next_yr")
            if _fv_eps_next is not None and _fv_eps_next > 15:
                fh_buy, fh_hold, fh_sell = 3, 1, 0
                fh_total = 4

        if fh_total > 0:
            if fh_buy > fh_hold + fh_sell:
                consensus = "buy"
            elif fh_buy + fh_hold > fh_sell * 3:
                consensus = "hold"
            else:
                consensus = "sell"
            # Compute recent revision direction from monthly trends
            # Finnhub recommendations endpoint returns monthly snapshots
            # Compare current month to 3 months ago for upgrade/downgrade count
            # Derive upgrades/downgrades from Finnhub monthly trend
            _fh_upgrades_10d = 0
            _fh_downgrades_10d = 0
            _fh_full_recs = fh.get("_recommendation_trend", [])
            if len(_fh_full_recs) >= 2:
                _cur = _fh_full_recs[0]
                _prev = _fh_full_recs[1]
                _cur_buy = (_cur.get("strongBuy", 0) or 0) + (_cur.get("buy", 0) or 0)
                _prev_buy = (_prev.get("strongBuy", 0) or 0) + (_prev.get("buy", 0) or 0)
                _cur_sell = (_cur.get("sell", 0) or 0) + (_cur.get("strongSell", 0) or 0)
                _prev_sell = (_prev.get("sell", 0) or 0) + (_prev.get("strongSell", 0) or 0)
                if _cur_buy > _prev_buy:
                    _fh_upgrades_10d = _cur_buy - _prev_buy
                if _cur_sell > _prev_sell:
                    _fh_downgrades_10d = _cur_sell - _prev_sell
            ad_patched = dict(ad)
            ad_patched.update({
                "strong_buy": fh_buy // 2,
                "buy": fh_buy - fh_buy // 2,
                "hold": fh_hold,
                "sell": fh_sell,
                "total_analysts": fh_total,
                "consensus": consensus,
                "recommendation": "strong_buy" if fh_buy > fh_total * 0.7 else "buy" if fh_buy > fh_total * 0.5 else "hold",
                "upgrades_10d": _fh_upgrades_10d,
                "downgrades_10d": _fh_downgrades_10d,
                "_source": "finnhub",
            })
            analyst_data[t] = ad_patched
            _ad_patched += 1

    # Layer 4 (2026-05-22) — Finviz scrape was already executed inside
    # get_analyst_data() and populated consensus/target_mean/latest_actions,
    # but never wrote `total_analysts`. The original yfinance quoteSummary
    # path (which DID populate it) was removed 2026-04-24 due to "Invalid
    # Crumb" 401 storms. Backfill `total_analysts` from the number of
    # distinct firms in latest_actions — undercount (only firms with recent
    # action are counted) but real data, and unblocks downstream consumers
    # (analysis.py:2464 reads `total_analysts` for the analyst-coverage gate).
    _ad_finviz_patched = 0
    for t in tickers_to_analyze:
        ad = analyst_data.get(t, {})
        if ad.get("total_analysts", 0) > 0:
            continue
        actions = ad.get("latest_actions") or ad.get("_finviz_actions") or []
        firms = {a.get("firm","").strip() for a in actions if isinstance(a, dict)}
        firms.discard("")
        if firms:
            ad["total_analysts"] = len(firms)
            ad.setdefault("_source", "finviz_actions")
            analyst_data[t] = ad
            _ad_finviz_patched += 1
    if _ad_patched or _ad_finviz_patched:
        log.info(f"  Analyst data backfill: Finnhub/FMP={_ad_patched} + Finviz-actions={_ad_finviz_patched} tickers")

    # ── IV Rank backfill — options removed 2026-04-25 ──
    # EODHD All-In-One does not include options data. Schwab options removed.
    # Falls back to Finviz ATR-as-IV proxy below for a rough approximation.
    _iv_patched = 0
    _iv_need = [t for t in tickers_to_analyze if (options_iv_data.get(t) or {}).get("iv_rank") is None]
    if _iv_need:
        log.info(f"  IV rank backfill (Finviz ATR proxy only — no options data): {len(_iv_need)} tickers...")

        # Finviz ATM IV (from bulk data already loaded — ATR/price * 16)
        for t in _iv_need:
            if (options_iv_data.get(t) or {}).get("iv_rank") is not None:
                continue
            fv = finviz_bulk.get(t, {})
            fv_atr = fv.get("atr")
            _fv_p = infos.get(t, {}).get("price")
            if not _fv_p:
                _qdf = qualified.get(t)
                _fv_p = float(_qdf["Close"].iloc[-1]) if _qdf is not None and hasattr(_qdf, "iloc") and len(_qdf) > 0 else 0
            fv_price = float(_fv_p or 0)
            if fv_atr and fv_price > 0:
                iv_est = round(fv_atr / fv_price * 100 * 16, 0)  # ATR-to-IV approximation (√252 ≈ 16)
                od = options_iv_data.get(t) or {"iv_current": None, "iv_rank": None, "pc_ratio": None, "uoa": False}
                od["iv_rank"] = min(100, max(0, int(iv_est)))
                od["iv_current"] = round(iv_est, 1)
                od["_iv_source"] = "finviz_atr"
                options_iv_data[t] = od
                _iv_patched += 1

        # Layer 3: Polygon chain (already fetched for some tickers)
        for t in _iv_need:
            if (options_iv_data.get(t) or {}).get("iv_rank") is not None:
                continue
            po = options_chain_data.get(t, {})
            calls = po.get("calls", [])
            if not calls:
                continue
            price = float(infos.get(t, {}).get("price") or 0)
            if price <= 0:
                continue
            atm = min(calls, key=lambda c: abs((c.get("strike") or 0) - price))
            atm_iv = atm.get("iv")
            if atm_iv and atm_iv > 0:
                od = options_iv_data.get(t) or {"iv_current": None, "iv_rank": None, "pc_ratio": None, "uoa": False}
                od["iv_rank"] = min(100, max(0, int(atm_iv * 100)))
                od["iv_current"] = round(atm_iv * 100, 1)
                od["_iv_source"] = "polygon"
                options_iv_data[t] = od
                _iv_patched += 1
    if _iv_patched:
        log.info(f"  IV rank backfill: {_iv_patched} tickers patched (Schwab + Finviz + Polygon)")

    # Build exchange map from yfinance info for TV scanner
    exchange_map = {t: info.get("exchange", "") for t, info in infos.items()}
    tv_ratings = get_tv_ratings_batch(tickers_to_analyze, exchange_map)
    log.info(f"  TV ratings: {len(tv_ratings)} tickers")

    # Step 4h: Fetch 1H bars via EODHD intraday, also resample to 4H.
    # 2026-05-17 · Now keeps BOTH the raw 1H and the 4H resample so the SMC
    # chart can show real intraday bars on 1H + 4H tabs.
    _4h_data: dict = {}
    _1h_data: dict = {}
    try:
        import eodhd_client as _eod_4h
        _intraday_tickers = list(qualified.keys())[:100]  # top-N pre-fetch; rest served lazily via /api/smc_bars
        log.info(f"  Fetching 1H + 4H bars (EODHD intraday) for {len(_intraday_tickers)} qualified tickers...")

        def _fetch_intraday(t):
            try:
                rows = _eod_4h.intraday(t, interval="1h")
                if not rows:
                    return t, None, None
                df = pd.DataFrame(rows)
                ts_col = "datetime" if "datetime" in df.columns else "timestamp"
                if ts_col not in df.columns:
                    return t, None, None
                df[ts_col] = pd.to_datetime(df[ts_col])
                df = df.set_index(ts_col).sort_index()
                df = df.rename(columns={"open":"Open","high":"High","low":"Low","close":"Close","volume":"Volume"})
                df = df[[c for c in ["Open","High","Low","Close","Volume"] if c in df.columns]]
                df_1h = df if not df.empty else None
                df_4h = df.resample("4h").agg({"Open":"first","High":"max","Low":"min","Close":"last","Volume":"sum"}).dropna()
                df_4h = df_4h if not df_4h.empty else None
                return t, df_1h, df_4h
            except Exception:
                return t, None, None

        with ThreadPoolExecutor(max_workers=4) as _4h_pool:
            _4h_futs = {_4h_pool.submit(_fetch_intraday, t): t for t in _intraday_tickers}
            for fut in as_completed(_4h_futs):
                t, d1, d4 = fut.result()
                if d1 is not None:
                    _1h_data[t] = d1
                if d4 is not None:
                    _4h_data[t] = d4
        log.info(f"  Intraday: 1H={len(_1h_data)} · 4H={len(_4h_data)} / {len(_intraday_tickers)} tickers")
    except Exception as _4h_err:
        log.warning(f"  Intraday fetch failed: {_4h_err}")

    # Step 5: Analyze all qualified tickers (parallel — 8 workers)
    log.info("Step 5: Running full analysis (parallel)...")
    all_results = []
    killed = []

    def _analyze_one(ticker: str):
        df = qualified[ticker]
        info = infos.get(ticker, {"ticker": ticker})
        earnings = earnings_data.get(ticker, {})
        news = news_data.get(ticker, {})
        insider = insider_data.get(ticker, {})
        zacks_dict = {"rank": 1, "rank_text": "Strong Buy"} if ticker in zacks_r1_set else None
        result = analyze_ticker(
            ticker, df, info, regime, earnings, news,
            insider, spy_close, cfg,
            zacks=zacks_dict,
            tv_rating=tv_ratings.get(ticker),
            weekly_df=weekly_data.get(ticker),
            options_data=options_iv_data.get(ticker),
            beat_rate=beat_rate_data.get(ticker),
            stocktwits=stocktwits_data.get(ticker),
            sector_etf_data=sector_etf_data,
            extra_fund=extra_fund_data.get(ticker),
            congressional=congressional_data.get(ticker),
            reddit_wsb=reddit_wsb_data.get(ticker),
            zacks_sell=ticker in zacks_sell_set,
            analyst=analyst_data.get(ticker, {}),
            uoa=uoa_data.get(ticker),
            borrow=borrow_data.get(ticker),
            finnhub=finnhub_data.get(ticker),
            fmp=fmp_data.get(ticker),
            sec=sec_data.get(ticker),
            breadth=market_breadth,
            premarket=premarket_data.get(ticker),
            inst_trend=inst_trend_data.get(ticker),
            gamma=gamma_data.get(ticker),
            eps_trend=eps_trend_data.get(ticker),
            finviz=finviz_bulk.get(ticker),
            quote_snapshot=quote_snapshot.get(ticker),
            news_articles=news_articles_data.get(ticker),
            options_chain=options_chain_data.get(ticker),
            df_4h=_4h_data.get(ticker),
            df_1h=_1h_data.get(ticker),
            rich_fund=rich_fund_data.get(ticker),
        )
        result["zacks_rank1"]    = ticker in zacks_r1_set
        result["zacks_vgm"]      = zacks_r1_scores.get(ticker, {})
        result["ticker_source"]  = ticker_sources.get(ticker, "unknown")
        result["analyst"]        = analyst_data.get(ticker, {})
        result["stocktwits"]     = stocktwits_data.get(ticker, {})
        result["finnhub"]        = finnhub_data.get(ticker, {})
        result["fmp"]            = fmp_data.get(ticker, {})
        result["sec_filings"]    = sec_data.get(ticker, {})
        # 2026-05-22 — surface beat_rate at top level so v2 dashboard +
        # data_health checks can read it without spelunking into fundamentals.details
        # (where it's only written as a display string, gated on qtrs>=4).
        result["beat_rate"]      = beat_rate_data.get(ticker, {})
        # 2026-05-08 — surface Finviz Elite fields on the ticker row so the
        # V2 dashboard can render performance strip / short pressure / quality KPIs.
        # analyze_ticker already consumes some, but we keep the raw bundle here too.
        _fv_row = finviz_bulk.get(ticker) or {}
        if _fv_row:
            result["finviz_elite"] = {
                # Performance decay strip (Week / Month / Quarter / Half / Year / YTD)
                "perf_week_pct":    _fv_row.get("perf_week_pct"),
                "perf_month_pct":   _fv_row.get("perf_month_pct"),
                "perf_quarter_pct": _fv_row.get("perf_quarter_pct"),
                "perf_half_pct":    _fv_row.get("perf_half_pct"),
                "perf_year_pct":    _fv_row.get("perf_year_pct"),
                "perf_ytd_pct":     _fv_row.get("perf_ytd_pct"),
                # Short pressure
                "short_float_pct":  _fv_row.get("short_float_pct"),
                "short_ratio":      _fv_row.get("short_ratio"),
                "inst_own_pct":     _fv_row.get("inst_own_pct"),
                "insider_own_pct":  _fv_row.get("insider_own_pct"),
                "shares_float":     _fv_row.get("shares_float"),
                # Quality / fundamentals (pre-computed by Finviz)
                "roe_pct":          _fv_row.get("roe_pct"),
                "roa_pct":          _fv_row.get("roa_pct"),
                "gross_margin_pct": _fv_row.get("gross_margin_pct"),
                "oper_margin_pct":  _fv_row.get("oper_margin_pct"),
                "profit_margin_pct":_fv_row.get("profit_margin_pct"),
                "current_ratio":    _fv_row.get("current_ratio"),
                # Misc (intra-day move, volatility)
                "change_pct":       _fv_row.get("change_pct"),
                "gap_pct":          _fv_row.get("gap_pct"),
                "volatility_w_pct": _fv_row.get("volatility_w_pct"),
                "rel_volume":       _fv_row.get("rel_volume"),
            }
        # VGM raw scores (per-ticker, grades assigned post-scan)
        try:
            rev_qoq = get_quarterly_revenue_growth(ticker)
            result["raw_value_score"]    = raw_value_score(info)
            result["raw_growth_score"]   = raw_growth_score(info, revenue_qoq=rev_qoq)
            result["raw_momentum_score"] = raw_momentum_score(df, result.get("technicals", {}).get("indicators", {}))
        except Exception as _vgm_err:
            log.debug(f"  VGM raw scores failed for {ticker}: {_vgm_err}")
            result["raw_value_score"]    = None
            result["raw_growth_score"]   = None
            result["raw_momentum_score"] = None
        return result

    analysis_workers = cfg.get("performance", {}).get("analysis_workers", 8)
    with ThreadPoolExecutor(max_workers=analysis_workers) as pool:
        futures = {pool.submit(_analyze_one, t): t for t in tickers_to_analyze}
        for fut in as_completed(futures):
            ticker = futures[fut]
            try:
                result = fut.result()
                if not result["gate"]["passed"]:
                    killed.append(result)
                else:
                    all_results.append(result)
            except Exception as e:
                log.warning(f"  Analysis failed for {ticker}: {e}")
                if ticker in zacks_r1_set:
                    zacks_r1_missing[ticker] = f"Analysis error: {e}"

    log.info(f"  Analyzed: {len(all_results)} passed, {len(killed)} killed")

    # AI-38: Daily data-quality report — null % per critical field across universe.
    # Alerts if any critical field > 10% null (suggests vendor feed broken).
    try:
        _dq_fields = ("rs_rank", "price", "score")
        _dq_counts = {f: 0 for f in _dq_fields}
        _dq_tech = {"rvol": 0, "rsi": 0, "ema20": 0, "atr": 0}
        _total_dq = len(all_results)
        for _r in all_results:
            for _f in _dq_fields:
                if _r.get(_f) is None:
                    _dq_counts[_f] += 1
            _ind = _r.get("technicals", {}).get("indicators", {}) or {}
            for _k in _dq_tech:
                if _ind.get(_k) is None:
                    _dq_tech[_k] += 1
        if _total_dq > 0:
            _dq_report = []
            for _f, _n in {**_dq_counts, **_dq_tech}.items():
                _pct = _n / _total_dq * 100
                if _pct >= 10:
                    _dq_report.append(f"{_f} {_pct:.0f}% null")
            if _dq_report:
                log.warning(f"  ⚠️  DATA QUALITY: {', '.join(_dq_report)} ({_total_dq} tickers) — check vendor feed")
            else:
                log.info(f"  Data quality: all critical fields <10% null ✓")
    except Exception as _dqe:
        log.debug(f"Data quality report failed: {_dqe}")

    # AI-32: "Why didn't X fire?" — top 10 RS tickers that are NOT BUY; log blocking reason.
    try:
        _top_rs_not_buy = sorted(
            [r for r in all_results
             if r.get("decision", {}).get("verdict") != "BUY"
             and (r.get("rs_rank", 0) or 0) >= 85],
            key=lambda r: r.get("rs_rank", 0),
            reverse=True,
        )[:10]
        if _top_rs_not_buy:
            log.info(f"  Why-not-BUY (top {len(_top_rs_not_buy)} by RS, RS>=85):")
            for _r in _top_rs_not_buy:
                _rsn = (_r.get("decision") or {}).get("reason", "")[:120]
                log.info(f"    {_r['ticker']:6s} RS {_r.get('rs_rank', 0):3d} score {_r.get('score', 0):3.0f} "
                         f"{_r.get('decision',{}).get('verdict','?'):5s} — {_rsn}")
    except Exception as _wbe:
        log.debug(f"why-not-BUY log failed: {_wbe}")

    # Post-score sanity checks (Data Pipeline → A): flag suspicious scores
    _sanity_flags = 0
    for _r in all_results:
        _t = _r.get("ticker", "")
        _sc = float(_r.get("score", 0) or 0)
        _rv = float(_r.get("technicals", {}).get("indicators", {}).get("rvol", 1.0) or 1.0)
        _px = float(_r.get("price", 0) or 0)
        _rs = int(_r.get("rs_rank", 0) or 0)
        # High score but no volume — likely stale signal
        if _sc >= 80 and _rv < 0.5:
            log.warning(f"  ⚠️  SANITY: {_t} score {_sc:.0f} with RVOL {_rv:.2f} (very low) — verify signal")
            _sanity_flags += 1
        # Price < $1 but passed liquidity — likely data error
        if 0 < _px < 1.0:
            log.warning(f"  ⚠️  SANITY: {_t} price ${_px:.3f} (<$1) but passed liquidity — check data")
            _sanity_flags += 1
        # Score > 85 but RS < 50 — inconsistent (high score should have strong RS)
        if _sc >= 85 and _rs > 0 and _rs < 50:
            log.warning(f"  ⚠️  SANITY: {_t} score {_sc:.0f} but RS {_rs} (low) — score inconsistency")
            _sanity_flags += 1
    if _sanity_flags:
        log.info(f"  Sanity checks: {_sanity_flags} flags across {len(all_results)} results")

    # Step 5a-ii: Recompute RS rank as true percentile across the full scanned universe
    # (The per-ticker linear mapping 0.8–1.2 ratio → 0-100 is replaced with cross-sectional rank)
    try:
        all_for_rs = all_results + killed
        ratios = []
        for r in all_for_rs:
            ratio = r.get("technicals", {}).get("indicators", {}).get("rs_ratio")
            ratios.append(float(ratio) if ratio is not None else None)
        valid_ratios = sorted([v for v in ratios if v is not None])
        n_valid = len(valid_ratios)
        if n_valid > 1:
            for r, ratio in zip(all_for_rs, ratios):
                if ratio is None:
                    continue
                # percentile rank: fraction of universe with lower ratio
                pct = int(sum(1 for v in valid_ratios if v < ratio) / n_valid * 100)
                pct = max(0, min(100, pct))
                r["rs_rank"] = pct
                try:
                    r["technicals"]["indicators"]["rs_rank"] = pct
                except (KeyError, TypeError):
                    pass
            log.info(f"  RS percentile re-ranked across {n_valid} tickers")
            # Persist the rs_ratio distribution so the deep-dive / server-live /
            # single-ticker path can map to a TRUE percentile between scans, instead
            # of the raw linear remap that over-promotes moderate outperformers past
            # the RS>=85/90 elite gates (audit 2026-06-03 HIGH false-signal fix).
            try:
                import json as _jrs
                _rsp = BASE_DIR / "cache" / "rs_distribution.json"
                _rsp.write_text(_jrs.dumps({
                    "sorted_ratios": valid_ratios, "n": n_valid,
                    "generated_at": datetime.now().isoformat(),
                }))
            except Exception as _rse:
                log.debug(f"rs distribution persist skipped: {_rse}")
    except Exception as e:
        log.warning(f"  RS percentile re-rank failed (non-fatal): {e}")

    # Step 5b: Gmail Zacks email bonus
    log.info("Step 5b: Fetching Zacks email signals from Gmail...")
    try:
        gmail_data = fetch_zacks_emails(days=2)
        gmail_count = gmail_data.get("total", 0)
        log.info(f"  Gmail: {gmail_count} Zacks emails | "
                 f"Rank changes: {len(gmail_data.get('rank_changes', {}))} | "
                 f"Trade alerts: {len(gmail_data.get('trade_alerts', []))}")
        # Apply email bonus to scored results
        for result in all_results + killed:
            t = result["ticker"]
            eb = get_zacks_email_bonus(t, gmail_data)
            if eb["bonus"] != 0:
                result["score"] = max(0, min(100, result["score"] + eb["bonus"]))
                result["gmail_bonus"] = eb
                log.info(f"    {t}: Gmail bonus {eb['bonus']:+d} → {result['score']:.0f} "
                         f"({', '.join(eb['signals'])})")
            else:
                result["gmail_bonus"] = eb
    except Exception as e:
        log.warning(f"  Gmail fetch failed (non-fatal): {e}")
        gmail_data = {"emails": [], "rank_changes": {}, "trade_alerts": [],
                      "bull_bear": [], "ticker_mentions": {}}

    # Step 5c: Assign VGM grades (percentile-ranked across full universe)
    log.info("Step 5c: Assigning VGM grades...")
    try:
        all_results = assign_vgm_grades(all_results)
        # Also assign to killed so they show grades in the Killed tab
        killed = assign_vgm_grades(killed)
        log.info(f"  VGM grades assigned to {len(all_results)} passed + {len(killed)} killed")
    except Exception as e:
        log.warning(f"  VGM grading failed (non-fatal): {e}")

    # Phase 1 — merge per-ticker Zacks enrichment (Industry Rank, ESP, Revisions, etc.)
    try:
        if zacks_per_ticker_map:
            _enriched = 0
            for r in all_results:
                t = r.get("ticker")
                enrich = zacks_per_ticker_map.get(t)
                if enrich:
                    r["zacks_industry_rank"]  = enrich.get("industry_rank")
                    r["zacks_industry_total"] = enrich.get("industry_total")
                    r["zacks_industry_pct"]   = enrich.get("industry_pct")
                    r["zacks_sector_rank"]    = enrich.get("sector_rank")
                    r["zacks_sector_total"]   = enrich.get("sector_total")
                    r["zacks_earnings_esp"]   = enrich.get("earnings_esp_pct")
                    r["zacks_lt_growth"]      = enrich.get("long_term_growth_pct")
                    r["zacks_recommendation"] = enrich.get("recommendation")
                    r["zacks_estimate_revisions"]    = enrich.get("estimate_revisions")
                    r["zacks_revision_counts"]       = enrich.get("estimate_revision_counts")
                    r["zacks_eps_surprise_history"]  = enrich.get("eps_surprise_history")
                    r["zacks_brokerage_recommendations"] = enrich.get("brokerage_recommendations")
                    _enriched += 1
            log.info(f"  Zacks per-ticker enrichment merged: {_enriched} tickers")
    except Exception as _ze:
        log.warning(f"  Zacks per-ticker enrichment merge failed (non-fatal): {_ze}")

    # ── Step 5d: Adaptive p90 threshold (2026-04-15) ────────────────────
    # When config.decisions.adaptive_mode == true, dynamically lower buy_min
    # to max(p90 - offset, floor) and re-evaluate WATCH→BUY for tickers that
    # would have qualified under the lower bar. Prevents 0-BUY days in chop.
    _adaptive = cfg.get("decisions", {}).get("adaptive_mode", False)
    if _adaptive and all_results:
        import numpy as np
        _scores = [r.get("score", 0) for r in all_results if r.get("score") is not None]
        if _scores:
            _p90 = float(np.percentile(_scores, 90))
            _offset = cfg.get("decisions", {}).get("adaptive_p90_offset", -8)
            _floor  = cfg.get("decisions", {}).get("adaptive_floor", 40)
            _adaptive_buy_min = max(int(_p90 + _offset), _floor)
            _rt = cfg.get("regime4_thresholds", {}).get(regime4, {}) if regime4 else {}
            _orig_buy_min = _rt.get("buy_min_score", cfg.get("decisions", {}).get("buy_min_score", 65))

            if _adaptive_buy_min < _orig_buy_min:
                _promoted = 0
                _skipped_state = 0
                _skipped_rvol = 0
                _rr_min = _rt.get("rr_min", cfg.get("decisions", {}).get("buy_min_rr", 2.0))
                _rs_min = _rt.get("rs_min", 50)
                for r in all_results:
                    if r.get("decision", {}).get("verdict") == "WATCH" and r.get("score", 0) >= _adaptive_buy_min:
                        # Guard: state classification — only apply when state data is reliable
                        # (has valid zones, not just default LOST_STRUCTURE from missing data)
                        _state = r.get("state") or {}
                        if isinstance(_state, dict):
                            _zones = _state.get("zones") or {}
                            _pz = _zones.get("primary_zone", (None, None)) if isinstance(_zones, dict) else (None, None)
                            _has_zones = _pz[0] is not None and _pz[1] is not None
                            if _has_zones:
                                # State data is reliable — apply guard
                                if _state.get("action") == "AVOID" and _state.get("location") == "LOST_STRUCTURE":
                                    _skipped_state += 1; continue
                            # If zones are None, state data is unreliable — skip guard
                        # Guard: RVOL < 0.3 = truly no participation → skip (relaxed from 0.5)
                        _rvol_check = (r.get("technicals") or {}).get("indicators", {}).get("rvol") or 0
                        if _rvol_check > 0 and _rvol_check < 0.3:
                            _skipped_rvol += 1; continue
                        # Only promote if R:R and RS thresholds still pass
                        _rr = (r.get("trade_plan") or {}).get("rr_ratio", 0) or 0
                        _rs = r.get("rs_rank", 0) or 0
                        if _rr >= _rr_min and _rs >= _rs_min:
                            r["decision"]["verdict"] = "BUY"
                            r["decision"]["reason"] = (
                                f"Adaptive BUY — Score {r.get('score')}/100, p90={_p90:.0f}, "
                                f"adaptive bar={_adaptive_buy_min} (orig {_orig_buy_min}), "
                                f"RS {_rs}, R:R {_rr:.1f}:1 [half-size in choppy]"
                            )
                            r["decision"]["color"] = "#059669"
                            r["decision"]["emoji"] = "check"
                            _promoted += 1
                log.info(f"  Adaptive mode: p90={_p90:.0f}, buy_min {_orig_buy_min}→{_adaptive_buy_min}, "
                         f"promoted {_promoted} WATCH→BUY, "
                         f"skipped {_skipped_state} (state=AVOID/LOST) + {_skipped_rvol} (RVOL<0.5)")

                # ── Fix 3: Setup bonuses in choppy regime ──────────────────────
                # Pullback/mean-reversion setups get +5 effective score boost in chop.
                # Breakout setups get -3 (they fail in chop). Applied as virtual score
                # adjustment for promotion decisions only — actual score unchanged.
                if regime4 in ("risk_on_choppy",):
                    _pullback_setups = {"EMA21 Pullback", "EMA50 Pullback", "Bounce off Support",
                                        "10-Week Pullback", "Trend Continuation"}
                    _breakout_setups = {"52wk Breakout", "VCP Breakout"}
                    _promoted_setup = 0
                    for r in all_results:
                        if r.get("decision", {}).get("verdict") != "WATCH":
                            continue
                        # Same guards as p90-relative pass (only when state data reliable)
                        _st2 = r.get("state") or {}
                        if isinstance(_st2, dict):
                            _z2 = (_st2.get("zones") or {}).get("primary_zone", (None,None)) if isinstance(_st2.get("zones"), dict) else (None,None)
                            if _z2[0] is not None and _st2.get("action") == "AVOID" and _st2.get("location") == "LOST_STRUCTURE": continue
                        _rv2 = (r.get("technicals") or {}).get("indicators", {}).get("rvol") or 0
                        if _rv2 > 0 and _rv2 < 0.3: continue
                        _setup = (r.get("trade_plan") or {}).get("setup_type", "")
                        _bonus = 5 if _setup in _pullback_setups else (-3 if _setup in _breakout_setups else 0)
                        if not _bonus:
                            continue
                        _eff_score = r.get("score", 0) + _bonus
                        if _eff_score >= _adaptive_buy_min:
                            _rr = (r.get("trade_plan") or {}).get("rr_ratio", 0) or 0
                            _rs = r.get("rs_rank", 0) or 0
                            if _rr >= _rr_min and _rs >= _rs_min:
                                r["decision"]["verdict"] = "BUY"
                                r["decision"]["reason"] = (
                                    f"Adaptive BUY (setup bonus) — {_setup} +{_bonus}pt in choppy, "
                                    f"effective score {_eff_score}, RS {_rs}, R:R {_rr:.1f}:1 [half-size]"
                                )
                                r["decision"]["color"] = "#059669"
                                r["decision"]["emoji"] = "check"
                                _promoted_setup += 1
                    if _promoted_setup:
                        log.info(f"  Adaptive setup bonuses: +{_promoted_setup} pullback promotions in choppy")

                # ── Fix 2: Top-N fallback ──────────────────────────────────────
                # If after p90 + setup bonuses, still fewer than top_n_buy BUYs,
                # take the top-N WATCH tickers by score (floor=40, half-size).
                _current_buys = sum(1 for r in all_results if r.get("decision", {}).get("verdict") == "BUY")
                _top_n_adaptive = cfg.get("decisions", {}).get("adaptive_top_n", 5)
                if _current_buys < _top_n_adaptive:
                    _need = _top_n_adaptive - _current_buys
                    _watch_pool = sorted(
                        [r for r in all_results
                         if r.get("decision", {}).get("verdict") == "WATCH"
                         and r.get("score", 0) >= _floor
                         and ((r.get("trade_plan") or {}).get("rr_ratio", 0) or 0) >= _rr_min
                         # State guard (only when zones data reliable) + RVOL guard (relaxed)
                         and not (isinstance(r.get("state"), dict)
                                  and isinstance(r["state"].get("zones"), dict)
                                  and (r["state"]["zones"].get("primary_zone") or (None,None))[0] is not None
                                  and r["state"].get("action") == "AVOID"
                                  and r["state"].get("location") == "LOST_STRUCTURE")
                         and not (0 < ((r.get("technicals") or {}).get("indicators", {}).get("rvol") or 0) < 0.3)],
                        key=lambda x: x.get("score", 0), reverse=True
                    )
                    _promoted_topn = 0
                    for r in _watch_pool[:_need]:
                        r["decision"]["verdict"] = "BUY"
                        r["decision"]["reason"] = (
                            f"Adaptive BUY (top-N fallback) — Score {r.get('score')}/100, "
                            f"ranked #{_current_buys + _promoted_topn + 1} by score, "
                            f"R:R {(r.get('trade_plan') or {}).get('rr_ratio', 0):.1f}:1 [half-size]"
                        )
                        r["decision"]["color"] = "#f59e0b"
                        r["decision"]["emoji"] = "check"
                        _promoted_topn += 1
                    if _promoted_topn:
                        log.info(f"  Adaptive top-N: promoted {_promoted_topn} WATCH→BUY (top-N fallback)")

            else:
                log.info(f"  Adaptive mode: p90={_p90:.0f}, adaptive bar {_adaptive_buy_min} >= orig {_orig_buy_min} — no adjustment")

    # ── Step 5e: Options intelligence — REMOVED 2026-04-25 ─────────────
    # EODHD All-In-One does not include options data; Unicornbay options
    # marketplace add-on is separate ($50/mo). Schwab options removed too.
    # Stocks scoring proceeds without options-derived signals.

    # ── Step 5f-pre-0: Affordable stock bonus ───────────────────────────
    # Boost stocks under $100 by +3 pts so cheaper names surface for
    # smaller accounts ($5K-$25K). Better position sizing flexibility.
    _affordable_boosted = 0
    for r in all_results:
        _pr = r.get("price", 0) or 0
        if 5 < _pr < 100:
            # 2026-05-25 fix: clamp to 100. Without this, a score-97 ticker
            # bumped to 100 by this bonus + then bumped again by sector_rotation
            # below would land at 103 (IONQ root cause).
            r["score"] = max(0, min(100, (r.get("score") or 0) + 3))
            r["_affordable_bonus"] = True
            _affordable_boosted += 1
    if _affordable_boosted:
        log.info(f"  Affordable bonus: +3 pts to {_affordable_boosted} tickers under $100")

    # ── Step 5f-pre: Sector rotation bonus ──────────────────────────────
    # Fix 5 (2026-04-15): boost tickers in leading sectors by +3 score pts.
    # Swing trading follows institutional capital flow — leading sectors
    # have tailwinds that improve win rate on pullback entries.
    if sector_etf_data:
        _leading_sectors = set()
        for _etf, _sd in sector_etf_data.items():
            if _etf != "SPY" and _sd.get("vs_spy_pct", 0) > 2.0 and _sd.get("outperforming"):
                _leading_sectors.add(_etf)
        if _leading_sectors:
            _sector_boosted = 0
            for r in all_results:
                _sec_etf = (r.get("technicals") or {}).get("indicators", {}).get("sector_etf", "")
                if _sec_etf in _leading_sectors:
                    # 2026-05-25 fix: clamp to 100 (companion to affordable_bonus above)
                    r["score"] = max(0, min(100, (r.get("score") or 0) + 3))
                    r["_sector_rotation_bonus"] = True
                    _sector_boosted += 1
            if _sector_boosted:
                log.info(f"  Sector rotation: +3 pts to {_sector_boosted} tickers in leading sectors ({', '.join(_leading_sectors)})")

    # ── Step 5f: WATCH-to-BUY auto-promote on entry zone touch ─────────
    # 2026-05-13 fix: this path was bypassing system circuit breakers
    # (macro blackout, drawdown kill, forced cash). It would promote
    # WATCH→BUY and send a Slack alert, then the downstream decision
    # engine cascade would reroute back to WATCH due to circuit breaker.
    # Result: Slack said "BUY" while the bundle showed 0 BUYs. Fix: check
    # the same blockers BEFORE promotion.
    _zone_promoted = 0
    _zone_block_reason = None
    try:
        import macro_calendar as _mc_check
        _ma_zone = bool((cfg.get("gates") or {}).get("macro_blackout_morning_after", False))
        _mb_active, _mb_reason = _mc_check.is_macro_blackout(morning_after=_ma_zone)
        if _mb_active:
            _zone_block_reason = f"macro blackout: {_mb_reason}"
    except Exception:
        pass
    if not _zone_block_reason:
        try:
            from portfolio_tracker import check_circuit_breaker as _cb_check
            _cb_state = _cb_check() or {}
            if _cb_state.get("active"):
                _zone_block_reason = f"circuit breaker active: {_cb_state.get('level', 'tripped')}"
        except Exception:
            pass
    if _zone_block_reason:
        log.info(f"  Entry-zone promotions SKIPPED — {_zone_block_reason}")
        # Skip the loop AND the Slack alert
        all_results_iter = iter(())
    else:
        all_results_iter = all_results
    for r in all_results_iter:
        if r.get("decision", {}).get("verdict") != "WATCH":
            continue
        _tp = r.get("trade_plan") or {}
        _el = _tp.get("entry_low", 0) or 0
        _eh = _tp.get("entry_high", 0) or 0
        _pr = r.get("price", 0) or 0
        if _el > 0 and _eh > 0 and _pr > 0 and _el <= _pr <= _eh * 1.01:
            _rr = _tp.get("rr_ratio", 0) or 0
            if _rr >= 2.0:
                r["decision"]["verdict"] = "BUY"
                r["decision"]["reason"] = (
                    f"Pullback entry \u2014 Price ${_pr:.2f} in zone "
                    f"(${_el:.2f}\u2013${_eh:.2f}), R:R {_rr:.1f}:1, "
                    f"Stop ${_tp.get('stop',0):.2f}"
                )
                r["decision"]["color"] = "#059669"
                r["decision"]["emoji"] = "check"
                _zone_promoted += 1
    if _zone_promoted:
        log.info(f"  Entry-zone promotions: {_zone_promoted} WATCH\u2192BUY (price in entry zone)")
        # Alert for WATCH→BUY promotions
        try:
            from alerts import send_alert
            _promoted = [r for r in all_results if "Pullback entry" in (r.get("decision", {}).get("reason", ""))]
            for _pm in _promoted[:3]:
                send_alert(f"WATCH→BUY: {_pm['ticker']} ${_pm.get('price',0):.2f} — pulled back to entry zone", level="info")
        except Exception:
            pass

    # Step 6: Sort and categorize
    all_results.sort(key=lambda x: x["score"], reverse=True)

    top_n_buy  = cfg.get("output", {}).get("top_n_buy",   5)
    top_n_sell = cfg.get("output", {}).get("top_n_sell",  5)
    top_n_watch = cfg.get("output", {}).get("top_n_watch", 5)
    sector_max = cfg.get("portfolio", {}).get("sector_max_positions", 2)
    # AI-10: industry cap — tighter than sector. Finer concentration control.
    industry_max = cfg.get("portfolio", {}).get("industry_max_positions", 2)
    # 2026-05-18: dynamic sector cap is now config-driven (was hardcoded 3/1).
    # outperforming = sector ETF beating SPY; underperforming = lagging.
    _dyn_cfg = cfg.get("portfolio", {}).get("dynamic_sector_cap", {})
    _dyn_max_out = int(_dyn_cfg.get("outperforming", 3))
    _dyn_max_und = int(_dyn_cfg.get("underperforming", 2))

    # Phase 5D: Dynamic sector concentration — adjust by sector performance
    # AI-10: plus industry cap (hard-block, not warn-only)
    sector_buy_count: dict[str, int] = {}
    industry_buy_count: dict[str, int] = {}
    buy_candidates_raw = []
    for r in all_results:
        if r["decision"]["verdict"] != "BUY":
            continue
        sector = r.get("sector", "Unknown")
        industry = r.get("industry", "") or sector  # fall back to sector if no industry
        # Phase 5D: dynamic cap — outperforming sectors get _dyn_max_out,
        # underperforming get _dyn_max_und (both config-driven as of 2026-05-18).
        _sec_etf = r.get("technicals", {}).get("indicators", {}).get("sector_etf", "")
        if _sec_etf and sector_etf_data and _sec_etf in sector_etf_data:
            _sec_outperf = sector_etf_data[_sec_etf].get("outperforming", False)
            _dynamic_max = _dyn_max_out if _sec_outperf else _dyn_max_und
        else:
            _dynamic_max = sector_max

        # Industry cap first (tighter)
        if industry_buy_count.get(industry, 0) >= industry_max:
            r["decision"]["verdict"] = "WATCH"
            r["decision"]["reason"] += (
                f" [industry cap: {industry} already has {industry_buy_count[industry]} BUY(s), limit={industry_max}]"
            )
            continue

        # Then sector cap
        if sector_buy_count.get(sector, 0) >= _dynamic_max:
            r["decision"]["verdict"] = "WATCH"
            r["decision"]["reason"] += (
                f" [sector cap: {sector} already has {sector_buy_count[sector]} BUY(s), limit={_dynamic_max}]"
            )
            continue

        buy_candidates_raw.append(r)
        sector_buy_count[sector] = sector_buy_count.get(sector, 0) + 1
        industry_buy_count[industry] = industry_buy_count.get(industry, 0) + 1

    # Show ALL BUY-verdicted tickers that survived sector/industry caps.
    # Sector caps already provide sizing discipline — the hard top-N truncation
    # was hiding good alternatives. User has $25K = capacity for 5-8 active
    # positions, so surface the full BUY funnel and let them pick.
    buy_candidates = buy_candidates_raw

    # VIX spike kill switch — apply to final candidates
    if _vix_kill_active:
        buy_candidates = []
        for r in all_results:
            if r.get("decision", {}).get("verdict") == "BUY" and r.get("direction") != "short":
                r["decision"]["verdict"] = "WATCH"
                r["decision"]["reason"] = f"VIX spike kill switch active — no new longs during risk-off"

    # Phase 5E: Graduated VIX — tighten mode raises score bar by 10 pts
    if _vix_tighten_active:
        for r in all_results:
            if r.get("decision", {}).get("verdict") == "BUY":
                if r.get("score", 0) < 75:  # score must be >= 75 in tighten mode
                    r["decision"]["verdict"] = "WATCH"
                    r["decision"]["reason"] += " [VIX tighten: need 75+ score during VIX spike]"
        buy_candidates = [r for r in buy_candidates if r.get("decision", {}).get("verdict") == "BUY"]

    # AI-25: PDT hard-block — under $25K equity, 4+ same-day round-trips in 5
    # business days triggers the SEC pattern-day-trader restriction. We
    # preempt at 3 to leave headroom (can't undo a trade once submitted).
    try:
        _port_pdt = get_portfolio_summary() if callable(get_portfolio_summary) else {}
        _equity_pdt = float(_port_pdt.get("equity", 5000) or 5000)
        if _equity_pdt < 25_000:
            from datetime import date as _date_pdt, timedelta as _td_pdt
            _today_pdt = _date_pdt.today()
            _lookback_pdt = _today_pdt - _td_pdt(days=7)  # ~5 business days
            _closed_pdt = _port_pdt.get("closed_trades", [])
            _dt_count = 0
            for _t in _closed_pdt:
                _ed = str(_t.get("entry_date", ""))[:10]
                _xd = str(_t.get("exit_date",  ""))[:10]
                if _ed and _xd and _ed == _xd:
                    try:
                        _d = _date_pdt.fromisoformat(_xd)
                        if _d >= _lookback_pdt:
                            _dt_count += 1
                    except Exception:
                        pass
            _pdt_block = cfg.get("portfolio", {}).get("position_management", {}).get("pdt_block_at", 3)
            if _dt_count >= _pdt_block:
                log.warning(f"  🔴 PDT HARD-BLOCK: {_dt_count} same-day round-trips in last 5d (<${_equity_pdt:,.0f} account) — no new BUYs today")
                for r in all_results:
                    if r.get("decision", {}).get("verdict") == "BUY":
                        r["decision"]["verdict"] = "WATCH"
                        r["decision"]["reason"] = f"PDT block: {_dt_count}/3 day-trades in 5d (sub-$25K account)"
    except Exception as _pe:
        log.debug(f"PDT hard-block check failed: {_pe}")

    # AI-47: Weekend risk cap — Friday PT scans cap new longs so weekend gross
    # exposure stays <= 50% (60% into 3-day weekends).
    try:
        _today_weekday = datetime.now().weekday()  # 0=Mon..6=Sun
        if _today_weekday == 4:  # Friday
            _weekend_cap = 0.5
            _port_we = get_portfolio_summary() if callable(get_portfolio_summary) else {}
            _cur_gross = sum(p.get("allocation_pct", 0) or 0 for p in _port_we.get("positions", [])) / 100.0
            if _cur_gross >= _weekend_cap:
                log.warning(f"  ⚠️  WEEKEND RISK CAP: current gross {_cur_gross*100:.0f}% >= {_weekend_cap*100:.0f}% — blocking new longs into weekend")
                for r in all_results:
                    if r.get("decision", {}).get("verdict") == "BUY":
                        r["decision"]["verdict"] = "WATCH"
                        r["decision"]["reason"] = f"Weekend risk cap: gross exposure {_cur_gross*100:.0f}%, cap {_weekend_cap*100:.0f}%"
    except Exception as _we:
        log.debug(f"Weekend cap check failed: {_we}")

    # AI-45: portfolio-level daily loss trigger — halt new positions if day P&L <= -4%
    try:
        _daily_loss_pct = cfg.get("portfolio", {}).get("position_management", {}).get("daily_halt_pct", -4.0)
        _port_summary_dl = get_portfolio_summary() if callable(get_portfolio_summary) else {}
        _positions_dl = _port_summary_dl.get("positions", [])
        _day_pnl_pct = 0.0
        if _positions_dl:
            # Day P&L = sum of today's change per open position, weighted by allocation
            _day_chg_weighted = 0.0
            _total_alloc_dl = 0.0
            for _p in _positions_dl:
                _dc = _p.get("day_chg_pct")
                _alloc = _p.get("allocation_pct", 0) or 0
                if _dc is not None and _alloc > 0:
                    _day_chg_weighted += _dc * _alloc
                    _total_alloc_dl += _alloc
            if _total_alloc_dl > 0:
                _day_pnl_pct = _day_chg_weighted / _total_alloc_dl
        if _day_pnl_pct <= _daily_loss_pct:
            log.warning(f"  🔴 DAILY-LOSS HALT: book down {_day_pnl_pct:.1f}% today (≤{_daily_loss_pct}%) — no new longs")
            buy_candidates = []
            for r in all_results:
                if r.get("decision", {}).get("verdict") == "BUY":
                    r["decision"]["verdict"] = "WATCH"
                    r["decision"]["reason"] = f"Daily-loss halt: portfolio -{abs(_day_pnl_pct):.1f}% today"
    except Exception as e:
        log.debug(f"Daily-loss halt check failed (non-fatal): {e}")

    # Portfolio drawdown kill switch — no new positions if book is -8%
    try:
        _port_summary = get_portfolio_summary() if callable(get_portfolio_summary) else {}
        _positions = _port_summary.get("positions", [])
        _total_alloc = sum(p.get("allocation_pct", 0) for p in _positions)
        if _positions and _total_alloc > 0:
            _open_pnl_pct = sum(
                p.get("unrealized_pnl_pct", 0) * p.get("allocation_pct", 0)
                for p in _positions
            ) / _total_alloc
        else:
            _open_pnl_pct = 0.0
        _kill_threshold = cfg.get("portfolio", {}).get("position_management", {}).get("drawdown_kill_pct", -8.0)
        if _open_pnl_pct <= _kill_threshold:
            log.warning(f"  DRAWDOWN KILL SWITCH: Portfolio P&L {_open_pnl_pct:.1f}% — no new BUY signals")
            buy_candidates = []
            for r in all_results:
                if r.get("decision", {}).get("verdict") == "BUY":
                    r["decision"]["verdict"] = "WATCH"
                    r["decision"]["reason"] = f"Drawdown kill switch active ({_open_pnl_pct:.1f}% open loss)"
    except Exception as e:
        log.debug(f"Portfolio drawdown check failed (non-fatal): {e}")

    # Phase 5A: Circuit breaker — pause after 3 consecutive losses
    try:
        from tracker import compute_stats
        _stats = compute_stats()
        _recent = _stats.get("recent_trades", [])
        # Count consecutive losses from most recent
        _consec_losses = 0
        for _t in reversed(_recent):
            if _t.get("pnl_pct", 0) < 0:
                _consec_losses += 1
            else:
                break
        if _consec_losses >= 3:
            log.warning(f"  CIRCUIT BREAKER: {_consec_losses} consecutive losses — no new BUY signals")
            buy_candidates = []
            for r in all_results:
                if r.get("decision", {}).get("verdict") == "BUY":
                    r["decision"]["verdict"] = "WATCH"
                    r["decision"]["reason"] = f"Circuit breaker: {_consec_losses} consecutive losses — pause trading"
    except Exception as _cb_err:
        log.debug(f"  Circuit breaker check failed (non-fatal): {_cb_err}")

    # Correlation gate — block BUY candidates that are >0.80 correlated to existing positions
    # Avoids false diversification: holding 3 highly correlated tech stocks = 1 concentrated bet
    try:
        from portfolio_tracker import compute_pairwise_correlation, load_portfolio
        _port_data = load_portfolio()
        _open_tickers = [p["ticker"] for p in _port_data.get("positions", []) if p.get("status") == "open"]
        _corr_threshold = cfg.get("portfolio", {}).get("position_management", {}).get("max_correlation", 0.80)
        if _open_tickers and buy_candidates:
            _candidate_tickers = [r["ticker"] for r in buy_candidates]
            _all_tickers = list(set(_open_tickers + _candidate_tickers))
            _corr_matrix = compute_pairwise_correlation(_all_tickers, period="3mo")
            for r in buy_candidates[:]:
                _cand = r["ticker"]
                for _pos_t in _open_tickers:
                    _pair = tuple(sorted((_cand, _pos_t)))
                    _corr = _corr_matrix.get(_pair)
                    if _corr is not None and abs(_corr) > _corr_threshold:
                        r["decision"]["verdict"] = "WATCH"
                        r["decision"]["reason"] += (
                            f" [corr gate: {_corr:.2f} correlation with open {_pos_t} > {_corr_threshold}]"
                        )
                        log.info(f"  Corr gate: {_cand} downgraded (corr {_corr:.2f} with {_pos_t})")
                        break
            buy_candidates = [r for r in buy_candidates if r.get("decision", {}).get("verdict") == "BUY"]
    except Exception as _ce:
        log.debug(f"  Correlation gate check failed (non-fatal): {_ce}")

    # Enforce max gross exposure cap (80% of portfolio)
    try:
        _max_exp = cfg.get("portfolio", {}).get("position_management", {}).get("max_gross_exposure_pct", 80)
        _total_alloc = sum(r.get("trade_plan", {}).get("allocation_pct", 7.5) for r in buy_candidates)
        if _total_alloc > _max_exp:
            # Trim lowest-score candidates until under cap
            buy_candidates.sort(key=lambda x: x.get("score", 0), reverse=True)
            while buy_candidates and sum(r.get("trade_plan", {}).get("allocation_pct", 7.5) for r in buy_candidates) > _max_exp:
                removed = buy_candidates.pop()
                log.info(f"  Exposure cap: removed {removed['ticker']} (total would exceed {_max_exp}%)")
    except Exception as e:
        log.debug(f"Exposure cap check failed (non-fatal): {e}")

    # P2.30 — Candidate correlation filter (drop highly-correlated picks)
    try:
        import correlation_factor as _cf
        kept, dropped_pairs = _cf.candidate_correlation_filter(
            buy_candidates, market_data,
            threshold=cfg.get("correlation_filter", {}).get("threshold", 0.7),
            lookback_days=60,
        )
        if dropped_pairs:
            log.info(f"  Correlation filter: dropped {len(dropped_pairs)} duplicates")
            for kept_t, dropped_t, corr in dropped_pairs[:5]:
                log.info(f"    {dropped_t} dropped (corr {corr} with {kept_t})")
        buy_candidates = kept
    except Exception as e:
        log.debug(f"Correlation filter skipped: {e}")

    # P2.31 — Factor exposure summary (tag candidates + flag breaches)
    try:
        import correlation_factor as _cf
        factor_summary = _cf.factor_exposure_summary(
            buy_candidates,
            max_per_factor=cfg.get("factor_caps", {}).get("max_per_factor", 3),
        )
        if factor_summary.get("breaches"):
            for factor, count, mx in factor_summary["breaches"]:
                log.warning(f"  ⚠️  Factor concentration: {count} candidates tagged '{factor}' (cap {mx})")
        # Attach factor tags to each candidate so v2 can render
        ticker_factors = factor_summary.get("ticker_factors", {})
        for r in buy_candidates:
            r["factor_tags"] = ticker_factors.get(r.get("ticker"), [])
    except Exception as e:
        log.debug(f"Factor exposure check skipped: {e}")

    # Persist full decision log (Phase 3.1 wiring) — BUY, WATCH, AVOID, SHORT
    try:
        from decision_logger import log_decisions_batch
        _profile = (
            cfg.get("_profile_name")
            or cfg.get("_meta", {}).get("profile")
            or cfg.get("_meta", {}).get("active_profile")
            or cfg.get("_meta", {}).get("_profile_name")
        )
        if not _profile:
            try:
                _pp = BASE_DIR / "config" / "history" / "active_profile.txt"
                if not _pp.exists():
                    _pp = BASE_DIR / "config" / "profiles" / "active_profile.txt"
                if _pp.exists():
                    _profile = _pp.read_text().strip() or None
            except Exception:
                _profile = None
        _profile = _profile or "unknown"
        log_decisions_batch(all_results, scan_date=date.today().isoformat(), profile=_profile)
    except Exception as _dle:
        log.warning(f"decision_log persist failed: {_dle}")

    # Show all WATCH-verdicted tickers (was capped at top_n_watch=5).
    # WATCH list is reference-only — no position taken — so wider visibility helps
    # spot setups that may promote to BUY tomorrow. Cap at 50 to keep dashboard sane.
    watch_list = [r for r in all_results if r["decision"]["verdict"] == "WATCH"][:50]

    # Sell candidates: confirmed SHORT setups (bear_setup score >= 10, bear regime, R:R >= 3:1)
    # Falls back to AVOID stocks in downtrend if no confirmed shorts exist
    # Split real SHORTs (verdict=="SHORT") from near-shorts blocked by gates.
    # Previously these were merged into sell_candidates which made "0 SHORT"
    # alerts confusing when the UI showed 5 rows. Now tracked separately.
    sell_candidates = [r for r in all_results if r["decision"]["verdict"] == "SHORT"][:top_n_sell]
    near_short_blocked = [r for r in all_results
                          if r["direction"] == "short"
                          and r["decision"]["verdict"] == "AVOID"
                          and r.get("bear_setup", {}).get("score", 0) >= 4][:top_n_sell]

    # Price-tier buckets: top 5 BUY per tier ($5–$50, $50–$100, >$100)
    price_tiers_cfg = cfg.get("filters", {}).get("price_tiers", [
        {"label": "$5–$50",   "min": 5,   "max": 50,   "top_n": 5},
        {"label": "$50–$100", "min": 50,  "max": 100,  "top_n": 5},
        {"label": ">$100",    "min": 100, "max": 9999, "top_n": 5},
    ])
    price_tier_results: list[dict] = []
    for tier in price_tiers_cfg:
        t_min, t_max, t_n = tier["min"], tier["max"], tier.get("top_n", 5)
        picks = [r for r in all_results
                 if t_min <= r.get("price", 0) < t_max
                 and r["decision"]["verdict"] in ("BUY", "WATCH")][:t_n]
        price_tier_results.append({
            "label":  tier["label"],
            "min":    t_min,
            "max":    t_max,
            "picks":  picks,
        })

    # Zacks #1 tab: all analyzed stocks that are Zacks Rank #1, sorted by score
    zacks_tab = sorted(
        [r for r in all_results + killed if r.get("zacks_rank1")],
        key=lambda x: x["score"], reverse=True
    )

    # Build industries
    ind_map = {}
    for r in all_results:
        ind = r.get("industry", "Unknown")
        if ind not in ind_map:
            ind_map[ind] = {"scores": [], "tickers": []}
        ind_map[ind]["scores"].append(r["score"])
        ind_map[ind]["tickers"].append(r["ticker"])

    industries = sorted(
        [{"industry": k, "avg_score": sum(v["scores"]) / len(v["scores"]),
          "count": len(v["scores"]), "tickers": v["tickers"]}
         for k, v in ind_map.items() if k != "Unknown"],
        key=lambda x: x["avg_score"], reverse=True
    )

    # Step 6b: Per-index per-tier BUY/SELL rankings
    sp500_set_upper  = {t.upper() for t in sp500}
    r1000_set_upper  = {t.upper() for t in russell1000}
    all_combined = all_results + killed

    def _index_tier_picks(index_set, all_data, max_price, top_n=5):
        """Top BUY and SELL from an index within a price cap."""
        pool = [r for r in all_data
                if r.get("ticker", "").upper() in index_set
                and 0 < r.get("price", 0) <= max_price]
        pool.sort(key=lambda x: x.get("score", 0), reverse=True)
        buys  = [r for r in pool if r["decision"]["verdict"] in ("BUY", "WATCH")][:top_n]
        sells = [r for r in pool if r["decision"]["verdict"] in ("SHORT",)
                 or (r["direction"] == "short" and r.get("bear_setup", {}).get("score", 0) >= 8)]
        sells.sort(key=lambda x: x.get("bear_setup", {}).get("score", 0), reverse=True)
        sells = sells[:top_n]
        return buys, sells

    idx_sp500_100_buy,  idx_sp500_100_sell  = _index_tier_picks(sp500_set_upper, all_combined, 100)
    idx_sp500_250_buy,  idx_sp500_250_sell  = _index_tier_picks(sp500_set_upper, all_combined, 250)
    idx_r1000_100_buy,  idx_r1000_100_sell  = _index_tier_picks(r1000_set_upper, all_combined, 100)
    idx_r1000_250_buy,  idx_r1000_250_sell  = _index_tier_picks(r1000_set_upper, all_combined, 250)
    r2000_set_upper = {t.upper() for t in russell2000}
    idx_r2000_100_buy,  idx_r2000_100_sell  = _index_tier_picks(r2000_set_upper, all_combined, 100)
    idx_r2000_250_buy,  idx_r2000_250_sell  = _index_tier_picks(r2000_set_upper, all_combined, 250)

    index_picks = {
        "sp500_100":  {"buy": idx_sp500_100_buy,  "sell": idx_sp500_100_sell},
        "sp500_250":  {"buy": idx_sp500_250_buy,  "sell": idx_sp500_250_sell},
        "r1000_100":  {"buy": idx_r1000_100_buy,  "sell": idx_r1000_100_sell},
        "r1000_250":  {"buy": idx_r1000_250_buy,  "sell": idx_r1000_250_sell},
        "r2000_100":  {"buy": idx_r2000_100_buy,  "sell": idx_r2000_100_sell},
        "r2000_250":  {"buy": idx_r2000_250_buy,  "sell": idx_r2000_250_sell},
    }

    # Step 6b: Track extended leaders — quality stocks killed by Extended gate
    # These are strong names to re-enter when they pull back to EMA21
    extended_leaders = []
    for r in killed:
        gate = r.get("gate", {})
        reasons = " ".join(gate.get("reasons", []))
        if "Extended gate" not in reasons:
            continue
        score = r.get("score", 0)
        rs = r.get("technicals", {}).get("indicators", {}).get("rs_rank", 0) or 0
        if score >= 65 and rs >= 70:
            _tp = r.get("trade_plan", {}) or {}
            _ind = r.get("technicals", {}).get("indicators", {}) or {}
            extended_leaders.append({
                "ticker": r.get("ticker"),
                "score": score,
                "rs_rank": rs,
                "price": r.get("price", 0),
                "ema21": _ind.get("ema21", 0),
                "atr_above_ema21": float(reasons.split("price ")[1].split(" ATR")[0]) if "price " in reasons else 0,
                "setup": _tp.get("setup_type", ""),
                "sector": r.get("sector", ""),
                "entry_zone": f"${_tp.get('entry_low', 0):.2f}-${_tp.get('entry_high', 0):.2f}" if _tp.get("entry_low") else "",
                "weekly_bull": _ind.get("weekly_ema_bullish", False),
            })
    extended_leaders.sort(key=lambda x: -x["score"])
    if extended_leaders:
        log.info(f"  Extended leaders (pullback watchlist): {len(extended_leaders)} stocks — "
                 f"{', '.join(e['ticker'] for e in extended_leaders[:5])}")
        # Save for dashboard
        try:
            import json as _elj
            _el_path = BASE_DIR / "cache" / "extended_leaders.json"
            _el_path.write_text(_elj.dumps({"date": run_date, "leaders": extended_leaders[:30]}, default=str))
        except Exception:
            pass
        # Alert for top ones pulling back
        try:
            from alerts import send_alert
            _approaching = [e for e in extended_leaders[:10] if e["atr_above_ema21"] < 3.0]
            if _approaching:
                _names = ", ".join(f"{e['ticker']} ({e['atr_above_ema21']:.1f}ATR)" for e in _approaching[:5])
                send_alert(f"Extended leaders approaching EMA21: {_names}", level="info")
        except Exception:
            pass

    # Step 6c: Portfolio risk metrics
    portfolio_risk = _compute_portfolio_risk(all_results, market_data, spy_close)

    # Step 7: Track
    log.info("Step 7: Recording picks...")
    record_run(buy_candidates + list(watch_list[:5]) + list(sell_candidates[:5]),
               run_date, regime_name=regime.get("regime", "unknown"),
               # AI-15: full market-context snapshot per run
               vix=vix_cur,
               breadth_pct_50d=regime.get("breadth_pct_50d"),
               regime4=regime4,
               spy_price=regime.get("spy_price"),
               spy_1m_ret=regime.get("spy_1m_ret"),
               distribution_days=regime.get("distribution_days"))

    # Also log to signal_tracker for drift/attribution. signal_tracker.log_signals
    # expects a flat schema (ticker/price/stop/target1/rr/...). Phase 2 fix
    # (2026-04-30): include WATCH-tier picks so audit trail captures every
    # alert generated, and tag each pick with its verdict (BUY/WATCH/SHORT).
    try:
        from signal_tracker import log_signals
        # Scan-level context — same across every candidate this run
        _hmm_blob = (regime or {}).get("hmm_regime") or {}
        _vix_now  = float(((regime or {}).get("vix") or {}).get("vix_current") or 0)
        _regime_name = (regime or {}).get("regime", "unknown")
        _regime4 = (regime or {}).get("regime4") or globals().get("regime4")
        _scan_ctx = {
            "regime4":        _regime4,
            "regime_name":    _regime_name,
            "vix_at_signal":  _vix_now,
            "hmm_p_bull":     _hmm_blob.get("p_bull"),
            "hmm_p_neutral":  _hmm_blob.get("p_neutral"),
            "hmm_p_bear":     _hmm_blob.get("p_bear"),
        }

        def _flatten_for_signal_log(c, verdict_label, mode_label="Swing"):
            plan = c.get("trade_plan") or {}
            ind  = c.get("technicals", {}).get("indicators", {}) or {}
            mc   = c.get("monte_carlo") or {}
            fd   = c.get("forward_dist") or {}
            conv = c.get("conviction")    or {}
            tier1 = c.get("tier1_signals") or {}
            options = c.get("options_iv") or {}
            ins   = c.get("insider") or {}
            news  = c.get("news") or {}
            zacks = c.get("zacks_per_ticker") or {}
            # A6 (2026-05-09): entry-time features for future ML training.
            # Per d3e6127ff lesson: mover_predictor v2 failed because these
            # features weren't logged at scan time. Logging now → 30-90 day
            # corpus → train classifier on real entry-time data, not derived.
            sma = ind.get("sma_distance_pct") or {}
            entry_features = {
                "ef_volume_surge_5d":   ind.get("rvol_5d") or ind.get("rvol"),
                "ef_volume_surge_20d":  ind.get("rvol_20d"),
                "ef_atr_pct":           ind.get("atr_pct") or ind.get("atr_pct_close"),
                "ef_atr_expansion":     ind.get("atr_expansion") or ind.get("atr_pct_change_5d"),
                "ef_dist_52w_high_pct": ind.get("dist_52w_high_pct"),
                "ef_dist_20d_high_pct": ind.get("dist_20d_high_pct"),
                "ef_rsi14":             ind.get("rsi") or ind.get("rsi14"),
                "ef_macd_hist":         ind.get("macd_hist"),
                "ef_stoch_rsi":         ind.get("stoch_rsi"),
                "ef_obv_slope":         ind.get("obv_slope"),
                "ef_mfi":               ind.get("mfi"),
                "ef_cmf":               ind.get("cmf"),
                "ef_dist_ema8_pct":     sma.get("ema8") if isinstance(sma, dict) else None,
                "ef_dist_ema21_pct":    sma.get("ema21") if isinstance(sma, dict) else None,
                "ef_dist_ema50_pct":    sma.get("ema50") if isinstance(sma, dict) else None,
                "ef_dist_ema200_pct":   sma.get("ema200") if isinstance(sma, dict) else None,
                "ef_in_squeeze":        bool(ind.get("squeeze") or ind.get("ttm_squeeze")),
                "ef_squeeze_release":   bool(ind.get("squeeze_released")),
                # Catalyst density features
                "ef_tier1_total_pts":   tier1.get("total_points"),
                "ef_tier1_count":       tier1.get("count"),
                "ef_has_pead":          bool(tier1.get("pead")),
                "ef_has_uoa_calls":     options.get("uoa_calls", 0) > 0,
                "ef_has_uoa_puts":      options.get("uoa_puts", 0) > 0,
                "ef_iv_rank":           options.get("iv_rank") or options.get("current_iv"),
                "ef_put_call_ratio":    options.get("put_call_ratio"),
                "ef_insider_score":     ins.get("score") or ins.get("insider_score"),
                "ef_insider_cluster_30d": ins.get("cluster_30d") or ins.get("buys_30d"),
                "ef_news_sentiment":    news.get("sentiment_score") or news.get("composite_score"),
                "ef_news_count_7d":     news.get("count_7d") or news.get("recent_count"),
                "ef_zacks_rank":        zacks.get("rank") or zacks.get("zacks_rank"),
                "ef_earn_days":         c.get("earn_days") or c.get("days_to_earnings"),
            }
            # Pillar breakdown + raw fundamentals — signal_tracker reads these
            # via c.get("scoring_breakdown"). Without pass-through, every signal
            # lands with qg_score=None and fund_adequacy gate cannot be audited.
            _sb = c.get("scoring_breakdown") or {}
            _fund = c.get("fundamentals") or {}
            return {
                "ticker":      c.get("ticker", ""),
                "strategy":    plan.get("setup_type") or c.get("setup_family", "Core Swing"),
                "price":       c.get("price", 0) or 0,
                "stop":        plan.get("stop") or 0,
                "target1":     plan.get("target1") or 0,
                "rr":          plan.get("rr_ratio") or 0,
                "star_rating": c.get("star_rating", 0),
                "score":       c.get("score", 0),
                "rs_rank":     c.get("rs_rank") if c.get("rs_rank") is not None else ind.get("rs_rank", 0),
                "direction":   c.get("direction", "long" if verdict_label != "SHORT" else "short"),
                "verdict":     verdict_label,
                "mode":        mode_label,
                # Tier A — regime + setup + predictions (2026-05-04)
                **_scan_ctx,
                "conviction_label":     conv.get("label"),
                "entry_quality":        c.get("entry_quality"),
                "setup_family":         c.get("setup_family"),
                "tail_filter_demoted":  bool(conv.get("tail_filter_demoted")),
                "mc_p_profit":          mc.get("p_profit"),
                "mc_p_target_first":    mc.get("p_hit_target_first"),
                "mc_p_stop_first":      mc.get("p_hit_stop_first"),
                "fd_var_95_pct":        fd.get("var_95_pct"),
                "fd_cvar_975_pct":      fd.get("cvar_975_pct"),
                # Scoring breakdown — pass through so signal_tracker can persist
                # the per-pillar normalized scores (audit ranking flaws #16/#17).
                "scoring_breakdown":    _sb,
                # Raw fundamentals (for fund_adequacy gate audit — the existing
                # qg_score persists the normalized 0-5 value; this captures the
                # raw fund_score/fund_max ratio that the gate actually checks).
                "fund_score_raw":       _fund.get("score"),
                "fund_max":             _fund.get("max"),
                # Catalyst tier (used by the conditional fund_adequacy bypass).
                "catalyst_tier":        c.get("catalyst_tier"),
                # A6 (2026-05-09): entry-time feature suite for ML training corpus
                **entry_features,
            }
        # Swing-mode signals (this scan's primary output)
        #
        # 2026-05-18 · UPSTREAM FIX for rolling-Sharpe poisoning. Previously,
        # any ticker in `buy_candidates` was logged as verdict='BUY', even if
        # the conviction engine had downgraded it to WATCH (paper-only, no
        # sizing). Those WATCH-conviction signals then fed `rolling_sharpe_kill`
        # as if they were real BUYs and silently inflated the loss count.
        #
        # Now we reconcile: if conviction_label is WATCH, log as verdict=WATCH
        # regardless of which bucket the candidate landed in.
        def _resolve_verdict(c, default_label):
            conv = c.get("conviction") or {}
            cl = (conv.get("label") if isinstance(conv, dict) else None) or c.get("conviction_label") or ""
            return "WATCH" if str(cl).upper() == "WATCH" else default_label

        _signal_payload = (
            [_flatten_for_signal_log(c, _resolve_verdict(c, "BUY"),   "Swing") for c in buy_candidates] +
            [_flatten_for_signal_log(c, _resolve_verdict(c, "WATCH"), "Swing") for c in (watch_list or [])] +
            [_flatten_for_signal_log(c, _resolve_verdict(c, "SHORT"), "Swing") for c in (sell_candidates or [])]
        )
        # 2026-05-04: log Position + Invest BUYs from medium-/long-term re-scoring.
        # These come from analysis.score_medium_term and analysis.score_long_term — both
        # are computed after the swing pipeline and held on the candidate. If they exist
        # AND verdict is BUY at that horizon, log them as separate entries.
        for c in buy_candidates + (watch_list or []):
            _mt = c.get("medium_term") or {}
            _lt = c.get("long_term")   or {}
            _mt_v = (_mt.get("verdict") or "").upper()
            _lt_v = (_lt.get("verdict") or "").upper()
            if _mt_v == "BUY":
                _signal_payload.append(_flatten_for_signal_log(c, "BUY", "Position"))
            if _lt_v == "BUY":
                _signal_payload.append(_flatten_for_signal_log(c, "BUY", "Invest"))
        log_signals(_signal_payload, run_date=run_date)
    except Exception as e:
        log.warning(f"signal_tracker.log_signals failed: {e}")

    # Refresh MTM / MAE / MFE for older open picks
    try:
        from signal_tracker import update_outcomes
        update_outcomes()
    except Exception as e:
        log.warning(f"signal_tracker.update_outcomes failed: {e}")

    # Step 7b: Social signals (nitter.net RSS — cached 1h)
    log.info("Step 7b: Fetching social signals...")
    try:
        social_signals_data = get_social_signals()
        log.info(f"  Social: {social_signals_data.get('active_handles', 0)} handles, "
                 f"{social_signals_data.get('total_tickers', 0)} tickers")
    except Exception as e:
        log.warning(f"  Social signals failed: {e}")
        social_signals_data = {}

    # Check WATCH triggers
    from tracker import check_watch_triggers, update_score_history
    _cur_prices = {r["ticker"]: r.get("price", 0) for r in all_results}
    watch_trigger_hits = check_watch_triggers(_cur_prices)
    if watch_trigger_hits:
        log.info(f"  WATCH triggers fired: {[w['ticker'] for w in watch_trigger_hits]}")
    update_score_history(all_results, run_date)

    # Step 7c: Pre-analyze strategy scanner picks so Full Analysis never shows partial data
    log.info("Step 7c: Pre-analyzing strategy scanner picks...")
    _existing_tickers = set(r["ticker"] for r in all_results)
    _strategy_tickers = set()
    try:
        from weekly_pullback import scan_weekly_pullback
        for c in scan_weekly_pullback():
            if c.get("trade_plan", {}).get("rr_ratio", 0) >= 1.0:
                _strategy_tickers.add(c["ticker"])
    except Exception:
        pass
    try:
        from mean_reversion import scan_mean_reversion
        for c in scan_mean_reversion():
            _strategy_tickers.add(c["ticker"])
    except Exception:
        pass

    _need_analyze = _strategy_tickers - _existing_tickers
    if _need_analyze:
        log.info(f"  {len(_need_analyze)} strategy picks need full analysis: {list(_need_analyze)[:10]}")
        from concurrent.futures import ThreadPoolExecutor as _TPE2, as_completed as _ac
        def _analyze_one(t):
            try:
                if t not in market_data:
                    return None
                return analyze_ticker(t, market_data[t], info_map.get(t, {}),
                                      regime, earnings_map.get(t, {}), {}, {},
                                      spy_close, config,
                                      weekly_df=weekly_data.get(t),
                                      sector_etf_data=sector_etf,
                                      finviz=finviz_map.get(t, {}))
            except Exception:
                return None

        with _TPE2(max_workers=4) as pool:
            futs = {pool.submit(_analyze_one, t): t for t in _need_analyze}
            for f in _ac(futs):
                t = futs[f]
                r = f.result()
                if r and r.get("score", 0) > 0:
                    r["ticker_source"] = ticker_sources.get(t, "strategy")
                    all_results.append(r)
        log.info(f"  Pre-analyzed: {len(all_results) - len(_existing_tickers)} added to universe")

    # Step 8: Generate HTML
    log.info("Step 8: Generating HTML dashboard...")
    stats        = compute_stats()
    full_history = get_full_history()
    mtm_data     = mark_to_market()
    setup_stats  = compute_stats_by_setup()
    log.info(f"  Mark-to-market: {len(mtm_data)} picks tracked | "
             f"Setup breakdown: {len(setup_stats.get('by_setup', {}))} setup types, "
             f"{setup_stats.get('total_trades', 0)} completed trades")
    portfolio_summary = get_portfolio_summary()
    refresh_prices()  # update open position P&L

    # Crypto scan — fast (~3–5s), runs in parallel with nothing
    try:
        crypto_data = run_crypto_scan()
        log.info(f"  Crypto: {crypto_data.get('total_passed', 0)} coins passed / "
                 f"top pick score {crypto_data['top_picks'][0]['score'] if crypto_data.get('top_picks') else 0}")
    except Exception as _ce:
        log.warning(f"  Crypto scan failed (non-fatal): {_ce}")
        crypto_data = {}

    # ── Data Health Audit ──────────────────────────────────────────────────
    _n_res = len(all_results)
    def _pct(count): return round(count / max(_n_res, 1) * 100, 1)
    _dh_checks = []
    def _dh(label, source, count, total, threshold_warn=50, threshold_fail=20):
        pct = round(count / max(total, 1) * 100, 1)
        status = "ok" if pct >= threshold_warn else "warn" if pct >= threshold_fail else "fail"
        _dh_checks.append({"label": label, "source": source, "available": count,
                           "total": total, "pct": pct, "status": status})
    _dh("Polygon News NLP", "Polygon", sum(1 for r in all_results if r.get("news_sentiment_score", {}).get("score") is not None), _n_res, threshold_warn=30)
    _dh("Insider Activity", "SEC/OpenInsider", sum(1 for r in all_results if (r.get("insider_data") or {}).get("buys", 0) + (r.get("insider_data") or {}).get("sells", 0) > 0), _n_res)
    _dh("Short Interest", "Finviz/Borrow", sum(1 for r in all_results if r.get("sentiment", {}).get("details", {}).get("short_interest", "N/A") != "N/A (0/2)"), _n_res)
    _dh("IV Rank", "Schwab options", sum(1 for r in all_results if (r.get("options_data") or {}).get("iv_rank") is not None or (r.get("options_kpis") or {}).get("iv_rank") is not None or (r.get("options_kpis") or {}).get("iv_percentile") is not None), _n_res)
    _dh("Beat Rate", "yfinance (tier-1)", sum(1 for r in all_results if (r.get("beat_rate") or {}).get("beat_rate") is not None), _n_res)
    _dh("Sector", "Polygon/Schwab", sum(1 for r in all_results if r.get("sector") not in (None, "Unknown", "")), _n_res)
    _dh("Beta", "Finviz/yfinance", sum(1 for r in all_results if r.get("beta") is not None), _n_res)
    _dh("Valuation (PEG)", "Finviz/yfinance", sum(1 for r in all_results if "(0/5)" not in str(r.get("fundamentals", {}).get("details", {}).get("valuation", "(0/5)"))), _n_res)
    _dh("Analyst Revisions", "Finviz scrape", sum(1 for r in all_results if (r.get("analyst") or {}).get("total_analysts", 0) > 0 or (r.get("analyst") or {}).get("target_mean") is not None), _n_res)
    _dh("Estimate Revision", "Finviz EPS", sum(1 for r in all_results if r.get("extra_fund", {}).get("estimate_revision")), _n_res)
    _dh("Weekly OHLCV", "Polygon", sum(1 for r in all_results if r.get("scoring_breakdown", {}).get("bonus_total", 0) != 0), _n_res, threshold_warn=30)
    _dh("Quote Snapshot", "Schwab L1", sum(1 for r in all_results if r.get("quote_snapshot")), _n_res)
    _dh("Finnhub Data", "Finnhub", sum(1 for r in all_results if r.get("finnhub") and len(r["finnhub"]) > 3), _n_res)
    _dh("FMP Data", "FMP", sum(1 for r in all_results if r.get("fmp") and len(r["fmp"]) > 3), _n_res)
    _dh("SMC Zones", "Polygon OHLCV", sum(1 for r in all_results if r.get("smc", {}).get("score", 0) != 0), _n_res, threshold_warn=30)
    data_health = {
        "checks": _dh_checks,
        "ok_count": sum(1 for c in _dh_checks if c["status"] == "ok"),
        "warn_count": sum(1 for c in _dh_checks if c["status"] == "warn"),
        "fail_count": sum(1 for c in _dh_checks if c["status"] == "fail"),
        "total_checks": len(_dh_checks),
        "timestamp": run_timestamp,
    }
    log.info(f"  Data Health: {data_health['ok_count']}/{data_health['total_checks']} OK, "
             f"{data_health['warn_count']} WARN, {data_health['fail_count']} FAIL")

    # Auto-fix: clear stale caches for FAIL sources so next scan gets fresh data
    _fail_labels = {c["label"] for c in _dh_checks if c["status"] == "fail"}
    if _fail_labels:
        import glob as _gl
        _cleared = 0
        _cache_map = {
            "IV Rank": "cache/_cache_options_*",
            "Beat Rate": "cache/_cache_finnhub_*",
            "Analyst Revisions": "cache/_cache_finnhub_*",
            "Insider Activity": "cache/_cache_insider_*",
            "Polygon News NLP": "cache/_cache_polygon_news_*",
            "Beta": "cache/_cache_finviz_*",
            "Valuation (PEG)": "cache/_cache_finviz_*",
        }
        _cleared_patterns = set()
        for label in _fail_labels:
            pattern = _cache_map.get(label)
            if pattern and pattern not in _cleared_patterns:
                for f in _gl.glob(str(BASE_DIR / pattern)):
                    try:
                        os.remove(f)
                        _cleared += 1
                    except Exception:
                        pass
                _cleared_patterns.add(pattern)
        if _cleared:
            log.warning(f"  Data Health auto-fix: cleared {_cleared} stale cache files for {_fail_labels}")

    # ── Horizon scoring (1-3 month + long-term) ──────────────────────────
    # Scores the FULL post-price-filter universe (all_results + killed), not
    # just BUY/WATCH, because medium/long-term picks are often boring stable
    # names that the short-term pre-trade gate rejects (low RVOL, no catalyst).
    log.info("Step 6d: Scoring horizon picks (1-3 month + long-term)...")
    from analysis import score_medium_term, score_long_term, apply_position_gates
    # Held-position lookup for ADD signal (Position pyramid stream)
    _held_set = set()
    try:
        from portfolio_tracker import _load_state as _load_pf
        _pf = _load_pf()
        _held_set = {p.get("ticker", "").upper() for p in (_pf.get("positions") or [])}
    except Exception:
        pass
    horizon_pool = all_results + killed
    _mt_buy = _mt_add = _mt_watch = _mt_avoid = 0
    _lt_pass = 0
    for r in horizon_pool:
        t = r.get("ticker")
        if not t:
            continue
        # Explicit None check — `x or y` on a DataFrame raises
        # "truth value of DataFrame is ambiguous".
        df = qualified.get(t)
        if df is None:
            df = market_data.get(t)
        info = infos.get(t, {})
        sf = get_schwab_fundamentals(t)
        w_df = weekly_data.get(t)
        try:
            mt_raw = score_medium_term(df, info, sf, w_df, sector_etf_data, spy_data)
            # Apply Phase-1 hard + soft gates (P1.1, P1.2 from feedback)
            mt = apply_position_gates(mt_raw, r, cfg, weekly_df=w_df,
                                       is_held=(t.upper() in _held_set))
        except Exception as _e:
            mt = {"score": 0, "verdict": "AVOID", "gate_status": "error",
                  "gate_reasons": [str(_e)], "breakdown": {"error": str(_e)}}
        # P1.5 — Invest universe filter: mcap ≥ $5B + positive FCF + ROIC ≥ 10
        # + D/E ≤ 200 + listed ≥ 5y. Tickers failing universe → AVOID immediately
        # (don't even score — saves cycles + prevents momentum-biased Invest picks).
        try:
            inv_mcap = (info.get("market_cap") or info.get("marketCap")
                        or (sf.get("_market_cap")) or 0)
            inv_fcf = sf.get("free_cash_flow") or sf.get("fcf_ttm")
            inv_roic = sf.get("roic") or sf.get("roi")  # roi as fallback
            inv_de = sf.get("debt_equity")
            invest_universe_pass = True
            invest_universe_reasons = []
            if inv_mcap and inv_mcap < 5_000_000_000:
                invest_universe_pass = False
                invest_universe_reasons.append(f"mcap ${inv_mcap/1e9:.1f}B < $5B")
            if inv_fcf is not None and inv_fcf < 0:
                invest_universe_pass = False
                invest_universe_reasons.append(f"FCF negative ({inv_fcf})")
            if inv_roic is not None and inv_roic < 10:
                invest_universe_pass = False
                invest_universe_reasons.append(f"ROIC {inv_roic} < 10")
            if inv_de is not None and inv_de > 200:
                invest_universe_pass = False
                invest_universe_reasons.append(f"D/E {inv_de} > 200")
            if not invest_universe_pass:
                lt = {"score": 0, "verdict": "AVOID", "gate_pass": False,
                      "breakdown": {"invest_universe_fail": invest_universe_reasons}}
            else:
                lt = score_long_term(df, info, sf, finviz_bulk.get(t), sector_etf_data)
        except Exception as _e:
            lt = {"score": 0, "verdict": "AVOID", "breakdown": {"error": str(_e)}}
        r["medium_term"] = mt
        r["long_term"]   = lt
        v = mt.get("verdict")
        if v == "BUY":   _mt_buy += 1
        elif v == "ADD": _mt_add += 1
        elif v == "WATCH": _mt_watch += 1
        else: _mt_avoid += 1
        if lt.get("verdict") in ("BUY", "WATCH"): _lt_pass += 1
    log.info(f"  Position gated: BUY={_mt_buy} ADD={_mt_add} WATCH={_mt_watch} AVOID={_mt_avoid} (rate {_mt_buy*100//max(1,len(horizon_pool))}%) | LT BUY/WATCH={_lt_pass}")

    # Build top 10 picks per horizon — full result dicts with horizon
    # score/verdict overlaid at the top level so _signal_row (html_generator)
    # renders them with the same visual design as Short-term picks.
    def _top_horizon(key: str, n: int = 10) -> list:
        qualifying = [
            r for r in horizon_pool
            if (r.get(key) or {}).get("verdict") in ("BUY", "WATCH")
        ]
        qualifying.sort(key=lambda r: (r.get(key) or {}).get("score") or 0, reverse=True)
        out = []
        for r in qualifying[:n]:
            horizon = r.get(key) or {}
            horizon_verdict = horizon.get("verdict", "WATCH")
            # Shallow clone r and overlay horizon score + verdict — these are
            # what _signal_row reads (r["score"] and r["decision"]["verdict"]).
            # Preserve all other scoring fields (technicals, plan, fundamentals)
            # so the card renders with full detail.
            pick = dict(r)
            pick["score"] = horizon.get("score") or 0
            orig_decision = dict(r.get("decision") or {})
            orig_decision["verdict"] = horizon_verdict
            orig_decision["horizon_reason"] = f"{key.replace('_',' ')} BUY/WATCH — score {horizon.get('score')}"
            pick["decision"] = orig_decision
            pick["horizon_score"]   = horizon.get("score")
            pick["horizon_verdict"] = horizon_verdict
            pick["horizon_breakdown"] = horizon.get("breakdown", {})
            pick["horizon_key"] = key
            out.append(pick)
        return out

    medium_term_picks = _top_horizon("medium_term", 10)
    long_term_picks   = _top_horizon("long_term",   10)
    log.info(f"  Top 10 medium-term: {[p['ticker'] for p in medium_term_picks]}")
    log.info(f"  Top 10 long-term:   {[p['ticker'] for p in long_term_picks]}")

    # Live Options Flow — institutional UOA imbalance scanner. Returns top 30
    # tickers by call/put dollar-volume imbalance, ranked STRONG > MODERATE > WEAK.
    # Surfaced in V2 dashboard as a separate panel for "smart money following"
    # entry triggers. (2026-05-07 — wired from previously orphan options_flow_scanner.)
    options_flow_top30: list = []
    try:
        from options_flow_scanner import scan as _options_flow_scan, scan_broader as _options_flow_scan_broader
        # Build the (price, fundamentals) sidecars from all_results — already enriched.
        _flow_prices = {r.get("ticker"): r.get("price") for r in all_results
                        if r.get("ticker") and r.get("price")}
        _flow_funds = {}
        for r in all_results:
            t = r.get("ticker")
            if not t:
                continue
            _flow_funds[t] = {
                "sector": r.get("sector") or "Unknown",
                "days_to_earnings": ((r.get("earnings") or {}).get("days_to_earnings")
                                     if isinstance(r.get("earnings"), dict) else None),
            }
        _flow_all = _options_flow_scan(options_iv_data, _flow_prices, _flow_funds)
        options_flow_top30 = _flow_all[:30]
        # Broader scan: bullish + bearish, looser thresholds; powers Top-50 tab
        try:
            _flow_broader = _options_flow_scan_broader(options_iv_data, _flow_prices, _flow_funds)
            options_flow_top50 = _flow_broader[:50]
            log.info(f"  Live Options Flow (BROADER): {len(_flow_broader)} candidates · top 50 taken")
        except Exception as _br_err:
            log.warning(f"  Options-flow broader scan failed: {_br_err}")
            options_flow_top50 = _flow_all[:50]
        if options_flow_top30:
            _strong = sum(1 for x in options_flow_top30 if x.get("status") == "STRONG")
            _mod    = sum(1 for x in options_flow_top30 if x.get("status") == "MODERATE")
            log.info(f"  Live Options Flow: {len(options_flow_top30)} candidates "
                     f"(STRONG={_strong}, MODERATE={_mod}); top: "
                     f"{[(x['ticker'], x['status']) for x in options_flow_top30[:5]]}")
        else:
            log.info("  Live Options Flow: 0 candidates (no UOA imbalance detected)")
    except Exception as _of_err:
        log.warning(f"  Live Options Flow scan failed: {_of_err}")
        options_flow_top30 = []
        options_flow_top50 = []

    bundle = {
        "run_date":         run_date,
        "run_timestamp":    run_timestamp,
        "regime":           regime,
        "data_health":      data_health,
        "buy_candidates":   buy_candidates,
        "sell_candidates":  sell_candidates,
        "near_short_blocked": near_short_blocked,
        "watch_list":       watch_list,
        "all_scored":       all_results,
        "killed":           killed,
        "options_flow_top30": options_flow_top30,
        "options_flow_top50": options_flow_top50,
        "medium_term_picks": medium_term_picks,
        "long_term_picks":   long_term_picks,
        "extended_leaders": extended_leaders,
        "industries":       industries,
        "zacks_tab":        zacks_tab,
        "zacks_r1_full":    zacks_r1,
        "zacks_r1_missing": zacks_r1_missing,
        "zacks_r1_scores":  zacks_r1_scores,
        "ultimate":         ultimate_data,
        "tazr":             tazr_data,
        "bbt":              bbt_data,
        "counterstrike":    cs_data,
        "headlinetrader":   ht_data,
        "alt_energy":       alt_energy_data,
        "blockchain":       blockchain_data,
        "tech_innovators":  tech_innov_data,
        # Phase 2 — 5 new services
        "surprise_trader":   surprise_data,
        "insider_trader":    insider_t_data,
        "value_investor":    value_inv_data,
        "home_run_investor": homerun_data,
        "income_investor":   income_inv_data,
        "sector_etf_data":  sector_etf_data,
        "price_tier_results": price_tier_results,
        "market_breadth":   market_breadth,
        "macro_signals":    macro_signals,
        "fear_greed":       fear_greed_data,
        "watch_trigger_hits": watch_trigger_hits,
        "portfolio_risk":   portfolio_risk,
        "portfolio":        portfolio_summary,
        "stats":            stats,
        "full_history":     full_history,
        "mtm_data":         mtm_data,
        "setup_stats":      setup_stats,
        "config":           cfg,
        "total_scanned":    total_scanned,
        "total_passed":     len(all_results),
        "social_signals":   social_signals_data,
        "sp500_list":       sp500,
        "russell1000_list": russell1000,
        "russell2000_list": russell2000,
        "zacks_sell_list":  zacks_data.get("zacks_sell_list", []),
        "index_picks":      index_picks,
        "gmail_zacks":      gmail_data,
        "crypto":           crypto_data,
        "ticker_sources":   ticker_sources,
    }

    # Harmless default — the suppression banner renderer short-circuits to an
    # (invisible) placeholder when empty, but the dict needs to exist so the
    # key is always present in persisted bundles.
    bundle.setdefault("suppression", {})

    # Phase A (2026-05-08): legacy cache/dashboard.html generation retired —
    # V2 (infra/prototype/) is the only authoritative dashboard. Saves ~30-60s
    # of scan time and removes the dual-truth-source confusion. The
    # html_generator.build_dashboard() call previously lived here.
    # html_path kept defined so downstream references (logging, email,
    # function return) don't NameError. send_dashboard_email already handles
    # 'file does not exist' gracefully (warns + returns).
    output_path = BASE_DIR / cfg.get("output", {}).get("html_output", "cache/dashboard.html")
    html_path = output_path

    # P2.21/2.22/2.23 — Populate system_status BEFORE bundle write (so v2 reads it)
    bundle.setdefault("system_status", {})
    # Forced cash rule
    _total_buys = len(buy_candidates) + len(near_short_blocked) + sum(
        1 for r in (all_results + killed) if (r.get("medium_term") or {}).get("verdict") == "BUY"
    )
    bundle["system_status"]["forced_cash"] = (
        {"active": True, "reason": "No setups passed gates across any mode",
         "guidance": "Cash is a valid position. Wait for setups to qualify rather than lowering standards.",
         "checked_at": datetime.now().isoformat()}
        if _total_buys == 0 else {"active": False}
    )
    # Circuit breaker
    try:
        from portfolio_tracker import check_circuit_breaker as _cb
        bundle["system_status"]["circuit_breaker"] = _cb()
    except Exception:
        bundle["system_status"]["circuit_breaker"] = {"active": False, "level": "normal"}
    # Macro calendar — respect config flag macro_blackout_morning_after (default False).
    # Previously hardcoded morning_after=True which silently blocked all BUYs the day
    # after every CPI/FOMC/NFP/PCE print (config flag was being ignored). 2026-05-14 fix.
    try:
        import macro_calendar as _mc
        _morning_after = bool((cfg.get("gates") or {}).get("macro_blackout_morning_after", False))
        _macro_blocked, _macro_reason = _mc.is_macro_blackout(morning_after=_morning_after)
        bundle["system_status"]["macro_calendar"] = {
            "blackout_today": _macro_blocked,
            "blackout_reason": _macro_reason,
            "next_event": _mc.next_macro_event(),
            "_morning_after_enabled": _morning_after,
        }
    except Exception:
        bundle["system_status"]["macro_calendar"] = {"blackout_today": False}

    # ── PRE-FOMC DRIFT overlay (2026-05-14, docs/strategy_prefomc_drift.md) ──
    # Lucca-Moench 2015: SPY drifts up 24h pre-FOMC. Multiply BUY sizing by
    # size_boost_mult on the trading day immediately before scheduled FOMC.
    try:
        _prefomc_cfg = (cfg.get("prefomc_drift_overlay") or {})
        _prefomc_active = False
        _prefomc_status = {"active": False, "fomc_date": None, "applied_to_n_buys": 0}
        if _prefomc_cfg.get("_enabled", True):
            import macro_calendar as _mc_pf
            from datetime import date as _date, timedelta as _td
            today_d = _date.today()
            # Check if tomorrow (or next trading day) is FOMC
            for _delta in (1, 2, 3):  # skip weekends — check up to 3 days
                _check_d = today_d + _td(days=_delta)
                _blocked, _reason = _mc_pf.is_macro_blackout(date=_check_d, morning_after=False)
                if _blocked and "FOMC" in (_reason or ""):
                    # Find which FOMC date
                    for _ev in _mc_pf._MACRO_EVENTS_2026:
                        if _ev.get("type") == "FOMC" and _ev.get("date") == _check_d.isoformat():
                            _prefomc_active = True
                            _prefomc_status["fomc_date"] = _ev["date"]
                            _prefomc_status["trading_days_until"] = _delta
                            break
                    break
            if _prefomc_active:
                _boost = float(_prefomc_cfg.get("size_boost_mult", 1.25))
                _apply_long = bool(_prefomc_cfg.get("apply_to_long_only", True))
                _n_applied = 0
                for _r in bundle.get("buy_candidates") or []:
                    if not isinstance(_r, dict):
                        continue
                    if _apply_long and _r.get("direction") == "short":
                        continue
                    _sm = float(_r.get("sizing_multiplier") or 1.0)
                    _r["sizing_multiplier"] = round(_sm * _boost, 3)
                    _r["_prefomc_boost_applied"] = _boost
                    _n_applied += 1
                _prefomc_status["active"] = True
                _prefomc_status["size_boost_mult"] = _boost
                _prefomc_status["applied_to_n_buys"] = _n_applied
                _prefomc_status["mechanism_note"] = "Lucca-Moench 2015 — pre-FOMC drift"
                log.info(f"  PRE-FOMC DRIFT ACTIVE: boosted {_n_applied} BUYs by {_boost}× "
                         f"(FOMC {_prefomc_status['fomc_date']})")
        bundle["system_status"]["prefomc_drift"] = _prefomc_status
    except Exception as _pf_err:
        log.debug(f"prefomc_drift overlay skipped: {_pf_err}")
        bundle["system_status"]["prefomc_drift"] = {"active": False, "error": str(_pf_err)}

    # ── Phase 3: Cross-sectional sector ranking ──────────────────────────
    # For each sector with enough candidates, compute percentile rank by score
    # within sector. Optionally demote BUY → WATCH for candidates below the
    # configured percentile threshold. Forces relative-strength selection vs
    # absolute score floor.
    try:
        _sr_cfg = cfg.get("sector_relative_ranking") or {}
        if _sr_cfg.get("_enabled", True):
            _min_n = int(_sr_cfg.get("min_candidates_per_sector_for_ranking", 3))
            _pct_threshold = float(_sr_cfg.get("min_sector_percentile_for_buy", 60.0))
            _demote = bool(_sr_cfg.get("demote_to_watch_below_threshold", True))
            # Group all results by sector
            from collections import defaultdict as _dd
            _by_sector = _dd(list)
            for _r in all_results:
                _sec = _r.get("sector") or "Unknown"
                _by_sector[_sec].append(_r)
            _ranked, _demoted = 0, 0
            for _sec, _rows in _by_sector.items():
                if len(_rows) < _min_n:
                    # Not enough candidates in sector — skip ranking
                    for _r in _rows:
                        _r["sector_pct_rank"] = None
                        _r["sector_rank_skipped"] = "insufficient_candidates"
                    continue
                _scores_sorted = sorted(_rows, key=lambda x: float(x.get("score", 0)))
                _n = len(_scores_sorted)
                for _idx, _r in enumerate(_scores_sorted):
                    _pct = (_idx / max(1, _n - 1)) * 100  # 0=lowest, 100=highest in sector
                    _r["sector_pct_rank"] = round(_pct, 1)
                    _r["sector_n"] = _n
                    _ranked += 1
                    # Demote BUY below threshold to WATCH
                    if _demote and _r.get("decision", {}).get("verdict") == "BUY" and _pct < _pct_threshold:
                        _r["decision"]["verdict"] = "WATCH"
                        _r.setdefault("decision", {})["sector_demotion_reason"] = (
                            f"sector_pct_rank {_pct:.0f}% < threshold {_pct_threshold:.0f}% in {_sec}"
                        )
                        _demoted += 1
            log.info(f"  Sector ranking: ranked {_ranked} candidates across {len(_by_sector)} sectors, "
                     f"demoted {_demoted} BUY→WATCH for below-sector-percentile {_pct_threshold:.0f}%")
            # Re-filter buy_candidates after demotion
            if _demote and _demoted > 0:
                buy_candidates = [r for r in buy_candidates if r.get("decision", {}).get("verdict") == "BUY"]
                bundle["system_status"]["sector_ranking_demotions"] = _demoted
    except Exception as _sr_e:
        log.warning(f"Sector ranking step failed (skipped, no impact): {_sr_e}")

    # ─────────────────────────────────────────────────────────────────────────
    # Decision engine — single source of truth for verdicts.
    # Per 2026-05-06 architecture review: 7 independent verdict engines were
    # disagreeing (AVT case). compute_final_verdict() is the AND-gate cascade
    # that overwrites every ticker's verdict before bundle write.
    # ─────────────────────────────────────────────────────────────────────────
    try:
        from decision_engine import (compute_final_verdict, compute_setup_kill_list,
                                       compute_setup_size_multipliers, compute_setup_score_band_kills,
                                       compute_regime_confidence_modifier)
        # Load config defensively — variable name varies (config/cfg) across scopes
        try:
            import json as _json
            _de_cfg = _json.loads((BASE_DIR / "config" / "config.json").read_text())
        except Exception:
            _de_cfg = {}
        _cfg_thr = _de_cfg.get("regime4_thresholds")
        _bundle_regime = (bundle.get("regime") or {}).get("regime4") or "risk_on_choppy"
        # Phase 3.2: compute live setup-kill list from signal_tracker (auto-prune losing setups)
        # PORTFOLIO-DECOUPLE (2026-06-07): compute_setup_kill_list / band_kills read the
        # owner's signal_log. For a universal 500-user signal layer they must not shape the
        # signal — skip when signal_layer_portfolio_blind is on. See config _note.
        _portfolio_blind = bool((_de_cfg.get("signal_layer_portfolio_blind") or {}).get("_enabled", False))
        # KILL->LABEL (2026-06-11): when signal_edge_labeling.mode == "label", the
        # setup-kill list + score-band kills must NOT block the verdict — they become
        # informational labels instead. Feed the engine empty kill-lists so the
        # setup_performance hard-gate always passes; the weak-edge label rides on the
        # row via analysis.py edge_warning + edge_labels.py edge_tier.
        _edge_label_mode = str(
            ((_de_cfg.get("signal_edge_labeling") or {}).get("mode", "suppress"))
        ).lower() == "label"
        if _portfolio_blind or _edge_label_mode:
            _setup_kills = {}
            _setup_band_kills = {}
            _why_skip = "PORTFOLIO-BLIND" if _portfolio_blind else "EDGE-LABEL mode"
            log.info(f"  Signal layer {_why_skip}: setup kills not used to block (label/blind)")
        else:
            _setup_kills = compute_setup_kill_list()
            # #7: stratified — also kill specific (setup, score_band) combos
            _setup_band_kills = compute_setup_score_band_kills()
        if _setup_kills:
            log.info(f"  Decision engine: setup-kill list = {list(_setup_kills.keys())}")
        if _setup_band_kills:
            log.info(f"  Decision engine: stratified kill = {list(_setup_band_kills.keys())}")
        # Bug fix #2 (2026-05-06): wire system circuit breaker into verdict
        _sys_status = bundle.get("system_status") or {}
        _cb = _sys_status.get("circuit_breaker") or {}
        if _cb.get("active"):
            log.warning(f"  Decision engine: CIRCUIT BREAKER ACTIVE ({_cb.get('level')}) — "
                        f"all BUYs will be force-routed to WATCH/WAIT")
        # Task #3 + #8 + Tier 1C: per-setup multipliers, regime-conditional + HMM-confidence-weighted
        _setup_mults = compute_setup_size_multipliers(regime=_bundle_regime)
        # Tier 1C: HMM regime confidence further scales sizing.
        # Compute HMM here (same logic as build_data.py) — read SPY closes from market data
        try:
            import regime_hmm as _rh
            _md = bundle.get("regime") or {}
            _spy_close_series = []
            # Try to pull SPY closes from bundle's regime cache or fetch fresh
            from data_fetcher import fetch_market_data as _fmd
            _spy_data = _fmd(["SPY"], period="3mo").get("SPY")
            if _spy_data is not None and "Close" in _spy_data.columns:
                _spy_close_series = _spy_data["Close"].dropna().tolist()
            _hmm = _rh.regime_probabilities_from_closes(_spy_close_series, lookback=21) if _spy_close_series else {}
            _regime_conf_mult = compute_regime_confidence_modifier(_hmm)
            bundle["regime_confidence"] = {**_hmm, "size_modifier": _regime_conf_mult}
            if _regime_conf_mult != 1.0:
                # Apply to all setup multipliers: regime confidence is a portfolio-wide scalar
                _setup_mults = {k: round(v * _regime_conf_mult, 2) for k, v in _setup_mults.items()}
                log.info(f"  Decision engine: regime confidence modifier = {_regime_conf_mult} "
                         f"(p_bull={_hmm.get('p_bull')}, confidence={_hmm.get('confidence')})")
        except Exception as _hmm_e:
            log.debug(f"HMM regime confidence step skipped: {_hmm_e}")
            _regime_conf_mult = 1.0
        if _setup_mults:
            _nondefault = {s: m for s, m in _setup_mults.items() if m != 1.0}
            if _nondefault:
                log.info(f"  Decision engine: setup size multipliers (non-default) = {_nondefault}")

        # 2026-05-19 — Inject QQQ-SPY 21d momentum spread for momentum_condition_gate.
        # Required when config.momentum_condition_gate._enabled=true. Computed once
        # globally (market-level signal); attached to every ticker dict before
        # compute_final_verdict reads it.
        _mom_spread_pct = None
        try:
            _qqq_data = _fmd(["QQQ"], period="3mo").get("QQQ")
            if (_qqq_data is not None and "Close" in _qqq_data.columns
                    and _spy_data is not None and "Close" in _spy_data.columns):
                _qqq_c = _qqq_data["Close"].dropna()
                _spy_c = _spy_data["Close"].dropna()
                if len(_qqq_c) >= 22 and len(_spy_c) >= 22:
                    _qqq_21 = (_qqq_c.iloc[-1] / _qqq_c.iloc[-22] - 1) * 100
                    _spy_21 = (_spy_c.iloc[-1] / _spy_c.iloc[-22] - 1) * 100
                    _mom_spread_pct = round(float(_qqq_21 - _spy_21), 3)
                    log.info(f"  Decision engine: QQQ-SPY 21d momentum spread = {_mom_spread_pct:+.2f}%")
        except Exception as _ms_e:
            log.debug(f"QQQ-SPY momentum spread step skipped: {_ms_e}")

        # PHASE 2 (2026-06-11, audit docs/signal_screener_audit_2026_06_11.html) —
        # honest regime-conditional edge tier. INFORMATIONAL ONLY: attaches an
        # edge_tier badge (PROVEN/DEVELOPING/WEAK/UNPROVEN) to each row from the
        # realized track record. Never gates a verdict or zeroes a score.
        try:
            from edge_labels import lookup_edge as _edge_lookup
        except Exception:
            _edge_lookup = None
        try:
            from edge_labels import lookup_tier as _tier_lookup
        except Exception:
            _tier_lookup = None
        _edge_tiers_cfg = (_de_cfg.get("signal_edge_labeling") or {}).get("tiers")
        _edge_regime4 = (bundle.get("regime") or {}).get("regime4") or _bundle_regime

        _de_count = 0
        _de_failed = 0
        for _sec_key, _sec_val in bundle.items():
            if not (isinstance(_sec_val, list) and _sec_val
                    and isinstance(_sec_val[0], dict) and "ticker" in _sec_val[0]):
                continue
            for _row in _sec_val:
                if not isinstance(_row, dict):
                    continue
                # Inject runtime momentum spread for momentum_condition_gate
                if _mom_spread_pct is not None:
                    _row["_runtime_qqq_spy_momentum_21d"] = _mom_spread_pct
                _r = compute_final_verdict(_row, regime=_bundle_regime, thresholds=_cfg_thr,
                                           setup_kill_list=_setup_kills,
                                           setup_band_kill_list=_setup_band_kills,
                                           system_status=_sys_status,
                                           config=cfg)
                # PHASE 2 — attach honest edge tier (display + sort only).
                if _edge_lookup is not None:
                    try:
                        _et = _edge_lookup(_row.get("setup_family"), _edge_regime4,
                                           tiers=_edge_tiers_cfg)
                        if _et:
                            _row["edge_tier"] = _et
                    except Exception:
                        pass
                # RANK-REBUILD-2026-06-13 (part b) — empirical regime-conditional
                # grade for the a-priori tiers the audit found INVERTED. Honest
                # label only (display/sort/conviction); never relabels or gates.
                if _tier_lookup is not None:
                    try:
                        _cte = _tier_lookup("catalyst_tier", _row.get("catalyst_tier"),
                                            _edge_regime4, tiers=_edge_tiers_cfg)
                        if _cte:
                            _row["catalyst_tier_empirical"] = _cte
                        _eqe = _tier_lookup("entry_quality", _row.get("entry_quality"),
                                            _edge_regime4, tiers=_edge_tiers_cfg)
                        if _eqe:
                            _row["entry_quality_empirical"] = _eqe
                    except Exception:
                        pass
                # Task #3: write per-ticker setup size multiplier (dashboard reads this)
                _setup_name = _row.get("setup_family") or _row.get("setup") or _row.get("setup_type")
                _mult = _setup_mults.get(_setup_name) if _setup_name else None
                if _mult is not None:
                    _row["setup_size_multiplier"] = _mult
                    # Phase 4 / #14.3: wire multiplier into actual position sizing.
                    # Apply to kelly_size's monetary/share fields so live trade plans
                    # honor historical setup edge.
                    if _mult != 1.0:
                        _ks = _row.get("kelly_size")
                        if isinstance(_ks, dict):
                            for _fld in ("suggested_shares", "position_value", "final_alloc_pct", "dollar_risk"):
                                _v = _ks.get(_fld)
                                if isinstance(_v, (int, float)):
                                    _ks[_fld] = (round(_v * _mult, 0) if _fld == "suggested_shares"
                                                 else round(_v * _mult, 2))
                _row["verdict"] = _r["verdict"]
                _row["reject_reason"] = _r["reason"] if _r["verdict"] != "BUY" else ""
                _row["caveats"] = _r["caveats"]
                _row["gates_evaluated"] = _r["gates_evaluated"]
                # Two-axis verdict (2026-06-10): orthogonal bias × action × reason_class
                # so the UI never renders an action (AVOID) as a direction (Bearish).
                _row["bias"] = _r.get("bias")
                _row["action"] = _r.get("action")
                _row["reason_class"] = _r.get("reason_class")
                _dec = _row.setdefault("decision", {})
                if isinstance(_dec, dict):
                    _dec["verdict"] = _r["verdict"]
                    _dec["reason"]  = _r["reason"]
                    _dec["bias"]    = _r.get("bias")
                    _dec["action"]  = _r.get("action")
                    _dec["reason_class"] = _r.get("reason_class")
                _row["audit_trail"] = {
                    "ticker": _row.get("ticker"),
                    "verdict": _r["verdict"],
                    "reason":  _r["reason"],
                    "hard_gates_passed": all(g["passed"] for g in _r["gates_evaluated"]),
                    "gate_failures": [g["name"] for g in _r["gates_evaluated"] if not g["passed"]],
                    "caveats": _r["caveats"],
                    "decided_by": "decision_engine.compute_final_verdict",
                }
                # K6 (2026-05-09): attach single canonical trade plan AFTER verdict is final.
                # All dashboard tabs (Plan, Thesis, SMC, Models, Overview) bind to this dict
                # instead of computing their own. Per Vinod feedback: "SMC plan ≠ Overview plan",
                # "Bear case ≠ Plan/Thesis", "Thesis T1/T2 ≠ outlook" — root cause was each tab
                # had its own derivation. Now: one source, all tabs read it.
                try:
                    from canonical_trade_plan import attach_to_result
                    attach_to_result(_row, regime_thresholds=_cfg_thr)
                except Exception:
                    pass  # never break the scan due to canonical-plan attach
                _de_count += 1
                if _r["verdict"] != "BUY":
                    _de_failed += 1
        # Re-route buy_candidates: only keep verdict==BUY; rest move to watch_list
        _bc_orig = list(bundle.get("buy_candidates") or [])
        _new_buy   = [r for r in _bc_orig if isinstance(r, dict) and r.get("verdict") == "BUY"]
        _demoted   = [r for r in _bc_orig if isinstance(r, dict) and r.get("verdict") != "BUY"]
        if _demoted:
            _wl = list(bundle.get("watch_list") or [])
            _seen = {r.get("ticker") for r in _wl if isinstance(r, dict)}
            for _r in _demoted:
                if _r.get("ticker") not in _seen:
                    _wl.append(_r); _seen.add(_r.get("ticker"))
            bundle["watch_list"] = _wl
        # WATCH → BUY promotion (2026-05-14): scan watch_list for items the
        # decision engine just upgraded to BUY (e.g. PEAD signals that gained
        # bypasses for entry_quality, decision_state, fund_adequacy). Without
        # this sweep, a BUY-verdicted ticker stuck in watch_list never reaches
        # the dashboard's BUY tab.
        _wl_now = list(bundle.get("watch_list") or [])
        _bc_tickers = {r.get("ticker") for r in _new_buy if isinstance(r, dict)}
        _promoted = []
        _kept_wl = []
        for _r in _wl_now:
            if isinstance(_r, dict) and _r.get("verdict") == "BUY" and _r.get("ticker") not in _bc_tickers:
                _promoted.append(_r)
                _bc_tickers.add(_r.get("ticker"))
            else:
                _kept_wl.append(_r)
        if _promoted:
            _new_buy.extend(_promoted)
            bundle["watch_list"] = _kept_wl
            log.info(f"  Decision engine: PROMOTED {len(_promoted)} WATCH → BUY "
                     f"({', '.join(r.get('ticker') for r in _promoted)})")
        bundle["buy_candidates"] = _new_buy
        bundle["decision_engine_version"] = "1.0"
        log.info(f"  Decision engine: scored {_de_count} tickers, "
                 f"buy_candidates {len(_bc_orig)}→{len(_new_buy)} "
                 f"(rerouted {len(_demoted)} BUY→WATCH for failed gates) — survived: "
                 f"{[r.get('ticker') for r in _new_buy[:10]]}{' ...' if len(_new_buy) > 10 else ''}")
        # 2026-05-18: log which gate rejected each demoted ticker (visibility into decision_engine internals)
        if _demoted:
            from collections import Counter as _C
            _reasons = _C(((r.get('decision', {}).get('reason') or r.get('reject_reason') or 'no_reason')[:60]) for r in _demoted)
            log.info(f"  Decision engine demotion reasons: {dict(_reasons.most_common(5))}")
        # Silent-failure detection: engine ran but processed nothing.
        if _de_count == 0:
            log.error("❌ DECISION ENGINE: 0 tickers scored — bundle structure changed or empty?")
            bundle["decision_engine_failed"] = {
                "error": "engine ran but processed 0 tickers",
                "type": "ZeroTickers",
            }
            try:
                from alerts import send_alert
                send_alert(
                    level="CRITICAL",
                    title="Decision engine: 0 tickers scored",
                    body=("Engine ran but processed 0 tickers — bundle may be empty or structure changed. "
                          "V2 dashboard verdicts will be stale."),
                )
            except Exception:
                pass
        # #5: Sector concentration cap — no more than N BUYs per sector.
        # Excess BUYs (lowest score) demote to watch_list with cap reason.
        try:
            _sec_cap = int(_de_cfg.get("sector_concentration_cap", 3))
            if _sec_cap > 0 and len(bundle.get("buy_candidates") or []) > _sec_cap:
                from collections import defaultdict as _dd
                _by_sec: dict = _dd(list)
                for r in bundle.get("buy_candidates") or []:
                    if isinstance(r, dict):
                        _by_sec[r.get("sector") or "Unknown"].append(r)
                _kept: list = []
                _capped: list = []
                for _sec, _rows in _by_sec.items():
                    _rows.sort(key=lambda x: -(x.get("score") or 0))
                    _kept.extend(_rows[:_sec_cap])
                    for _r in _rows[_sec_cap:]:
                        _r["verdict"] = "WATCH"
                        _r["reject_reason"] = (f"Sector concentration cap: only top {_sec_cap} BUYs per sector "
                                                f"({_sec} had {len(_rows)})")
                        _dec = _r.setdefault("decision", {})
                        if isinstance(_dec, dict):
                            _dec["verdict"] = "WATCH"
                        _capped.append(_r)
                if _capped:
                    bundle["buy_candidates"] = _kept
                    _wl = list(bundle.get("watch_list") or [])
                    _seen = {x.get("ticker") for x in _wl if isinstance(x, dict)}
                    for _r in _capped:
                        if _r.get("ticker") not in _seen:
                            _wl.append(_r); _seen.add(_r.get("ticker"))
                    bundle["watch_list"] = _wl
                    log.info(f"  Sector cap (decision_engine): {len(_capped)} excess BUYs demoted "
                             f"(cap={_sec_cap} per sector) — tickers: {[r.get('ticker') for r in _capped]}")
                    # 2026-05-18: emit decision_log entries so the audit trail captures these silent demotions
                    try:
                        from decision_logger import log_decisions_batch
                        log_decisions_batch(_capped, scan_date=date.today().isoformat(), profile=cfg.get('_profile_name', 'sector_cap_demote'))
                    except Exception:
                        pass
        except Exception as _sc_e:
            log.warning(f"Sector concentration cap step failed (skipped): {_sc_e}")

        # #11: Portfolio-level position cap — DISABLED by default (2026-05-30).
        # It demoted valid BUY signals to WATCH purely because the OWNER's paper book was
        # near capacity — gating a multi-user informational signal by one user's slots
        # (violates project_unified_system_1k_to_1m + user-agency). The paper EXECUTOR
        # enforces its own max_positions independently (executor.py:225), so the BUY list
        # can stay complete without over-trading. Set decision_engine_portfolio_cap_enabled
        # =true in config.json to restore slot-based demotion.
        try:
            _cap_on = bool(_de_cfg.get("decision_engine_portfolio_cap_enabled", False))
            _max_open = int(_de_cfg.get("max_total_open_positions", 15))
            # Phase B.1 (2026-05-09): route through state_layer for cache + future Mode 2.
            _cur_open = 0
            try:
                from state_layer import load_portfolio_state
                _ps = load_portfolio_state()
                _cur_open = len(_ps.get("positions") or [])
            except Exception:
                _ps_path = BASE_DIR / "data" / "portfolio_state.json"
                if _ps_path.exists():
                    try:
                        _ps = json.loads(_ps_path.read_text())
                        _cur_open = len(_ps.get("positions") or [])
                    except Exception:
                        _cur_open = 0
            _slots = max(0, _max_open - _cur_open)
            _bcs = bundle.get("buy_candidates") or []
            if not _cap_on:
                log.info(f"  Portfolio cap: OFF — all {len(_bcs)} BUY candidate(s) kept "
                         f"({_cur_open} paper position(s) open; executor enforces max_positions "
                         f"independently). Set decision_engine_portfolio_cap_enabled=true to restore.")
            if _cap_on and len(_bcs) > _slots:
                _bcs.sort(key=lambda x: -(x.get("score") or 0))
                _kept = _bcs[:_slots]
                _excess = _bcs[_slots:]
                for _r in _excess:
                    _r["verdict"] = "WATCH"
                    _r["reject_reason"] = (f"Portfolio cap: {_cur_open}/{_max_open} positions open, "
                                            f"only {_slots} slot(s) available — top score(s) prioritized")
                    _dec = _r.setdefault("decision", {})
                    if isinstance(_dec, dict):
                        _dec["verdict"] = "WATCH"
                bundle["buy_candidates"] = _kept
                _wl = list(bundle.get("watch_list") or [])
                _seen = {x.get("ticker") for x in _wl if isinstance(x, dict)}
                for _r in _excess:
                    if _r.get("ticker") not in _seen:
                        _wl.append(_r); _seen.add(_r.get("ticker"))
                bundle["watch_list"] = _wl
                log.info(f"  Portfolio cap: {_cur_open} open, {_slots} slots → "
                         f"{len(_kept)} BUYs kept, {len(_excess)} demoted "
                         f"— excess: {[r.get('ticker') for r in _excess]}")
                # 2026-05-18: emit decision_log entries for portfolio-cap demotions too
                try:
                    from decision_logger import log_decisions_batch
                    log_decisions_batch(_excess, scan_date=date.today().isoformat(), profile=cfg.get('_profile_name', 'portfolio_cap_demote'))
                except Exception:
                    pass
        except Exception as _pc_e:
            log.warning(f"Portfolio cap step failed (skipped): {_pc_e}")

        # #13: Elite picks — top 5 BUYs by expected-value score
        # ev_score = ticker_score × setup_size_multiplier × forward_dist.fwd_sharpe
        try:
            _elite: list = []
            for _r in bundle.get("buy_candidates") or []:
                if not isinstance(_r, dict):
                    continue
                _sc = float(_r.get("score") or 0)
                _sm = _r.get("setup_size_multiplier") or 1.0
                _fd = _r.get("forward_dist") or {}
                _shp = float(_fd.get("fwd_sharpe") or 1.0)
                # composite EV score; clamp sharpe to avoid blowups
                _ev = _sc * _sm * max(0.5, min(_shp, 3.0))
                _elite.append({
                    "ticker": _r.get("ticker"),
                    "score": _sc,
                    "size_mult": _sm,
                    "fwd_sharpe": _shp,
                    "ev_score": round(_ev, 1),
                    "setup": _r.get("setup_family") or _r.get("setup"),
                    "p_profit": _fd.get("p_profit"),
                    "median_pct": _fd.get("p50_pct"),
                })
            _elite.sort(key=lambda x: -x["ev_score"])
            bundle["elite_picks"] = _elite[:5]
            if _elite[:5]:
                log.info(f"  Elite picks: {[e['ticker'] for e in _elite[:5]]}")
        except Exception as _ep_e:
            log.warning(f"Elite picks step failed (skipped): {_ep_e}")
    except Exception as _de_e:
        # Engine failure is a P0 — would silently emit stale verdicts to dashboard.
        # Log loud, send Mac notification, and persist a flag in the bundle so
        # downstream consumers (dashboard, V2 builder) can show a banner.
        log.error(f"❌ DECISION ENGINE FAILED: {_de_e}", exc_info=True)
        bundle["decision_engine_failed"] = {
            "error": str(_de_e),
            "type": type(_de_e).__name__,
            "scan_run": str(run_date) if "run_date" in dir() else "",
        }
        try:
            from alerts import send_alert
            send_alert(
                level="CRITICAL",
                title="Decision engine FAILED",
                body=(f"Engine crashed: {type(_de_e).__name__}: {str(_de_e)[:200]}. "
                      f"Scan continued but verdicts may be stale. Check cache/logs/scan_*.log."),
            )
        except Exception:
            pass

    # Persist bundle for fast re-render (html_generator changes, no re-scan needed).
    # Write atomically via a .tmp + rename so a failed write never leaves a truncated file,
    # and surface errors at warning level so silent skips are visible.
    try:
        bundle_path = BASE_DIR / "cache" / "last_bundle.json"
        tmp_path    = bundle_path.with_suffix(".json.tmp")
        with open(tmp_path, "w") as _bf:
            json.dump(bundle, _bf, default=str)
        os.replace(tmp_path, bundle_path)
    except Exception as _be:
        log.warning(f"last_bundle.json write failed: {_be}")

    # Audit-trail meta write — records "what did the last successful scan
    # find" in Supabase public.meta. Cheap (single upsert), never raises
    # (safe_upsert returns False on failure), gives a queryable cross-session
    # audit trail without scraping log files. Added 2026-05-11 alongside the
    # 0022_meta migration that created the table.
    try:
        import subprocess
        from supabase_client import safe_upsert as _sb_upsert
        try:
            _git_sha = subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=str(BASE_DIR), stderr=subprocess.DEVNULL,
                timeout=2
            ).decode().strip()
        except Exception:
            _git_sha = None
        _meta_payload = {
            "scan_at":       run_timestamp,
            "run_date":      run_date,
            "regime":        (regime.get("regime4") if isinstance(regime, dict) else regime) or "unknown",
            "buy_count":     len(buy_candidates or []),
            "watch_count":   len(watch_list or []),
            "short_count":   len(sell_candidates or []),
            "killed_count":  len(killed or []),
            "scan_count":    len(all_results or []),
            "git_sha":       _git_sha,
        }
        _sb_upsert("meta", {"key": "last_scan", "value": _meta_payload}, on_conflict="key")
    except Exception as _me:
        log.debug(f"meta upsert skipped (non-fatal): {_me}")

    # Mirror the full scan into Supabase (analysis-domain tables) — BACKGROUND (#2 perf).
    # The ~12-min normalized write used to block the dashboard / options-flow / notification.
    # Run it in a NON-daemon thread: it overlaps the remaining post-bundle steps and the
    # process still waits for it before exiting (guaranteed completion; uses the correct
    # in-memory bundle — no stale-file risk). Non-fatal: errors logged, never break the scan.
    def _supabase_sync_bg(_b):
        try:
            from supabase_analysis_sync import sync_scan as _sync_analysis_scan
            _res = _sync_analysis_scan(_b)
            if _res.get("ok"):
                log.info(
                    f"supabase analysis sync (bg): {_res.get('n_tickers', 0)} tickers in "
                    f"{_res.get('elapsed_sec', 0):.1f}s · errors={_res.get('errors') or 'none'}"
                )
            elif _res.get("reason") != "disabled":
                log.warning(f"supabase analysis sync skipped: {_res.get('reason')}")
        except Exception as _se:
            log.warning(f"supabase analysis sync failed (non-fatal): {_se}")
    try:
        import threading as _thr
        _thr.Thread(target=_supabase_sync_bg, args=(bundle,), name="supabase-sync", daemon=False).start()
        log.info("  supabase analysis sync: dispatched to background (non-blocking, #2 perf)")
    except Exception as _se:
        log.warning(f"supabase sync background dispatch failed, running inline: {_se}")
        _supabase_sync_bg(bundle)

    # Options flow refresh — always pull fresh UOA data from the standalone
    # scanner (200-ticker universe) before build_data.py reads it (2026-05-11).
    # The in-scan options-flow only sees the ~75 enriched tickers; the
    # standalone scanner covers 200 by liquidity. Running it on every
    # /Swing-Trade fire keeps options_flow.json fresh + uses --force to
    # bypass the market-hours gate (user directive: always pull both).
    try:
        import subprocess
        _of_refresh = BASE_DIR / "refresh_options_flow.py"
        if _of_refresh.exists():
            log.info("Step 8b: Refreshing standalone options-flow scanner (--force)...")
            _r = subprocess.run(["python3", str(_of_refresh), "--force"],
                                check=False, capture_output=True, timeout=300)
            if _r.returncode == 0:
                _tail = (_r.stdout or b"").decode("utf-8", errors="replace").strip().split("\n")[-1][:200]
                log.info(f"  Options flow refreshed: {_tail}")
            else:
                _err = (_r.stderr or b"").decode("utf-8", errors="replace").strip()[-300:]
                log.warning(f"  Options flow refresh exit {_r.returncode}; using cached. {_err}")
    except subprocess.TimeoutExpired:
        log.warning("  Options flow refresh timed out after 300s; using cached.")
    except Exception as _of_e:
        log.warning(f"  Options flow refresh error (non-fatal): {_of_e}")

    # Rebuild prototype data.json + tickers.json so the new-design dashboard
    # at /v2/ stays in sync with the production scan.
    # NOTE: v2 is now the canonical dashboard — failures here mean v2 goes stale
    # while legacy keeps updating, so failures are warnings, not debug.
    try:
        import subprocess
        _proto_builder = BASE_DIR / "infra" / "prototype" / "build_data.py"
        if _proto_builder.exists():
            _r = subprocess.run(["python3", str(_proto_builder)], check=False,
                                capture_output=True, timeout=180)
            if _r.returncode == 0:
                log.info(f"  Prototype data refreshed: infra/prototype/data.json")
            else:
                _err = (_r.stderr or b"").decode("utf-8", errors="replace").strip()[-500:]
                log.warning(f"v2 build_data.py failed (exit {_r.returncode}); v2 dashboard is now stale. stderr tail: {_err}")
    except subprocess.TimeoutExpired:
        log.warning("v2 build_data.py timed out after 180s; v2 dashboard is now stale")
    except Exception as _pe:
        log.warning(f"v2 build_data.py error; v2 dashboard is now stale: {_pe}")

    # ticker_snapshots — append per-scan rows so we can audit field-by-field
    # change-over-time tomorrow. Reads the JUST-WRITTEN infra/prototype/tickers.json
    # (post-build_data.py) so the snapshot matches what the dashboard renders.
    # Best-effort — failures here don't block scan completion.
    try:
        from datetime import datetime as _dt
        import ticker_snapshots
        _tjson = BASE_DIR / "infra" / "prototype" / "tickers.json"
        if _tjson.exists():
            _t = json.loads(_tjson.read_text())
            _now = _dt.now()
            _run_id = _now.strftime("%Y-%m-%d_%H:%M")
            _n = ticker_snapshots.capture_scan(_t, run_id=_run_id,
                                                captured_at=_now.isoformat(timespec="seconds"))
            log.info(f"  ticker_snapshots: captured {_n} rows (run_id={_run_id})")
        else:
            log.debug("ticker_snapshots: tickers.json not present — skipping snapshot")
    except Exception as _se:
        log.warning(f"ticker_snapshots capture failed: {_se}")

    # ── Data-quality alarm: too many tickers with score=0 = upstream outage ──
    # 2026-05-18: count tickers with score=0. If >10 (out of typical 400-500),
    # indicates EODHD partial outage or scoring bug. Slack alert so user knows
    # BEFORE seeing empty BUY list. Includes per-pillar breakdown if available.
    # 2026-05-26 (K2 defensive guard): exclude tickers whose score=0 is the result
    # of an INTENTIONAL verdict-side rejection (Wilson-validated setup×band kills,
    # sector blocklist, bear-setup demote, entry-quality gate, cooldown, score_mult
    # kill). These are not data-quality problems — they are the engine working as
    # designed. Without this filter, the alarm chronically misfires whenever a
    # killed setup family (e.g., Trend Continuation@<50) is heavily represented
    # in the universe. The TRUE outage signature is score=0 + no audit-trail
    # reason + no score_mult_audit.killed.
    try:
        _intent_markers = (
            "kill", "blocklist", "bear", "demoted",
            "cooldown", "wait for pullback", "fresh",
        )
        def _is_intentional_zero(r):
            sma = r.get("score_mult_audit") or {}
            if sma.get("killed"):
                return True
            at = r.get("audit_trail") or {}
            reason = (at.get("reason") or "").lower()
            if any(m in reason for m in _intent_markers):
                return True
            dec = r.get("decision") or {}
            dec_reason = (dec.get("reason") or "").lower()
            if any(m in dec_reason for m in _intent_markers):
                return True
            return False

        _all_zero = [r for r in (all_results or []) if isinstance(r, dict) and (r.get("score") or 0) == 0]
        _zero_score = [r for r in _all_zero if not _is_intentional_zero(r)]
        _intentional_n = len(_all_zero) - len(_zero_score)
        if _intentional_n > 0:
            log.info(f"  score=0 breakdown: {_intentional_n} intentional verdict kills "
                     f"(setup×band, sector blocklist, bear, FRESH gate, cooldown) "
                     f"vs {len(_zero_score)} unexplained/data-quality")
        if len(_zero_score) > 10:
            _tk_sample = [r.get("ticker") for r in _zero_score[:15] if r.get("ticker")]
            # Aggregate which pillar caused most zeros (from score_breakdown)
            from collections import Counter as _C
            _pillar_zero = _C()
            for r in _zero_score:
                bd = r.get("score_breakdown") or {}
                for p in ("tech", "catalyst", "rs", "smart_money", "quality_gate", "entry_rr"):
                    if (bd.get(p) or 0) == 0:
                        _pillar_zero[p] += 1
            _pillar_summary = " · ".join(f"{p}={n}" for p, n in _pillar_zero.most_common(3))
            log.warning(f"⚠ DATA-QUALITY ALARM: {len(_zero_score)} tickers scored 0 this scan "
                        f"(typical: 0-5, excluding {_intentional_n} intentional kills). "
                        f"Sample: {_tk_sample}. "
                        f"Most-failed pillars: {_pillar_summary or 'unknown (no breakdown data)'}")
            try:
                from alerts import send_alert
                send_alert(
                    level="WARNING",
                    title=f"⚠ {len(_zero_score)} tickers scored 0",
                    body=(f"This scan: {len(_zero_score)} tickers returned score=0 (typical: 0-5, "
                          f"after excluding {_intentional_n} intentional kills). "
                          f"Likely EODHD partial outage or scoring pipeline gap.\n"
                          f"Sample: {', '.join(_tk_sample[:10])}\n"
                          f"Most-failed pillars: {_pillar_summary or 'no breakdown data yet'}\n"
                          f"Action: check EODHD quota, review Pipeline tab → per-pillar matrix"),
                )
            except Exception as _ae:
                log.warning(f"Slack alarm send failed: {_ae}")
    except Exception as _zse:
        log.warning(f"data-quality alarm check failed: {_zse}")

    log.info(f"=== Done! Dashboard: http://localhost:7432/kairos.html ===")
    # 2026-05-18: read from FINAL bundle state (not stale locals) so the count
    # reflects what's actually written to disk after all demotion passes.
    _final_buys = bundle.get("buy_candidates", []) if isinstance(bundle, dict) else []
    _final_watch = bundle.get("watch_list", []) if isinstance(bundle, dict) else []
    _final_sells = bundle.get("sell_candidates", []) if isinstance(bundle, dict) else []
    _final_killed = bundle.get("killed", []) if isinstance(bundle, dict) else []
    _stale_diff = len(buy_candidates) - len(_final_buys)
    _diff_note = f" (post-demotion: {_stale_diff} dropped since intermediate count)" if _stale_diff > 0 else ""
    log.info(f"  BUY: {len(_final_buys)}{_diff_note} | WATCH: {len(_final_watch)} | SHORT: {len(_final_sells)} | Near-Short Blocked: {len(near_short_blocked)} | Killed: {len(_final_killed)}")

    # HTML snapshot to DB (2026-05-14) — store dashboard.html for retrieval
    try:
        import db
        dash_path = BASE_DIR / "cache" / "dashboard.html"
        if dash_path.exists():
            html_content = dash_path.read_text()
            snap_id = db.save_html_snapshot(
                kind="dashboard",
                html_content=html_content,
                label=f"dashboard {bundle.get('run_timestamp', '')}",
                meta={
                    "buy_count": len(buy_candidates),
                    "watch_count": len(watch_list),
                    "short_count": len(sell_candidates),
                    "regime": (bundle.get("regime") or {}).get("regime4"),
                    "scan_run_date": bundle.get("run_date"),
                },
            )
            log.info(f"  HTML snapshot saved to DB: id={snap_id}")
            # Prune to keep last 200 (~6 months of daily scans)
            db.prune_html_snapshots(keep_last_n=200)
    except Exception as _html_err:
        log.warning(f"HTML snapshot save failed: {_html_err}")

    # P2.21/22/23 — log warnings for any active system_status flags
    ss = bundle.get("system_status", {})
    if ss.get("forced_cash", {}).get("active"):
        log.warning("  ⚠️  FORCED CASH: zero qualifying setups across modes — hold cash.")
    if ss.get("circuit_breaker", {}).get("active"):
        cb = ss["circuit_breaker"]
        log.warning(f"  ⚠️  CIRCUIT BREAKER {cb.get('level','').upper()}: {'; '.join(cb.get('reasons', []))}")
    if ss.get("macro_calendar", {}).get("blackout_today"):
        log.warning(f"  ⚠️  MACRO BLACKOUT: {ss['macro_calendar'].get('blackout_reason')} — new entries blocked")

    # Screener time-travel (2026-04-15) — archive a trimmed per-date snapshot
    try:
        import bundle_archive, audit as _au
        _snap = bundle_archive.save_snapshot(bundle, active_profile=_au.active_profile())
        if _snap:
            log.info(f"  Bundle snapshot saved: {_snap.name}")
    except Exception as _sae:
        log.debug(f"bundle_archive.save_snapshot skipped: {_sae}")

    # EODHD call counter — log per-scan budget audit
    try:
        from eodhd_client import get_call_stats as _eodhd_stats
        _stats = _eodhd_stats()
        _net = _stats.get("network", 0); _hit = _stats.get("cache_hit", 0)
        _total = _net + _hit
        _hit_rate = (_hit / _total * 100) if _total > 0 else 0
        log.info(f"  EODHD calls this scan: {_net} network + {_hit} cache_hit "
                 f"= {_total} total (cache hit rate {_hit_rate:.1f}%)")
    except Exception as _ce:
        log.debug(f"EODHD call stats unavailable: {_ce}")

    # Phase G: per-endpoint quota flush to Supabase (idempotent on bucket_date+endpoint)
    try:
        from eodhd_client import flush_quota_to_supabase as _flush_quota
        _qres = _flush_quota()
        if _qres.get("pushed", 0) > 0:
            log.info(f"  EODHD quota: flushed {_qres['pushed']} endpoint buckets to Supabase")
    except Exception as _qe:
        log.debug(f"EODHD quota flush skipped: {_qe}")

    # #9: 90-day retention on bundle snapshots — prevents unbounded disk growth
    try:
        from datetime import timedelta as _td
        _bundles_dir = BASE_DIR / "cache" / "bundles"
        if _bundles_dir.exists():
            _cutoff = (datetime.now() - _td(days=90)).date()
            _purged = 0
            for _p in _bundles_dir.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].json"):
                try:
                    _file_date = datetime.strptime(_p.stem, "%Y-%m-%d").date()
                    if _file_date < _cutoff:
                        _p.unlink()
                        _purged += 1
                except Exception:
                    pass
            if _purged:
                log.info(f"  Bundle retention: purged {_purged} snapshots older than 90 days")
    except Exception as _ret_e:
        log.debug(f"Bundle retention step skipped: {_ret_e}")

    # Unified audit log (2026-04-15) — one row per scan run for attribution joins
    try:
        import audit
        audit.log("scan_run", {
            "buy_count":   len(buy_candidates),
            "watch_count": len(watch_list),
            "sell_count":  len(sell_candidates),
            "near_short_blocked": len(near_short_blocked),
            "killed":      len(killed),
            "regime":      regime.get("regime"),
            "regime4":     regime.get("regime4"),
            "spy_price":   regime.get("spy_price"),
            "vix":         vix_cur,
            "breadth_50":  market_breadth.get("pct_above_50d"),
        })
    except Exception as _ae:
        log.debug(f"audit.log scan_run skipped: {_ae}")

    # ── Killed-tickers drift tracking + alert ────────────────────────
    try:
        from datetime import datetime as _dt_sh
        import json as _json_sh
        _health_file = BASE_DIR / "data" / "scan_health.json"
        _health = {"history": [], "max_keep": 100}
        if _health_file.exists():
            try:
                with open(_health_file) as _hf:
                    _health = _json_sh.load(_hf)
            except Exception:
                pass
        _total_sh = len(buy_candidates) + len(watch_list) + len(sell_candidates) + len(killed)
        _killed_pct = (len(killed) / _total_sh * 100) if _total_sh > 0 else 0
        _health.setdefault("history", []).append({
            "ts": _dt_sh.now().isoformat(),
            "total": _total_sh,
            "killed": len(killed),
            "pct": round(_killed_pct, 2),
        })
        _max_keep = _health.get("max_keep", 100)
        _health["history"] = _health["history"][-_max_keep:]
        _health["max_keep"] = _max_keep
        _health_file.parent.mkdir(exist_ok=True)
        with open(_health_file, "w") as _hf:
            _json_sh.dump(_health, _hf, indent=2, default=str)

        # Alert if drift detected: need >=10 prior scans, gap > 10pp (lowered from 15pp
        # so drift fires sooner; removed the extra absolute-delta gate).
        _hist = _health["history"]
        if len(_hist) >= 11:
            _recent = _hist[-11:-1]  # exclude current
            _avg_pct = sum(h["pct"] for h in _recent) / len(_recent)
            log.info(f"Kill-drift check: {_killed_pct:.1f}% vs avg {_avg_pct:.1f}% (last {len(_recent)} scans)")
            if _killed_pct > _avg_pct + 10:
                log.warning(f"KILLED DRIFT: {_killed_pct:.1f}% killed (avg last 10: {_avg_pct:.1f}%) — dispatching Slack alert")
                try:
                    from alerts import send_alert
                    _sent = send_alert(
                        level="WARN",
                        title="Scan health drift",
                        body=(f"Killed tickers: {_killed_pct:.1f}% "
                              f"(vs avg {_avg_pct:.1f}% over last 10 scans). "
                              f"Data pipeline may have an issue."),
                    )
                    if not _sent:
                        log.warning("Drift alert: Slack webhook not configured or post failed — "
                                    "check SLACK_WEBHOOK_URL (env/.env) or config/config.json → alerts.slack_webhook")
                except Exception as _se:
                    log.error(f"Drift alert dispatch failed: {_se}")
        else:
            log.info(f"Kill-drift check: {_killed_pct:.1f}% killed ({len(_hist)} prior scans — need >=11 for drift alert)")
    except Exception as _sh_e:
        log.debug(f"Killed-drift tracking failed: {_sh_e}")

    # ── Score distribution vs threshold calibration check ────────────
    try:
        from score_distribution_check import check_distribution
        dist = check_distribution()
        if dist.get("warnings"):
            for w in dist["warnings"]:
                log.warning(f"THRESHOLD CALIBRATION: {w}")
            try:
                from alerts import send_alert
                send_alert(level="WARN",
                           title="Score threshold miscalibration",
                           body=dist["warnings"][0])
            except Exception:
                pass
        if dist.get("stats"):
            log.info(f"Score distribution: mean={dist['stats']['mean']}, "
                     f"p90={dist['stats']['p90']}, BUY qualifiers={dist['n_above_buy']}")
    except Exception as _dc_e:
        log.debug(f"Distribution check failed: {_dc_e}")

    # Print quick summary
    print("\n" + "=" * 60)
    print(f"  SWINGTRADE DAILY SCAN — {run_date}")
    print(f"  Regime: {regime['regime'].upper()} | SPY ${regime['spy_price']}")
    print("=" * 60)

    def _print_tier(label, buys, sells):
        print(f"\n  {label}")
        if buys:
            print(f"    BUY:")
            for r in buys:
                plan = r["trade_plan"]
                print(f"      {r['ticker']:6s} ${r['price']:7.2f}  Score:{r['score']:.0f}  "
                      f"R:R {plan['rr_ratio']:.1f}:1  {plan['setup_type']}")
        else:
            print(f"    BUY:  (none)")
        if sells:
            print(f"    SELL:")
            for r in sells:
                bear_sc = r.get("bear_setup", {}).get("score", 0)
                print(f"      {r['ticker']:6s} ${r['price']:7.2f}  Score:{r['score']:.0f}  "
                      f"Bear {bear_sc}/15")
        else:
            print(f"    SELL: (none)")

    _print_tier("🇺🇸 S&P 500  < $100",  idx_sp500_100_buy,  idx_sp500_100_sell)
    _print_tier("🇺🇸 S&P 500  < $250",  idx_sp500_250_buy,  idx_sp500_250_sell)
    _print_tier("📈 Russell 1000 < $100", idx_r1000_100_buy,  idx_r1000_100_sell)
    _print_tier("📈 Russell 1000 < $250", idx_r1000_250_buy,  idx_r1000_250_sell)

    if industries[:5]:
        print(f"\n  STRONGEST INDUSTRIES:")
        for ind in industries[:5]:
            print(f"    {ind['industry'][:35]:35s}  Avg:{ind['avg_score']:.0f}  "
                  f"({ind['count']} stocks)")

    print(f"\n  Dashboard: http://localhost:7432/kairos.html")
    print("=" * 60)

    # Send alerts (Slack + macOS notification)
    try:
        spy_price_float = float(regime.get("spy_price", 0)) or None
        send_scan_alerts(
            buy_candidates=buy_candidates,
            sell_candidates=sell_candidates,
            watch_candidates=list(watch_list),
            regime=regime.get("regime", "unknown"),
            spy_price=spy_price_float,
            near_short_blocked=near_short_blocked,
        )
    except Exception:
        pass  # alerts are non-critical

    # Email report retired with html_generator (Phase B). Slack handles
    # high-signal events; email-the-dashboard would need a V2 export path.

    # Position-level alerts (stop-approach + T1-hit) — market-hours gated, throttled
    try:
        from position_alerts import run_alerts_pass
        run_alerts_pass()
    except Exception as e:
        log.debug(f"Position alerts pass failed: {e}")

    # Check actual positions hitting stops (position_tracker)
    try:
        from position_tracker import check_stops
        stopped = check_stops()
        if stopped:
            from alerts import send_alert
            tickers_hit = ", ".join(s["ticker"] for s in stopped)
            body = " | ".join(
                f"{s['ticker']} ${s['current_price']:.2f} (stop ${s['stop']:.2f}, {s['loss_pct']:+.1f}%)"
                for s in stopped
            )
            send_alert("WARN", f"STOP HIT: {tickers_hit}", body)
            log.warning(f"Positions hitting stops: {body}")
    except Exception as e:
        log.debug(f"Position tracker stop check failed: {e}")

    # ── ML Edge inference over the FRESH bundle (config-gated) ───────────
    # PROBLEM-2 fix: the standalone ml.run_ml_edge launchd job fires at 05:00,
    # BEFORE this 06:30 scan, so it always scored YESTERDAY's bundle. Running
    # inference here — AFTER cache/last_bundle.json is written and the v2
    # dashboard/build_data + snapshots are finalized — couples predictions to
    # today's scan. The local Parquet archive was just delta-updated at the top
    # of this scan, so feature_extractor reads fresh bars WITHOUT new EODHD
    # calls. Fully guarded: this must NEVER raise into the scan.
    try:
        _ml_cfg = (cfg.get("ml_edge") or {}) if isinstance(cfg, dict) else {}
        if _ml_cfg.get("run_after_scan", False):
            log.info("ML Edge: running inference over fresh bundle (run_after_scan=true)...")
            try:
                import time as _ml_time
                _ml_start = _ml_time.time()
                _ml_ran = False
                # Prefer in-process call — defaults to universe=bundle (last_bundle.json).
                try:
                    from ml.run_ml_edge import main as _ml_edge_main
                    _ml_edge_main([])
                    _ml_ran = True
                except Exception as _ml_imp_e:
                    log.warning(f"ML Edge: in-process call failed ({type(_ml_imp_e).__name__}: "
                                f"{str(_ml_imp_e)[:160]}) — falling back to subprocess")
                    import subprocess as _ml_sub
                    _r = _ml_sub.run([sys.executable, "-m", "ml.run_ml_edge"],
                                     cwd=str(BASE_DIR), timeout=1800,
                                     capture_output=True)
                    if _r.returncode == 0:
                        _ml_ran = True
                    else:
                        _err = (_r.stderr or b"").decode("utf-8", errors="replace").strip()[-400:]
                        log.warning(f"ML Edge subprocess exit {_r.returncode}: {_err}")
                if _ml_ran:
                    log.info(f"ML Edge: inference finished in {_ml_time.time()-_ml_start:.0f}s")
            except Exception as _ml_inner_e:
                log.warning(f"ML Edge: inference failed (non-fatal): "
                            f"{type(_ml_inner_e).__name__}: {str(_ml_inner_e)[:200]}")
        else:
            log.debug("ML Edge: run_after_scan disabled — skipping post-scan inference")
    except Exception as _ml_outer_e:
        log.warning(f"ML Edge post-scan hook skipped (non-fatal): {_ml_outer_e}")

    # Auto-start server so live analysis + portfolio work in the browser
    _auto_start_server()

    return html_path


def _auto_start_server():
    """Start server.py in background if not already running on port 7432."""
    import socket
    import subprocess
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        s.connect(("localhost", 7432))
        s.close()
        log.info("Server already running on localhost:7432")
    except (ConnectionRefusedError, OSError):
        log.info("Starting server on localhost:7432...")
        subprocess.Popen(
            [sys.executable, str(BASE_DIR / "server.py")],
            cwd=str(BASE_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        import time
        time.sleep(1)
        log.info("Server started — http://localhost:7432/dashboard")


def run_quick_dive(ticker: str, timeout_per_endpoint: float = 10.0):
    # 10s is the TOTAL deadline for the parallel enrichment pool (not per-future).
    # If any future stalls past this, we cancel it and use defaults.
    """
    FAST-LANE per-ticker analysis — designed for on-demand UI requests.
    Skips heavy enrichment (Finviz bulk, social scrapers, decommissioned fallbacks).
    Target: <30s. Calls only EODHD-backed endpoints + a few cheap scrapes.

    Used by /api/elite/{ticker} when user searches a ticker outside the scan universe.
    For full enrichment matching the nightly scan, use run_deep_dive() instead.
    """
    import time as _time
    cfg = load_config()
    t_start = _time.time()
    timings = {}
    def _mark(label, t0):
        timings[label] = round(_time.time() - t0, 2)
    log.info(f"=== Quick Dive: {ticker} (fast-lane, target <30s) ===")

    t0 = _time.time()
    data = fetch_market_data([ticker], period="1y")
    _mark('ticker_ohlcv', t0)
    if ticker not in data:
        log.error(f"No data for {ticker}")
        return None
    df = data[ticker]

    t0 = _time.time()
    from data_fetcher import fetch_ohlcv_with_failover
    spy_data, _ = fetch_ohlcv_with_failover("SPY", days=365)
    spy_close = spy_data["Close"].squeeze().dropna() if spy_data is not None and not spy_data.empty else None
    _mark('spy_ohlcv', t0)

    # Slim parallel enrichment — non-blocking exit (don't wait for stragglers)
    t0 = _time.time()
    log.info(f"  Slim enrichment for {ticker}...")
    pool = ThreadPoolExecutor(max_workers=8)
    futs = {
        'info':     pool.submit(get_stock_info,        ticker),
        'regime':   pool.submit(get_market_regime),
        'earnings': pool.submit(get_earnings_date,     ticker),
        'news':     pool.submit(get_news_sentiment,    ticker),
        'insider':  pool.submit(get_insider_activity,  ticker),
        'analyst':  pool.submit(get_analyst_data,      ticker),
        'weekly':   pool.submit(get_weekly_data,       [ticker]),
        'sector':   pool.submit(get_sector_etf_data),
    }
    defaults = {
        'info':     {}, 'regime': {}, 'earnings': {},
        'news':     {"score": 0, "bias": "neutral"},
        'insider':  {"buys": 0, "sells": 0},
        'analyst':  {}, 'weekly': {}, 'sector': {},
    }
    # Wait at most timeout_per_endpoint seconds TOTAL — collect whatever finished
    deadline = _time.time() + timeout_per_endpoint
    results = {}
    for label, f in futs.items():
        t_f = _time.time()
        remaining = max(0.05, deadline - _time.time())
        try:
            results[label] = f.result(timeout=remaining)
        except Exception as e:
            results[label] = defaults[label]
            log.debug(f"  Quick dive: {label} skipped ({type(e).__name__})")
        timings[f'fetch_{label}'] = round(_time.time() - t_f, 2)
    # Don't wait for stragglers — kill the pool immediately. Their work is wasted but
    # we already have whatever finished within the deadline.
    pool.shutdown(wait=False, cancel_futures=True)
    info, regime, earnings = results['info'], results['regime'], results['earnings']
    news, insider, analyst = results['news'], results['insider'], results['analyst']
    weekly_all, sector_etf_data = results['weekly'], results['sector']
    _mark('parallel_enrichment_total', t0)

    weekly_df = weekly_all.get(ticker)
    t0 = _time.time()
    news_articles = []
    try:
        news_articles = get_news_articles(ticker, 8) or []
    except Exception:
        pass
    _mark('news_articles', t0)

    log.info(f"  Enrichment done in {_time.time()-t_start:.1f}s — running scoring…")

    t0 = _time.time()
    result = analyze_ticker(
        ticker, df, info, regime, earnings, news,
        insider, spy_close, cfg,
        weekly_df=weekly_df,
        sector_etf_data=sector_etf_data,
        analyst=analyst,
        news_articles=news_articles,
        options_data=None, beat_rate=None, stocktwits=None,
        extra_fund=None, congressional=None, reddit_wsb=None,
        zacks=None, tv_rating=None, uoa=None, borrow=None,
        finnhub=None, fmp=None, sec=None, breadth=None,
        premarket=None, inst_trend=None, gamma=None, eps_trend=None,
        finviz=None, quote_snapshot=None, options_chain=None, df_4h=None,
        zacks_sell=False,
    )
    _mark('analyze_ticker', t0)
    total = round(_time.time() - t_start, 2)
    log.info(f"=== Quick Dive {ticker} done in {total}s ===")
    # Sorted timing breakdown — surface in log so we can find the bottleneck
    sorted_t = sorted(timings.items(), key=lambda x: -x[1])
    log.info(f"  Quick dive timing breakdown ({ticker}):")
    for label, secs in sorted_t:
        log.info(f"    {label:30s} {secs:6.2f}s")
    return result


def run_deep_dive(ticker: str):
    """Run full 9-section deep dive on a single ticker (full enrichment, same as daily scan)."""
    cfg = load_config()
    log.info(f"=== Deep Dive: {ticker} ===")

    # Fetch price data + SPY
    data = fetch_market_data([ticker], period="1y")
    if ticker not in data:
        log.error(f"No data for {ticker}")
        return None

    df = data[ticker]
    # EODHD primary (post-2026-04-25 migration), yfinance fallback
    from data_fetcher import fetch_ohlcv_with_failover
    spy_data, _src = fetch_ohlcv_with_failover("SPY", days=365)
    spy_close = spy_data["Close"].squeeze().dropna() if spy_data is not None and not spy_data.empty else None
    if spy_close is None or len(spy_close) == 0:
        log.warning("  SPY data unavailable — relative strength will default to neutral")
        spy_close = None

    # Fetch all enrichment data in parallel (matching daily scan)
    log.info(f"  Fetching enrichment data for {ticker}...")
    with ThreadPoolExecutor(max_workers=16) as pool:
        f_info      = pool.submit(get_stock_info, ticker)
        f_regime    = pool.submit(get_market_regime)
        f_earnings  = pool.submit(get_earnings_date, ticker)
        f_news      = pool.submit(get_news_sentiment, ticker)
        f_insider   = pool.submit(get_insider_activity, ticker)
        f_analyst   = pool.submit(get_analyst_data, ticker)
        f_stocktwit = pool.submit(get_stocktwits_data, ticker)
        f_options   = pool.submit(get_options_iv_data, ticker)
        f_beat      = pool.submit(get_earnings_beat_rate, ticker)
        f_extra     = pool.submit(get_extra_fundamentals, ticker)
        f_cong      = pool.submit(get_congressional_trades, ticker)
        f_wsb       = pool.submit(get_reddit_wsb, ticker)
        f_uoa       = pool.submit(get_unusual_options, ticker)
        f_borrow    = pool.submit(get_borrow_rate, ticker)
        f_finnhub   = pool.submit(get_finnhub_data, ticker)
        f_fmp       = pool.submit(get_fmp_data, ticker)
        f_sec       = pool.submit(get_sec_filings, ticker)
        f_weekly    = pool.submit(get_weekly_data, [ticker])
        f_sector    = pool.submit(get_sector_etf_data)
        f_finviz    = pool.submit(get_finviz_bulk)   # Finviz bulk for SMA%, perf%, ownership

        info        = f_info.result()
        regime      = f_regime.result()
        earnings    = f_earnings.result()
        news        = f_news.result()
        insider     = f_insider.result()
        analyst     = f_analyst.result()
        stocktwits  = f_stocktwit.result()
        options     = f_options.result()
        beat_rate   = f_beat.result()
        extra_fund  = f_extra.result()
        congressional = f_cong.result()
        reddit_wsb  = f_wsb.result()
        uoa         = f_uoa.result()
        borrow      = f_borrow.result()
        finnhub     = f_finnhub.result()
        fmp         = f_fmp.result()
        sec         = f_sec.result()
        weekly_all  = f_weekly.result()
        sector_etf_data = f_sector.result()
        finviz_data = f_finviz.result().get(ticker, {})

    weekly_df = weekly_all.get(ticker)

    result = analyze_ticker(ticker, df, info, regime, earnings, news,
                            insider, spy_close, cfg,
                            weekly_df=weekly_df,
                            options_data=options,
                            beat_rate=beat_rate,
                            stocktwits=stocktwits,
                            sector_etf_data=sector_etf_data,
                            extra_fund=extra_fund,
                            congressional=congressional,
                            reddit_wsb=reddit_wsb,
                            analyst=analyst,
                            uoa=uoa,
                            borrow=borrow,
                            finnhub=finnhub,
                            fmp=fmp,
                            sec=sec,
                            finviz=finviz_data)

    # Print detailed report
    print("\n" + "=" * 60)
    print(f"  DEEP DIVE: {ticker} — {info.get('name', ticker)}")
    print("=" * 60)

    gate = result["gate"]
    print(f"\n  GATE: {'PASS' if gate['passed'] else 'FAIL'}")
    if not gate["passed"]:
        for r in gate["reasons"]:
            print(f"    - {r}")

    print(f"\n  FUNDAMENTALS ({result['fundamentals']['score']}/30)")
    for k, v in result["fundamentals"]["details"].items():
        print(f"    {k}: {v}")

    print(f"\n  OPTIONALITY ({result['optionality']['score']}/20)")
    for k, v in result["optionality"]["details"].items():
        print(f"    {k}: {v}")
    print(f"    Bull case: ${result['optionality']['bull_case']}")
    print(f"    Base case: ${result['optionality']['base_case']}")
    print(f"    Bear case: ${result['optionality']['bear_case']}")

    print(f"\n  TECHNICALS ({result['technicals']['score']}/30)")
    for k, v in result["technicals"]["details"].items():
        print(f"    {k}: {v}")

    print(f"\n  SENTIMENT ({result['sentiment']['score']}/10)")
    for k, v in result["sentiment"]["details"].items():
        print(f"    {k}: {v}")

    plan = result["trade_plan"]
    print(f"\n  TRADE PLAN — {plan['setup_type']}")
    print(f"    Entry:    {plan['entry_zone']}")
    print(f"    Stop:     ${plan['stop']}")
    print(f"    Target 1: ${plan['target1']}")
    print(f"    Target 2: ${plan['target2']}")
    print(f"    R:R:      {plan['rr_ratio']:.1f}:1")
    print(f"    Risk:     ${plan['risk_per_share']:.2f}/share")

    print(f"\n  TOTAL SCORE: {result['score']:.0f}/100")
    verdict = result["decision"]
    print(f"  VERDICT: {verdict['verdict']} — {verdict['reason']}")

    print("=" * 60)

    # Also generate a single-ticker HTML
    bundle = {
        "run_date": datetime.now().strftime("%Y-%m-%d"),
        "regime": regime,
        "buy_candidates": [result] if verdict["verdict"] == "BUY" else [],
        "sell_candidates": [result] if verdict["verdict"] == "AVOID" else [],
        "watch_list": [result] if verdict["verdict"] == "WATCH" else [],
        "all_scored": [result],
        "killed": [] if gate["passed"] else [result],
        "industries": [],
        "stats": compute_stats(),
        "config": cfg,
        "total_scanned": 1,
        "total_passed": 1 if gate["passed"] else 0,
    }

    # Phase B (2026-05-08): legacy single-ticker deep-dive HTML retired with
    # html_generator. View ticker detail in V2 instead:
    print(f"  View: http://localhost:7432/kairos.html?t={ticker}")

    return result


def show_history():
    """Display performance tracking stats with detailed trade table grouped by date."""
    from tracker import get_full_history

    stats = compute_stats()
    history = get_full_history()

    print("\n" + "=" * 120)
    print("  SWINGTRADE PERFORMANCE SUMMARY")
    print("=" * 120)

    if not stats.get("sufficient_data"):
        print(f"  Need {stats.get('min_required', 5) - stats.get('total_trades', 0)} "
              f"more trades ({stats.get('total_trades', 0)}/{stats.get('min_required', 5)})")
        return

    print(f"  Win Rate:       {stats['win_rate']:.0f}%")
    print(f"  Profit Factor:  {stats['profit_factor']:.1f}")
    print(f"  Avg Win:        +{stats['avg_win']:.1f}%")
    print(f"  Avg Loss:       {stats['avg_loss']:.1f}%")
    print(f"  Total Trades:   {stats['total_trades']}")
    print(f"  Best Streak:    {stats['best_streak']}")

    if stats.get("best_trade"):
        b = stats["best_trade"]
        print(f"  Best Trade:     {b['ticker']} +{b['pct_chg']:.1f}%")
    if stats.get("worst_trade"):
        w = stats["worst_trade"]
        print(f"  Worst Trade:    {w['ticker']} {w['pct_chg']:.1f}%")

    # Group trades by date (not datetime)
    if history and history.get("trades"):
        print("\n" + "=" * 130)
        print("  DETAILED TRADE HISTORY (GROUPED BY DATE)")
        print("=" * 130)

        trades_by_date = {}
        for trade in history.get("trades", []):
            date_key = trade.get("run_date", "unknown")
            if date_key not in trades_by_date:
                trades_by_date[date_key] = []
            trades_by_date[date_key].append(trade)

        # Header
        print(f"{'Ticker':<8} {'Date':<12} {'Time':<6} {'Dir':<5} {'Signal':<8} {'Score':<6} {'Entry':<10} "
              f"{'Exit':<10} {'P&L':<8} {'Win?':<5} {'Setup':<30} {'MAE':<7} {'MFE':<7}")
        print("-" * 130)

        # Print trades grouped by date (most recent first)
        for date_key in sorted(trades_by_date.keys(), reverse=True):
            # Sort trades within each date by time
            day_trades = sorted(trades_by_date[date_key],
                               key=lambda t: t.get("run_time", "00:00"), reverse=True)

            for trade in day_trades:
                ticker = trade.get("ticker", "?")
                run_time = trade.get("run_time", "--:--")
                direction = "SHORT" if trade.get("direction") == "short" else "LONG"
                verdict = trade.get("verdict", "?")
                score = f"{trade.get('score', 0):.0f}"
                entry = f"${trade.get('entry_price', 0):.2f}"
                exit_p = f"${trade.get('exit_price', 0):.2f}"
                pnl = f"{trade.get('pct_chg', 0):+.2f}%"
                win = "✓" if trade.get("win") else "✗"
                setup = trade.get("setup_type", "")[:28]
                mae = f"{trade.get('mae', 0):+.1f}%"
                mfe = f"{trade.get('mfe', 0):+.1f}%"

                print(f"{ticker:<8} {date_key:<12} {run_time:<6} {direction:<5} {verdict:<8} {score:<6} {entry:<10} "
                      f"{exit_p:<10} {pnl:<8} {win:<5} {setup:<30} {mae:<7} {mfe:<7}")

    print("=" * 120)


def _build_sample_bundle() -> dict:
    """Generate a realistic sample bundle for UI development (no API calls)."""
    import random, math
    random.seed(42)

    SAMPLES = [
        ("NVDA", "NVIDIA Corp",          "Technology",    "Semiconductors",               87, "BUY",   3.8, 142.50, "Stage 2 Breakout"),
        ("MSFT", "Microsoft Corp",        "Technology",    "Software—Infrastructure",      81, "BUY",   3.2, 418.20, "Weekly Trend Continuation"),
        ("AAPL", "Apple Inc",             "Technology",    "Consumer Electronics",         76, "BUY",   3.0,  189.45, "Bounce off Support"),
        ("GLD",  "SPDR Gold Shares",      "Financials",    "Gold",                         74, "WATCH", 2.8, 225.80, "SAR Reversal"),
        ("FTI",  "TechnipFMC plc",        "Energy",        "Oil & Gas Equipment & Services",64,"BUY",  3.0,  73.89, "Stage 2 Breakout"),
        ("VIRT", "Virtu Financial",        "Financials",    "Capital Markets",              60, "WATCH", 3.0,  48.37, "Stage 2 Breakout"),
        ("WELL", "Welltower Inc",          "Real Estate",   "REIT - Healthcare",            58, "WATCH", 3.0, 207.07, "Bounce off Support"),
        ("MRVL", "Marvell Technology",     "Technology",    "Semiconductors",               55, "WATCH", 3.0, 127.62, "Stage 2 Breakout"),
        ("ANET", "Arista Networks",        "Technology",    "Computer Hardware",            54, "WATCH", 3.0, 146.46, "Breakout"),
        ("NEM",  "Newmont Corp",           "Materials",     "Gold",                         53, "WATCH", 3.0, 120.55, "Weekly Trend Continuation"),
        ("EIX",  "Edison International",   "Utilities",     "Utilities—Regulated Electric", 54, "WATCH", 3.0,  76.09, "Stage 2 Breakout"),
        ("PLTR", "Palantir Technologies",  "Technology",    "Software—Application",         51, "AVOID", 0.0, 127.83, "Distribution"),
        ("PATH", "UiPath Inc",             "Technology",    "Software—Application",         47, "AVOID", 0.0,   9.55, "Breakdown"),
        ("CRM",  "Salesforce Inc",         "Technology",    "Software—Application",         47, "AVOID", 0.0, 164.92, "Distribution"),
        ("NOW",  "ServiceNow Inc",         "Technology",    "Software—Infrastructure",      45, "SHORT", 2.2,  82.69, "Breakdown"),
        ("BSX",  "Boston Scientific",      "Healthcare",    "Medical Devices",              45, "SHORT", 2.5,  61.35, "Breakdown"),
        ("TTD",  "The Trade Desk",         "Technology",    "Software—Application",         39, "SHORT", 2.8,  20.42, "Stage 4 Decline"),
        ("OKTA", "Okta Inc",               "Technology",    "Software—Infrastructure",      42, "SHORT", 2.6,  64.11, "Stage 4 Decline"),
        ("TOST", "Toast Inc",              "Technology",    "Software—Application",         42, "SHORT", 2.4,  25.42, "Breakdown"),
        ("IR",   "Ingersoll Rand",         "Industrials",   "Specialty Industrial Machinery",52,"WATCH",3.0,  86.18, "SAR Reversal"),
        ("BKR",  "Baker Hughes",           "Energy",        "Oil & Gas Equipment & Services",49,"WATCH",3.0,  62.73, "SAR Reversal"),
        ("GEN",  "Gen Digital",            "Technology",    "Software—Infrastructure",      48, "WATCH", 3.0,  18.25, "Breakdown"),
        ("MKC",  "McCormick & Co",         "Consumer Def.", "Packaged Foods",               48, "WATCH", 3.0,  52.87, "Breakdown"),
        ("OMF",  "OneMain Financial",      "Financials",    "Credit Services",              54, "WATCH", 3.0,  56.28, "SAR Reversal"),
        ("CGNX", "Cognex Corp",            "Technology",    "Scientific Instruments",       54, "WATCH", 3.0,  53.51, "Weekly Trend Continuation"),
    ]

    all_scored, killed = [], []
    for tk, name, sector, industry, score, verdict, rr, price, setup in SAMPLES:
        direction = "short" if verdict == "SHORT" else "long"
        stop   = round(price * (0.94 if direction == "long" else 1.06), 2)
        t1     = round(price * (1.08 if direction == "long" else 0.92), 2)
        entry  = round(price * 0.999, 2)
        is_buy = verdict == "BUY"
        r = {
            "ticker": tk, "name": name, "price": price, "score": score,
            "sector": sector, "industry": industry, "direction": direction,
            "rsi":  round(random.uniform(35, 75), 1),
            "rvol": round(random.uniform(0.8, 2.8), 2),
            "rs_rank": random.randint(30, 95),
            "atr_pct": round(random.uniform(1.0, 4.0), 2),
            "squeeze": random.random() > 0.7,
            "zacks_rank1": is_buy and random.random() > 0.4,
            "zacks_sell":  verdict in ("SHORT", "AVOID") and random.random() > 0.5,
            "beta": round(random.uniform(0.6, 1.8), 2),
            "price_tier": f"${int(price//50)*50}–${int(price//50)*50+50}",
            "decision": {"verdict": verdict, "reason": f"{setup} — score {score}"},
            "gate": {"passed": verdict != "KILLED"},
            "fundamentals": {"score": random.randint(10, 28), "bull_drivers": ["Revenue growth"], "bear_risks": [], "details": {}},
            "technicals":   {"score": random.randint(10, 28), "details": {}, "indicators": {}},
            "optionality":  {"score": random.randint(5, 18),  "details": {}, "bull_case": f"+{rr*5:.0f}% in 5d", "base_case": f"+{rr*3:.0f}% in 5d", "bear_case": f"-3% stop"},
            "sentiment":    {"score": random.randint(2, 9),   "details": {}},
            "bear_setup":   {"score": 0 if direction == "long" else random.randint(8, 14), "details": {}},
            "trade_plan": {
                "entry_low": entry, "entry_high": round(entry * 1.005, 2),
                "stop": stop, "target1": t1, "target2": round(price * (1.15 if direction == "long" else 0.86), 2),
                "rr_ratio": rr, "setup_type": setup, "allocation_pct": 7.5,
            },
            "catalyst_tags": ["Earnings beat"] if random.random() > 0.7 else [],
            "trade_thesis": f"{setup} on {tk} — {score}/100 score",
            "conviction": {"label": "High" if score >= 75 else "Medium" if score >= 60 else "Standard"},
            "entry_quality": "good",
            "zacks_vgm": {"value": random.choice(["A","B","C"]), "growth": random.choice(["A","B","C"]), "momentum": random.choice(["A","B","C"]), "vgm": random.choice(["A","B","C"])},
            "analyst": {},
            "stocktwits": {},
        }
        if verdict == "KILLED":
            killed.append(r)
        else:
            all_scored.append(r)

    buy_list = [r["ticker"] for r in all_scored if r["decision"]["verdict"] == "BUY"]
    sell_list = [r["ticker"] for r in all_scored if r["decision"]["verdict"] in ("SHORT", "AVOID")]
    watch_list = [r for r in all_scored if r["decision"]["verdict"] == "WATCH"]

    return {
        "config": {"output": {"html_output": "cache/dashboard.html"}},
        "run_date": datetime.now().strftime("%Y-%m-%d"),
        "buy_candidates":  [r for r in all_scored if r["decision"]["verdict"] == "BUY"],
        "sell_candidates": [r for r in all_scored if r["decision"]["verdict"] in ("SHORT", "AVOID")],
        "watch_list":      watch_list,
        "all_scored":      all_scored,
        "killed":          killed,
        "regime": {
            "regime": "bull", "spy_price": 494.50, "spy_1m_ret": 1.2,
            "above_50ema": True, "above_200sma": True,
            "market_cycle": "mid_bull", "distribution_days": 2,
            "vix": {"vix_current": 18.4, "regime": "normal", "trend": "stable"},
        },
        "market_breadth": {
            "pct_above_50d": 64.0, "label_50": "moderate",
            "pct_above_100d": 58.0, "label_100": "moderate",
        },
        "macro_signals": {
            "risk_signal": "risk-on",
            "yield_curve": {"spread": 0.32, "inverted": False},
            "hyg": {"trend": "up"}, "dxy": {"trend": "down"},
        },
        "sector_etf_data": {},
        "fear_greed": {"value": 58, "label": "Greed"},
        "industries": [],  # built from all_scored in _tab_industries
        "portfolio_risk": {},
        "price_tier_results": [],
        "zacks_r1_full": buy_list,
        "zacks_r1_scores": {r["ticker"]: r["zacks_vgm"] for r in all_scored if r.get("zacks_rank1")},
        "zacks_r1_missing": {},
        "zacks_sell_list_raw": [{"ticker": t, "company": next((r["name"] for r in all_scored if r["ticker"]==t), "")} for t in sell_list],
        "ultimate": {
            "overview": {"description": "Sample data — run a full scan for live data.", "stats": {"Total Trades": "329", "Avg Return": "+18.4%", "Win Rate": "67%"}, "highlights": []},
            "all_trades": [],
            "commentary": [{"title": "Sample Commentary", "author": "Dev Mode", "date": datetime.now().strftime("%m/%d/%y"), "body_text": "This is sample data generated for UI development. Run /swing-trade for live data."}],
            "special_reports": [],
            "confidential_commentary": [],
            "confidential_overview": {},
        },
        "tazr": {"trades": [], "portfolio_stats": {}, "commentary": []},
        "bbt": {"trades": [], "portfolio_stats": {}, "commentary": []},
        "counterstrike": {"trades": [], "portfolio_stats": {}, "commentary": []},
        "headlinetrader": {"trades": [], "portfolio_stats": {}, "commentary": []},
        "alt_energy": {"trades": [], "portfolio_stats": {}, "commentary": []},
        "blockchain": {"trades": [], "portfolio_stats": {}, "commentary": []},
        "tech_innovators": {"trades": [], "portfolio_stats": {}, "commentary": []},
        "social": {},
        "gmail_zacks": {},
        "watch_trigger_hits": [],
        "sp500_list": [r["ticker"] for r in all_scored],
        "russell1000_list": [r["ticker"] for r in all_scored],
        "market_data_count": len(all_scored),
        "total_scanned": len(all_scored),
        "run_timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "scores_table": all_scored,
    }


if __name__ == "__main__":
    args = sys.argv[1:]

    # File lock: prevent concurrent swing_trade.py runs racing on bundle write.
    # 2026-05-07: caught 2 schedulers (cron + launchd) firing overlapping scans.
    # Lock applies only to the daily scan path; deep-dive / history etc. don't lock.
    if not args or (len(args) == 1 and args[0].lower() == "--fresh"):
        import fcntl as _fcntl
        _LOCK_PATH = "/tmp/swing_trade_scan.lock"
        try:
            _scan_lock = open(_LOCK_PATH, "w")
            _fcntl.flock(_scan_lock, _fcntl.LOCK_EX | _fcntl.LOCK_NB)
            _scan_lock.write(f"pid={os.getpid()} started={datetime.now().isoformat()}\n")
            _scan_lock.flush()
        except (IOError, OSError) as _le:
            print(f"❌ ABORT: another swing_trade.py scan is running ({_LOCK_PATH} locked). "
                  f"Kill it manually if stuck. Error: {_le}", file=sys.stderr)
            sys.exit(2)

    if not args or (len(args) == 1 and args[0].lower() == "--fresh"):
        try:
            run_daily_scan(force_fresh="--fresh" in args)
        except Exception as _scan_exc:
            # scan-failure alert (Q2) — a crashed scan was silent before; ping Slack then re-raise.
            try:
                import json as _json, urllib.request as _ur, traceback as _tb
                _wh = os.environ.get("SLACK_WEBHOOK_URL", "")
                if _wh:
                    _ur.urlopen(_ur.Request(
                        _wh, data=_json.dumps({"text": f":rotating_light: *SwingTrade scan FAILED* — "
                        f"{type(_scan_exc).__name__}: {str(_scan_exc)[:300]}"}).encode(),
                        headers={"Content-Type": "application/json"}), timeout=8)
                log.error("Scan failed: %s", _tb.format_exc())
            except Exception:
                pass
            raise
        # Append today's top-20 Momentum candidates to data/momentum_snapshots.jsonl
        # so the HISTORY sub-view of the Momentum tab can build a predicted-vs-
        # realized calibration over time. Idempotent per-date; never raises.
        try:
            import momentum_snapshot as _ms
            _msr = _ms.write_snapshot()
            try:
                log.info(f"momentum_snapshot: {_msr.get('status')} "
                         f"date={_msr.get('date')} written={_msr.get('written')} "
                         f"of {_msr.get('total_candidates','-')} candidates")
            except Exception:
                pass
        except Exception as _mse:
            try: log.warning(f"momentum_snapshot failed: {_mse}")
            except Exception: pass
    elif args[0].lower() == "deep" and len(args) > 1:
        run_deep_dive(args[1].upper())
    elif args[0].lower() == "history":
        show_history()
    elif args[0].lower() == "add" and len(args) >= 5:
        # add TICKER ENTRY SHARES STOP TARGET1 [TARGET2]
        from portfolio_tracker import add_position
        ticker = args[1].upper()
        entry = float(args[2])
        shares = int(float(args[3]))
        stop = float(args[4])
        target1 = float(args[5]) if len(args) > 5 else entry * 1.10
        target2 = float(args[6]) if len(args) > 6 else None
        pos = add_position(ticker, entry, shares, stop, target1, target2)
        _entry_px = pos.get('entry_price', pos.get('entry'))
        print(f"Added: {pos['ticker']} {pos['shares']}sh @ ${_entry_px} | Stop ${pos['stop']} | T1 ${pos['target1']}")
    elif args[0].lower() == "close" and len(args) >= 3:
        # close TICKER EXIT_PRICE
        from portfolio_tracker import close_position
        result = close_position(args[1].upper(), float(args[2]))
        if result:
            print(f"Closed: {result['ticker']} @ ${result['exit_price']} | P&L {result['pnl_pct']:+.1f}%")
    elif args[0].lower() in ("regen", "dev"):
        # Phase A (2026-05-08): regen now rebuilds V2 prototype data from the
        # cached bundle — no scan, no API calls, no legacy HTML generation.
        # Use case: pull a tested change to build_data.py / V2 templates and
        # see it on the V2 dashboard without a full 12-min scan.
        bundle_path = BASE_DIR / "cache" / "last_bundle.json"
        if not bundle_path.exists():
            print("No cached bundle found at cache/last_bundle.json.")
            print("Run a full scan first: python3 swing_trade.py")
        else:
            try:
                import subprocess
                _pb = BASE_DIR / "infra" / "prototype" / "build_data.py"
                if not _pb.exists():
                    print("ERROR: infra/prototype/build_data.py is missing")
                else:
                    _r = subprocess.run(["python3", str(_pb)], check=False, capture_output=True, timeout=180)
                    if _r.returncode == 0:
                        print("V2 prototype data refreshed: http://localhost:7432/kairos.html")
                    else:
                        _err = (_r.stderr or b"").decode("utf-8", errors="replace").strip()[-800:]
                        print(f"FAIL: build_data.py exited {_r.returncode}\n{_err}")
            except subprocess.TimeoutExpired:
                print("FAIL: build_data.py timed out after 180s")
            except Exception as _pe:
                print(f"FAIL: {_pe}")
    elif args[0].lower() == "sample":
        # Phase B (2026-05-08): legacy sample-dashboard generation retired.
        # Sample bundle is still saved so V2 dev can regen V2 from mock data.
        _sample_bundle = _build_sample_bundle()
        _sbp = BASE_DIR / "cache" / "sample_bundle.json"
        _sbp.parent.mkdir(parents=True, exist_ok=True)
        with open(_sbp, "w") as _sf:
            json.dump(_sample_bundle, _sf, default=str)
        print(f"Sample bundle saved: {_sbp}")
        print(f"To preview in V2 dev mode, copy to cache/last_bundle.json then run:")
        print(f"  python3 swing_trade.py regen")
    else:
        print("Usage:")
        print("  python3 swing_trade.py                              # Daily scan (uses Zacks cache if <20h old)")
        print("  python3 swing_trade.py --fresh                     # Daily scan, force fresh Zacks scrape")
        print("  python3 swing_trade.py regen                       # Re-render dashboard (no re-scan) [alias: dev]")
        print("  python3 swing_trade.py sample                      # Generate sample dashboard with mock data")
        print("  python3 swing_trade.py deep NVDA                   # Deep dive")
        print("  python3 swing_trade.py history                     # Performance stats")
        print("  python3 swing_trade.py add NVDA 89.50 100 83.50 98.00  # Add position")
        print("  python3 swing_trade.py close NVDA 94.00            # Close position")
