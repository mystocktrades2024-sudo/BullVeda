#!/usr/bin/env python3
"""
hedge_fund_report.py — comprehensive backtest analytics HTML report.

Reads cache/portfolio_backtest.json and emits a single self-contained HTML file
with hedge-fund-style analytics: profit factor + Wilson-CI gated setup table,
score-band stratification, risk metrics (Pain/Ulcer/Calmar/IR/CVaR), equity
curve + drawdown timeline, signal-decay rolling-WR per setup, counterfactual
sweeps, and a sortable trade-level table.

Phase 1 — uses ONLY existing trade data (no external OHLCV/VIX/regime fetch).
Phase 2 (separate module): regime × setup matrix, hold-period sweep,
VIX-conditional WR, catalyst-conditional WR.

Usage:
    python3 hedge_fund_report.py                # uses cache/portfolio_backtest.json
    python3 hedge_fund_report.py --in PATH      # alternate input
    python3 hedge_fund_report.py --open         # opens in browser after generate

Output: cache/backtest_report_YYYYMMDD_HHMMSS.html
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import webbrowser
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
DEFAULT_IN = BASE / "cache" / "portfolio_backtest.json"
BUNDLES_DIR = BASE / "cache" / "bundles"
OHLCV_ARCHIVE = BASE / "data" / "ohlcv"


# ─── Bundle / OHLCV loaders for Phase 2/3 ────────────────────────────────────

_BUNDLE_CACHE: dict = {}

def _load_bundle(date_str: str) -> dict | None:
    """Load cached daily bundle by date (YYYY-MM-DD). Returns None if missing."""
    if not date_str:
        return None
    date_str = date_str[:10]
    if date_str in _BUNDLE_CACHE:
        return _BUNDLE_CACHE[date_str]
    p = BUNDLES_DIR / f"{date_str}.json"
    if not p.exists():
        _BUNDLE_CACHE[date_str] = None
        return None
    try:
        b = json.loads(p.read_text())
        _BUNDLE_CACHE[date_str] = b
        return b
    except Exception:
        _BUNDLE_CACHE[date_str] = None
        return None


def _bundle_regime(date_str: str) -> str | None:
    b = _load_bundle(date_str)
    if not b:
        return None
    r = b.get("regime")
    if isinstance(r, dict):
        return r.get("regime") or r.get("name")
    if isinstance(r, str):
        return r
    return b.get("regime4")


def _bundle_vix(date_str: str) -> float | None:
    b = _load_bundle(date_str)
    if not b:
        return None
    v = b.get("vix")
    try:
        return float(v) if v else None
    except (TypeError, ValueError):
        return None


def _bundle_catalyst_tags(date_str: str, ticker: str) -> list[str]:
    b = _load_bundle(date_str)
    if not b:
        return []
    for r in (b.get("all_scored") or []):
        if r.get("ticker") == ticker:
            return r.get("catalyst_tags") or []
    return []


def _ohlcv_load(ticker: str):
    """Load OHLCV parquet for ticker. Returns DataFrame or None."""
    try:
        import pandas as pd
        p = OHLCV_ARCHIVE / f"{ticker}.parquet"
        if not p.exists():
            return None
        df = pd.read_parquet(p)
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date").sort_index()
        elif df.index.name != "date":
            df.index = pd.to_datetime(df.index)
            df = df.sort_index()
        return df
    except Exception:
        return None


# ─── Statistical helpers ─────────────────────────────────────────────────────

def wilson_lower_bound(wins: int, n: int, z: float = 1.96) -> float:
    """Wilson 95% lower bound for binomial proportion (default z=1.96)."""
    if n == 0:
        return 0.0
    p = wins / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    spread = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)
    return max(0.0, (centre - spread) / denom)


def safe_div(a, b, default=0.0):
    return a / b if b else default


def annualize(daily_ret: float, periods: int = 252) -> float:
    return (1 + daily_ret) ** periods - 1


# ─── Section 1: Executive summary ────────────────────────────────────────────

def section_summary(data: dict, trades: list[dict]) -> dict:
    n = len(trades)
    wins = sum(1 for t in trades if t.get("win"))
    losses = n - wins
    wr = safe_div(wins, n)
    pnls = [t.get("pnl_pct", 0) for t in trades]
    avg_win = statistics.mean([t["pnl_pct"] for t in trades if t.get("win")]) if wins else 0
    avg_loss = statistics.mean([t["pnl_pct"] for t in trades if not t.get("win")]) if losses else 0
    expectancy = wr * avg_win + (1 - wr) * avg_loss
    pf = data.get("profit_factor", 0)
    sharpe = data.get("sharpe", 0)
    max_dd = data.get("max_drawdown_pct", 0)
    total_pnl = data.get("total_pnl", 0)
    total_return = data.get("total_return_pct", 0)
    monthly = data.get("monthly_pnl", {})
    pos_months = sum(1 for v in monthly.values() if v > 0)
    n_months = len(monthly) or 1
    avg_monthly = statistics.mean(monthly.values()) if monthly else 0
    # Calmar = annual return / max drawdown
    days = (datetime.fromisoformat(trades[-1]["exit_date"][:10]) -
            datetime.fromisoformat(trades[0]["entry_date"][:10])).days if n >= 2 else 1
    annual_return_pct = (total_return / max(days, 1)) * 365
    calmar = safe_div(annual_return_pct, abs(max_dd))
    # Best/worst trade
    best = max(pnls) if pnls else 0
    worst = min(pnls) if pnls else 0
    return {
        "n_trades": n,
        "wins": wins,
        "losses": losses,
        "wr_pct": round(wr * 100, 1),
        "pf": round(pf, 2),
        "sharpe": round(sharpe, 2),
        "max_dd_pct": round(max_dd, 1),
        "total_return_pct": round(total_return, 2),
        "total_pnl_dollar": round(total_pnl, 2),
        "avg_win_pct": round(avg_win, 2),
        "avg_loss_pct": round(avg_loss, 2),
        "expectancy_pct": round(expectancy, 2),
        "avg_monthly_dollar": round(avg_monthly, 2),
        "pos_months": pos_months,
        "n_months": n_months,
        "calmar": round(calmar, 2),
        "best_trade_pct": round(best, 2),
        "worst_trade_pct": round(worst, 2),
        "annual_return_pct": round(annual_return_pct, 1),
    }


# ─── Section 2: Equity curve + drawdown ──────────────────────────────────────

def section_equity_curve(data: dict) -> dict:
    eq = data.get("equity_curve", [])
    if not eq:
        return {"dates": [], "equity": [], "drawdown": []}
    dates = [pt.get("date") for pt in eq]
    values = [float(pt.get("equity", 0)) for pt in eq]
    # Compute running peak + drawdown%
    peak = values[0]
    drawdown = []
    for v in values:
        peak = max(peak, v)
        dd = (v - peak) / peak * 100 if peak else 0
        drawdown.append(dd)
    return {"dates": dates, "equity": values, "drawdown": drawdown}


# ─── Section 3: Setup performance table with Wilson CI ───────────────────────

def section_setup_table(trades: list[dict]) -> list[dict]:
    by_setup = defaultdict(list)
    for t in trades:
        s = t.get("setup_type") or "?"
        by_setup[s].append(t)
    rows = []
    for setup, items in by_setup.items():
        n = len(items)
        wins = sum(1 for t in items if t.get("win"))
        wr = wins / n
        wr_lb = wilson_lower_bound(wins, n)
        pnls = [t["pnl_pct"] for t in items]
        total_pnl_pct = sum(pnls)
        avg_pnl = statistics.mean(pnls)
        winning = [p for p in pnls if p > 0]
        losing = [p for p in pnls if p <= 0]
        gross_win = sum(winning)
        gross_loss = abs(sum(losing))
        pf_setup = safe_div(gross_win, gross_loss, 999)
        avg_win = statistics.mean(winning) if winning else 0
        avg_loss = statistics.mean(losing) if losing else 0
        expectancy = wr * avg_win + (1 - wr) * avg_loss
        # Verdict: edge real if wr_lb >= 0.40 AND expectancy > 0
        if wr_lb >= 0.45 and expectancy > 0.5:
            verdict = "ALPHA"
            verdict_color = "pass"
        elif wr_lb >= 0.30 and expectancy > 0:
            verdict = "EDGE"
            verdict_color = "info"
        elif n < 10:
            verdict = "SAMPLE"
            verdict_color = "warn"
        elif expectancy < -0.3:
            verdict = "KILL"
            verdict_color = "fail"
        else:
            verdict = "FLAT"
            verdict_color = "warn"
        rows.append({
            "setup": setup,
            "n": n,
            "wins": wins,
            "losses": n - wins,
            "wr_pct": round(wr * 100, 1),
            "wr_lb_pct": round(wr_lb * 100, 1),
            "avg_pnl_pct": round(avg_pnl, 2),
            "total_pnl_pct": round(total_pnl_pct, 2),
            "avg_win_pct": round(avg_win, 2),
            "avg_loss_pct": round(avg_loss, 2),
            "expectancy_pct": round(expectancy, 2),
            "pf": round(pf_setup, 2) if pf_setup < 999 else "∞",
            "verdict": verdict,
            "verdict_color": verdict_color,
        })
    rows.sort(key=lambda r: -r["expectancy_pct"])
    return rows


# ─── Section 4: Score-band stratification ────────────────────────────────────

def section_score_band(trades: list[dict]) -> list[dict]:
    bands = [(0, 60, "<60"), (60, 70, "60-69"), (70, 80, "70-79"),
             (80, 90, "80-89"), (90, 101, "90+")]
    rows = []
    for lo, hi, label in bands:
        items = [t for t in trades if lo <= (t.get("score") or 0) < hi]
        n = len(items)
        if n == 0:
            rows.append({"band": label, "n": 0, "wr_pct": 0, "wr_lb_pct": 0,
                         "avg_pnl_pct": 0, "total_pnl_pct": 0, "expectancy_pct": 0})
            continue
        wins = sum(1 for t in items if t.get("win"))
        wr = wins / n
        wr_lb = wilson_lower_bound(wins, n)
        pnls = [t["pnl_pct"] for t in items]
        avg_pnl = statistics.mean(pnls)
        total = sum(pnls)
        winning = [p for p in pnls if p > 0]
        losing = [p for p in pnls if p <= 0]
        avg_win = statistics.mean(winning) if winning else 0
        avg_loss = statistics.mean(losing) if losing else 0
        expectancy = wr * avg_win + (1 - wr) * avg_loss
        rows.append({
            "band": label,
            "n": n,
            "wins": wins,
            "wr_pct": round(wr * 100, 1),
            "wr_lb_pct": round(wr_lb * 100, 1),
            "avg_pnl_pct": round(avg_pnl, 2),
            "total_pnl_pct": round(total, 2),
            "expectancy_pct": round(expectancy, 2),
        })
    return rows


# ─── Section 7: Risk metrics suite ───────────────────────────────────────────

def section_risk_metrics(data: dict, trades: list[dict]) -> dict:
    eq = data.get("equity_curve", [])
    if not eq:
        return {}
    values = [float(pt.get("equity", 0)) for pt in eq]
    # Daily returns
    rets = []
    for i in range(1, len(values)):
        if values[i-1] > 0:
            rets.append((values[i] - values[i-1]) / values[i-1])
    # Drawdowns
    peak = values[0]
    dds = []
    for v in values:
        peak = max(peak, v)
        dd = (v - peak) / peak if peak else 0
        dds.append(dd)
    max_dd = abs(min(dds)) if dds else 0
    # Pain index = mean of |drawdown|
    pain_index = statistics.mean(abs(d) for d in dds) if dds else 0
    # Ulcer index = sqrt(mean(dd^2))
    ulcer_index = math.sqrt(statistics.mean(d * d for d in dds)) if dds else 0
    # Calmar = annualized return / max drawdown
    days = len(rets) or 1
    total_return = (values[-1] / values[0] - 1) if values[0] else 0
    annual_return = (1 + total_return) ** (252 / days) - 1 if days >= 1 else 0
    calmar = safe_div(annual_return, max_dd)
    # Sortino = annual return / downside deviation
    downside_rets = [r for r in rets if r < 0]
    downside_dev = math.sqrt(statistics.mean([r * r for r in downside_rets])) if downside_rets else 0
    sortino = safe_div(annual_return, downside_dev * math.sqrt(252))
    # Max consecutive losses
    cur_streak = 0
    max_streak = 0
    for t in trades:
        if not t.get("win"):
            cur_streak += 1
            max_streak = max(max_streak, cur_streak)
        else:
            cur_streak = 0
    # CVaR-95 / CVaR-97 on trade-level pnl_pct (worst N% mean)
    pnls = sorted(t["pnl_pct"] for t in trades)
    n = len(pnls)
    cvar95 = statistics.mean(pnls[: max(1, int(n * 0.05))]) if n else 0
    cvar97 = statistics.mean(pnls[: max(1, int(n * 0.025))]) if n else 0
    # Information ratio — placeholder until SPY series wired (Phase 2)
    return {
        "pain_index_pct":     round(pain_index * 100, 2),
        "ulcer_index_pct":    round(ulcer_index * 100, 2),
        "calmar":             round(calmar, 2),
        "sortino":            round(sortino, 2),
        "max_dd_pct":         round(max_dd * 100, 2),
        "max_consec_losses":  max_streak,
        "cvar_95_pct":        round(cvar95, 2),
        "cvar_97_5_pct":      round(cvar97, 2),
        "annual_return_pct":  round(annual_return * 100, 2),
        "downside_dev_pct":   round(downside_dev * math.sqrt(252) * 100, 2),
    }


# ─── Section 10: Signal decay (rolling WR per setup) ─────────────────────────

def section_signal_decay(trades: list[dict], window: int = 10) -> dict:
    """For each setup, compute rolling-N WR over chronological order."""
    by_setup = defaultdict(list)
    for t in sorted(trades, key=lambda x: x.get("entry_date", "")):
        s = t.get("setup_type") or "?"
        by_setup[s].append(t)
    out = {}
    for setup, items in by_setup.items():
        if len(items) < 5:
            continue
        rolling = []
        eff_window = min(window, max(3, len(items) // 3))
        for i in range(eff_window - 1, len(items)):
            window_items = items[i - eff_window + 1: i + 1]
            wins = sum(1 for t in window_items if t.get("win"))
            wr = wins / eff_window * 100
            rolling.append({
                "trade_idx": i + 1,
                "exit_date": items[i].get("exit_date", "")[:10],
                "wr": round(wr, 1),
            })
        out[setup] = rolling
    return out


# ─── Section 11: Counterfactual sweeps ───────────────────────────────────────

def section_counterfactuals(trades: list[dict]) -> dict:
    """What-if analyses on existing trade data — buy_min sweep, hold caps, kill-list deltas."""
    out = {}
    # Buy-min sweep: filter trades by score, recompute aggregate
    out["buy_min_sweep"] = []
    for thr in (60, 65, 70, 75, 80, 85, 90):
        items = [t for t in trades if (t.get("score") or 0) >= thr]
        if not items:
            out["buy_min_sweep"].append({"threshold": thr, "n": 0, "wr_pct": 0, "total_pct": 0, "pf": 0})
            continue
        n = len(items)
        wins = sum(1 for t in items if t.get("win"))
        wr = wins / n
        pnls = [t["pnl_pct"] for t in items]
        total = sum(pnls)
        winning = sum(p for p in pnls if p > 0)
        losing = abs(sum(p for p in pnls if p <= 0))
        pf = safe_div(winning, losing, 999)
        out["buy_min_sweep"].append({
            "threshold": thr, "n": n, "wr_pct": round(wr * 100, 1),
            "total_pct": round(total, 2), "pf": round(pf, 2) if pf < 999 else "∞",
        })

    # Setup-removal sweep: what if each setup were killed?
    out["setup_removal"] = []
    by_setup = defaultdict(list)
    for t in trades:
        by_setup[t.get("setup_type") or "?"].append(t)
    for setup_to_kill in by_setup.keys():
        kept = [t for t in trades if (t.get("setup_type") or "?") != setup_to_kill]
        if not kept:
            continue
        n = len(kept)
        wins = sum(1 for t in kept if t.get("win"))
        wr = wins / n if n else 0
        total = sum(t["pnl_pct"] for t in kept)
        winning = sum(t["pnl_pct"] for t in kept if t["pnl_pct"] > 0)
        losing = abs(sum(t["pnl_pct"] for t in kept if t["pnl_pct"] <= 0))
        pf = safe_div(winning, losing, 999)
        delta_total = total - sum(t["pnl_pct"] for t in trades)
        out["setup_removal"].append({
            "kill": setup_to_kill,
            "remaining_n": n,
            "wr_pct": round(wr * 100, 1),
            "total_pct": round(total, 2),
            "delta_pct": round(delta_total, 2),
            "pf": round(pf, 2) if pf < 999 else "∞",
        })
    out["setup_removal"].sort(key=lambda r: -r["delta_pct"])

    # Exit-reason analysis: keep all trades but cap exits
    out["exit_reason"] = []
    by_exit = defaultdict(list)
    for t in trades:
        by_exit[t.get("exit_reason") or "?"].append(t)
    for reason, items in by_exit.items():
        n = len(items)
        wins = sum(1 for t in items if t.get("win"))
        total = sum(t["pnl_pct"] for t in items)
        out["exit_reason"].append({
            "reason": reason,
            "n": n,
            "wr_pct": round(wins / n * 100, 1) if n else 0,
            "total_pct": round(total, 2),
            "avg_pct": round(total / n, 2) if n else 0,
        })
    out["exit_reason"].sort(key=lambda r: -r["total_pct"])
    return out


# ─── Section 5: Regime × Setup × Score-band matrix ──────────────────────────

def section_regime_matrix(trades: list[dict]) -> dict:
    """Cross-tab WR by (regime, setup, score-band). Looks up regime from cached
    bundle on each trade's entry_date. Trades where bundle is missing fall under
    'unknown'."""
    score_band = lambda s: ("90+" if s >= 90 else "80-89" if s >= 80 else
                            "70-79" if s >= 70 else "60-69" if s >= 60 else "<60")
    cells: dict = defaultdict(list)  # (regime, setup, band) -> list of pnls
    for t in trades:
        regime = _bundle_regime(t.get("entry_date") or "") or "unknown"
        setup = t.get("setup_type") or "?"
        band = score_band(t.get("score") or 0)
        cells[(regime, setup, band)].append(t)
    rows = []
    for (regime, setup, band), items in cells.items():
        n = len(items)
        wins = sum(1 for x in items if x.get("win"))
        wr = wins / n if n else 0
        avg_pnl = statistics.mean(x.get("pnl_pct", 0) for x in items)
        wr_lb = wilson_lower_bound(wins, n)
        rows.append({
            "regime": regime, "setup": setup, "band": band,
            "n": n, "wr_pct": round(wr * 100, 1), "wr_lb_pct": round(wr_lb * 100, 1),
            "avg_pnl_pct": round(avg_pnl, 2),
        })
    rows.sort(key=lambda r: -r["n"])
    # Also build a regime-level rollup
    regime_roll: dict = defaultdict(list)
    for t in trades:
        regime = _bundle_regime(t.get("entry_date") or "") or "unknown"
        regime_roll[regime].append(t)
    rollup = []
    for regime, items in regime_roll.items():
        n = len(items)
        wins = sum(1 for x in items if x.get("win"))
        avg = statistics.mean(x.get("pnl_pct", 0) for x in items)
        rollup.append({
            "regime": regime, "n": n,
            "wr_pct": round(wins / n * 100, 1) if n else 0,
            "avg_pnl_pct": round(avg, 2),
        })
    rollup.sort(key=lambda r: -r["n"])
    return {"cells": rows, "rollup": rollup}


# ─── Section 6: Hold-period sensitivity sweep ────────────────────────────────

def section_hold_sweep(trades: list[dict], horizons: list[int] = (3, 5, 7, 10, 15)) -> list[dict]:
    """For each horizon, replay each trade's exit at entry_date + N trading days.
    Reads cache/ohlcv parquet — falls back gracefully if archive missing.
    """
    try:
        import pandas as pd
    except ImportError:
        return []
    rows = []
    for n_days in horizons:
        replayed = []
        skipped = 0
        for t in trades:
            ticker = t.get("ticker")
            entry_date = (t.get("entry_date") or "")[:10]
            entry_price = t.get("entry_price")
            stop = t.get("stop_price")
            if not (ticker and entry_date and entry_price):
                skipped += 1
                continue
            df = _ohlcv_load(ticker)
            if df is None or df.empty:
                skipped += 1
                continue
            try:
                idx = df.index.get_indexer([pd.Timestamp(entry_date)], method="nearest")[0]
                if idx < 0 or idx + 1 >= len(df):
                    skipped += 1
                    continue
                future_slice = df.iloc[idx + 1: idx + 1 + n_days]
                if len(future_slice) == 0:
                    skipped += 1
                    continue
                # Stop hit during window? exit at stop
                exit_price = None
                exit_reason = "time_stop"
                if stop:
                    low_col = "Low" if "Low" in future_slice.columns else "low"
                    if low_col in future_slice.columns:
                        for j, row in future_slice.iterrows():
                            if row[low_col] <= float(stop):
                                exit_price = float(stop)
                                exit_reason = "stop_loss"
                                break
                if exit_price is None:
                    close_col = "Close" if "Close" in future_slice.columns else "close"
                    exit_price = float(future_slice[close_col].iloc[-1])
                pnl_pct = (exit_price - float(entry_price)) / float(entry_price) * 100
                replayed.append({"pnl_pct": pnl_pct, "win": pnl_pct > 0, "exit_reason": exit_reason})
            except Exception:
                skipped += 1
                continue
        n = len(replayed)
        if n == 0:
            rows.append({"hold_days": n_days, "n_eligible": 0, "wr_pct": 0,
                         "avg_pnl_pct": 0, "total_pnl_pct": 0, "stop_outs": 0, "skipped": skipped})
            continue
        wins = sum(1 for r in replayed if r["win"])
        avg = statistics.mean(r["pnl_pct"] for r in replayed)
        total = sum(r["pnl_pct"] for r in replayed)
        stop_outs = sum(1 for r in replayed if r["exit_reason"] == "stop_loss")
        rows.append({
            "hold_days": n_days,
            "n_eligible": n,
            "wr_pct": round(wins / n * 100, 1),
            "avg_pnl_pct": round(avg, 2),
            "total_pnl_pct": round(total, 1),
            "stop_outs": stop_outs,
            "skipped": skipped,
        })
    return rows


# ─── Section 8: VIX-regime conditional WR ────────────────────────────────────

def section_vix_regime(trades: list[dict]) -> list[dict]:
    bands = [(0, 16, "low (<16)"), (16, 25, "med (16-25)"), (25, 999, "high (>25)")]
    bucketed: dict = defaultdict(list)
    n_unknown = 0
    for t in trades:
        v = _bundle_vix(t.get("entry_date") or "")
        if v is None:
            n_unknown += 1
            continue
        for lo, hi, lbl in bands:
            if lo <= v < hi:
                bucketed[lbl].append(t)
                break
    rows = []
    for _, _, lbl in bands:
        items = bucketed.get(lbl, [])
        n = len(items)
        if n == 0:
            rows.append({"vix_band": lbl, "n": 0, "wr_pct": 0, "avg_pnl_pct": 0, "total_pnl_pct": 0})
            continue
        wins = sum(1 for x in items if x.get("win"))
        avg = statistics.mean(x.get("pnl_pct", 0) for x in items)
        total = sum(x.get("pnl_pct", 0) for x in items)
        rows.append({
            "vix_band": lbl, "n": n,
            "wr_pct": round(wins / n * 100, 1),
            "avg_pnl_pct": round(avg, 2),
            "total_pnl_pct": round(total, 2),
        })
    if n_unknown:
        rows.append({"vix_band": f"unknown ({n_unknown} trades)",
                     "n": n_unknown, "wr_pct": 0, "avg_pnl_pct": 0, "total_pnl_pct": 0})
    return rows


# ─── Section 9: Catalyst-conditional WR ──────────────────────────────────────

def section_catalyst_wr(trades: list[dict]) -> list[dict]:
    """Group trades by which catalyst tags were present at entry."""
    by_tag: dict = defaultdict(list)
    no_tags: list = []
    for t in trades:
        tags = _bundle_catalyst_tags(t.get("entry_date") or "", t.get("ticker") or "")
        if not tags:
            no_tags.append(t)
            continue
        for tag in tags:
            by_tag[tag].append(t)
    rows = []
    for tag, items in by_tag.items():
        n = len(items)
        if n < 3:
            continue  # skip very rare tags
        wins = sum(1 for x in items if x.get("win"))
        avg = statistics.mean(x.get("pnl_pct", 0) for x in items)
        wr_lb = wilson_lower_bound(wins, n)
        rows.append({
            "catalyst": tag, "n": n,
            "wr_pct": round(wins / n * 100, 1),
            "wr_lb_pct": round(wr_lb * 100, 1),
            "avg_pnl_pct": round(avg, 2),
            "total_pnl_pct": round(sum(x.get("pnl_pct", 0) for x in items), 2),
        })
    rows.sort(key=lambda r: -r["avg_pnl_pct"])
    if no_tags:
        n = len(no_tags)
        wins = sum(1 for x in no_tags if x.get("win"))
        rows.append({
            "catalyst": "(no tags)", "n": n,
            "wr_pct": round(wins / n * 100, 1),
            "wr_lb_pct": round(wilson_lower_bound(wins, n) * 100, 1),
            "avg_pnl_pct": round(statistics.mean(x.get("pnl_pct", 0) for x in no_tags), 2),
            "total_pnl_pct": round(sum(x.get("pnl_pct", 0) for x in no_tags), 2),
        })
    return rows


# ─── Section 13-15: Hedge-fund enhancers (statistical, Bayesian, drift) ─────

def section_bootstrap_ci(trades: list[dict]) -> dict:
    """Bootstrap 95% CI on profit factor + WR + total return."""
    try:
        from hedge_fund_enhancers import bootstrap_pf_ci
    except ImportError:
        return {}
    rets = [t.get("pnl_pct", 0) for t in trades]
    return bootstrap_pf_ci(rets, n_iter=2000)


def section_bayesian_setups(trades: list[dict]) -> list[dict]:
    """Bayesian hierarchical pooling — sparse setups borrow from family priors."""
    try:
        from hedge_fund_enhancers import bayesian_setup_pool
    except ImportError:
        return []
    by_setup: dict = defaultdict(lambda: {"wins": 0, "n": 0, "family": "default"})
    for t in trades:
        s = t.get("setup_type") or "?"
        family = ("pullback"     if "Pullback" in s else
                  "breakout"     if "Breakout" in s or "Pivot" in s else
                  "continuation" if "Continuation" in s else "default")
        by_setup[s]["family"] = family
        by_setup[s]["n"] += 1
        if t.get("win"):
            by_setup[s]["wins"] += 1
    pooled = bayesian_setup_pool(dict(by_setup))
    rows = []
    for setup, m in pooled.items():
        rows.append({"setup": setup, **m})
    rows.sort(key=lambda r: -r["posterior_wr"])
    return rows


def section_train_test_holdout(trades: list[dict]) -> dict:
    """70/15/15 time-ordered split — overfit detection."""
    try:
        from hedge_fund_enhancers import train_test_holdout_split
    except ImportError:
        return {"available": False}
    sorted_trades = sorted(trades, key=lambda t: t.get("entry_date") or "")
    return train_test_holdout_split(sorted_trades, ratios=(0.7, 0.15, 0.15))


def section_kfold_cv(trades: list[dict]) -> dict:
    """K-fold time-series CV — variance check across disjoint windows."""
    try:
        from hedge_fund_enhancers import kfold_timeseries_cv
    except ImportError:
        return {"available": False}
    sorted_trades = sorted(trades, key=lambda t: t.get("entry_date") or "")
    return kfold_timeseries_cv(sorted_trades, k=5)


def section_signal_stability(trades: list[dict]) -> dict:
    """Per-setup WR stability across Q1/Q2/Q3/Q4 of the period."""
    try:
        from hedge_fund_enhancers import signal_stability_quartiles
    except ImportError:
        return {"available": False}
    sorted_trades = sorted(trades, key=lambda t: t.get("entry_date") or "")
    return signal_stability_quartiles(sorted_trades)


def section_drift_status() -> dict:
    """Read most recent drift alert from data/drift_alerts.jsonl."""
    p = BASE / "data" / "drift_alerts.jsonl"
    if not p.exists():
        return {"available": False, "reason": "drift_alerts.jsonl not yet generated; run model_drift_alert.py"}
    try:
        lines = p.read_text().strip().splitlines()
        if not lines:
            return {"available": False, "reason": "drift log empty"}
        last = json.loads(lines[-1])
        return {"available": True, **last}
    except Exception as e:
        return {"available": False, "reason": f"parse error: {e}"}


# ─── HTML rendering ──────────────────────────────────────────────────────────

_CSS = """
:root {
  --bg-0: #0a0e1a; --bg-1: #111827; --bg-2: #1e293b; --bg-3: #334155;
  --ink-0: #f1f5f9; --ink-1: #cbd5e1; --ink-2: #94a3b8; --ink-3: #64748b;
  --rule: #334155; --rule-2: #475569;
  --accent: #60a5fa; --pass: #10b981; --fail: #ef4444; --warn: #f59e0b;
  --info: #06b6d4; --purple: #a78bfa;
  --mono: 'JetBrains Mono', 'SF Mono', monospace;
}
* { box-sizing: border-box; }
body { margin: 0; padding: 0; font-family: 'Inter', -apple-system, system-ui, sans-serif;
       background: var(--bg-0); color: var(--ink-0); line-height: 1.5; }

/* Header — gradient hero with KPI-style sub-meta */
header { padding: 32px 40px 22px; border-bottom: 1px solid var(--rule);
         background: linear-gradient(135deg, #1e293b, #0a0e1a); position: sticky; top: 0; z-index: 10; }
header h1 { margin: 0; font-size: 28px; font-weight: 800; letter-spacing: -0.01em; }
header .sub { color: var(--ink-2); font-size: 13px; margin-top: 6px; font-family: var(--mono); max-width: 880px; line-height: 1.55; }
.preview-banner { background: linear-gradient(135deg, color-mix(in oklch, var(--accent) 14%, transparent), transparent);
                  border: 1px solid var(--accent); border-radius: 8px; padding: 11px 16px; margin: 14px 40px 0;
                  font-size: 12.5px; color: var(--ink-1); display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
.preview-banner b { color: var(--accent); }

/* Nav — sticky chips */
nav { display: flex; gap: 6px; flex-wrap: wrap; padding: 12px 40px; background: var(--bg-1);
      border-bottom: 1px solid var(--rule); position: sticky; top: 96px; z-index: 9; }
nav a { color: var(--ink-2); text-decoration: none; font-family: var(--mono); letter-spacing: 0.04em;
        font-weight: 600; padding: 5px 10px; font-size: 11px; border-radius: 5px;
        background: var(--bg-2); border: 1px solid var(--rule-2); transition: all 0.15s; }
nav a:hover { color: var(--accent); border-color: var(--accent); }

main { padding: 24px 40px; max-width: 1500px; margin: 0 auto; }

/* Sections — richer card style */
section { margin-bottom: 36px; background: var(--bg-1); border: 1px solid var(--rule);
          border-radius: 12px; padding: 24px 28px; }
section h2 { margin: 0 0 6px; font-size: 18px; font-weight: 800; letter-spacing: -0.01em; color: var(--ink-0);
             display: flex; align-items: baseline; gap: 12px; }
section h2 .num { font-size: 14px; color: var(--accent); font-family: var(--mono); }
section h2 .tag { font-size: 9.5px; padding: 3px 8px; border-radius: 3px; letter-spacing: 0.08em;
                  font-weight: 800; text-transform: uppercase; }
section h2 .tag.live { background: var(--pass); color: var(--bg-0); }
section h2 .tag.partial { background: var(--warn); color: var(--bg-0); }
section h2 .tag.mock { background: var(--purple); color: var(--bg-0); }
section .desc { color: var(--ink-2); font-size: 13px; margin-bottom: 18px; line-height: 1.6; max-width: 1000px; }
section .narrative { background: color-mix(in oklch, var(--accent) 10%, var(--bg-2)); border-left: 3px solid var(--accent);
                      padding: 11px 16px; margin: 12px 0 18px; border-radius: 0 6px 6px 0;
                      font-size: 13px; line-height: 1.6; color: var(--ink-1); }
section .narrative b { color: var(--accent); }
section .insight { background: color-mix(in oklch, var(--warn) 8%, var(--bg-2)); border-left: 3px solid var(--warn);
                    padding: 10px 14px; margin: 14px 0 0; border-radius: 0 4px 4px 0;
                    font-size: 12.5px; line-height: 1.6; color: var(--ink-1); }
section .insight b { color: var(--warn); }
section .verdict-good { background: color-mix(in oklch, var(--pass) 10%, var(--bg-2)); border-left: 3px solid var(--pass);
                         padding: 10px 14px; margin: 14px 0 0; border-radius: 0 4px 4px 0;
                         font-size: 12.5px; line-height: 1.6; color: var(--ink-1); }

/* KPI grid — richer with subtitles + color tops */
.kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; }
.kpi { background: var(--bg-2); padding: 14px 16px; border-radius: 7px; border-top: 2.5px solid var(--accent);
       transition: transform 0.15s; }
.kpi:hover { transform: translateY(-1px); }
.kpi.pos { border-top-color: var(--pass); }
.kpi.neg { border-top-color: var(--fail); }
.kpi.warn { border-top-color: var(--warn); }
.kpi.info { border-top-color: var(--info); }
.kpi.purple { border-top-color: var(--purple); }
.kpi-l { font-size: 10.5px; color: var(--ink-3); letter-spacing: 0.06em; text-transform: uppercase; font-weight: 600; }
.kpi-v { font-size: 22px; font-family: var(--mono); font-weight: 800; margin-top: 6px; color: var(--ink-0);
         font-variant-numeric: tabular-nums; }
.kpi-sub { font-size: 10.5px; color: var(--ink-2); margin-top: 4px; line-height: 1.4; }

/* Tables */
table { width: 100%; border-collapse: collapse; font-family: var(--mono); font-size: 12px; }
th { text-align: left; padding: 10px 8px; color: var(--ink-2); border-bottom: 1px solid var(--rule);
     font-weight: 600; letter-spacing: 0.05em; cursor: pointer; user-select: none; transition: color 0.15s; }
th.num { text-align: right; }
th:hover { color: var(--accent); }
td { padding: 9px 8px; border-bottom: 1px solid color-mix(in oklch, var(--rule-2) 30%, transparent); color: var(--ink-1); }
td.num { text-align: right; font-variant-numeric: tabular-nums; }
tbody tr:hover { background: color-mix(in oklch, var(--bg-2) 60%, transparent); }

/* Tags / verdict pills */
.pass { color: var(--pass); }
.fail { color: var(--fail); }
.warn { color: var(--warn); }
.info { color: var(--info); }
.dim  { color: var(--ink-3); }
.tag  { display: inline-block; padding: 2px 7px; border-radius: 3px; font-size: 10px; font-weight: 800;
        letter-spacing: 0.05em; }
.tag.pass { background: var(--pass); color: var(--bg-0); }
.tag.fail { background: var(--fail); color: var(--bg-0); }
.tag.warn { background: var(--warn); color: var(--bg-0); }
.tag.info { background: var(--info); color: var(--bg-0); }

/* Bars — for tables AND inline visualizations */
.bar { background: var(--bg-3); height: 5px; border-radius: 2px; overflow: hidden; margin-top: 4px; }
.bar > div { height: 100%; background: var(--accent); }

/* Forest plot rows (Bayesian, Setup CI) */
.fp-row { display: grid; grid-template-columns: 220px 1fr 110px; gap: 12px; align-items: center;
           padding: 9px 0; border-bottom: 1px solid color-mix(in oklch, var(--rule-2) 30%, transparent); }
.fp-row:last-child { border-bottom: none; }
.fp-row .nm { font-family: var(--mono); font-size: 12.5px; color: var(--ink-0); }
.fp-row .nm small { color: var(--ink-3); font-weight: 400; font-size: 11px; }
.fp-row .ci { position: relative; height: 26px; background: var(--bg-3); border-radius: 4px; overflow: visible; }
.fp-row .ci::before { content: ''; position: absolute; left: 50%; top: 0; bottom: 0; width: 1px;
                       background: var(--ink-3); opacity: 0.4; }
.fp-row .ci .band { position: absolute; height: 16px; top: 5px; border-radius: 3px;
                     background: var(--accent); opacity: 0.45; }
.fp-row .ci .point { position: absolute; width: 12px; height: 12px; top: 7px; border-radius: 50%;
                      background: var(--accent); border: 2px solid var(--bg-1); box-shadow: 0 0 6px rgba(96,165,250,0.6); }
.fp-row .ci .band.fail { background: var(--fail); }
.fp-row .ci .point.fail { background: var(--fail); box-shadow: 0 0 6px rgba(239,68,68,0.6); }
.fp-row .ci .band.warn { background: var(--warn); }
.fp-row .ci .point.warn { background: var(--warn); box-shadow: 0 0 6px rgba(245,158,11,0.6); }
.fp-row .ci .band.pass { background: var(--pass); }
.fp-row .ci .point.pass { background: var(--pass); box-shadow: 0 0 6px rgba(16,185,129,0.6); }
.fp-row .v { font-family: var(--mono); font-size: 11.5px; color: var(--ink-1); text-align: right; }
.fp-axis { display: grid; grid-template-columns: 220px 1fr 110px; gap: 12px; padding: 4px 0; margin-bottom: 6px;
            font-family: var(--mono); font-size: 10.5px; color: var(--ink-3); }
.fp-axis .ticks { display: flex; justify-content: space-between; }

/* SHAP/Bonus waterfall */
.wf-row { display: grid; grid-template-columns: 240px 1fr 90px; gap: 12px; align-items: center;
           padding: 7px 0; font-size: 12.5px; border-bottom: 1px solid color-mix(in oklch, var(--rule-2) 30%, transparent); }
.wf-row .lbl { font-family: var(--mono); color: var(--ink-1); }
.wf-row .bar-c { position: relative; height: 18px; background: var(--bg-3); border-radius: 3px; overflow: hidden; }
.wf-row .bar-c::after { content: ''; position: absolute; left: 50%; top: 0; bottom: 0; width: 1px; background: var(--ink-3); opacity: 0.3; }
.wf-row .b { position: absolute; height: 100%; }
.wf-row .b.pos { background: var(--pass); left: 50%; }
.wf-row .b.neg { background: var(--fail); right: 50%; }
.wf-row .v { font-family: var(--mono); font-weight: 800; text-align: right; }
.wf-row .v.pos { color: var(--pass); }
.wf-row .v.neg { color: var(--fail); }
.wf-row .v.dim { color: var(--ink-3); }

/* Section header pill row (used for sub-sections) */
.subhead { font-size: 12.5px; color: var(--ink-2); margin: 18px 0 8px; letter-spacing: 0.06em;
            text-transform: uppercase; font-weight: 700; display: flex; align-items: center; gap: 10px; }
.subhead::before { content: ''; width: 6px; height: 6px; background: var(--accent); border-radius: 50%; }
.subhead .count { color: var(--ink-3); font-weight: 600; font-family: var(--mono); }

footer { padding: 26px 40px 36px; color: var(--ink-3); font-size: 11px; text-align: center;
          border-top: 1px solid var(--rule); margin-top: 30px; }
footer a { color: var(--accent); text-decoration: none; }
"""


def _verdict_explain(v: str) -> str:
    return {
        "ALPHA":  "WR lower-bound ≥45% AND expectancy >0.5% — statistically real edge",
        "EDGE":   "WR lower-bound ≥30% AND positive expectancy — promising, monitor",
        "FLAT":   "Marginal — keep observing",
        "KILL":   "Negative expectancy with sufficient sample — drop",
        "SAMPLE": "<10 trades — not enough data to judge",
    }.get(v, "")


def render_html(in_path: Path, summary: dict, eq_curve: dict, setup_table: list[dict],
                score_band: list[dict], risk: dict, decay: dict, counter: dict,
                trades: list[dict], regime_data: dict | None = None,
                hold_sweep: list[dict] | None = None, vix_band: list[dict] | None = None,
                catalyst: list[dict] | None = None, boot_ci: dict | None = None,
                bayes: list[dict] | None = None, drift: dict | None = None) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    json_setup = json.dumps(setup_table, default=str)
    json_band = json.dumps(score_band, default=str)
    json_eq = json.dumps(eq_curve, default=str)
    json_decay = json.dumps(decay, default=str)
    json_regime = json.dumps(regime_data or {"cells": [], "rollup": []}, default=str)
    json_hold = json.dumps(hold_sweep or [], default=str)
    json_vix = json.dumps(vix_band or [], default=str)
    json_catalyst = json.dumps(catalyst or [], default=str)
    json_boot = json.dumps(boot_ci or {}, default=str)
    json_bayes = json.dumps(bayes or [], default=str)
    json_drift = json.dumps(drift or {}, default=str)
    json_trades = json.dumps([{
        "ticker": t.get("ticker"), "entry_date": (t.get("entry_date") or "")[:10],
        "exit_date": (t.get("exit_date") or "")[:10], "setup": t.get("setup_type"),
        "score": t.get("score"), "entry": t.get("entry_price"), "exit": t.get("exit_price"),
        "stop": t.get("stop_price"), "pnl_pct": t.get("pnl_pct"), "pnl_dollar": t.get("pnl_dollar"),
        "exit_reason": t.get("exit_reason"), "hold": t.get("days_held"),
        "win": bool(t.get("win")),
    } for t in trades], default=str)

    # Summary KPI cards
    kpi_color = lambda val, neg_threshold=0: "pos" if val > neg_threshold else "neg" if val < 0 else "warn"
    pf_class = "pos" if summary["pf"] >= 1.5 else "warn" if summary["pf"] >= 1.0 else "neg"
    sharpe_class = "pos" if summary["sharpe"] >= 1.0 else "warn" if summary["sharpe"] >= 0 else "neg"

    summary_kpis = f"""
    <div class="kpi {pf_class}"><div class="kpi-l">Profit Factor</div><div class="kpi-v">{summary['pf']}</div><div class="kpi-sub">Σwins / Σlosses</div></div>
    <div class="kpi {sharpe_class}"><div class="kpi-l">Sharpe</div><div class="kpi-v">{summary['sharpe']}</div><div class="kpi-sub">risk-adjusted return</div></div>
    <div class="kpi neg"><div class="kpi-l">Max Drawdown</div><div class="kpi-v">{summary['max_dd_pct']}%</div><div class="kpi-sub">peak-to-trough</div></div>
    <div class="kpi {kpi_color(summary['total_return_pct'])}"><div class="kpi-l">Total Return</div><div class="kpi-v">{summary['total_return_pct']}%</div><div class="kpi-sub">${summary['total_pnl_dollar']:+,}</div></div>
    <div class="kpi {kpi_color(summary['wr_pct'] - 50)}"><div class="kpi-l">Win Rate</div><div class="kpi-v">{summary['wr_pct']}%</div><div class="kpi-sub">{summary['wins']}W / {summary['losses']}L · n={summary['n_trades']}</div></div>
    <div class="kpi {kpi_color(summary['expectancy_pct'])}"><div class="kpi-l">Expectancy</div><div class="kpi-v">{summary['expectancy_pct']}%</div><div class="kpi-sub">per trade</div></div>
    <div class="kpi {kpi_color(summary['calmar'] - 0.5)}"><div class="kpi-l">Calmar</div><div class="kpi-v">{summary['calmar']}</div><div class="kpi-sub">annual / max DD</div></div>
    <div class="kpi info"><div class="kpi-l">Annualized</div><div class="kpi-v">{summary['annual_return_pct']}%</div><div class="kpi-sub">extrapolated</div></div>
    """

    # Risk KPIs
    risk_kpis = "" if not risk else f"""
    <div class="kpi neg"><div class="kpi-l">Pain Index</div><div class="kpi-v">{risk['pain_index_pct']}%</div><div class="kpi-sub">avg |drawdown|</div></div>
    <div class="kpi neg"><div class="kpi-l">Ulcer Index</div><div class="kpi-v">{risk['ulcer_index_pct']}%</div><div class="kpi-sub">DD frequency × depth</div></div>
    <div class="kpi {'pos' if risk['calmar'] > 0.5 else 'warn'}"><div class="kpi-l">Calmar</div><div class="kpi-v">{risk['calmar']}</div><div class="kpi-sub">return / max DD</div></div>
    <div class="kpi {'pos' if risk['sortino'] > 1 else 'warn'}"><div class="kpi-l">Sortino</div><div class="kpi-v">{risk['sortino']}</div><div class="kpi-sub">return / downside σ</div></div>
    <div class="kpi neg"><div class="kpi-l">CVaR-95</div><div class="kpi-v">{risk['cvar_95_pct']}%</div><div class="kpi-sub">avg of worst 5%</div></div>
    <div class="kpi neg"><div class="kpi-l">CVaR-97.5</div><div class="kpi-v">{risk['cvar_97_5_pct']}%</div><div class="kpi-sub">avg of worst 2.5%</div></div>
    <div class="kpi warn"><div class="kpi-l">Max consec losses</div><div class="kpi-v">{risk['max_consec_losses']}</div><div class="kpi-sub">streak</div></div>
    <div class="kpi info"><div class="kpi-l">Downside σ</div><div class="kpi-v">{risk['downside_dev_pct']}%</div><div class="kpi-sub">annualized</div></div>
    """

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<title>Backtest Analytics — {now}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&family=JetBrains+Mono:wght@400;600;800&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/plotly.js-dist-min@2.35.2/plotly.min.js"></script>
<style>{_CSS}</style>
</head><body>
<header>
  <h1>Hedge-Fund Backtest Report</h1>
  <div class="sub">Generated {now} · Source: {in_path.name} · n={summary['n_trades']} trades</div>
</header>
<nav>
  <a href="#summary">① Summary</a><a href="#equity">② Equity</a><a href="#setup">③ Setup CI</a>
  <a href="#score">④ Score Band</a><a href="#regime">⑤ Regime×Setup</a>
  <a href="#hold">⑥ Hold Sweep</a><a href="#risk">⑦ Risk</a><a href="#vix">⑧ VIX</a>
  <a href="#catalyst">⑨ Catalysts</a><a href="#decay">⑩ Signal Decay</a>
  <a href="#counter">⑪ Counterfactuals</a><a href="#trades">⑫ Trades</a>
  <a href="#bootstrap">⑬ Bootstrap CI</a><a href="#bayes">⑭ Bayesian</a><a href="#drift">⑮ Drift</a>
</nav>
<main>

<section id="summary">
  <h2>① Executive summary</h2>
  <div class="desc">Top-line performance KPIs. Color: green = good, red = bad, amber = marginal. PF≥1.5 / Sharpe≥1.0 / WR≥50% are professional thresholds.</div>
  <div class="kpi-grid">{summary_kpis}</div>
</section>

<section id="equity">
  <h2>② Equity curve + drawdown</h2>
  <div class="desc">Account equity over time (top) with running drawdown shaded below (bottom). Persistent underwater periods = pain.</div>
  <div id="equityChart" style="height:480px;"></div>
</section>

<section id="setup">
  <h2><span class="num">③</span> Setup Performance — Wilson CI Gated <span class="tag live">LIVE</span></h2>
  <div class="desc">For each setup: point WR vs <b>Wilson 95% lower-bound</b>. ALPHA = real edge (WR_LB ≥45% + expectancy &gt;0.5%). KILL = negative expectancy. SAMPLE = n&lt;10.</div>
  <div class="narrative">
    <b>Trust the lower bound, not the point.</b> A setup at 50% WR with n=4 looks real but Wilson LB might be 9%. Always read the LB column first.
  </div>

  <h3 class="subhead">Win-rate forest plot</h3>
  <div style="background: var(--bg-2); padding: 16px 20px; border-radius: 8px;">
    <div class="fp-axis">
      <span></span>
      <span class="ticks"><span>0%</span><span>20%</span><span style="color:var(--warn);font-weight:700">50%</span><span>80%</span><span>100%</span></span>
      <span style="text-align:right;">point · LB</span>
    </div>
    <div id="setupForest"></div>
  </div>

  <h3 class="subhead">Detail table <span class="count">— sortable, expectancy + PF + verdict</span></h3>
  <table id="setupTable"><thead><tr>
    <th>Setup</th><th class="num">N</th><th class="num">WR%</th><th class="num">WR LB%</th>
    <th class="num">Avg P&amp;L%</th><th class="num">Total P&amp;L%</th>
    <th class="num">Avg Win%</th><th class="num">Avg Loss%</th>
    <th class="num">Expect%</th><th class="num">PF</th><th>Verdict</th>
  </tr></thead><tbody></tbody></table>
</section>

<section id="score">
  <h2>④ Score-band stratification</h2>
  <div class="desc">WR + expectancy by score band. Confirms whether higher-score picks actually perform better. The 70-79 band is where most trades live; check whether 80+ delivers premium WR or just fewer trades.</div>
  <table id="scoreTable"><thead><tr>
    <th>Band</th><th class="num">N</th><th class="num">WR%</th><th class="num">WR LB%</th>
    <th class="num">Avg P&amp;L%</th><th class="num">Total P&amp;L%</th><th class="num">Expect%</th>
  </tr></thead><tbody></tbody></table>
</section>

<section id="regime">
  <h2>⑤ Regime × Setup × Score-band matrix</h2>
  <div class="desc">Cross-tab WR by (regime, setup, score-band). Looks up regime from the daily bundle on each trade's entry date. Cells with low n are noise — focus on rollup table for stable patterns.</div>

  <h3 style="font-size:13px;margin:6px 0 6px;color:var(--ink-2);">Regime rollup</h3>
  <table id="regimeRollup"><thead><tr>
    <th>Regime</th><th class="num">N</th><th class="num">WR%</th><th class="num">Avg P&amp;L%</th>
  </tr></thead><tbody></tbody></table>

  <h3 style="font-size:13px;margin:18px 0 6px;color:var(--ink-2);">Full grid (n≥3 cells shown)</h3>
  <table id="regimeGrid"><thead><tr>
    <th>Regime</th><th>Setup</th><th>Band</th><th class="num">N</th>
    <th class="num">WR%</th><th class="num">WR LB%</th><th class="num">Avg P&amp;L%</th>
  </tr></thead><tbody></tbody></table>
</section>

<section id="hold">
  <h2>⑥ Hold-period sensitivity sweep</h2>
  <div class="desc">Replays each backtest entry through alternate exit horizons (3/5/7/10/15 trading days) using OHLCV archive. Stops still apply. Reveals whether 5-day hold is optimal or if longer/shorter would extract more alpha.</div>
  <table id="holdSweep"><thead><tr>
    <th class="num">Hold (days)</th><th class="num">N eligible</th><th class="num">WR%</th>
    <th class="num">Avg P&amp;L%</th><th class="num">Total P&amp;L%</th>
    <th class="num">Stop-outs</th><th class="num">Skipped</th>
  </tr></thead><tbody></tbody></table>
</section>

<section id="risk">
  <h2>⑦ Risk metrics suite</h2>
  <div class="desc">Beyond P&amp;L. Pain/Ulcer = drawdown intensity. Calmar &gt;0.5 = decent. Sortino &gt;1.0 = good downside-adj. CVaR-95 = average of worst 5% losses (tail risk).</div>
  <div class="kpi-grid">{risk_kpis}</div>
</section>

<section id="vix">
  <h2>⑧ VIX-regime conditional WR</h2>
  <div class="desc">Win rate sliced by VIX level at trade entry. VIX>25 historically destroys edge — confirms whether system has fair-weather behavior.</div>
  <table id="vixTable"><thead><tr>
    <th>VIX band</th><th class="num">N</th><th class="num">WR%</th>
    <th class="num">Avg P&amp;L%</th><th class="num">Total P&amp;L%</th>
  </tr></thead><tbody></tbody></table>
</section>

<section id="catalyst">
  <h2>⑨ Catalyst-conditional WR</h2>
  <div class="desc">Group trades by catalyst tags present at entry (BREAKOUT, MOMENTUM, EARNINGS_BEAT, INSIDER, etc.). Identifies which catalyst types add real alpha vs. random.</div>
  <table id="catTable"><thead><tr>
    <th>Catalyst</th><th class="num">N</th><th class="num">WR%</th><th class="num">WR LB%</th>
    <th class="num">Avg P&amp;L%</th><th class="num">Total P&amp;L%</th>
  </tr></thead><tbody></tbody></table>
</section>

<section id="decay">
  <h2>⑩ Signal decay — rolling WR per setup</h2>
  <div class="desc">Is the edge stable or fading? Rolling-N win rate over chronological order. Sharp decline = setup may be dying or regime-conditional.</div>
  <div id="decayChart" style="height:380px;"></div>
</section>

<section id="counter">
  <h2>⑪ Counterfactual sweeps</h2>
  <div class="desc">"What-if" analyses on existing trade set. Buy-min sweep: would different score thresholds change outcomes? Setup removal: which kills helped/hurt? Exit reason: where does P&amp;L actually come from?</div>

  <h3 style="font-size:13px;margin:10px 0 6px;color:var(--ink-2);">Buy-min threshold sweep</h3>
  <table id="cfBuyMin"><thead><tr>
    <th class="num">Threshold ≥</th><th class="num">Trades</th><th class="num">WR%</th><th class="num">Total %</th><th class="num">PF</th>
  </tr></thead><tbody></tbody></table>

  <h3 style="font-size:13px;margin:18px 0 6px;color:var(--ink-2);">Setup removal — what if X were killed?</h3>
  <table id="cfSetupKill"><thead><tr>
    <th>Removed setup</th><th class="num">Remaining N</th><th class="num">WR%</th>
    <th class="num">Total %</th><th class="num">Δ vs baseline</th><th class="num">PF</th>
  </tr></thead><tbody></tbody></table>

  <h3 style="font-size:13px;margin:18px 0 6px;color:var(--ink-2);">Exit-reason breakdown</h3>
  <table id="cfExit"><thead><tr>
    <th>Reason</th><th class="num">N</th><th class="num">WR%</th><th class="num">Total %</th><th class="num">Avg %</th>
  </tr></thead><tbody></tbody></table>
</section>

<section id="bootstrap">
  <h2>⑬ Bootstrap profit-factor confidence interval</h2>
  <div class="desc">Resamples trades with replacement 2000× to estimate uncertainty in PF / WR / total return. The point estimate alone is dangerous — if the 95% CI straddles PF=1.0, the system has not <i>statistically</i> proven edge despite a positive nominal result.</div>
  <div id="bootstrapKpis" class="kpi-grid"></div>
  <div id="bootstrapVerdict" style="margin-top:12px;font-size:13px;color:var(--ink-1);"></div>
</section>

<section id="bayes">
  <h2><span class="num">⑭</span> Bayesian Hierarchical Pooling <span class="tag live">LIVE</span></h2>
  <div class="desc">Sparse-setup correction. Each setup borrows strength from its family prior (breakout / pullback / continuation / reversal) via Beta-Binomial conjugate update. The wider the gap between <i>raw</i> and <i>posterior</i>, the less you should trust the raw estimate.</div>
  <div class="narrative">
    <b>How to read this:</b> The colored bar shows the posterior WR. Width = sample size (more trades → tighter band). When the bar is mostly inside the green zone (≥45%), the setup has real edge. Mostly red zone = kill candidate.
  </div>

  <div style="background: var(--bg-2); padding: 16px 20px; border-radius: 8px; margin-top: 14px;">
    <div class="fp-axis">
      <span></span>
      <span class="ticks"><span>0%</span><span>20%</span><span style="color:var(--warn);font-weight:700">50%</span><span>80%</span><span>100%</span></span>
      <span style="text-align:right;">posterior · CI</span>
    </div>
    <div id="bayesForest"></div>
  </div>

  <h3 class="subhead">Detail table <span class="count">— same data, sortable</span></h3>
  <table id="bayesTable"><thead><tr>
    <th>Setup</th><th>Family</th><th class="num">N</th>
    <th class="num">Raw WR%</th><th class="num">Prior WR%</th><th class="num">Posterior WR%</th>
    <th class="num">Shrinkage</th>
  </tr></thead><tbody></tbody></table>
</section>

<section id="drift">
  <h2>⑮ Live-vs-backtest drift status</h2>
  <div class="desc">Compares last 30 days of CLOSED live signals to backtest baseline. Alerts when live WR diverges by &gt;5pp. Run <code>python3 model_drift_alert.py</code> daily to populate.</div>
  <div id="driftBody" style="font-family: var(--mono); font-size: 13px; line-height: 1.7;"></div>
</section>

<section id="trades">
  <h2>⑫ Trade-level table</h2>
  <div class="desc">Every backtest trade. Click any column header to sort. Win=green row, loss=red.</div>
  <table id="tradesTable"><thead><tr>
    <th>Ticker</th><th>Entry</th><th>Exit</th><th>Setup</th>
    <th class="num">Score</th><th class="num">Entry $</th><th class="num">Exit $</th>
    <th class="num">Stop $</th><th class="num">P&amp;L%</th><th class="num">P&amp;L$</th>
    <th>Exit reason</th><th class="num">Hold</th>
  </tr></thead><tbody></tbody></table>
</section>

</main>
<footer>SwingTrade backtest analytics · {now}</footer>

<script>
const SETUP = {json_setup};
const BAND = {json_band};
const EQ = {json_eq};
const DECAY = {json_decay};
const TRADES = {json_trades};
const REGIME = {json_regime};
const HOLD = {json_hold};
const VIX = {json_vix};
const CATALYST = {json_catalyst};
const BOOT = {json_boot};
const BAYES = {json_bayes};
const DRIFT = {json_drift};
const COUNTER = {{
  buy_min: {json.dumps(counter.get("buy_min_sweep", []))},
  setup_kill: {json.dumps(counter.get("setup_removal", []))},
  exit_reason: {json.dumps(counter.get("exit_reason", []))}
}};

function fillTable(id, rows, cols) {{
  const tb = document.querySelector('#' + id + ' tbody');
  tb.innerHTML = rows.map(r => '<tr>' + cols.map(c => {{
    const v = r[c.key];
    const cls = c.cls ? c.cls(v, r) : (c.num ? 'num' : '');
    const disp = c.fmt ? c.fmt(v, r) : (v == null ? '—' : v);
    return '<td class="' + cls + '">' + disp + '</td>';
  }}).join('') + '</tr>').join('');
}}

// Setup table
fillTable('setupTable', SETUP, [
  {{ key: 'setup' }},
  {{ key: 'n', num: true }},
  {{ key: 'wr_pct', num: true, fmt: v => v.toFixed(1) }},
  {{ key: 'wr_lb_pct', num: true, fmt: v => v.toFixed(1), cls: v => v >= 45 ? 'num pass' : v >= 30 ? 'num info' : 'num fail' }},
  {{ key: 'avg_pnl_pct', num: true, fmt: v => v.toFixed(2), cls: v => v > 0 ? 'num pass' : 'num fail' }},
  {{ key: 'total_pnl_pct', num: true, fmt: v => v.toFixed(1), cls: v => v > 0 ? 'num pass' : 'num fail' }},
  {{ key: 'avg_win_pct', num: true, fmt: v => v.toFixed(2), cls: () => 'num pass' }},
  {{ key: 'avg_loss_pct', num: true, fmt: v => v.toFixed(2), cls: () => 'num fail' }},
  {{ key: 'expectancy_pct', num: true, fmt: v => v.toFixed(2), cls: v => v > 0 ? 'num pass' : 'num fail' }},
  {{ key: 'pf', num: true }},
  {{ key: 'verdict', fmt: (v, r) => '<span class="tag ' + r.verdict_color + '">' + v + '</span>' }},
]);

// Score band
fillTable('scoreTable', BAND, [
  {{ key: 'band' }},
  {{ key: 'n', num: true }},
  {{ key: 'wr_pct', num: true, fmt: v => v.toFixed(1) }},
  {{ key: 'wr_lb_pct', num: true, fmt: v => v.toFixed(1) }},
  {{ key: 'avg_pnl_pct', num: true, fmt: v => v.toFixed(2), cls: v => v > 0 ? 'num pass' : 'num fail' }},
  {{ key: 'total_pnl_pct', num: true, fmt: v => v.toFixed(1), cls: v => v > 0 ? 'num pass' : 'num fail' }},
  {{ key: 'expectancy_pct', num: true, fmt: v => v.toFixed(2), cls: v => v > 0 ? 'num pass' : 'num fail' }},
]);

// Counterfactual: buy_min sweep
fillTable('cfBuyMin', COUNTER.buy_min, [
  {{ key: 'threshold', num: true }},
  {{ key: 'n', num: true }},
  {{ key: 'wr_pct', num: true, fmt: v => v.toFixed(1) }},
  {{ key: 'total_pct', num: true, fmt: v => v.toFixed(1), cls: v => v > 0 ? 'num pass' : 'num fail' }},
  {{ key: 'pf', num: true }},
]);

// Setup removal
fillTable('cfSetupKill', COUNTER.setup_kill, [
  {{ key: 'kill' }},
  {{ key: 'remaining_n', num: true }},
  {{ key: 'wr_pct', num: true, fmt: v => v.toFixed(1) }},
  {{ key: 'total_pct', num: true, fmt: v => v.toFixed(1), cls: v => v > 0 ? 'num pass' : 'num fail' }},
  {{ key: 'delta_pct', num: true, fmt: v => (v >= 0 ? '+' : '') + v.toFixed(1), cls: v => v > 0 ? 'num pass' : v < 0 ? 'num fail' : 'num dim' }},
  {{ key: 'pf', num: true }},
]);

// Exit reason
fillTable('cfExit', COUNTER.exit_reason, [
  {{ key: 'reason' }},
  {{ key: 'n', num: true }},
  {{ key: 'wr_pct', num: true, fmt: v => v.toFixed(1) }},
  {{ key: 'total_pct', num: true, fmt: v => v.toFixed(1), cls: v => v > 0 ? 'num pass' : 'num fail' }},
  {{ key: 'avg_pct', num: true, fmt: v => v.toFixed(2), cls: v => v > 0 ? 'num pass' : 'num fail' }},
]);

// Regime rollup
fillTable('regimeRollup', REGIME.rollup || [], [
  {{ key: 'regime' }},
  {{ key: 'n', num: true }},
  {{ key: 'wr_pct', num: true, fmt: v => v.toFixed(1), cls: v => v >= 50 ? 'num pass' : 'num fail' }},
  {{ key: 'avg_pnl_pct', num: true, fmt: v => v.toFixed(2), cls: v => v > 0 ? 'num pass' : 'num fail' }},
]);

// Regime grid (filter cells with n>=3)
fillTable('regimeGrid', (REGIME.cells || []).filter(c => c.n >= 3), [
  {{ key: 'regime' }},
  {{ key: 'setup' }},
  {{ key: 'band' }},
  {{ key: 'n', num: true }},
  {{ key: 'wr_pct', num: true, fmt: v => v.toFixed(1) }},
  {{ key: 'wr_lb_pct', num: true, fmt: v => v.toFixed(1), cls: v => v >= 45 ? 'num pass' : v >= 30 ? 'num info' : 'num fail' }},
  {{ key: 'avg_pnl_pct', num: true, fmt: v => v.toFixed(2), cls: v => v > 0 ? 'num pass' : 'num fail' }},
]);

// Hold sweep
fillTable('holdSweep', HOLD, [
  {{ key: 'hold_days', num: true, fmt: v => v + 'd' }},
  {{ key: 'n_eligible', num: true }},
  {{ key: 'wr_pct', num: true, fmt: v => v.toFixed(1) }},
  {{ key: 'avg_pnl_pct', num: true, fmt: v => v.toFixed(2), cls: v => v > 0 ? 'num pass' : 'num fail' }},
  {{ key: 'total_pnl_pct', num: true, fmt: v => v.toFixed(1), cls: v => v > 0 ? 'num pass' : 'num fail' }},
  {{ key: 'stop_outs', num: true }},
  {{ key: 'skipped', num: true, cls: () => 'num dim' }},
]);

// VIX band
fillTable('vixTable', VIX, [
  {{ key: 'vix_band' }},
  {{ key: 'n', num: true }},
  {{ key: 'wr_pct', num: true, fmt: v => v.toFixed(1) }},
  {{ key: 'avg_pnl_pct', num: true, fmt: v => v.toFixed(2), cls: v => v > 0 ? 'num pass' : 'num fail' }},
  {{ key: 'total_pnl_pct', num: true, fmt: v => v.toFixed(1), cls: v => v > 0 ? 'num pass' : 'num fail' }},
]);

// Catalyst
fillTable('catTable', CATALYST, [
  {{ key: 'catalyst' }},
  {{ key: 'n', num: true }},
  {{ key: 'wr_pct', num: true, fmt: v => v.toFixed(1) }},
  {{ key: 'wr_lb_pct', num: true, fmt: v => v.toFixed(1), cls: v => v >= 45 ? 'num pass' : v >= 30 ? 'num info' : 'num fail' }},
  {{ key: 'avg_pnl_pct', num: true, fmt: v => v.toFixed(2), cls: v => v > 0 ? 'num pass' : 'num fail' }},
  {{ key: 'total_pnl_pct', num: true, fmt: v => v.toFixed(1), cls: v => v > 0 ? 'num pass' : 'num fail' }},
]);

// Section ⑬ — Bootstrap CI
if (BOOT && BOOT.pf_point !== null && BOOT.pf_point !== undefined) {{
  const pfClass = BOOT.pf_lo >= 1.5 ? 'pos' : BOOT.pf_lo >= 1.0 ? 'info' : BOOT.pf_lo >= 0.8 ? 'warn' : 'neg';
  document.getElementById('bootstrapKpis').innerHTML = `
    <div class="kpi info"><div class="kpi-l">PF point</div><div class="kpi-v">${{BOOT.pf_point}}</div><div class="kpi-sub">observed</div></div>
    <div class="kpi ${{pfClass}}"><div class="kpi-l">PF 95% CI</div><div class="kpi-v">[${{BOOT.pf_lo}}, ${{BOOT.pf_hi}}]</div><div class="kpi-sub">${{BOOT.n_iter}} resamples</div></div>
    <div class="kpi info"><div class="kpi-l">WR point</div><div class="kpi-v">${{BOOT.wr_point}}%</div></div>
    <div class="kpi info"><div class="kpi-l">WR 95% CI</div><div class="kpi-v">[${{BOOT.wr_lo}}, ${{BOOT.wr_hi}}]%</div></div>
    <div class="kpi neg"><div class="kpi-l">Total CI lo</div><div class="kpi-v">${{BOOT.total_lo}}%</div></div>
    <div class="kpi pos"><div class="kpi-l">Total CI hi</div><div class="kpi-v">${{BOOT.total_hi}}%</div></div>
  `;
  const verdictColor = BOOT.pf_lo >= 1.5 ? 'var(--pass)' : BOOT.pf_lo >= 1.0 ? 'var(--info)' : BOOT.pf_lo >= 0.8 ? 'var(--warn)' : 'var(--fail)';
  document.getElementById('bootstrapVerdict').innerHTML =
    '<b style="color:' + verdictColor + ';">' + BOOT.interpretation.toUpperCase() + '</b> — ' +
    (BOOT.pf_lo >= 1.0
      ? 'sample size sufficient to claim edge with 95% confidence.'
      : 'sample too small to statistically prove edge. Need more trades or longer backtest window.');
}}

// Section ⑭ — Bayesian
fillTable('bayesTable', BAYES, [
  {{ key: 'setup' }},
  {{ key: 'family' }},
  {{ key: 'n', num: true }},
  {{ key: 'raw_wr', num: true, fmt: v => v.toFixed(1) }},
  {{ key: 'prior_wr', num: true, fmt: v => v.toFixed(1), cls: () => 'num dim' }},
  {{ key: 'posterior_wr', num: true, fmt: v => v.toFixed(1), cls: v => v >= 50 ? 'num pass' : v >= 35 ? 'num info' : 'num fail' }},
  {{ key: 'shrinkage_pp', num: true, fmt: v => v.toFixed(1) + 'pp' }},
]);

// Section ⑮ — Drift
const dEl = document.getElementById('driftBody');
if (DRIFT && DRIFT.available) {{
  const cls = DRIFT.alert_fired ? 'fail' : Math.abs(DRIFT.delta_pp) > 3 ? 'warn' : 'pass';
  const icon = DRIFT.alert_fired ? '🚨' : Math.abs(DRIFT.delta_pp) > 3 ? '⚠️' : '✓';
  dEl.innerHTML = `
    <div>${{icon}} Drift status: <b class="${{cls}}">${{DRIFT.alert_fired ? 'ALERT FIRED' : 'within tolerance'}}</b></div>
    <div style="margin-top:8px;color:var(--ink-2);">
      Last check: ${{DRIFT.timestamp}}<br>
      Window: ${{DRIFT.window_days}} days · Trades observed: ${{DRIFT.n_live}}<br>
      Live WR: <b>${{DRIFT.live_wr_pct}}%</b> · Backtest WR: <b>${{DRIFT.backtest_wr_pct}}%</b><br>
      Delta: <b class="${{cls}}">${{DRIFT.delta_pp >= 0 ? '+' : ''}}${{DRIFT.delta_pp}}pp</b> (alert threshold: ±${{DRIFT.alert_threshold_pp}}pp)
    </div>`;
}} else {{
  dEl.innerHTML = `<div class="dim">${{DRIFT.reason || 'Drift log not yet generated.'}}<br>Run <code>python3 model_drift_alert.py</code> to start tracking.</div>`;
}}

// Trades table
fillTable('tradesTable', TRADES, [
  {{ key: 'ticker', fmt: (v, r) => '<a href="/kairos.html?t=' + v + '" style="color:var(--accent);text-decoration:none;">' + v + '</a>' }},
  {{ key: 'entry_date' }},
  {{ key: 'exit_date' }},
  {{ key: 'setup' }},
  {{ key: 'score', num: true }},
  {{ key: 'entry', num: true, fmt: v => v ? '$' + v.toFixed(2) : '—' }},
  {{ key: 'exit', num: true, fmt: v => v ? '$' + v.toFixed(2) : '—' }},
  {{ key: 'stop', num: true, fmt: v => v ? '$' + v.toFixed(2) : '—' }},
  {{ key: 'pnl_pct', num: true, fmt: v => v != null ? (v >= 0 ? '+' : '') + v.toFixed(2) + '%' : '—', cls: v => v > 0 ? 'num pass' : 'num fail' }},
  {{ key: 'pnl_dollar', num: true, fmt: v => v != null ? (v >= 0 ? '+$' : '-$') + Math.abs(v).toFixed(0) : '—', cls: v => v > 0 ? 'num pass' : 'num fail' }},
  {{ key: 'exit_reason' }},
  {{ key: 'hold', num: true, fmt: v => v + 'd' }},
]);

// Equity + drawdown chart
if (EQ.dates && EQ.dates.length) {{
  Plotly.newPlot('equityChart', [
    {{ x: EQ.dates, y: EQ.equity, type: 'scatter', mode: 'lines', name: 'Equity',
       line: {{ color: '#60a5fa', width: 2 }}, yaxis: 'y' }},
    {{ x: EQ.dates, y: EQ.drawdown, type: 'scatter', mode: 'lines', name: 'Drawdown %',
       line: {{ color: '#ef4444', width: 1.5 }}, fill: 'tozeroy', fillcolor: 'rgba(239,68,68,0.15)', yaxis: 'y2' }},
  ], {{
    paper_bgcolor: '#111827', plot_bgcolor: '#0a0e1a',
    font: {{ family: 'Inter, system-ui', color: '#cbd5e1', size: 11 }},
    xaxis: {{ gridcolor: '#334155', zeroline: false }},
    yaxis: {{ title: 'Equity ($)', gridcolor: '#334155', zeroline: false, domain: [0.4, 1] }},
    yaxis2: {{ title: 'Drawdown (%)', gridcolor: '#334155', zeroline: true, zerolinecolor: '#475569', domain: [0, 0.32], tickformat: '.1f' }},
    margin: {{ t: 16, l: 60, r: 50, b: 40 }}, showlegend: true, legend: {{ orientation: 'h', y: 1.05 }},
  }}, {{ responsive: true, displayModeBar: false }});
}}

// Signal decay chart — one line per setup
const decayTraces = [];
const decayColors = ['#10b981', '#60a5fa', '#f59e0b', '#06b6d4', '#a78bfa', '#ec4899'];
let i = 0;
for (const [setup, rolling] of Object.entries(DECAY)) {{
  decayTraces.push({{
    x: rolling.map(p => p.exit_date), y: rolling.map(p => p.wr),
    type: 'scatter', mode: 'lines+markers', name: setup,
    line: {{ color: decayColors[i % decayColors.length], width: 2 }},
    marker: {{ size: 5 }},
  }});
  i++;
}}
if (decayTraces.length) {{
  Plotly.newPlot('decayChart', decayTraces, {{
    paper_bgcolor: '#111827', plot_bgcolor: '#0a0e1a',
    font: {{ family: 'Inter, system-ui', color: '#cbd5e1', size: 11 }},
    xaxis: {{ title: 'Exit date', gridcolor: '#334155' }},
    yaxis: {{ title: 'Rolling WR (%)', gridcolor: '#334155', range: [0, 100] }},
    margin: {{ t: 16, l: 60, r: 30, b: 50 }}, legend: {{ orientation: 'h', y: -0.2 }},
  }}, {{ responsive: true, displayModeBar: false }});
}} else {{
  document.getElementById('decayChart').innerHTML = '<div style="padding:30px;color:var(--ink-3);text-align:center;">Not enough trades per setup for rolling WR (need ≥5 per setup).</div>';
}}

// Sortable table headers — vanilla JS
document.querySelectorAll('table').forEach(table => {{
  const headers = table.querySelectorAll('th');
  headers.forEach((th, idx) => {{
    let asc = true;
    th.addEventListener('click', () => {{
      const tbody = table.querySelector('tbody');
      const rows = Array.from(tbody.rows);
      rows.sort((a, b) => {{
        const aV = a.cells[idx].textContent.replace(/[$%,+]/g, '').trim();
        const bV = b.cells[idx].textContent.replace(/[$%,+]/g, '').trim();
        const aN = parseFloat(aV); const bN = parseFloat(bV);
        if (!isNaN(aN) && !isNaN(bN)) return asc ? aN - bN : bN - aN;
        return asc ? aV.localeCompare(bV) : bV.localeCompare(aV);
      }});
      rows.forEach(r => tbody.appendChild(r));
      asc = !asc;
    }});
  }});
}});
</script>
</body></html>
"""


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--in", dest="in_path", default=str(DEFAULT_IN))
    p.add_argument("--out", dest="out_path", default=None)
    p.add_argument("--open", action="store_true", help="Open the report in browser after generating")
    args = p.parse_args()

    in_path = Path(args.in_path)
    if not in_path.exists():
        print(f"ERR: input not found: {in_path}")
        return 1
    data = json.loads(in_path.read_text())
    trades = data.get("trades") or []
    if not trades:
        print(f"ERR: no trades in {in_path}")
        return 1

    print(f"Loaded {len(trades)} trades from {in_path.name}")
    summary = section_summary(data, trades)
    eq_curve = section_equity_curve(data)
    setup_table = section_setup_table(trades)
    score_band = section_score_band(trades)
    risk = section_risk_metrics(data, trades)
    decay = section_signal_decay(trades)
    counter = section_counterfactuals(trades)
    print("Phase 2/3 — pulling external context (regime, VIX, catalysts, OHLCV)...")
    regime_data = section_regime_matrix(trades)
    vix_band = section_vix_regime(trades)
    catalyst = section_catalyst_wr(trades)
    print("  Regime matrix: %d cells, %d regimes" % (len(regime_data["cells"]), len(regime_data["rollup"])))
    print("  VIX bands populated: %d" % sum(1 for r in vix_band if r["n"]))
    print("  Catalyst groups: %d" % len(catalyst))
    print("Hold-period replay (uses data/ohlcv/*.parquet)...")
    hold_sweep = section_hold_sweep(trades)
    print("  Horizons evaluated: %d" % len(hold_sweep))
    print("Hedge-fund enhancers (bootstrap CI, Bayesian, drift, CV, stability)...")
    boot_ci = section_bootstrap_ci(trades)
    bayes = section_bayesian_setups(trades)
    drift = section_drift_status()
    tt_split = section_train_test_holdout(trades)
    kfold = section_kfold_cv(trades)
    stability = section_signal_stability(trades)
    print(f"  Bootstrap PF CI: [{boot_ci.get('pf_lo')}, {boot_ci.get('pf_hi')}]")
    print(f"  Bayesian setups pooled: {len(bayes)}")
    print(f"  Drift available: {drift.get('available', False)}")
    print(f"  Train/test/holdout: {tt_split.get('interpretation','?')}")
    print(f"  K-fold CV (5): mean PF={kfold.get('mean_pf','?')} CV={kfold.get('cv','?')} ({kfold.get('interpretation','?')})")
    print(f"  Signal stability: {len(stability.get('rows',[]))} setups analyzed")

    html = render_html(in_path, summary, eq_curve, setup_table, score_band,
                       risk, decay, counter, trades, regime_data=regime_data,
                       hold_sweep=hold_sweep, vix_band=vix_band, catalyst=catalyst,
                       boot_ci=boot_ci, bayes=bayes, drift=drift)

    out_path = (Path(args.out_path) if args.out_path
                else BASE / "cache" / f"backtest_report_{datetime.now():%Y%m%d_%H%M%S}.html")
    out_path.write_text(html)

    # Also write a stable "latest" pointer so /v2/backtest-report can serve newest
    latest = BASE / "cache" / "backtest_report_latest.html"
    try:
        if latest.exists() or latest.is_symlink():
            latest.unlink()
        latest.write_text(html)  # write a copy (symlinks are flaky on macOS)
    except Exception as e:
        print(f"  (latest pointer skipped: {e})")

    print(f"\n✓ Generated: {out_path}")
    print(f"  Size: {out_path.stat().st_size:,} bytes")
    print(f"  Sections: 1-12 (all)")
    print(f"  Latest copy: {latest}")
    print(f"\n  Open: file://{out_path}")
    print(f"  Or: http://localhost:7432/v2/backtest-report")

    if args.open:
        webbrowser.open(f"file://{out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
