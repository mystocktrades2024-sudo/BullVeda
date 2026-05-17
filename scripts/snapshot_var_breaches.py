#!/usr/bin/env python3
"""
snapshot_var_breaches.py — Detect when realized portfolio losses exceeded VaR estimates.

Reads portfolio_risk_history.portfolio_var_95_1d and compares against
next-day equity_curve change. Inserts a row whenever a breach occurs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv():
    p = ROOT / ".env"
    if not p.exists(): return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line: continue
        k, v = line.split("=", 1)
        if k.strip() and k.strip() not in os.environ:
            os.environ[k.strip()] = v.strip()


def _h(*parts): return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:32]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    _load_dotenv()
    os.environ["SUPABASE_MODE"] = "1"
    sys.path.insert(0, str(ROOT))
    from supabase_client import sb_client, healthcheck
    if not healthcheck()["ok"]:
        print("Supabase down"); return 2
    sb = sb_client()

    # Pull VaR snapshots + equity_curve
    try:
        var_data = sb.table("portfolio_risk_history").select("snapshot_at,portfolio_var_95_1d").limit(1000).execute().data or []
        equity = sb.table("equity_curve").select("date,equity").order("date").limit(2000).execute().data or []
    except Exception as e:
        print(f"  ! select: {e}"); return 1

    print(f"  VaR snapshots: {len(var_data)} · equity bars: {len(equity)}")
    if len(var_data) < 1 or len(equity) < 2:
        print("(Not enough history yet — re-run after a few days of risk snapshots.)")
        return 0

    # Build date → equity map
    eq_by_date: dict = {}
    for e in equity:
        try:
            eq_by_date[e["date"]] = float(e["equity"])
        except Exception:
            continue

    breaches = []
    for v in var_data:
        snap_iso = v.get("snapshot_at") or ""
        snap_d = snap_iso[:10]
        var_est = v.get("portfolio_var_95_1d")
        if not (snap_d and var_est): continue
        try: var_est = float(var_est)
        except: continue
        # Next-day realized loss
        try:
            d0 = date.fromisoformat(snap_d)
            d1 = (d0 + timedelta(days=1)).isoformat()
        except Exception:
            continue
        e0 = eq_by_date.get(snap_d)
        e1 = eq_by_date.get(d1)
        if not (e0 and e1): continue
        realized_loss = max(0.0, e0 - e1)
        if realized_loss > var_est:
            breaches.append({
                "breached_at": d1 + "T16:00:00Z",
                "scope": "portfolio",
                "var_estimate": var_est,
                "realized_loss": realized_loss,
                "breach_magnitude": realized_loss / var_est if var_est else None,
                "confidence_level": 0.95,
                "sync_key": _h("vb", d1, "port"),
                "raw_json": json.dumps({"d0": snap_d, "d1": d1, "e0": e0, "e1": e1}),
            })

    print(f"  Detected {len(breaches)} breaches")
    if not args.apply: return 0
    if not breaches: return 0
    ok = fail = 0
    for i in range(0, len(breaches), 100):
        b = breaches[i:i+100]
        try:
            sb.table("var_breaches").upsert(b, on_conflict="sync_key").execute()
            ok += len(b)
        except Exception as e:
            fail += len(b); print(f"  ! {e}")
    print(f"  pushed={ok} failed={fail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
