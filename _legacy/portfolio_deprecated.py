"""
DEPRECATED - DO NOT IMPORT FROM THIS MODULE.

This file was the original portfolio manager (cache/portfolio.json schema).
It has been superseded by `portfolio_tracker.py`, which is now the single
source of truth for portfolio state (data/portfolio_state.json schema).

All previously-public helpers have been ported to portfolio_tracker.py:
    add_position, close_position, get_portfolio_summary, refresh_prices,
    load_portfolio, check_correlation_risk, get_portfolio_correlation_matrix,
    compute_pairwise_correlation, PORTFOLIO_PATH (= STATE_PATH alias).

This file is retained temporarily so git history is preserved and so the
old cache/portfolio.json contents remain readable via its _load() helper
if any forensic recovery is ever needed.  It is NOT imported by any live
module as of 2026-04-14 and should be deleted in a future cleanup pass.

----- ORIGINAL MODULE DOCSTRING BELOW -----
Portfolio tracker for SwingTrade.
Tracks open/closed positions with real-time P&L via yfinance.
Stored in cache/portfolio.json
"""
from __future__ import annotations

import warnings as _warnings
_warnings.warn(
    "portfolio_deprecated is dead code; import from portfolio_tracker instead.",
    DeprecationWarning,
    stacklevel=2,
)

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

log = logging.getLogger("swingtrade.portfolio")

BASE_DIR = Path(__file__).parent
PORTFOLIO_PATH = BASE_DIR / "cache" / "portfolio.json"


def _load() -> dict:
    if PORTFOLIO_PATH.exists():
        with open(PORTFOLIO_PATH) as f:
            return json.load(f)
    return {"positions": [], "closed": []}


def _save(data: dict):
    PORTFOLIO_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PORTFOLIO_PATH, "w") as f:
        json.dump(data, f, indent=2, default=str)


def add_position(ticker: str, entry: float, shares: float,
                 stop: float, target1: float, target2: float | None = None,
                 setup: str = "", allocation_pct: float = 7.5,
                 direction: str = "long", notes: str = "", entry_date: str | None = None) -> dict:
    """Add a new open position."""
    data = _load()
    pos = {
        "id": len(data["positions"]) + len(data["closed"]) + 1,
        "ticker": ticker.upper(),
        "direction": direction,
        "entry": round(entry, 2),
        "shares": shares,
        "stop": round(stop, 2),
        "target1": round(target1, 2),
        "target2": round(target2, 2) if target2 else None,
        "setup": setup,
        "allocation_pct": allocation_pct,
        "notes": notes,
        "entry_date": entry_date or datetime.now().strftime("%Y-%m-%d"),
        "status": "open",
        "current_price": entry,
        "unrealized_pnl_pct": 0.0,
        "unrealized_pnl_dollars": 0.0,
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    data["positions"].append(pos)
    _save(data)
    log.info(f"Added position: {ticker} {shares} shares @ ${entry}")
    return pos


def close_position(ticker: str, exit_price: float, exit_date: str | None = None,
                   exit_reason: str = "manual") -> dict | None:
    """Close an open position.

    Args:
        ticker:      Ticker symbol.
        exit_price:  Price at close.
        exit_date:   Date string (YYYY-MM-DD), defaults to today.
        exit_reason: Why the trade was closed — one of:
                     "hit_stop" | "hit_t1" | "hit_t2" | "trailing_stop" |
                     "time_stop" | "manual" | "drawdown_kill"
    """
    data = _load()
    ticker = ticker.upper()

    for i, pos in enumerate(data["positions"]):
        if pos["ticker"] == ticker and pos["status"] == "open":
            exit_date = exit_date or datetime.now().strftime("%Y-%m-%d")
            entry = pos["entry"]
            if pos["direction"] == "long":
                pnl_pct = (exit_price - entry) / entry * 100
            else:
                pnl_pct = (entry - exit_price) / entry * 100
            pnl_dollars = pnl_pct / 100 * entry * pos["shares"]

            # Auto-detect exit reason from price vs stop/target if not specified
            _auto_reason = exit_reason
            if exit_reason == "manual":
                t1 = pos.get("target1", 0) or 0
                t2 = pos.get("target2", 0) or 0
                stop = pos.get("stop", 0) or 0
                direction = pos.get("direction", "long")
                if direction == "long":
                    if stop and exit_price <= stop * 1.005:
                        _auto_reason = "hit_stop"
                    elif t2 and exit_price >= t2 * 0.995:
                        _auto_reason = "hit_t2"
                    elif t1 and exit_price >= t1 * 0.995:
                        _auto_reason = "hit_t1"
                else:  # short
                    if stop and exit_price >= stop * 0.995:
                        _auto_reason = "hit_stop"
                    elif t2 and exit_price <= t2 * 1.005:
                        _auto_reason = "hit_t2"
                    elif t1 and exit_price <= t1 * 1.005:
                        _auto_reason = "hit_t1"

            closed = {**pos,
                      "status": "closed",
                      "exit_price": round(exit_price, 2),
                      "exit_date": exit_date,
                      "exit_reason": _auto_reason,
                      "pnl_pct": round(pnl_pct, 2),
                      "pnl_dollars": round(pnl_dollars, 2),
                      "win": pnl_pct > 0}
            data["closed"].append(closed)
            data["positions"].pop(i)
            _save(data)
            log.info(f"Closed {ticker} @ ${exit_price} | P&L: {pnl_pct:+.1f}% | Reason: {_auto_reason}")
            return closed
    log.warning(f"No open position found for {ticker}")
    return None


def refresh_prices() -> list[dict]:
    """Fetch current prices for all open positions and update P&L."""
    data = _load()
    if not data["positions"]:
        return []

    tickers = [p["ticker"] for p in data["positions"]]
    try:
        raw = yf.download(tickers if len(tickers) > 1 else tickers[0],
                          period="1d", interval="1m", progress=False)
        prices = {}
        if len(tickers) == 1:
            if not raw.empty:
                prices[tickers[0]] = float(raw["Close"].iloc[-1])
        else:
            for t in tickers:
                try:
                    prices[t] = float(raw["Close"][t].dropna().iloc[-1])
                except Exception:
                    pass
    except Exception:
        prices = {}

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    for pos in data["positions"]:
        t = pos["ticker"]
        if t in prices:
            cur = prices[t]
            entry = pos["entry"]
            if pos["direction"] == "long":
                pnl_pct = (cur - entry) / entry * 100
            else:
                pnl_pct = (entry - cur) / entry * 100
            pnl_dollars = pnl_pct / 100 * entry * pos["shares"]
            pos["current_price"] = round(cur, 2)
            pos["unrealized_pnl_pct"] = round(pnl_pct, 2)
            pos["unrealized_pnl_dollars"] = round(pnl_dollars, 2)
            pos["last_updated"] = now

            # Auto-flag stop/target hits
            if pos["direction"] == "long":
                pos["stop_hit"] = cur <= pos["stop"]
                pos["t1_hit"] = cur >= pos["target1"]
                pos["t2_hit"] = pos.get("target2") and cur >= pos["target2"]
            else:
                pos["stop_hit"] = cur >= pos["stop"]
                pos["t1_hit"] = cur <= pos["target1"]
                pos["t2_hit"] = pos.get("target2") and cur <= pos["target2"]

            # Trailing stop: move stop to breakeven AFTER T1 is hit (not at arbitrary +2%)
            # This matches professional partial-close discipline:
            # 1) T1 hit → close 50% and move stop to entry + 0.5% slippage buffer
            # 2) After breakeven stop set → trail by ATR as price extends
            try:
                entry     = float(pos["entry"])
                cur       = float(pos.get("current_price", entry))
                atr_est   = entry * 0.025  # ~2.5% fallback ATR if unavailable
                direction = pos.get("direction", "long")

                # Move stop to breakeven only after T1 is confirmed hit
                if pos.get("t1_hit"):
                    if direction == "long":
                        be_stop = round(entry * 1.005, 2)  # entry + 0.5% slippage buffer
                        if pos.get("stop", 0) < be_stop:
                            pos["stop"] = be_stop
                            pos["stop_note"] = "Moved to breakeven after T1"
                    elif direction == "short":
                        be_stop = round(entry * 0.995, 2)
                        if pos.get("stop", 9999) > be_stop:
                            pos["stop"] = be_stop
                            pos["stop_note"] = "Moved to breakeven after T1"

                # T1 partial close flag — alert once, mark taken to prevent repeat
                if pos.get("t1_hit") and not pos.get("t1_partial_taken"):
                    pos["t1_partial_alert"] = True   # alert trader to close 50% at T1
            except Exception:
                pass

    _save(data)
    return data["positions"]


def get_portfolio_summary() -> dict:
    """Compute portfolio-level stats."""
    data = _load()
    positions = data["positions"]
    closed = data["closed"]

    open_pnl = sum(p.get("unrealized_pnl_dollars", 0) for p in positions)
    closed_pnl = sum(p.get("pnl_dollars", 0) for p in closed)
    total_alloc = sum(p.get("allocation_pct", 0) for p in positions)

    wins = [p for p in closed if p.get("win")]
    losses = [p for p in closed if not p.get("win")]
    win_rate = len(wins) / len(closed) * 100 if closed else 0

    return {
        "open_positions": len(positions),
        "closed_trades": len(closed),
        "open_pnl_dollars": round(open_pnl, 2),
        "closed_pnl_dollars": round(closed_pnl, 2),
        "total_allocation_pct": round(total_alloc, 1),
        "win_rate": round(win_rate, 1),
        "wins": len(wins),
        "losses": len(losses),
        "positions": positions,
        "closed": closed[-20:]  # last 20 closed trades
    }


def load_portfolio() -> dict:
    """Public alias for _load() — returns raw portfolio dict with 'positions' and 'closed' keys."""
    return _load()


# ---------------------------------------------------------------------------
# Correlation cache: avoids re-downloading on every API call.
# Keyed by frozenset of tickers + period; expires after CORR_CACHE_TTL_MINUTES.
# ---------------------------------------------------------------------------
_corr_cache: dict[str, tuple[datetime, pd.DataFrame]] = {}
_CORR_CACHE_TTL_MINUTES = 30


def _get_returns(tickers: list[str], period: str = "3mo") -> pd.DataFrame:
    """
    Download daily close prices for the given tickers and return a DataFrame
    of daily percentage returns, one column per ticker.
    Uses an in-memory cache (TTL = 30 minutes) to avoid redundant downloads.
    """
    if not tickers:
        return pd.DataFrame()

    cache_key = f"{sorted(tickers)}|{period}"
    now = datetime.now()

    if cache_key in _corr_cache:
        cached_at, cached_df = _corr_cache[cache_key]
        if now - cached_at < timedelta(minutes=_CORR_CACHE_TTL_MINUTES):
            return cached_df

    try:
        raw = yf.download(
            tickers if len(tickers) > 1 else tickers[0],
            period=period,
            interval="1d",
            progress=False,
            auto_adjust=True,
        )
        if raw.empty:
            return pd.DataFrame()

        # Normalise multi-level columns produced by batch download
        if len(tickers) == 1:
            close = raw["Close"].squeeze().rename(tickers[0])
            prices = pd.DataFrame({tickers[0]: close})
        else:
            if raw.columns.nlevels > 1:
                prices = raw["Close"]
            else:
                prices = raw[["Close"]]

        returns = prices.pct_change().dropna(how="all")
        _corr_cache[cache_key] = (now, returns)
        return returns
    except Exception as e:
        log.warning(f"_get_returns failed for {tickers}: {e}")
        return pd.DataFrame()


def compute_pairwise_correlation(tickers: list[str], period: str = "3mo") -> dict:
    """
    Compute pairwise Pearson correlation between tickers using daily returns.

    Returns a dict keyed by sorted tuple pairs:
        {("AMD", "NVDA"): 0.85, ...}

    Handles missing data gracefully — pairs with fewer than 20 overlapping
    bars are skipped (correlation would be statistically meaningless).
    """
    if len(tickers) < 2:
        return {}

    returns = _get_returns(tickers, period)
    if returns.empty or returns.shape[1] < 2:
        return {}

    # Only keep columns that actually correspond to requested tickers
    available = [t for t in tickers if t in returns.columns]
    if len(available) < 2:
        return {}

    corr_matrix = returns[available].corr(method="pearson")
    pairs: dict[tuple[str, str], float] = {}

    for i, t1 in enumerate(available):
        for t2 in available[i + 1:]:
            # Require at least 20 overlapping non-NaN bars
            overlap = returns[[t1, t2]].dropna()
            if len(overlap) < 20:
                continue
            val = corr_matrix.loc[t1, t2]
            if pd.isna(val):
                continue
            pair = tuple(sorted([t1, t2]))
            pairs[pair] = round(float(val), 4)

    return pairs


def check_correlation_risk(
    candidate: str,
    open_positions: list[str],
    threshold: float = 0.80,
    period: str = "3mo",
    sector_map: Optional[dict[str, str]] = None,
) -> dict:
    """
    Check if a new candidate is highly correlated with any open position.

    Parameters
    ----------
    candidate       : ticker symbol to evaluate (e.g. "NVDA")
    open_positions  : list of currently held ticker symbols
    threshold       : Pearson correlation above which a position is flagged (default 0.80)
    period          : lookback period for yfinance (default "3mo")
    sector_map      : optional pre-built {ticker: sector} dict; if omitted, sectors
                      are fetched via yf.Ticker.info (one call per ticker)

    Returns
    -------
    {
        "has_risk"       : bool,
        "correlated_with": [{"ticker": str, "correlation": float}, ...],
        "max_correlation": float,
        "sector_count"   : {"Technology": 2, ...},
        "sector_risk"    : bool,   # True if any sector has > 2 positions incl. candidate
    }
    """
    candidate = candidate.upper()
    open_positions = [t.upper() for t in open_positions]

    if not open_positions:
        return {
            "has_risk": False,
            "correlated_with": [],
            "max_correlation": 0.0,
            "sector_count": {},
            "sector_risk": False,
            "message": "No open positions to compare against",
        }

    all_tickers = [candidate] + open_positions
    pairs = compute_pairwise_correlation(all_tickers, period=period)

    # Filter pairs that involve the candidate
    correlated_with = []
    for (t1, t2), corr in pairs.items():
        other = None
        if t1 == candidate:
            other = t2
        elif t2 == candidate:
            other = t1
        if other and corr >= threshold:
            correlated_with.append({"ticker": other, "correlation": corr})

    correlated_with.sort(key=lambda x: x["correlation"], reverse=True)
    max_corr = correlated_with[0]["correlation"] if correlated_with else 0.0

    # Sector concentration
    sector_count: dict[str, int] = {}
    if sector_map is None:
        sector_map = {}
        for t in all_tickers:
            try:
                info = yf.Ticker(t).info
                sec = info.get("sector") or "Unknown"
            except Exception:
                sec = "Unknown"
            sector_map[t] = sec

    for t in all_tickers:
        sec = sector_map.get(t, "Unknown")
        sector_count[sec] = sector_count.get(sec, 0) + 1

    sector_risk = any(v > 2 for v in sector_count.values())

    return {
        "has_risk": bool(correlated_with) or sector_risk,
        "correlated_with": correlated_with,
        "max_correlation": round(max_corr, 4),
        "sector_count": sector_count,
        "sector_risk": sector_risk,
    }


def get_portfolio_correlation_matrix(period: str = "3mo") -> dict:
    """
    Compute full Pearson correlation matrix for all open positions.

    Returns
    -------
    {
        "tickers"    : ["AMD", "NVDA", ...],
        "matrix"     : [[1.0, 0.85, ...], ...],   # N x N, JSON-serialisable
        "high_pairs" : [{"t1": str, "t2": str, "corr": float}, ...],  # pairs > 0.70
    }
    """
    data = _load()
    positions = data.get("positions", [])
    tickers = [p["ticker"] for p in positions if p.get("ticker")]

    if len(tickers) < 2:
        return {
            "tickers": tickers,
            "matrix": [[1.0]] if len(tickers) == 1 else [],
            "high_pairs": [],
            "message": "Need at least 2 open positions for a correlation matrix",
        }

    returns = _get_returns(tickers, period)
    available = [t for t in tickers if t in returns.columns]

    if len(available) < 2:
        return {
            "tickers": tickers,
            "matrix": [],
            "high_pairs": [],
            "message": "Insufficient price data for open positions",
        }

    corr_df = returns[available].corr(method="pearson")

    # Convert to plain list of lists (JSON-safe, NaN → null)
    matrix = []
    for row_t in available:
        row = []
        for col_t in available:
            val = corr_df.loc[row_t, col_t]
            try:
                row.append(None if np.isnan(float(val)) else round(float(val), 4))
            except (TypeError, ValueError):
                row.append(None)
        matrix.append(row)

    # Identify high-correlation pairs (above 0.70)
    HIGH_THRESHOLD = 0.70
    high_pairs = []
    for i, t1 in enumerate(available):
        for t2 in available[i + 1:]:
            val = corr_df.loc[t1, t2]
            try:
                val_f = float(val)
            except (TypeError, ValueError):
                continue
            if not np.isnan(val_f) and val_f >= HIGH_THRESHOLD:
                high_pairs.append({"t1": t1, "t2": t2, "corr": round(float(val), 4)})

    high_pairs.sort(key=lambda x: x["corr"], reverse=True)

    return {
        "tickers": available,
        "matrix": matrix,
        "high_pairs": high_pairs,
    }


# ── Fix #20: Portfolio correlation gate ────────────────────────────────────────

def check_correlation_gate(candidate: str, threshold: float = 0.70,
                           period: str = "3mo") -> dict:
    """
    Block new entries if the candidate has pairwise correlation > threshold
    with any existing open position.

    Uses get_portfolio_correlation_matrix() for existing positions, then
    checks pairwise correlation of the candidate against each.

    Returns:
        {
            "allowed": bool,       # True if candidate passes correlation gate
            "blocked_by": list,    # tickers with correlation > threshold
            "max_correlation": float,
            "message": str,
        }
    """
    data = _load()
    positions = data.get("positions", [])
    open_tickers = [p["ticker"] for p in positions if p.get("status") == "open"]

    if not open_tickers:
        return {
            "allowed": True,
            "blocked_by": [],
            "max_correlation": 0.0,
            "message": "No open positions — correlation gate passed",
        }

    candidate = candidate.upper()
    if candidate in open_tickers:
        return {
            "allowed": False,
            "blocked_by": [candidate],
            "max_correlation": 1.0,
            "message": f"Already holding {candidate}",
        }

    # Compute pairwise correlation between candidate and all open positions
    pairs = compute_pairwise_correlation([candidate] + open_tickers, period=period)

    blocked_by = []
    max_corr = 0.0
    for (t1, t2), corr in pairs.items():
        other = None
        if t1 == candidate:
            other = t2
        elif t2 == candidate:
            other = t1
        if other and corr > threshold:
            blocked_by.append({"ticker": other, "correlation": round(corr, 4)})
        if other:
            max_corr = max(max_corr, corr)

    blocked_by.sort(key=lambda x: x["correlation"], reverse=True)
    allowed = len(blocked_by) == 0

    if not allowed:
        blocked_names = ", ".join(f"{b['ticker']}({b['correlation']:.2f})" for b in blocked_by)
        msg = f"Correlation gate BLOCKED: {candidate} correlated >{threshold:.0%} with {blocked_names}"
    else:
        msg = f"Correlation gate passed: max corr {max_corr:.2f} < {threshold:.2f}"

    return {
        "allowed": allowed,
        "blocked_by": blocked_by,
        "max_correlation": round(max_corr, 4),
        "message": msg,
    }


# ── Fix #21: Open-risk budgeting ─────────────────────────────────────────────

def check_risk_budget(account_equity: float, config: dict,
                      candidate_risk_dollars: float = 0.0,
                      candidate_sector: str = "") -> dict:
    """
    Calculate current open risk and block new entries if risk budget limits exceeded.

    Open risk = sum(position_size_dollars * stop_distance_pct) for all open positions.

    Returns:
        {
            "allowed": bool,
            "total_open_risk_pct": float,
            "sector_risk": dict,
            "message": str,
        }
    """
    risk_cfg = config.get("risk_budget", {})
    max_total_risk = risk_cfg.get("max_total_open_risk_pct", 0.05)
    max_new_per_day = risk_cfg.get("max_new_risk_per_day_pct", 0.02)
    max_sector_risk = risk_cfg.get("max_open_risk_per_sector_pct", 0.02)

    data = _load()
    positions = data.get("positions", [])

    # Calculate current open risk
    total_open_risk = 0.0
    sector_risk: dict[str, float] = {}
    today_new_risk = 0.0
    today_str = datetime.now().strftime("%Y-%m-%d")

    for pos in positions:
        if pos.get("status") != "open":
            continue
        entry = pos.get("entry", 0)
        stop = pos.get("stop", 0)
        shares = pos.get("shares", 0)
        if entry <= 0 or shares <= 0:
            continue

        if pos.get("direction", "long") == "long":
            stop_dist_pct = (entry - stop) / entry if stop < entry else 0.02
        else:
            stop_dist_pct = (stop - entry) / entry if stop > entry else 0.02

        position_risk = shares * entry * stop_dist_pct
        total_open_risk += position_risk

        # Sector tracking
        sector = pos.get("sector", "Unknown")
        sector_risk[sector] = sector_risk.get(sector, 0.0) + position_risk

        # Track today's new entries
        if pos.get("entry_date", "") == today_str:
            today_new_risk += position_risk

    total_risk_pct = total_open_risk / account_equity if account_equity > 0 else 0
    today_risk_pct = today_new_risk / account_equity if account_equity > 0 else 0

    # Check limits
    reasons = []
    allowed = True

    # Total open risk check
    candidate_total = total_risk_pct + (candidate_risk_dollars / account_equity if account_equity > 0 else 0)
    if candidate_total > max_total_risk:
        allowed = False
        reasons.append(f"Total open risk {candidate_total:.1%} > limit {max_total_risk:.1%}")

    # Daily new risk check
    candidate_daily = today_risk_pct + (candidate_risk_dollars / account_equity if account_equity > 0 else 0)
    if candidate_daily > max_new_per_day:
        allowed = False
        reasons.append(f"Daily new risk {candidate_daily:.1%} > limit {max_new_per_day:.1%}")

    # Sector risk check
    if candidate_sector:
        sector_total = sector_risk.get(candidate_sector, 0.0) + candidate_risk_dollars
        sector_pct = sector_total / account_equity if account_equity > 0 else 0
        if sector_pct > max_sector_risk:
            allowed = False
            reasons.append(f"Sector '{candidate_sector}' risk {sector_pct:.1%} > limit {max_sector_risk:.1%}")

    return {
        "allowed": allowed,
        "total_open_risk_pct": round(total_risk_pct * 100, 2),
        "today_new_risk_pct": round(today_risk_pct * 100, 2),
        "sector_risk": {k: round(v / account_equity * 100, 2) if account_equity > 0 else 0
                        for k, v in sector_risk.items()},
        "message": "; ".join(reasons) if reasons else "Risk budget OK",
    }


# ── Fix #28: Account-level drawdown controls ──────────────────────────────────

def check_drawdown_controls(account_equity: float, config: dict) -> dict:
    """
    Track daily/weekly P&L and block new entries when drawdown limits are hit.

    Uses closed trades from portfolio history to compute rolling P&L.

    Returns:
        {
            "allowed": bool,
            "daily_pnl_pct": float,
            "weekly_pnl_pct": float,
            "rolling_drawdown_pct": float,
            "cool_off_until": str or None,
            "message": str,
        }
    """
    dd_cfg = config.get("drawdown_controls", {})
    daily_limit = dd_cfg.get("daily_loss_limit_pct", 0.02)
    weekly_limit = dd_cfg.get("weekly_loss_limit_pct", 0.05)
    rolling_throttle = dd_cfg.get("rolling_drawdown_throttle_pct", 0.10)
    cool_off_days = dd_cfg.get("cool_off_days", 2)

    data = _load()
    closed = data.get("closed", [])
    positions = data.get("positions", [])

    today = datetime.now().date()
    week_ago = today - timedelta(days=7)

    # Daily P&L from closed trades
    daily_pnl = 0.0
    weekly_pnl = 0.0
    for trade in closed:
        exit_date_str = trade.get("exit_date", "")
        try:
            exit_date = datetime.strptime(exit_date_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue
        pnl = trade.get("pnl_dollars", 0)
        if exit_date == today:
            daily_pnl += pnl
        if exit_date >= week_ago:
            weekly_pnl += pnl

    # Add unrealized P&L from open positions
    for pos in positions:
        unrealized = pos.get("unrealized_pnl_dollars", 0)
        weekly_pnl += unrealized
        daily_pnl += unrealized

    daily_pnl_pct = daily_pnl / account_equity if account_equity > 0 else 0
    weekly_pnl_pct = weekly_pnl / account_equity if account_equity > 0 else 0

    # Rolling drawdown from peak equity
    total_realized = sum(t.get("pnl_dollars", 0) for t in closed)
    total_unrealized = sum(p.get("unrealized_pnl_dollars", 0) for p in positions)
    current_equity = account_equity + total_realized + total_unrealized
    peak_equity = max(account_equity, current_equity)  # simplified — tracks from start
    rolling_dd = (peak_equity - current_equity) / peak_equity if peak_equity > 0 else 0

    allowed = True
    reasons = []
    cool_off_until = None

    if daily_pnl_pct < -daily_limit:
        allowed = False
        cool_off_until = (today + timedelta(days=cool_off_days)).strftime("%Y-%m-%d")
        reasons.append(f"Daily loss {daily_pnl_pct:.1%} exceeds limit {-daily_limit:.1%}")

    if weekly_pnl_pct < -weekly_limit:
        allowed = False
        cool_off_until = (today + timedelta(days=cool_off_days)).strftime("%Y-%m-%d")
        reasons.append(f"Weekly loss {weekly_pnl_pct:.1%} exceeds limit {-weekly_limit:.1%}")

    if rolling_dd > rolling_throttle:
        allowed = False
        reasons.append(f"Rolling drawdown {rolling_dd:.1%} exceeds throttle {rolling_throttle:.1%}")

    return {
        "allowed": allowed,
        "daily_pnl_pct": round(daily_pnl_pct * 100, 2),
        "weekly_pnl_pct": round(weekly_pnl_pct * 100, 2),
        "rolling_drawdown_pct": round(rolling_dd * 100, 2),
        "cool_off_until": cool_off_until,
        "message": "; ".join(reasons) if reasons else "Drawdown controls OK — trading allowed",
    }


# ── Phase 1: Forced Exit Logic (Change 21) ──────────────────────────────────

def check_forced_exits(config: dict | None = None) -> list[dict]:
    """
    Check if any open positions should be force-exited due to:
    1. Max hold days exceeded (default 5d)
    2. Flat after N days with no profit (default 3d)

    For swing trading, we don't want losers lingering. Exit if:
    - Held for 5+ days (max swing hold period)
    - Held for 3+ days and still flat (within ±1%)

    Returns: list of positions to exit with reason
    """
    data = _load()
    positions = data.get("positions", [])

    if not config:
        config = {}

    max_hold_days = config.get("portfolio", {}).get("position_management", {}).get("max_hold_days", 5)
    exit_flat_after_days = config.get("portfolio", {}).get("position_management", {}).get("exit_if_flat_after_days", 3)

    to_exit = []

    for pos in positions:
        entry_date_str = pos.get("entry_date", datetime.now().strftime("%Y-%m-%d"))
        try:
            entry_date = datetime.strptime(entry_date_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            entry_date = datetime.now().date()

        days_held = (datetime.now().date() - entry_date).days

        # Try to get current price
        try:
            ticker = pos["ticker"]
            current_data = yf.download(ticker, period="1d", progress=False)
            current_price = float(current_data["Close"].iloc[-1])
        except Exception:
            current_price = pos["entry"]

        # Calculate current % change
        if pos["direction"] == "long":
            current_pct = (current_price - pos["entry"]) / pos["entry"] * 100
        else:  # short
            current_pct = (pos["entry"] - current_price) / pos["entry"] * 100

        # Rule 1: Force exit after max_hold_days
        if days_held >= max_hold_days:
            to_exit.append({
                "ticker": pos["ticker"],
                "id": pos.get("id"),
                "reason": f"Max hold days ({max_hold_days}d) reached",
                "days_held": days_held,
                "current_pct": round(current_pct, 2),
                "exit_price": "market"
            })

        # Rule 2: Exit if flat after exit_flat_after_days
        elif days_held >= exit_flat_after_days and abs(current_pct) < 1.0:
            to_exit.append({
                "ticker": pos["ticker"],
                "id": pos.get("id"),
                "reason": f"Flat after {exit_flat_after_days}d ({current_pct:+.1f}%) — no progress",
                "days_held": days_held,
                "current_pct": round(current_pct, 2),
                "exit_price": "market"
            })

    return to_exit
