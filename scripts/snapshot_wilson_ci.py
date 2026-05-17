#!/usr/bin/env python3
"""
snapshot_wilson_ci.py — Daily Wilson 95% LB per (setup × regime × score_band × entry_quality).

Reads signal_log + picks_history → groups → computes Wilson interval per cell →
writes to wilson_ci_snapshot.

Critical for audit principle 1 (statistical rigor) and edge-erosion detection.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
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


def _score_band(s):
    if s is None: return "unknown"
    try: s = float(s)
    except: return "unknown"
    if s >= 90: return "90-100"
    if s >= 80: return "80-89"
    if s >= 70: return "70-79"
    if s >= 60: return "60-69"
    return "<60"


def _wilson(wins: int, n: int, z: float = 1.96):
    """Wilson confidence interval — returns (lower, upper)."""
    if n == 0:
        return 0.0, 1.0
    p = wins / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / denom
    return max(0.0, centre - margin), min(1.0, centre + margin)


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

    # Aggregate from picks_history.trades (largest sample)
    ph = ROOT / "cache" / "picks_history.json"
    if not ph.exists():
        print("No picks_history"); return 1
    j = json.loads(ph.read_text())

    # cells[(setup_family, regime, score_band, entry_quality)] = [wins, n, r_sum, pf_pos, pf_neg]
    cells: dict = defaultdict(lambda: {"wins": 0, "n": 0, "r_sum": 0.0, "r_n": 0,
                                        "gross_wins": 0.0, "gross_losses": 0.0})
    for t in (j.get("trades") or []):
        sf = t.get("setup_family") or "unknown"
        reg = t.get("regime") or t.get("regime4") or "all"
        sb_band = _score_band(t.get("score"))
        eq = t.get("entry_quality") or "unknown"
        win = 1 if (t.get("win") in (1, True, "true")) else 0
        pct = float(t.get("pct_chg") or 0)
        key = (sf, reg, sb_band, eq)
        c = cells[key]
        c["n"] += 1
        c["wins"] += win
        if pct > 0: c["gross_wins"] += pct
        elif pct < 0: c["gross_losses"] += abs(pct)
        try:
            ep, xp, stp = float(t.get("entry_price") or 0), float(t.get("exit_price") or 0), float(t.get("stop") or 0)
            if ep and stp and abs(ep - stp) > 1e-9:
                c["r_sum"] += (xp - ep) / (ep - stp)
                c["r_n"] += 1
        except Exception:
            pass

    today = date.today().isoformat()
    rows = []
    for (sf, reg, sb_band, eq), c in cells.items():
        if c["n"] == 0: continue
        wr = c["wins"] / c["n"]
        lb, ub = _wilson(c["wins"], c["n"])
        pf = (c["gross_wins"] / c["gross_losses"]) if c["gross_losses"] > 0 else None
        avg_r = (c["r_sum"] / c["r_n"]) if c["r_n"] > 0 else None
        rows.append({
            "snapshot_date": today,
            "setup_family": sf,
            "regime": reg,
            "score_band": sb_band,
            "entry_quality": eq,
            "n_trades": c["n"],
            "n_wins": c["wins"],
            "wr": wr,
            "wilson_lb_95": lb,
            "wilson_ub_95": ub,
            "profit_factor": pf,
            "avg_r_multiple": avg_r,
            "sharpe": None,
            "sync_key": _h("wci", today, sf, reg, sb_band, eq),
            "raw_json": json.dumps({**c, "wr": wr, "lb": lb, "ub": ub}),
        })

    print(f"Computed {len(rows)} (setup × regime × band × entry) cells for {today}")
    if not args.apply:
        print("Dry-run"); return 0
    sb = sb_client()
    seen = {}
    for r in rows: seen[r["sync_key"]] = r
    rows = list(seen.values())
    ok = fail = 0
    for i in range(0, len(rows), 200):
        batch = rows[i:i+200]
        try:
            sb.table("wilson_ci_snapshot").upsert(batch, on_conflict="snapshot_date,setup_family,regime,score_band,entry_quality").execute()
            ok += len(batch)
        except Exception as e:
            fail += len(batch)
            print(f"  ! batch {i}: {type(e).__name__}: {str(e)[:200]}")
    print(f"  pushed={ok} failed={fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
