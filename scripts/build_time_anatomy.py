#!/usr/bin/env python3
"""
build_time_anatomy.py — Time Anatomy Engine calibration (Kairos whitepaper Phase 4.1-4.2).

Builds the regime-conditioned survival table OFFLINE from ALREADY-CACHED daily bars.
ZERO new API calls: reads cache/eodhd/eod_*.US_*.json directly (EODHD_CACHE_ONLY=1 as a
belt-and-suspenders guard). Never fetches. Safe to run any time — does not touch the
live EODHD quota.

Mechanism (faithful to the whitepaper, simplified cell index for a robust v1):
  For each (symbol, entry-day) at point-in-time, and for a grid of target ATR-distances D,
  scan forward up to HORIZON sessions and record the first session where:
      high >= entry + D*ATR   (target reached)   OR
      low  <= entry - STOP_ATR*ATR (stop hit)    OR
      neither within horizon   (censored / still-open)
  Net of a modeled cost haircut. Group observations by the conditioning cell
      [V1 regime, V2 vol-state, V3 rs-band, V4 quality-band, V5 dist-bucket]
  and build empirical competing-risk survival curves S_reach(t), S_stop(t).
  T1 and T2 at runtime are the SAME process queried at their two ATR-distance buckets.

Output: cache/time_anatomy_table.json  (ships with the app; loaded by the Time lens).
        Small: ~ (4*4*5*3*4)=960 cells x ~30 session points + collapse fallbacks.

Run:  python3 scripts/build_time_anatomy.py            (full)
      python3 scripts/build_time_anatomy.py --max 800  (cap symbols, faster)
"""
from __future__ import annotations
import os, sys, json, glob, math, time, argparse
os.environ["EODHD_CACHE_ONLY"] = "1"  # guard: never hit the network from this script
import numpy as np

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(BASE, "cache", "eodhd")
# write into the served BullVeda dir so the Time lens can sync-load it at /v2/bullveda/
OUT = os.path.join(BASE, "infra", "prototype", "bullveda", "time_anatomy_table.json")

HORIZON = 63          # max sessions tracked (covers swing 21 + position 63)
STOP_ATR = 1.25       # stop distance in ATR (config stop_atr_mult)
DIST_GRID = [1.5, 3.5, 7.5, 12.0]   # representative target ATR-distances → V5 buckets
DIST_BUCKET = ["<2", "2-5", "5-10", ">10"]
N_MIN = 40            # minimum analogues for a confident cell (whitepaper §4.3)
HALFLIFE_D = 756      # recency weighting half-life (~3y), §4.4
COST_FRAC = 0.0015    # modeled round-trip cost haircut on the target (净 §5.3, simplified)
MIN_BARS = 320        # require this many bars to include a symbol


def latest_file_per_symbol():
    """Pick, per symbol, the cached eod_*.US_*_d.json file with the widest range."""
    best = {}
    for fp in glob.glob(os.path.join(CACHE, "eod_*.US_*_d.json")):
        name = os.path.basename(fp)
        try:
            sym = name.split("_")[1].split(".US")[0]
        except Exception:
            continue
        sz = os.path.getsize(fp)
        if sym not in best or sz > best[sym][1]:
            best[sym] = (fp, sz)
    return {s: v[0] for s, v in best.items()}


def load_bars(fp):
    try:
        d = json.load(open(fp))
    except Exception:
        return None
    if not isinstance(d, list) or len(d) < MIN_BARS:
        return None
    d = sorted(d, key=lambda r: r.get("date", ""))
    o = np.array([r.get("open") or r.get("close") or np.nan for r in d], float)
    h = np.array([r.get("high") or np.nan for r in d], float)
    l = np.array([r.get("low") or np.nan for r in d], float)
    c = np.array([r.get("close") or np.nan for r in d], float)
    v = np.array([r.get("volume") or 0 for r in d], float)
    dates = [r.get("date", "") for r in d]
    if np.isnan(c).any():
        return None
    return dates, o, h, l, c, v


def atr14(h, l, c):
    pc = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    atr = np.full_like(tr, np.nan)
    if len(tr) >= 14:
        atr[13] = tr[:14].mean()
        for i in range(14, len(tr)):
            atr[i] = (atr[i - 1] * 13 + tr[i]) / 14
    return atr


def ema(x, n):
    a = 2 / (n + 1)
    out = np.full_like(x, np.nan)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out


def build():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=0, help="cap number of symbols (0=all)")
    args = ap.parse_args()

    files = latest_file_per_symbol()
    print(f"[time-anatomy] cached symbols available: {len(files)}")

    # ── market regime series from SPY + QQQ (cached) ──
    spy = load_bars(files.get("SPY", ""))
    qqq = load_bars(files.get("QQQ", ""))
    if not spy:
        print("[time-anatomy] FATAL: no cached SPY bars; cannot compute regime."); sys.exit(1)
    sdates, _, _, _, sc, _ = spy
    s_ema50, s_ema200 = ema(sc, 50), ema(sc, 200)
    # realized 20d vol (annualized) for panic detection
    sret = np.concatenate([[0.0], np.diff(np.log(sc))])
    rv20 = np.array([sret[max(0, i - 19):i + 1].std() * math.sqrt(252) for i in range(len(sret))])
    rv_med = np.nanmedian(rv20[200:]) if len(rv20) > 200 else np.nanmedian(rv20)
    regime_by_date = {}
    for i, dt in enumerate(sdates):
        if i < 200:
            regime_by_date[dt] = "risk_on_choppy"; continue
        above50, above200 = sc[i] > s_ema50[i], sc[i] > s_ema200[i]
        hot = rv20[i] > rv_med * 1.6
        if hot and sc[i] < s_ema50[i]:
            r = "panic"
        elif sc[i] < s_ema50[i]:
            r = "risk_off_trending"
        elif above50 and above200 and rv20[i] < rv_med * 1.05:
            r = "risk_on_trending"
        else:
            r = "risk_on_choppy"
        regime_by_date[dt] = r
    # SPY close-by-date for relative strength
    spy_close = {dt: sc[i] for i, dt in enumerate(sdates)}

    REG = ["risk_on_trending", "risk_on_choppy", "risk_off_trending", "panic"]
    VOL = ["compressed", "normal", "expanding", "spike"]
    RSB = ["strong_out", "mild_out", "neutral", "mild_in", "strong_in"]
    QB = ["standard", "high", "elite"]

    def vol_bucket(rvol):
        return "compressed" if rvol < 0.7 else "normal" if rvol <= 1.1 else "expanding" if rvol <= 1.5 else "spike"

    def rs_bucket(rs):  # rs = 63d return minus SPY 63d return, in pct points
        return "strong_in" if rs > 8 else "mild_in" if rs > 2 else "neutral" if rs > -2 else "mild_out" if rs > -8 else "strong_out"

    def qual_bucket(score):
        return "elite" if score >= 80 else "high" if score >= 65 else "standard"

    # cells[(reg,vol,rsb,qb,dist)] = {"reach":[counts per session], "stop":[...], "n":int, "wsum":float, "recent":int}
    cells = {}
    nowts = None  # recency anchor = latest date overall

    syms = [s for s in files if s not in ("SPY", "QQQ")]
    syms.sort()
    if args.max:
        syms = syms[:args.max]
    t0 = time.time()
    done = 0; obs = 0
    for sym in syms:
        b = load_bars(files[sym])
        if not b:
            continue
        dates, o, h, l, c, vv = b
        n = len(c)
        atr = atr14(h, l, c)
        avgv = np.array([vv[max(0, i - 19):i + 1].mean() for i in range(n)])
        e8, e21, e50a = ema(c, 8), ema(c, 21), ema(c, 50)
        hi20 = np.array([h[max(0, i - 19):i + 1].max() for i in range(n)])  # 20d high
        # iterate entry days with enough history + forward room
        for i in range(63, n - 5):  # need 63 back for RS, allow censored near the end
            A = atr[i]
            if not (A > 0) or c[i] <= 0:
                continue
            dt = dates[i]
            reg = regime_by_date.get(dt)
            if reg is None:
                continue
            rvol = (vv[i] / avgv[i]) if avgv[i] > 0 else 1.0
            # 63d relative strength vs SPY
            sp_then = spy_close.get(dates[i - 63]); sp_now = spy_close.get(dt)
            if sp_then and sp_now and c[i - 63] > 0:
                rs = (c[i] / c[i - 63] - 1) * 100 - (sp_now / sp_then - 1) * 100
            else:
                rs = 0.0
            # proxy composite quality: trend + momentum + RS (0-100)
            trend = 1 if c[i] > e50a[i] else 0
            mom = (c[i] / c[i - 20] - 1) * 100 if i >= 20 and c[i - 20] > 0 else 0
            score = 50 + trend * 12 + max(-15, min(18, mom * 0.8)) + max(-10, min(12, rs * 0.4))
            vb, rb, qb = vol_bucket(rvol), rs_bucket(rs), qual_bucket(score)
            # setup family from price action (V4 dimension): each family resolves on its own clock
            stacked = e8[i] > e21[i] and e21[i] > e50a[i]
            at_high = hi20[i] > 0 and c[i] >= 0.985 * hi20[i]
            near_e21 = e21[i] > 0 and 0.97 * e21[i] <= c[i] <= 1.03 * e21[i]
            fam = "breakout" if at_high else "pullback" if (stacked and near_e21) else "trend" if (stacked and c[i] > e21[i]) else "other"
            entry = c[i]
            stop_px = entry - STOP_ATR * A
            fwd_h = h[i + 1:i + 1 + HORIZON]
            fwd_l = l[i + 1:i + 1 + HORIZON]
            # stop session (first low <= stop)
            stop_hits = np.where(fwd_l <= stop_px)[0]
            stop_s = int(stop_hits[0]) + 1 if len(stop_hits) else None
            # recency weight
            try:
                age_d = (np.datetime64(dates[-1]) - np.datetime64(dt)).astype(int)
            except Exception:
                age_d = 0
            w = 0.5 ** (max(0, age_d) / HALFLIFE_D)
            recent = 1 if age_d <= 756 else 0
            for di, D in enumerate(DIST_GRID):
                tgt = entry + D * A * (1 + COST_FRAC)  # net-of-cost target
                tgt_hits = np.where(fwd_h >= tgt)[0]
                tgt_s = int(tgt_hits[0]) + 1 if len(tgt_hits) else None
                key = (reg, vb, rb, fam, qb, DIST_BUCKET[di])
                cell = cells.get(key)
                if cell is None:
                    cell = {"reach": [0.0] * (HORIZON + 1), "stop": [0.0] * (HORIZON + 1),
                            "n": 0, "wsum": 0.0, "recent": 0}
                    cells[key] = cell
                cell["n"] += 1; cell["wsum"] += w; cell["recent"] += recent
                obs += 1
                # competing risk: whichever comes first
                if tgt_s is not None and (stop_s is None or tgt_s <= stop_s):
                    cell["reach"][tgt_s] += w
                elif stop_s is not None:
                    cell["stop"][stop_s] += w
                # else censored (neither) — contributes to denominator only
        done += 1
        if done % 250 == 0:
            print(f"  · {done}/{len(syms)} symbols · {obs:,} obs · {time.time()-t0:.0f}s")

    print(f"[time-anatomy] populated {len(cells)} cells from {obs:,} observations in {time.time()-t0:.0f}s")

    # ── convert weighted event counts → cumulative competing-risk survival curves ──
    def finalize(cell):
        N = cell["wsum"] or 1.0
        reach_cum, stop_cum = [], []
        rc = sc_ = 0.0
        for t in range(HORIZON + 1):
            rc += cell["reach"][t]; sc_ += cell["stop"][t]
            reach_cum.append(round(rc / N, 4))
            stop_cum.append(round(sc_ / N, 4))
        return {"n": cell["n"], "recent_share": round(cell["recent"] / max(1, cell["n"]), 3),
                "p_reach": reach_cum[-1], "p_stop": stop_cum[-1],
                "S_reach": reach_cum, "S_stop": stop_cum}

    table = {}
    for key, cell in cells.items():
        table["|".join(key)] = finalize(cell)

    meta = {
        "version": 1,
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "horizon": HORIZON, "stop_atr": STOP_ATR, "dist_grid": DIST_GRID, "dist_bucket": DIST_BUCKET,
        "n_min": N_MIN, "halflife_d": HALFLIFE_D, "cost_frac": COST_FRAC,
        "regimes": REG, "vol": VOL, "rs": RSB, "qual": QB,
        "families": ["breakout", "pullback", "trend", "other"],
        "key_order": ["regime", "vol", "rs", "family", "qual", "dist"],
        "symbols": len(syms), "observations": obs, "cells": len(table),
        "date_range": [sdates[0], sdates[-1]],
        "source": "cached EODHD daily bars (zero new API)",
        "note": "v1 calibration on ~3yr cached window; regime diversity limited. "
                "Cells below n_min collapse the least-significant dim at lookup; "
                "deeper collapse lowers confidence. 20-yr rebuild upgrades coverage.",
    }
    json.dump({"meta": meta, "cells": table}, open(OUT, "w"))
    kb = os.path.getsize(OUT) / 1024
    print(f"[time-anatomy] wrote {OUT} ({kb:.0f} KB) · {len(table)} cells")
    # quick coverage report
    confident = sum(1 for v in table.values() if v["n"] >= N_MIN)
    print(f"[time-anatomy] cells with n>=N_MIN({N_MIN}): {confident}/{len(table)} "
          f"({100*confident/max(1,len(table)):.0f}%)")


if __name__ == "__main__":
    build()
