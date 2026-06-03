#!/usr/bin/env python3
"""
fetch_20yr_history.py — the ONE API-spending step of the Time Anatomy engine.

Extends the cached daily-bar history back to ~2006 for the calibration universe,
then rebuilds the survival table over the wider window (more regime cycles →
better bear/panic coverage). Designed to run OFF-HOURS (launchd ~2:15am PT, well
before the 6:30am scan) with hard safety rails so it never starves the live scan:

  · QUOTA RESERVE — aborts if today's EODHD quota is already heavily used, and
    stops once it would dip below the reserve (protects the morning scan).
  · QUARTERLY GUARD — skips if the 20-yr table was rebuilt < ~80 days ago.
  · BOUNDED — caps the number of symbols (--max), throttled by the client limiter.
  · One EOD-historical call per symbol (full history in a single response).

Run (manual):  python3 scripts/fetch_20yr_history.py --max 1200
Scheduled:     infra/launchd/com.swingtrade.time-anatomy-recal.plist (self-guards)
"""
from __future__ import annotations
import os, sys, json, glob, time, argparse, subprocess
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
import eodhd_client as eod  # NOT cache-only — this is the deliberate fetch

CACHE = os.path.join(BASE, "cache", "eodhd")
MARKER = os.path.join(BASE, "cache", ".time_anatomy_20yr.json")
TABLE = os.path.join(BASE, "infra", "prototype", "bullveda", "time_anatomy_table.json")
LOG = os.path.join(BASE, "cache", "logs", "time_anatomy_fetch.log")
FROM = "2006-01-01"
QUOTA_RESERVE = 25000   # leave this many calls for the morning scan
RECAL_DAYS = 80         # quarterly-ish


def log(msg):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    line = time.strftime("%Y-%m-%d %H:%M:%S") + "  " + msg
    print(line)
    try:
        open(LOG, "a").write(line + "\n")
    except Exception:
        pass


def quota_remaining():
    try:
        q = eod.eodhd_quota_status() or {}
        for rk in ("remaining", "left"):
            if isinstance(q.get(rk), (int, float)):
                return int(q[rk])
        lim = q.get("limit") or q.get("daily_limit"); used = q.get("used") or q.get("count")
        if isinstance(lim, (int, float)) and isinstance(used, (int, float)):
            return int(lim - used)
    except Exception as e:
        log(f"quota check failed ({e}) — proceeding cautiously")
    return None  # unknown


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=1200, help="cap symbols fetched")
    ap.add_argument("--force", action="store_true", help="ignore the quarterly guard")
    a = ap.parse_args()

    # quarterly guard
    if not a.force and os.path.exists(MARKER):
        try:
            m = json.load(open(MARKER))
            age = (time.time() - m.get("ts", 0)) / 86400
            if age < RECAL_DAYS:
                log(f"SKIP — 20yr table rebuilt {age:.0f}d ago (< {RECAL_DAYS}d). Use --force to override.")
                return
        except Exception:
            pass

    rem0 = quota_remaining()
    if rem0 is not None and rem0 < QUOTA_RESERVE:
        log(f"ABORT — only {rem0} EODHD calls left today (reserve {QUOTA_RESERVE} for the scan). Try tomorrow.")
        return
    log(f"START 20yr fetch · quota remaining≈{rem0} · reserve {QUOTA_RESERVE} · from {FROM}")

    # universe = symbols we already calibrate on (have a cached eod file)
    syms = sorted({os.path.basename(fp).split("_")[1].split(".US")[0]
                   for fp in glob.glob(os.path.join(CACHE, "eod_*.US_*_d.json"))})
    # always include the index anchors
    for s in ("SPY", "QQQ"):
        if s not in syms:
            syms.insert(0, s)
    syms = syms[:a.max]
    log(f"universe: {len(syms)} symbols")

    fetched = 0
    for i, sym in enumerate(syms):
        rem = quota_remaining()
        if rem is not None and rem < QUOTA_RESERVE:
            log(f"STOP at {i}/{len(syms)} — quota reserve hit ({rem} left). Resume tomorrow.")
            break
        try:
            bars = eod.eod(sym, from_date=FROM)   # fetches + caches full history (throttled by client limiter)
            if bars:
                fetched += 1
        except Exception as e:
            log(f"  · {sym} failed: {e}")
        if (i + 1) % 200 == 0:
            log(f"  · {i+1}/{len(syms)} fetched={fetched} quota≈{quota_remaining()}")
        time.sleep(0.05)  # gentle; client also rate-limits

    log(f"fetched {fetched} symbols. Rebuilding survival table over the wider window…")
    r = subprocess.run([sys.executable, os.path.join(BASE, "scripts", "build_time_anatomy.py")],
                       capture_output=True, text=True)
    log((r.stdout or "").strip().splitlines()[-1] if r.stdout else "(build produced no stdout)")
    if r.returncode != 0:
        log("BUILD FAILED:\n" + (r.stderr or "")[-800:])
        return

    # stamp the marker with the new table's date range
    try:
        meta = json.load(open(TABLE)).get("meta", {})
        json.dump({"ts": time.time(), "date_range": meta.get("date_range"),
                   "fetched": fetched, "cells": meta.get("cells")}, open(MARKER, "w"))
    except Exception:
        pass
    log(f"DONE — table date range now {json.load(open(TABLE)).get('meta',{}).get('date_range')}")


if __name__ == "__main__":
    main()
