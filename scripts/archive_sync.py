#!/usr/bin/env python3
"""Archive sync — keep data/ohlcv/*.parquet covering the SCAN universe so ML Edge
feature extraction reads local Parquet (fast) instead of a live 400d EODHD fetch.

Two phases:
  1. delta_update()  — refresh every existing parquet with the latest bar via ONE
                       bulk_eod call (cheap).
  2. backfill missing — download full history for any scored/held ticker that has
                       no parquet yet (per-ticker; these are the R2000/mid/small
                       names that data_archive.download_universe (SP500+R1000) skips).

Why: 2026-06-05 the archive covered only ~669 of the 1,171 scored tickers, so ML
live-fetched the other ~502 (400d each) and took ~3h. Run nightly so coverage stays
~complete and ML stays fast.
"""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
import data_archive as da  # noqa: E402


def _scan_universe() -> set[str]:
    syms: set[str] = set()
    try:
        b = json.loads((BASE / "cache" / "last_bundle.json").read_text())
        for key in ("all_scored", "buy_candidates", "elite_picks", "watch_list"):
            for r in (b.get(key) or []):
                t = (r.get("ticker") if isinstance(r, dict) else None)
                if t:
                    syms.add(t.upper())
    except Exception as e:
        print(f"[archive-sync] bundle read failed: {e}", file=sys.stderr)
    # held positions (always archive what we hold)
    try:
        ps = json.loads((BASE / "data" / "portfolio_state.json").read_text())
        for p in (ps.get("positions") or []):
            t = (p.get("ticker") or "").upper()
            if t:
                syms.add(t)
    except Exception:
        pass
    return {s for s in syms if 1 <= len(s) <= 8}


def main() -> int:
    print("[archive-sync] phase 1: delta_update (refresh existing, 1 bulk_eod call)…")
    try:
        da.delta_update()
    except Exception as e:
        print(f"[archive-sync] delta_update failed (continuing to backfill): {e}", file=sys.stderr)

    uni = _scan_universe()
    have = {f[:-8] for f in os.listdir(da.OHLCV_DIR) if f.endswith(".parquet")}
    missing = sorted(uni - have)
    print(f"[archive-sync] universe={len(uni)} · archived={len(have)} · missing={len(missing)}")
    if not missing:
        print("[archive-sync] full coverage — nothing to backfill")
        return 0

    ok = fail = 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = {pool.submit(da._download_ticker, t): t for t in missing}
        for i, f in enumerate(as_completed(futs), 1):
            try:
                if f.result():
                    ok += 1
                else:
                    fail += 1
            except Exception:
                fail += 1
            if i % 100 == 0:
                print(f"  backfilled {i}/{len(missing)} …")
    print(f"[archive-sync] backfilled {ok} ok, {fail} failed · coverage now ~{len(have)+ok}/{len(uni)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
