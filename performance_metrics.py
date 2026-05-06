"""Performance analytics module for the swing-trade dashboard Performance Tab."""

from __future__ import annotations

import statistics
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _closed(trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return only closed trades (have exit_date and pnl_dollar)."""
    out = []
    for t in trades or []:
        if t.get("exit_date") and t.get("pnl_dollar") is not None:
            out.append(t)
    return out


def _parse_date(s: Any) -> Optional[date]:
    """Parse an ISO date string into a date, or return None."""
    if s is None:
        return None
    if isinstance(s, (datetime,)):
        return s.date()
    if isinstance(s, date):
        return s
    try:
        return datetime.fromisoformat(str(s)[:10]).date()
    except Exception:
        return None


def _sorted_by_exit(trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sort closed trades by exit_date ascending."""
    return sorted(
        _closed(trades),
        key=lambda t: _parse_date(t.get("exit_date")) or date.min,
    )


def _pct_color(pct: float) -> str:
    """Map pnl pct to a hex color (red/green gradient)."""
    if pct is None or np.isnan(pct):
        return "#cccccc"
    clamped = max(-20.0, min(20.0, float(pct)))
    intensity = int(min(255, abs(clamped) / 20.0 * 200 + 40))
    if clamped >= 0:
        return f"#{0:02x}{intensity:02x}{0:02x}"
    return f"#{intensity:02x}{0:02x}{0:02x}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_equity_curve(
    trades: List[Dict[str, Any]], starting_equity: float = 5000
) -> List[Dict[str, Any]]:
    """Return equity curve as list of {date, equity, pnl_cumulative} sorted by exit_date."""
    closed = _sorted_by_exit(trades)
    out: List[Dict[str, Any]] = []
    equity = float(starting_equity)
    cum = 0.0
    for t in closed:
        pnl = float(t.get("pnl_dollar") or 0.0)
        equity += pnl
        cum += pnl
        d = _parse_date(t.get("exit_date"))
        out.append(
            {
                "date": d.isoformat() if d else None,
                "equity": round(equity, 2),
                "pnl_cumulative": round(cum, 2),
            }
        )
    return out


def compute_drawdown_stats(equity_curve: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute max/current drawdown and average recovery days from an equity curve."""
    if not equity_curve:
        return {
            "max_dd_pct": 0.0,
            "max_dd_dates": (None, None),
            "current_dd_pct": 0.0,
            "days_in_current_dd": 0,
            "avg_recovery_days": 0.0,
        }

    eq = [float(p["equity"]) for p in equity_curve]
    dates = [_parse_date(p["date"]) for p in equity_curve]
    peak = eq[0]
    peak_date = dates[0]
    max_dd = 0.0
    max_peak_d: Optional[date] = None
    max_trough_d: Optional[date] = None

    recoveries: List[int] = []
    in_dd = False
    dd_peak_eq = peak
    dd_peak_date = peak_date

    for i, e in enumerate(eq):
        if e > peak:
            peak = e
            peak_date = dates[i]
            if in_dd:
                if dd_peak_date and dates[i]:
                    recoveries.append((dates[i] - dd_peak_date).days)
                in_dd = False
        dd = (e - peak) / peak * 100.0 if peak else 0.0
        if dd < max_dd:
            max_dd = dd
            max_peak_d = peak_date
            max_trough_d = dates[i]
        if e < peak and not in_dd:
            in_dd = True
            dd_peak_eq = peak
            dd_peak_date = peak_date

    current_dd = (eq[-1] - peak) / peak * 100.0 if peak else 0.0
    days_in_current_dd = 0
    if current_dd < 0 and peak_date and dates[-1]:
        days_in_current_dd = (dates[-1] - peak_date).days

    avg_recovery = float(np.mean(recoveries)) if recoveries else 0.0

    return {
        "max_dd_pct": round(max_dd, 2),
        "max_dd_dates": (
            max_peak_d.isoformat() if max_peak_d else None,
            max_trough_d.isoformat() if max_trough_d else None,
        ),
        "current_dd_pct": round(current_dd, 2),
        "days_in_current_dd": int(days_in_current_dd),
        "avg_recovery_days": round(avg_recovery, 1),
    }


def compute_risk_metrics(
    equity_curve: List[Dict[str, Any]],
    daily_returns: Optional[List[float]] = None,
) -> Dict[str, Any]:
    """Compute Sharpe, Sortino, Calmar and daily-return stats (rf=0, annualized)."""
    zero = {
        "sharpe_ann": 0.0,
        "sortino_ann": 0.0,
        "calmar": 0.0,
        "avg_daily_return": 0.0,
        "std_daily_return": 0.0,
    }
    if daily_returns is None:
        if len(equity_curve) < 2:
            return zero
        eq = np.array([float(p["equity"]) for p in equity_curve], dtype=float)
        daily_returns = list(np.diff(eq) / eq[:-1])

    if not daily_returns:
        return zero

    arr = np.array(daily_returns, dtype=float)
    avg = float(np.mean(arr))
    std = float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0
    downside = arr[arr < 0]
    d_std = float(np.std(downside, ddof=1)) if len(downside) > 1 else 0.0

    sharpe = float(avg / std * np.sqrt(252)) if std > 0 else 0.0
    sortino = float(avg / d_std * np.sqrt(252)) if d_std > 0 else 0.0

    calmar = 0.0
    if equity_curve:
        dd = compute_drawdown_stats(equity_curve)
        max_dd = abs(dd["max_dd_pct"]) / 100.0
        ann_return = avg * 252
        calmar = (ann_return / max_dd) if max_dd > 0 else 0.0

    return {
        "sharpe_ann": round(sharpe, 3),
        "sortino_ann": round(sortino, 3),
        "calmar": round(calmar, 3),
        "avg_daily_return": round(avg, 5),
        "std_daily_return": round(std, 5),
    }


def compute_regime_attribution(trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group closed trades by regime and compute per-regime WR, avg pct and profit factor."""
    closed = _closed(trades)
    if not closed:
        return []

    groups: Dict[str, List[Dict[str, Any]]] = {}
    for t in closed:
        groups.setdefault(t.get("regime") or "unknown", []).append(t)

    out: List[Dict[str, Any]] = []
    for regime, ts in groups.items():
        n = len(ts)
        wins = sum(1 for t in ts if t.get("win") or (t.get("pnl_dollar") or 0) > 0)
        losses = n - wins
        wr = wins / n if n else 0.0
        avg_pct = float(np.mean([float(t.get("pnl_pct") or 0.0) for t in ts]))
        gross_win = sum(float(t.get("pnl_dollar") or 0.0) for t in ts if (t.get("pnl_dollar") or 0) > 0)
        gross_loss = abs(sum(float(t.get("pnl_dollar") or 0.0) for t in ts if (t.get("pnl_dollar") or 0) < 0))
        pf = (gross_win / gross_loss) if gross_loss > 0 else (float("inf") if gross_win > 0 else 0.0)
        out.append(
            {
                "regime": regime,
                "n": n,
                "wins": wins,
                "losses": losses,
                "wr": round(wr, 4),
                "avg_pct": round(avg_pct, 2),
                "pf": round(pf, 3) if pf != float("inf") else None,
            }
        )
    out.sort(key=lambda r: r["n"], reverse=True)
    return out


def compute_hold_period_stats(trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group closed trades by setup_family and compute hold-period stats."""
    closed = _closed(trades)
    if not closed:
        return []
    groups: Dict[str, List[int]] = {}
    for t in closed:
        d = t.get("days_held")
        if d is None:
            continue
        groups.setdefault(t.get("setup_family") or "unknown", []).append(int(d))
    out: List[Dict[str, Any]] = []
    for fam, days in groups.items():
        if not days:
            continue
        out.append(
            {
                "setup_family": fam,
                "avg_days": round(float(np.mean(days)), 2),
                "min_days": int(min(days)),
                "max_days": int(max(days)),
                "median_days": round(float(statistics.median(days)), 2),
                "n": len(days),
            }
        )
    out.sort(key=lambda r: r["n"], reverse=True)
    return out


def compute_time_of_day_stats(trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Bucket entries by ET time and compute WR / avg pct per bucket."""
    buckets = {
        "9:30-10:30 ET": [],
        "10:30-15:00 ET": [],
        "15:00-16:00 ET": [],
    }
    for t in _closed(trades):
        et = t.get("entry_time")
        if not et:
            continue
        try:
            hh, mm = str(et).split(":")[:2]
            minutes = int(hh) * 60 + int(mm)
        except Exception:
            continue
        if 9 * 60 + 30 <= minutes < 10 * 60 + 30:
            buckets["9:30-10:30 ET"].append(t)
        elif 10 * 60 + 30 <= minutes < 15 * 60:
            buckets["10:30-15:00 ET"].append(t)
        elif 15 * 60 <= minutes < 16 * 60:
            buckets["15:00-16:00 ET"].append(t)

    out: List[Dict[str, Any]] = []
    for label, ts in buckets.items():
        n = len(ts)
        wr = (sum(1 for t in ts if t.get("win") or (t.get("pnl_dollar") or 0) > 0) / n) if n else 0.0
        avg_pct = float(np.mean([float(t.get("pnl_pct") or 0.0) for t in ts])) if n else 0.0
        out.append(
            {
                "bucket": label,
                "n": n,
                "wr": round(wr, 4),
                "avg_pct": round(avg_pct, 2),
            }
        )
    return out


def _failure_reason(t: Dict[str, Any]) -> str:
    """Heuristically infer a failure reason from trade fields."""
    exit_reason = (t.get("exit_reason") or "").lower()
    if "stop" in exit_reason or "sl" in exit_reason:
        if t.get("rvol") is not None and float(t.get("rvol") or 0) < 1.0:
            return "low RVOL"
    if "gap" in exit_reason:
        return "gap down"
    if "earnings" in exit_reason or any(
        "earnings" in str(c).lower() for c in (t.get("catalyst_tags") or [])
    ):
        return "earnings miss"
    if "regime" in exit_reason or "flip" in exit_reason:
        return "regime flip during hold"
    if t.get("rvol") is not None and float(t.get("rvol") or 0) < 1.0:
        return "low RVOL"
    return "adverse price action"


def compute_worst_trades(
    trades: List[Dict[str, Any]], n: int = 5
) -> List[Dict[str, Any]]:
    """Return the worst n closed trades by pnl_pct with an inferred failure reason."""
    closed = _closed(trades)
    if not closed:
        return []
    sorted_t = sorted(closed, key=lambda t: float(t.get("pnl_pct") or 0.0))
    out: List[Dict[str, Any]] = []
    for t in sorted_t[:n]:
        out.append(
            {
                "ticker": t.get("ticker"),
                "entry_date": t.get("entry_date"),
                "exit_date": t.get("exit_date"),
                "entry_price": t.get("entry_price"),
                "exit_price": t.get("exit_price"),
                "pnl_pct": round(float(t.get("pnl_pct") or 0.0), 2),
                "setup_type": t.get("setup_type"),
                "regime": t.get("regime"),
                "failure_reason": _failure_reason(t),
            }
        )
    return out


def _size_rec(wr: float, expectancy: float) -> str:
    """Map WR and expectancy to a position-size recommendation."""
    if wr >= 0.70 and expectancy >= 0.3:
        return "full"
    if wr >= 0.60 and expectancy >= 0.15:
        return "75%"
    if wr >= 0.50 and expectancy >= 0.0:
        return "50%"
    return "reduce bar"


def compute_score_bucket_stats(trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Bucket closed trades by score and compute WR, avg pct, expectancy and size rec."""
    closed = _closed(trades)
    buckets: List[Tuple[str, float, float]] = [
        ("85+", 85.0, float("inf")),
        ("75-84", 75.0, 85.0),
        ("65-74", 65.0, 75.0),
        ("55-64", 55.0, 65.0),
        ("<55", float("-inf"), 55.0),
    ]
    out: List[Dict[str, Any]] = []
    for label, lo, hi in buckets:
        ts = [t for t in closed if t.get("score") is not None and lo <= float(t["score"]) < hi]
        n = len(ts)
        if n == 0:
            out.append(
                {
                    "bucket_label": label,
                    "n": 0,
                    "wr": 0.0,
                    "avg_pct": 0.0,
                    "expectancy_per_dollar": 0.0,
                    "size_recommendation": "reduce bar",
                }
            )
            continue
        wins = [t for t in ts if t.get("win") or (t.get("pnl_dollar") or 0) > 0]
        losses = [t for t in ts if t not in wins]
        wr = len(wins) / n
        avg_pct = float(np.mean([float(t.get("pnl_pct") or 0.0) for t in ts]))
        avg_win = float(np.mean([float(t.get("pnl_dollar") or 0.0) for t in wins])) if wins else 0.0
        avg_loss_amt = (
            float(np.mean([abs(float(t.get("pnl_dollar") or 0.0)) for t in losses])) if losses else 0.0
        )
        expectancy = (
            (wr * avg_win - (1 - wr) * avg_loss_amt) / avg_loss_amt if avg_loss_amt > 0 else 0.0
        )
        out.append(
            {
                "bucket_label": label,
                "n": n,
                "wr": round(wr, 4),
                "avg_pct": round(avg_pct, 2),
                "expectancy_per_dollar": round(expectancy, 3),
                "size_recommendation": _size_rec(wr, expectancy),
            }
        )
    return out


def compute_monthly_pnl_heatmap(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build a monthly PnL% heatmap payload with years, months and per-cell color."""
    closed = _closed(trades)
    if not closed:
        return {"years": [], "months": []}
    rows = []
    for t in closed:
        d = _parse_date(t.get("exit_date"))
        if not d:
            continue
        rows.append({"year": d.year, "month": d.month, "pct": float(t.get("pnl_pct") or 0.0)})
    if not rows:
        return {"years": [], "months": []}
    df = pd.DataFrame(rows)
    agg = df.groupby(["year", "month"])["pct"].sum().reset_index()
    years = sorted(df["year"].unique().tolist())
    months: List[Dict[str, Any]] = []
    for _, r in agg.iterrows():
        pct = float(r["pct"])
        months.append(
            {
                "year": int(r["year"]),
                "month": int(r["month"]),
                "pnl_pct": round(pct, 2),
                "color": _pct_color(pct),
            }
        )
    return {"years": years, "months": months}


def compute_streak(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute current and longest win/loss streaks chronologically."""
    closed = _sorted_by_exit(trades)
    if not closed:
        return {
            "current_streak": 0,
            "streak_type": "W",
            "longest_win_streak": 0,
            "longest_loss_streak": 0,
        }
    results = [bool(t.get("win")) or (float(t.get("pnl_dollar") or 0.0) > 0) for t in closed]
    longest_w = longest_l = 0
    cur_w = cur_l = 0
    for r in results:
        if r:
            cur_w += 1
            cur_l = 0
            longest_w = max(longest_w, cur_w)
        else:
            cur_l += 1
            cur_w = 0
            longest_l = max(longest_l, cur_l)
    if results[-1]:
        current_streak = cur_w
        streak_type = "W"
    else:
        current_streak = cur_l
        streak_type = "L"
    return {
        "current_streak": int(current_streak),
        "streak_type": streak_type,
        "longest_win_streak": int(longest_w),
        "longest_loss_streak": int(longest_l),
    }


def compute_expectancy(trades: List[Dict[str, Any]]) -> float:
    """Compute dollar-weighted expectancy per $1 risked across closed trades."""
    closed = _closed(trades)
    if not closed:
        return 0.0
    wins = [float(t.get("pnl_dollar") or 0.0) for t in closed if (t.get("pnl_dollar") or 0) > 0]
    losses = [abs(float(t.get("pnl_dollar") or 0.0)) for t in closed if (t.get("pnl_dollar") or 0) < 0]
    n = len(closed)
    wr = len(wins) / n if n else 0.0
    avg_win = float(np.mean(wins)) if wins else 0.0
    avg_loss = float(np.mean(losses)) if losses else 0.0
    if avg_loss == 0:
        return 0.0
    return round((wr * avg_win - (1 - wr) * avg_loss) / avg_loss, 4)


def compute_rolling_wr_vs_backtest(
    trades: List[Dict[str, Any]],
    backtest_wr: float = 0.857,
    window: int = 30,
) -> Dict[str, Any]:
    """Compare a rolling live WR against backtest WR and flag drift/alarm status."""
    closed = _sorted_by_exit(trades)
    if not closed:
        return {
            "rolling_wr": 0.0,
            "backtest_wr": backtest_wr,
            "delta": -backtest_wr,
            "status": "alarm",
        }
    recent = closed[-window:]
    wins = sum(1 for t in recent if t.get("win") or (t.get("pnl_dollar") or 0) > 0)
    rolling_wr = wins / len(recent) if recent else 0.0
    delta = rolling_wr - backtest_wr
    abs_pp = abs(delta) * 100.0
    if abs_pp <= 10:
        status = "on-track"
    elif abs_pp <= 20:
        status = "drift"
    else:
        status = "alarm"
    return {
        "rolling_wr": round(rolling_wr, 4),
        "backtest_wr": round(float(backtest_wr), 4),
        "delta": round(delta, 4),
        "status": status,
    }


def compute_unique_trades(runs: List[Dict[str, Any]]) -> int:
    """Count distinct tickers across all runs (dedup)."""
    tickers = set()
    for run in runs or []:
        for t in run.get("trades", []) or []:
            tk = t.get("ticker")
            if tk:
                tickers.add(str(tk).upper())
        for tk in run.get("tickers", []) or []:
            if tk:
                tickers.add(str(tk).upper())
    return len(tickers)


# ---------------------------------------------------------------------------
# Decision-log analytics (HARDENING 3.3)
# ---------------------------------------------------------------------------

def _load_decisions_or(decisions: Optional[List[Dict[str, Any]]],
                       window_days: int) -> List[Dict[str, Any]]:
    """Return the passed-in list, or load from decision_logger if None."""
    if decisions is not None:
        return decisions
    try:
        from decision_logger import load_recent_decisions
        return load_recent_decisions(days=window_days)
    except Exception:
        return []


def compute_flip_rate(
    decisions: Optional[List[Dict[str, Any]]] = None,
    window_days: int = 3,
) -> Dict[str, Any]:
    """Per-ticker verdict change frequency in a rolling window.

    A "flip" is any change in verdict for the same ticker between consecutive
    scan dates within the window. A ticker with N distinct verdicts across M
    dates counts as flipped if N > 1.

    Returns:
        {
          "window_days": int,
          "total_tickers_with_verdict": int,
          "tickers_flipped": int,
          "flip_rate_pct": float,
          "by_ticker": [
              {"ticker": T, "flips": K, "verdicts": [...]}
          ]
        }
    """
    recs = _load_decisions_or(decisions, window_days)
    by_ticker: Dict[str, List[Tuple[str, str]]] = {}
    for r in recs:
        tk = (r.get("ticker") or "").upper()
        if not tk:
            continue
        d = str(r.get("date") or "")[:10]
        v = str(r.get("verdict") or "").upper()
        if not d or not v:
            continue
        by_ticker.setdefault(tk, []).append((d, v))

    details: List[Dict[str, Any]] = []
    flipped = 0
    for tk, events in by_ticker.items():
        events.sort(key=lambda e: e[0])
        verdicts = [v for _, v in events]
        # Count transitions (day N verdict != day N-1 verdict)
        flips = 0
        last = None
        for _, v in events:
            if last is not None and v != last:
                flips += 1
            last = v
        if flips > 0:
            flipped += 1
        details.append({
            "ticker": tk,
            "flips": flips,
            "verdicts": verdicts,
            "dates": [d for d, _ in events],
        })

    total = len(by_ticker)
    rate = round(flipped / total * 100, 2) if total else 0.0
    # Sort by_ticker by flip count desc for easier dashboard consumption
    details.sort(key=lambda d: d["flips"], reverse=True)

    return {
        "window_days": window_days,
        "total_tickers_with_verdict": total,
        "tickers_flipped": flipped,
        "flip_rate_pct": rate,
        "by_ticker": details,
    }


def compute_watch_conversion_rate(
    decisions: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """For each setup_type, % of WATCH signals that became BUY within
    5 trading days (approximated as 7 calendar days).

    Returns:
        {
          "by_setup": {
              setup: {
                  "watch_count": int,
                  "converted_count": int,
                  "rate_pct": float,
                  "avg_days_to_convert": float | None
              }
          }
        }
    """
    # Need at least enough history to detect conversions — pull 30 days.
    recs = _load_decisions_or(decisions, 30)

    # Group events by ticker, sorted by date
    by_ticker: Dict[str, List[Tuple[date, str, str]]] = {}
    for r in recs:
        tk = (r.get("ticker") or "").upper()
        if not tk:
            continue
        try:
            d = datetime.fromisoformat(str(r.get("date"))[:10]).date()
        except (ValueError, TypeError):
            continue
        v = str(r.get("verdict") or "").upper()
        s = r.get("setup_type") or "unknown"
        by_ticker.setdefault(tk, []).append((d, v, s))

    watch_by_setup: Dict[str, int] = {}
    convert_days_by_setup: Dict[str, List[int]] = {}
    CONVERT_WINDOW = 7  # ~5 trading days

    for tk, events in by_ticker.items():
        events.sort(key=lambda e: e[0])
        for i, (d_i, v_i, s_i) in enumerate(events):
            if v_i != "WATCH":
                continue
            watch_by_setup[s_i] = watch_by_setup.get(s_i, 0) + 1
            for j in range(i + 1, len(events)):
                d_j, v_j, _ = events[j]
                gap = (d_j - d_i).days
                if gap > CONVERT_WINDOW:
                    break
                if v_j == "BUY":
                    convert_days_by_setup.setdefault(s_i, []).append(gap)
                    break

    by_setup: Dict[str, Dict[str, Any]] = {}
    for setup, wc in watch_by_setup.items():
        converted = convert_days_by_setup.get(setup, [])
        count_conv = len(converted)
        avg_days = (
            round(sum(converted) / count_conv, 2) if count_conv else None
        )
        by_setup[setup] = {
            "watch_count": wc,
            "converted_count": count_conv,
            "rate_pct": round(count_conv / wc * 100, 2) if wc else 0.0,
            "avg_days_to_convert": avg_days,
        }

    return {"by_setup": by_setup}


# ---------------------------------------------------------------------------
# Wave-1 additions: SPY-relative alpha & setup efficiency
# ---------------------------------------------------------------------------

def _fetch_spy_history(days: int = 400):
    """Best-effort fetch of SPY OHLCV. Tries Polygon, falls back to yfinance."""
    try:
        from data_fetcher import get_polygon_ohlcv  # type: ignore
        df = get_polygon_ohlcv("SPY", days=days, timespan="day")
        if df is not None and len(df) > 0:
            return df
    except Exception:
        pass
    try:
        from data_fetcher import yf  # _YfStub (yfinance removed 2026-04-25)
        df = yf.download("SPY", period=f"{max(days, 90)}d", interval="1d",
                         progress=False, threads=False, auto_adjust=True)
        if df is not None and len(df) > 0:
            return df
    except Exception:
        pass
    return None


def _spy_return_between(spy_df, entry_d: Optional[date], exit_d: Optional[date]) -> Optional[float]:
    """Return SPY pct change between entry_d and exit_d (inclusive). None if not computable."""
    if spy_df is None or entry_d is None or exit_d is None:
        return None
    try:
        if isinstance(spy_df.columns, pd.MultiIndex):
            close = spy_df["Close"].iloc[:, 0].dropna()
        else:
            close = spy_df["Close"].squeeze().dropna()
    except Exception:
        return None

    try:
        dates = []
        for ix in close.index:
            try:
                dates.append(ix.date() if hasattr(ix, "date") else
                             datetime.fromisoformat(str(ix)[:10]).date())
            except Exception:
                dates.append(None)

        entry_i = None
        for i, d in enumerate(dates):
            if d is not None and d >= entry_d:
                entry_i = i
                break
        exit_i = None
        # exit: last index <= exit_d (walking forward)
        for i, d in enumerate(dates):
            if d is not None and d <= exit_d:
                exit_i = i
        if entry_i is None or exit_i is None or exit_i <= entry_i:
            return None
        p0 = float(close.iloc[entry_i])
        p1 = float(close.iloc[exit_i])
        if p0 <= 0:
            return None
        return (p1 / p0 - 1.0) * 100.0
    except Exception:
        return None


def compute_spy_relative_wr(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    """For each closed trade, compute ticker_return - SPY_return over the
    same holding window.

    Returns:
        {
          'n_trades': N,
          'avg_alpha_pct': mean excess return over SPY,
          'pct_beating_spy': fraction of trades with positive alpha,
          'alpha_by_setup': {setup: {'n': N, 'avg_alpha_pct': X}},
          'alpha_by_regime': {regime: {'n': N, 'avg_alpha_pct': X}}
        }
    """
    closed = _closed(trades)
    if not closed:
        return {
            "n_trades": 0,
            "avg_alpha_pct": None,
            "pct_beating_spy": None,
            "alpha_by_setup": {},
            "alpha_by_regime": {},
        }

    spy_df = _fetch_spy_history(days=400)
    if spy_df is None:
        return {
            "n_trades": 0,
            "avg_alpha_pct": None,
            "pct_beating_spy": None,
            "alpha_by_setup": {},
            "alpha_by_regime": {},
            "error": "SPY history unavailable",
        }

    alphas: List[float] = []
    beats = 0
    by_setup: Dict[str, List[float]] = {}
    by_regime: Dict[str, List[float]] = {}

    for t in closed:
        entry_d = _parse_date(t.get("entry_date") or t.get("run_date"))
        exit_d = _parse_date(t.get("exit_date"))
        if entry_d is None or exit_d is None:
            continue

        # Ticker return pct: prefer pnl_pct; else derive from prices
        tret = t.get("pnl_pct")
        if tret is None:
            try:
                ep = float(t.get("entry_price") or 0)
                xp = float(t.get("exit_price") or 0)
                if ep > 0 and xp > 0:
                    tret = (xp / ep - 1.0) * 100.0
            except (TypeError, ValueError):
                tret = None
        if tret is None:
            continue

        spy_ret = _spy_return_between(spy_df, entry_d, exit_d)
        if spy_ret is None:
            continue

        alpha = float(tret) - float(spy_ret)
        alphas.append(alpha)
        if alpha > 0:
            beats += 1

        setup = str(t.get("setup_type") or "unknown")
        regime = str(t.get("regime") or t.get("market_regime") or "unknown")
        by_setup.setdefault(setup, []).append(alpha)
        by_regime.setdefault(regime, []).append(alpha)

    n = len(alphas)
    if n == 0:
        return {
            "n_trades": 0,
            "avg_alpha_pct": None,
            "pct_beating_spy": None,
            "alpha_by_setup": {},
            "alpha_by_regime": {},
        }

    def _agg(bucket: Dict[str, List[float]]) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        for k, vs in bucket.items():
            if not vs:
                continue
            out[k] = {
                "n": len(vs),
                "avg_alpha_pct": round(sum(vs) / len(vs), 3),
                "pct_beating_spy": round(sum(1 for v in vs if v > 0) / len(vs), 4),
            }
        return out

    return {
        "n_trades": n,
        "avg_alpha_pct": round(sum(alphas) / n, 3),
        "pct_beating_spy": round(beats / n, 4),
        "alpha_by_setup": _agg(by_setup),
        "alpha_by_regime": _agg(by_regime),
    }


def compute_setup_efficiency(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Per-setup MFE/MAE ratio — "runs big vs. chops small".

    Efficiency = avg_mfe / avg_mae. Edge_score = efficiency × wr.
    Sorted by edge_score desc.
    """
    closed = _closed(trades)
    if not closed:
        return {"by_setup": {}}

    buckets: Dict[str, Dict[str, List[float]]] = {}
    for t in closed:
        setup = str(t.get("setup_type") or "unknown")
        b = buckets.setdefault(setup, {"mfe": [], "mae": [], "wins": [], "pnl": []})

        # MFE / MAE — accept either percent or absolute; prefer pct keys
        mfe = t.get("mfe_pct")
        if mfe is None:
            mfe = t.get("mfe")
        mae = t.get("mae_pct")
        if mae is None:
            mae = t.get("mae")

        try:
            if mfe is not None:
                b["mfe"].append(abs(float(mfe)))
        except (TypeError, ValueError):
            pass
        try:
            if mae is not None:
                b["mae"].append(abs(float(mae)))
        except (TypeError, ValueError):
            pass

        win = t.get("win")
        if win is None:
            pnl = t.get("pnl_dollar")
            if pnl is None:
                pnl = t.get("pnl_pct")
            try:
                win = float(pnl) > 0 if pnl is not None else None
            except (TypeError, ValueError):
                win = None
        if win is not None:
            b["wins"].append(1.0 if bool(win) else 0.0)

    rows: List[tuple[str, Dict[str, Any]]] = []
    for setup, b in buckets.items():
        n = max(len(b["wins"]), len(b["mfe"]), len(b["mae"]))
        if n == 0:
            continue
        avg_mfe = (sum(b["mfe"]) / len(b["mfe"])) if b["mfe"] else 0.0
        avg_mae = (sum(b["mae"]) / len(b["mae"])) if b["mae"] else 0.0
        wr = (sum(b["wins"]) / len(b["wins"])) if b["wins"] else 0.0
        efficiency = (avg_mfe / avg_mae) if avg_mae > 0 else None
        edge_score = (efficiency * wr) if efficiency is not None else None
        rows.append((setup, {
            "n": n,
            "wr": round(wr, 4),
            "avg_mfe": round(avg_mfe, 3),
            "avg_mae": round(avg_mae, 3),
            "efficiency": round(efficiency, 3) if efficiency is not None else None,
            "edge_score": round(edge_score, 4) if edge_score is not None else None,
        }))

    # Sort by edge_score desc (None → end)
    rows.sort(key=lambda kv: (kv[1]["edge_score"] is None,
                              -(kv[1]["edge_score"] or 0.0)))
    return {"by_setup": dict(rows)}
