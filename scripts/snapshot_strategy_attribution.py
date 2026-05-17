#!/usr/bin/env python3
"""
snapshot_strategy_attribution.py — Daily $ PnL split by sleeve.

Reads closed_trades (live) + picks_history.json (backtest) and computes
per-sleeve daily attribution. Writes one row per (date × sleeve) to
strategy_pnl_attribution.

Usage: python3 scripts/snapshot_strategy_attribution.py --apply
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
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

    # Aggregate from picks_history.json (broadest source)
    ph = ROOT / "cache" / "picks_history.json"
    if not ph.exists():
        print("No picks_history"); return 1
    j = json.loads(ph.read_text())
    # by_day_sleeve[date][sleeve] = {pnl, n, wins, losses, r_multiples}
    buckets: dict = defaultdict(lambda: defaultdict(lambda: {
        "pnl": 0.0, "n": 0, "wins": 0, "losses": 0, "r_sum": 0.0, "r_n": 0,
    }))

    for t in (j.get("trades") or []):
        exit_d = (t.get("exit_date") or t.get("run_date") or "")[:10]
        if not exit_d: continue
        sleeve = t.get("setup_family") or "unknown"
        try:
            pnl = float(t.get("pct_chg") or 0)
        except Exception:
            continue
        b = buckets[exit_d][sleeve]
        b["n"] += 1
        b["pnl"] += pnl
        if pnl > 0:
            b["wins"] += 1
        elif pnl < 0:
            b["losses"] += 1
        # R-multiple if entry/exit/stop present
        try:
            ep, xp, stp = float(t.get("entry_price") or 0), float(t.get("exit_price") or 0), float(t.get("stop") or 0)
            if ep and stp and abs(ep - stp) > 1e-9:
                r = (xp - ep) / (ep - stp)
                b["r_sum"] += r
                b["r_n"] += 1
        except Exception:
            pass

    rows = []
    for d, sleeves in buckets.items():
        for sleeve, b in sleeves.items():
            if b["n"] == 0: continue
            avg_r = (b["r_sum"] / b["r_n"]) if b["r_n"] > 0 else None
            rows.append({
                "attribution_date": d,
                "sleeve": sleeve,
                "n_positions": 0,  # not tracked from this source
                "n_closes": b["n"],
                "realized_pnl": b["pnl"],
                "unrealized_pnl": 0,
                "total_pnl": b["pnl"],
                "win_count": b["wins"],
                "loss_count": b["losses"],
                "avg_r_multiple": avg_r,
                "sync_key": _h("attr", d, sleeve),
                "raw_json": json.dumps({"date": d, "sleeve": sleeve, **b}),
            })

    print(f"Built {len(rows)} (date × sleeve) attribution rows")
    if not args.apply:
        print("Dry-run"); return 0
    if not rows:
        return 0
    sb = sb_client()
    # Dedup within source
    seen = {}
    for r in rows: seen[r["sync_key"]] = r
    rows = list(seen.values())
    ok = fail = 0
    for i in range(0, len(rows), 200):
        batch = rows[i:i+200]
        try:
            sb.table("strategy_pnl_attribution").upsert(batch, on_conflict="attribution_date,sleeve").execute()
            ok += len(batch)
        except Exception as e:
            fail += len(batch)
            print(f"  ! batch {i}: {type(e).__name__}: {str(e)[:200]}")
    print(f"  pushed={ok} failed={fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
