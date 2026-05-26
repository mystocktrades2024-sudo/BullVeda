#!/usr/bin/env python3
"""
One-shot backfill: compute VWAP/AVWAP/fractal levels for every ticker in
infra/prototype/tickers.json and write them in place.

This avoids re-running the full 15-min swing_trade.py scan when all that
changed is the addition of SMC-level computation in lib/smc_levels.py.

Usage:
    python3 scripts/backfill_smc_levels.py
    python3 scripts/backfill_smc_levels.py --dry-run    # print stats, no write
    python3 scripts/backfill_smc_levels.py --file path  # custom tickers.json

Idempotent — re-running is safe (preserves any pre-computed Williams-fractal
values from analysis.py for scored tickers).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime

# Make 'lib' importable when invoked from project root
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PROJECT_ROOT)

from lib.smc_levels import merge_smc_levels_into_ticker  # noqa: E402


DEFAULT_FILE = os.path.join(PROJECT_ROOT, "infra", "prototype", "tickers.json")


def _coverage(data: dict) -> dict:
    n = len(data)
    has_ohlcv = sum(1 for v in data.values()
                    if isinstance(v, dict) and isinstance(v.get("ohlcv"), list) and v.get("ohlcv"))
    has_v20 = sum(1 for v in data.values()
                  if isinstance(v, dict) and (v.get("vwap") or {}).get("vwap_20d") is not None)
    has_avSL = sum(1 for v in data.values()
                   if isinstance(v, dict) and (v.get("vwap") or {}).get("avwap_swing_low") is not None)
    has_avER = sum(1 for v in data.values()
                   if isinstance(v, dict) and (v.get("vwap") or {}).get("avwap_er") is not None)
    has_avFOMC = sum(1 for v in data.values()
                     if isinstance(v, dict) and (v.get("vwap") or {}).get("avwap_fomc") is not None)
    has_band = sum(1 for v in data.values()
                   if isinstance(v, dict) and (v.get("vwap") or {}).get("vwap_band_upper") is not None)
    has_fH = sum(1 for v in data.values()
                 if isinstance(v, dict) and v.get("fractal_high") is not None)
    has_fL = sum(1 for v in data.values()
                 if isinstance(v, dict) and v.get("fractal_low") is not None)
    return {
        "total": n,
        "with_ohlcv": has_ohlcv,
        "vwap_20d": has_v20,
        "avwap_swing_low": has_avSL,
        "avwap_er": has_avER,
        "avwap_fomc": has_avFOMC,
        "vwap_band": has_band,
        "fractal_high": has_fH,
        "fractal_low": has_fL,
    }


def _fmt(stats: dict) -> str:
    n = stats["total"]
    lines = [f"  total tickers:    {n}",
             f"  with ohlcv bars:  {stats['with_ohlcv']}  ({stats['with_ohlcv']/max(n,1)*100:.1f}%)"]
    for k in ("vwap_20d", "avwap_swing_low", "avwap_er", "avwap_fomc",
              "vwap_band", "fractal_high", "fractal_low"):
        v = stats[k]
        lines.append(f"  {k:18s} {v}  ({v/max(n,1)*100:.1f}%)")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=DEFAULT_FILE,
                    help=f"path to tickers.json (default: {DEFAULT_FILE})")
    ap.add_argument("--dry-run", action="store_true",
                    help="compute + print stats, don't write")
    ap.add_argument("--no-backup", action="store_true",
                    help="skip .bak file (default: write tickers.json.bak.<ts>)")
    ap.add_argument("--sample", nargs="*", default=["IONQ", "HST", "WMB", "QCOM", "NVDA", "AAPL"],
                    help="tickers to print before/after for verification")
    args = ap.parse_args()

    if not os.path.isfile(args.file):
        print(f"ERROR: file not found: {args.file}", file=sys.stderr)
        return 1

    print(f"[backfill_smc] reading {args.file} ...")
    with open(args.file) as f:
        data = json.load(f)
    print(f"[backfill_smc] loaded {len(data)} tickers")

    print("\n[backfill_smc] BEFORE coverage:")
    print(_fmt(_coverage(data)))

    print(f"\n[backfill_smc] sample BEFORE (tickers={args.sample}):")
    for t in args.sample:
        e = data.get(t) or {}
        vw = e.get("vwap") or {}
        print(f"  {t}: v20={vw.get('vwap_20d')} avSL={vw.get('avwap_swing_low')} "
              f"avER={vw.get('avwap_er')} avFOMC={vw.get('avwap_fomc')} "
              f"fH={e.get('fractal_high')} fL={e.get('fractal_low')}")

    # ── Compute for every ticker that has ohlcv ──────────────────────
    n_processed = n_skipped = 0
    for ticker, entry in data.items():
        if not isinstance(entry, dict):
            n_skipped += 1
            continue
        ohlcv = entry.get("ohlcv")
        if not isinstance(ohlcv, list) or len(ohlcv) < 5:
            n_skipped += 1
            continue
        try:
            merge_smc_levels_into_ticker(entry)
            n_processed += 1
        except Exception as e:
            print(f"  [warn] {ticker}: {e}", file=sys.stderr)
            n_skipped += 1

    print(f"\n[backfill_smc] processed {n_processed}, skipped {n_skipped}")
    print("\n[backfill_smc] AFTER coverage:")
    print(_fmt(_coverage(data)))

    print(f"\n[backfill_smc] sample AFTER (tickers={args.sample}):")
    for t in args.sample:
        e = data.get(t) or {}
        vw = e.get("vwap") or {}
        print(f"  {t}: v20={vw.get('vwap_20d')} avSL={vw.get('avwap_swing_low')} "
              f"avER={vw.get('avwap_er')} avFOMC={vw.get('avwap_fomc')} "
              f"bandU={vw.get('vwap_band_upper')} bandL={vw.get('vwap_band_lower')} "
              f"fH={e.get('fractal_high')} fL={e.get('fractal_low')}")

    if args.dry_run:
        print("\n[backfill_smc] --dry-run: NOT writing file")
        return 0

    # Backup
    if not args.no_backup:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        bak = f"{args.file}.bak.{ts}"
        shutil.copy2(args.file, bak)
        print(f"\n[backfill_smc] backup -> {bak}")

    # Write
    with open(args.file, "w") as f:
        json.dump(data, f, separators=(",", ":"))
    sz = os.path.getsize(args.file)
    print(f"[backfill_smc] wrote {args.file} ({sz/1024/1024:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
