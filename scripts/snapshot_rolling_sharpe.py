#!/usr/bin/env python3
"""
snapshot_rolling_sharpe.py — Compute rolling Sharpe/Sortino/Calmar from
closed_trades and write a daily row to rolling_sharpe_history.

Audit principle 11 (edge erosion): without persistent time series we can't
detect strategy decay. This script runs Mon-Fri 4:30pm PT via launchd.

Usage:
    python3 scripts/snapshot_rolling_sharpe.py            # dry-run
    python3 scripts/snapshot_rolling_sharpe.py --apply    # write to Supabase
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WINDOWS = [30, 63, 126, 252]  # standard quant windows in trading days


def _load_dotenv():
    p = ROOT / ".env"
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if k.strip() and k.strip() not in os.environ:
            os.environ[k.strip()] = v.strip()


def _h(*parts) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:32]


def _annualize_sharpe(daily_returns: list[float]) -> float | None:
    if len(daily_returns) < 2:
        return None
    mean = sum(daily_returns) / len(daily_returns)
    var = sum((r - mean) ** 2 for r in daily_returns) / max(len(daily_returns) - 1, 1)
    std = math.sqrt(var)
    if std == 0:
        return None
    return (mean / std) * math.sqrt(252)


def _annualize_sortino(daily_returns: list[float]) -> float | None:
    if len(daily_returns) < 2:
        return None
    mean = sum(daily_returns) / len(daily_returns)
    downside = [r for r in daily_returns if r < 0]
    if not downside:
        return None
    downside_var = sum(r ** 2 for r in downside) / len(downside)
    downside_std = math.sqrt(downside_var)
    if downside_std == 0:
        return None
    return (mean / downside_std) * math.sqrt(252)


def _max_drawdown(equity_series: list[float]) -> float:
    if not equity_series:
        return 0.0
    peak = equity_series[0]
    max_dd = 0.0
    for v in equity_series:
        if v > peak:
            peak = v
        dd = (peak - v) / peak if peak else 0.0
        if dd > max_dd:
            max_dd = dd
    return max_dd


def _build_pnl_pct_series(closed_trades: list[dict], cutoff_iso: str) -> list[float]:
    """Group trades by exit_date, sum pnl_pct per day. Returns chronological list."""
    by_day: dict[str, float] = {}
    for t in closed_trades:
        d = (t.get("exit_date") or "")[:10]
        if not d or d < cutoff_iso:
            continue
        try:
            by_day[d] = by_day.get(d, 0) + float(t.get("pnl_pct") or 0)
        except (TypeError, ValueError):
            continue
    return [by_day[d] for d in sorted(by_day)]


def compute_snapshot(closed_trades: list[dict], window_days: int) -> dict:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days)).date().isoformat()
    in_window = [t for t in closed_trades if (t.get("exit_date") or "")[:10] >= cutoff]
    if not in_window:
        return {"n_trades": 0}

    daily_pct = _build_pnl_pct_series(closed_trades, cutoff)
    daily_decimal = [p / 100.0 for p in daily_pct]
    sharpe = _annualize_sharpe(daily_decimal)
    sortino = _annualize_sortino(daily_decimal)

    # Equity curve from daily compounding
    equity = [1.0]
    for r in daily_decimal:
        equity.append(equity[-1] * (1 + r))
    max_dd = _max_drawdown(equity)
    calmar = (sharpe / max_dd) if (sharpe is not None and max_dd > 0) else None

    n_trades = len(in_window)
    wins = sum(1 for t in in_window if (t.get("win") in (1, True, "true", "t") or (t.get("pnl_pct") or 0) > 0))
    win_rate = wins / n_trades
    gross_wins = sum(float(t.get("pnl_pct") or 0) for t in in_window if (t.get("pnl_pct") or 0) > 0)
    gross_losses = abs(sum(float(t.get("pnl_pct") or 0) for t in in_window if (t.get("pnl_pct") or 0) < 0))
    pf = (gross_wins / gross_losses) if gross_losses > 0 else None
    avg_r = sum(float(t.get("r_multiple") or 0) for t in in_window if t.get("r_multiple") is not None) / max(n_trades, 1)

    return {
        "n_trades": n_trades,
        "sharpe": sharpe,
        "sortino": sortino,
        "calmar": calmar,
        "max_drawdown": max_dd,
        "win_rate": win_rate,
        "profit_factor": pf,
        "avg_r_multiple": avg_r if avg_r else None,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    _load_dotenv()
    os.environ["SUPABASE_MODE"] = "1"
    sys.path.insert(0, str(ROOT))
    from supabase_client import sb_client, healthcheck

    hc = healthcheck()
    print(f"Supabase healthcheck: ok={hc['ok']}")
    if not hc["ok"]:
        return 2

    # Load closed_trades from JSON canonical
    pf = ROOT / "data" / "portfolio_state.json"
    closed: list[dict] = []
    if pf.exists():
        j = json.loads(pf.read_text())
        closed.extend(j.get("closed_trades") or [])
    # Also pull from cache/picks_history.json trades (backtest equivalent)
    ph = ROOT / "cache" / "picks_history.json"
    if ph.exists():
        j = json.loads(ph.read_text())
        for t in (j.get("trades") or []):
            if t.get("exit_date"):
                closed.append({
                    "exit_date": t.get("exit_date"),
                    "pnl_pct": t.get("pct_chg"),
                    "win": t.get("win"),
                    "r_multiple": None,
                })

    print(f"Loaded {len(closed)} closed trade rows (live + backtest)")
    now_iso = datetime.now(timezone.utc).isoformat()
    rows = []
    for w in WINDOWS:
        snap = compute_snapshot(closed, w)
        print(f"  window={w:>3}d  trades={snap.get('n_trades',0):>4}  "
              f"sharpe={snap.get('sharpe')}  PF={snap.get('profit_factor')}  "
              f"WR={snap.get('win_rate')}")
        if snap.get("n_trades", 0) == 0:
            continue
        rows.append({
            "observed_at": now_iso,
            "window_days": w,
            "sharpe": snap.get("sharpe"),
            "sortino": snap.get("sortino"),
            "calmar": snap.get("calmar"),
            "max_drawdown": snap.get("max_drawdown"),
            "n_trades": snap.get("n_trades"),
            "win_rate": snap.get("win_rate"),
            "profit_factor": snap.get("profit_factor"),
            "avg_r_multiple": snap.get("avg_r_multiple"),
            "sync_key": _h("rs", now_iso[:10], w),
            "raw_json": json.dumps(snap),
        })

    if not args.apply:
        print("\nDry-run. Re-run with --apply.")
        return 0
    if not rows:
        print("No windows had data; nothing to write.")
        return 0

    sb = sb_client()
    try:
        # sync_key is unique per (date, window) — re-runs same day update in place
        sb.table("rolling_sharpe_history").upsert(rows, on_conflict="sync_key").execute()
        print(f"\n✓ Wrote {len(rows)} snapshots")
    except Exception as e:
        print(f"✗ Write failed: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
