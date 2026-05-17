#!/usr/bin/env python3
"""
snapshot_portfolio_risk.py — Daily portfolio + per-position risk snapshot.

Writes to:
  - position_risk_snapshot  (one row per open position)
  - portfolio_risk_history  (one row total)

Inputs:
  - data/portfolio_state.json (positions + equity)
  - cache/picks_history.json (for beta/correlation if needed)

Usage:
    python3 scripts/snapshot_portfolio_risk.py            # dry-run
    python3 scripts/snapshot_portfolio_risk.py --apply
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORTFOLIO_JSON = ROOT / "data" / "portfolio_state.json"


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


def _compute_position_var(market_value: float, beta: float, spy_vol_daily: float = 0.012) -> float:
    """1-day 95% VaR via parametric (1.65σ on beta-adjusted vol)."""
    if not market_value or not beta:
        return 0.0
    return market_value * abs(beta) * spy_vol_daily * 1.65


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

    if not PORTFOLIO_JSON.exists():
        print(f"ERROR: {PORTFOLIO_JSON} not found"); return 1
    state = json.loads(PORTFOLIO_JSON.read_text())
    positions = state.get("positions") or []
    equity = float(state.get("equity") or 0)
    cash = float(state.get("cash") or 0)
    now = datetime.now(timezone.utc).isoformat()
    today = now[:10]

    # === Per-position rows ===
    pos_rows = []
    sector_exposure: dict[str, float] = {}
    total_mv = 0.0
    total_risk_dollars = 0.0
    total_var_95 = 0.0
    largest_pct = 0.0
    betas: list[tuple[float, float]] = []  # (weight, beta)

    for p in positions:
        ticker = p.get("ticker")
        if not ticker:
            continue
        shares = float(p.get("shares") or 0)
        entry = float(p.get("entry_price") or 0)
        current = float(p.get("current_price") or entry)
        stop = float(p.get("stop") or 0)
        sector = p.get("sector") or "unknown"
        beta = float(p.get("beta") or 1.0)
        mv = shares * current
        risk = max(0.0, (entry - stop) * shares)
        risk_pct = (risk / equity * 100) if equity else 0
        notional_pct = (mv / equity * 100) if equity else 0
        var_95 = _compute_position_var(mv, beta)

        sector_exposure[sector] = sector_exposure.get(sector, 0) + mv
        total_mv += mv
        total_risk_dollars += risk
        total_var_95 += var_95
        if notional_pct > largest_pct:
            largest_pct = notional_pct
        betas.append((mv, beta))

        unrealized_d = (current - entry) * shares
        unrealized_pct = ((current / entry) - 1) * 100 if entry else 0
        days_held = 0
        try:
            entry_date = (p.get("entry_date") or "")[:10]
            if entry_date:
                d0 = datetime.strptime(entry_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                days_held = (datetime.now(timezone.utc) - d0).days
        except Exception:
            pass

        pos_rows.append({
            "snapshot_at": now,
            "ticker": ticker,
            "market_value": mv,
            "notional_pct_portfolio": notional_pct,
            "risk_dollars": risk,
            "risk_pct_portfolio": risk_pct,
            "var_95_1d": var_95,
            "cvar_95_1d": var_95 * 1.27,  # approximation: E[loss|loss>VaR] ≈ 1.27 × VaR for normal
            "var_99_1d": var_95 * 1.41,   # 2.33σ / 1.65σ
            "beta_to_spy": beta,
            "sector": sector,
            "unrealized_pnl_pct": unrealized_pct,
            "unrealized_pnl_dollars": unrealized_d,
            "days_held": days_held,
            "sync_key": _h("pr", today, ticker),
            "raw_json": json.dumps(p, default=str),
        })

    # Sector concentration (largest sector pct)
    sector_max_pct = (max(sector_exposure.values()) / equity * 100) if (sector_exposure and equity) else 0
    # Portfolio beta = exposure-weighted
    portfolio_beta = (sum(w * b for w, b in betas) / total_mv) if total_mv > 0 else 0
    # Top3 concentration
    sorted_pos = sorted(pos_rows, key=lambda x: -x["market_value"])
    top3_pct = sum(p["notional_pct_portfolio"] for p in sorted_pos[:3])

    portfolio_row = {
        "snapshot_at": now,
        "n_positions": len(pos_rows),
        "total_exposure_pct": (total_mv / equity * 100) if equity else 0,
        "gross_exposure_pct": (total_mv / equity * 100) if equity else 0,
        "net_exposure_pct": (total_mv / equity * 100) if equity else 0,
        "portfolio_beta": portfolio_beta,
        "portfolio_var_95_1d": total_var_95,
        "portfolio_cvar_95_1d": total_var_95 * 1.27,
        "largest_position_pct": largest_pct,
        "top3_concentration_pct": top3_pct,
        "sector_max_pct": sector_max_pct,
        "sync_key": _h("port", today),
        "raw_json": json.dumps({
            "sector_exposure": sector_exposure,
            "equity": equity,
            "cash": cash,
            "total_mv": total_mv,
        }),
    }

    print(f"  Equity: ${equity:,.2f}  cash: ${cash:,.2f}")
    print(f"  Positions: {len(pos_rows)}  MV: ${total_mv:,.2f}  ({(total_mv/equity*100 if equity else 0):.1f}%)")
    print(f"  Portfolio β: {portfolio_beta:.2f}  VaR95-1d: ${total_var_95:,.2f}")
    print(f"  Largest: {largest_pct:.1f}%  Top3: {top3_pct:.1f}%  Sector max: {sector_max_pct:.1f}%")

    if not args.apply:
        print("\nDry-run. Re-run with --apply.")
        return 0

    sb = sb_client()
    try:
        if pos_rows:
            sb.table("position_risk_snapshot").upsert(pos_rows, on_conflict="sync_key").execute()
            print(f"✓ Wrote {len(pos_rows)} per-position rows")
        sb.table("portfolio_risk_history").upsert([portfolio_row], on_conflict="sync_key").execute()
        print(f"✓ Wrote portfolio snapshot for {today}")
    except Exception as e:
        print(f"✗ Write failed: {type(e).__name__}: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
