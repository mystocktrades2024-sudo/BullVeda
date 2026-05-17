#!/usr/bin/env python3
"""
backfill_scan_cluster.py — Populate Supabase runs / picks / trades from
cache/picks_history.json (the canonical scan-history file).

Idempotent — uses sync_key for dedup. Safe to re-run.

Usage:
    python3 scripts/backfill_scan_cluster.py             # dry-run
    python3 scripts/backfill_scan_cluster.py --apply     # actually write
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache"
BATCH = 200


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    _load_dotenv()
    os.environ["SUPABASE_MODE"] = "1"
    sys.path.insert(0, str(ROOT))
    from supabase_client import sb_client, healthcheck

    print("=" * 70)
    print(f"Backfill scan cluster  ({'APPLY' if args.apply else 'DRY-RUN'})")
    print("=" * 70)

    hc = healthcheck()
    print(f"Supabase healthcheck: ok={hc['ok']} url={hc.get('url')}")
    if not hc["ok"]:
        return 2

    sb = sb_client() if args.apply else None
    src = CACHE / "picks_history.json"
    if not src.exists():
        print(f"ERROR: {src} not found"); return 1
    j = json.loads(src.read_text())

    # === Build runs ===
    runs_payload = []
    for r in j.get("runs", []):
        run_date = r.get("run_date")
        if not run_date:
            continue
        runs_payload.append({
            "run_date": run_date,
            "run_time": run_date + "T00:00:00Z",
            "regime": r.get("regime"),
            "num_picks": r.get("num_picks"),
            "evaluated": 1 if r.get("evaluated") else 0,
            "sync_key": _h("run", run_date),
        })
    print(f"\n→ runs: {len(runs_payload)} entries")

    # === Build trades (use sequential id mapping from run_date) ===
    trades_payload = []
    for t in j.get("trades", []):
        run_date = t.get("run_date")
        ticker = t.get("ticker")
        if not (run_date and ticker):
            continue
        trades_payload.append({
            "run_date": run_date,
            "ticker": ticker,
            "direction": t.get("direction"),
            "entry_price": t.get("entry_price"),
            "exit_price": t.get("exit_price"),
            "pct_chg": t.get("pct_chg"),
            "win": int(t["win"]) if t.get("win") is not None else None,
            "score": t.get("score"),
            "hold_days": t.get("hold_days"),
            "setup_family": t.get("setup_family"),
            "regime": t.get("regime"),
            "regime4": t.get("regime4"),
            "catalyst_tier": t.get("catalyst_tier"),
            "entry_quality": t.get("entry_quality"),
            "entry_subtype": t.get("entry_subtype"),
            "sector": t.get("sector"),
            "industry": t.get("industry"),
            "conviction_tier": t.get("conviction_tier"),
            "entry_date": t.get("entry_date"),
            "exit_date": t.get("exit_date"),
            "sync_key": _h("trade", run_date, ticker, t.get("entry_date"), t.get("entry_price")),
            "raw_json": json.dumps(t),
        })
    print(f"→ trades: {len(trades_payload)} entries")

    # === Build picks (flatten run.picks[] into picks rows) ===
    picks_payload = []
    for r in j.get("runs", []):
        run_date = r.get("run_date")
        if not run_date:
            continue
        for p in (r.get("picks") or []):
            ticker = p.get("ticker")
            if not ticker:
                continue
            picks_payload.append({
                "ticker": ticker,
                "direction": p.get("direction"),
                "verdict": p.get("verdict"),
                "score": p.get("score"),
                "setup_type": p.get("setup_type"),
                "setup_family": p.get("setup_family") or p.get("setup_type"),
                "entry_price": p.get("entry_price"),
                "first_seen_time": run_date + "T00:00:00Z",
                "updated_count": 1,
                "sync_key": _h("pick", run_date, ticker, p.get("entry_price"), p.get("score")),
                "raw_json": json.dumps(p),
            })
    print(f"→ picks: {len(picks_payload)} entries")

    if not args.apply:
        print("\nDry-run only. Re-run with --apply to actually write.")
        return 0

    # Dedup-within-source then push
    def _push(table, rows, key="sync_key"):
        seen = {}
        for r in rows:
            seen[r.get(key)] = r
        rows = list(seen.values())
        n_ok = n_fail = 0
        for i in range(0, len(rows), BATCH):
            batch = rows[i:i+BATCH]
            try:
                sb.table(table).upsert(batch, on_conflict=key).execute()
                n_ok += len(batch)
            except Exception as e:
                n_fail += len(batch)
                print(f"   ! {table} batch {i}: {type(e).__name__}: {str(e)[:200]}")
                break
        return n_ok, n_fail

    t0 = time.time()
    # runs has UNIQUE(run_date) constraint, so upsert on that
    for table, rows, key in [("runs", runs_payload, "run_date"),
                              ("trades", trades_payload, "sync_key"),
                              ("picks", picks_payload, "sync_key")]:
        ok, fail = _push(table, rows, key)
        print(f"  {table:20s} on_conflict={key:12s} pushed={ok:>6,}  failed={fail}")
    print(f"\nElapsed: {time.time()-t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
