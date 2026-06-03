#!/usr/bin/env python3
"""
validate_time_anatomy.py — walk-forward validation of the survival table (whitepaper §8).

Splits the cached observations by date into TRAIN (build the table) and TEST (held out),
then checks the two acceptance criteria we can measure from price alone:
  1) Calibration — predicted P(reach by session S) vs realized hit-rate on TEST, by
     probability bin, with the mean absolute calibration error and Wilson 95% bands.
  2) Coverage — share of TEST signals that land in a confident (n>=N_MIN) train cell.

ZERO API: reads cached bars only (EODHD_CACHE_ONLY=1). Reuses the build's labeling.

Run: python3 scripts/validate_time_anatomy.py --split 2025-01-01 --max 800 --check-session 21
"""
from __future__ import annotations
import os, json, glob, math, time, argparse
os.environ["EODHD_CACHE_ONLY"] = "1"
import numpy as np

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(BASE, "cache", "eodhd")
HORIZON, STOP_ATR, MIN_BARS = 63, 1.25, 320
DIST_GRID = [1.5, 3.5, 7.5, 12.0]; DIST_BUCKET = ["<2", "2-5", "5-10", ">10"]
N_MIN, COST_FRAC = 40, 0.0015


def files_by_sym():
    best = {}
    for fp in glob.glob(os.path.join(CACHE, "eod_*.US_*_d.json")):
        sym = os.path.basename(fp).split("_")[1].split(".US")[0]; sz = os.path.getsize(fp)
        if sym not in best or sz > best[sym][1]: best[sym] = (fp, sz)
    return {s: v[0] for s, v in best.items()}


def load(fp):
    try: d = json.load(open(fp))
    except Exception: return None
    if not isinstance(d, list) or len(d) < MIN_BARS: return None
    d = sorted(d, key=lambda r: r.get("date", ""))
    c = np.array([r.get("close") or np.nan for r in d], float)
    if np.isnan(c).any(): return None
    return ([r["date"] for r in d], np.array([r.get("high") or np.nan for r in d], float),
            np.array([r.get("low") or np.nan for r in d], float), c,
            np.array([r.get("volume") or 0 for r in d], float))


def atr14(h, l, c):
    pc = np.concatenate([[c[0]], c[:-1]]); tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    a = np.full_like(tr, np.nan); a[13] = tr[:14].mean()
    for i in range(14, len(tr)): a[i] = (a[i - 1] * 13 + tr[i]) / 14
    return a


def wilson(p, n, z=1.96):
    if n == 0: return (0, 1)
    d = 1 + z * z / n; c = p + z * z / (2 * n)
    m = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)
    return (max(0, (c - m) / d), min(1, (c + m) / d))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="2025-01-01"); ap.add_argument("--max", type=int, default=800)
    ap.add_argument("--check-session", type=int, default=21)
    a = ap.parse_args(); S = a.check_session
    files = files_by_sym()
    spy = load(files.get("SPY", ""));
    sd, _, _, sc, _ = spy
    def from_e(x, n):
        a = 2/(n+1); out = np.empty(len(x)); out[0] = x[0]
        for i in range(1, len(x)): out[i] = a*x[i] + (1-a)*out[i-1]
        return out
    e50, e200 = from_e(sc, 50), from_e(sc, 200)
    ret = np.concatenate([[0.0], np.diff(np.log(sc))]); rv = np.array([ret[max(0,i-19):i+1].std()*math.sqrt(252) for i in range(len(ret))])
    rvm = np.nanmedian(rv[200:])
    reg = {}
    for i, dt in enumerate(sd):
        if i < 200: reg[dt] = "risk_on_choppy"; continue
        if rv[i] > rvm*1.6 and sc[i] < e50[i]: reg[dt] = "panic"
        elif sc[i] < e50[i]: reg[dt] = "risk_off_trending"
        elif sc[i] > e50[i] and sc[i] > e200[i] and rv[i] < rvm*1.05: reg[dt] = "risk_on_trending"
        else: reg[dt] = "risk_on_choppy"
    spc = {dt: sc[i] for i, dt in enumerate(sd)}

    vb = lambda r: "compressed" if r<0.7 else "normal" if r<=1.1 else "expanding" if r<=1.5 else "spike"
    rbk = lambda x: "strong_in" if x>8 else "mild_in" if x>2 else "neutral" if x>-2 else "mild_out" if x>-8 else "strong_out"
    qbk = lambda s: "elite" if s>=80 else "high" if s>=65 else "standard"

    syms = [s for s in files if s not in ("SPY","QQQ")]; syms.sort()
    if a.max: syms = syms[:a.max]
    # train cells: key -> [reach_count(by S), n]; test obs: (key, reached_by_S 0/1)
    train = {}; test = []
    t0 = time.time()
    for k_, sym in enumerate(syms):
        b = load(files[sym])
        if not b: continue
        dates, h, l, c, v = b; n = len(c); A = atr14(h, l, c)
        av = np.array([v[max(0,i-19):i+1].mean() for i in range(n)])
        for i in range(63, n-1):
            if not (A[i] > 0): continue
            dt = dates[i]; rg = reg.get(dt)
            if rg is None: continue
            rvol = v[i]/av[i] if av[i] > 0 else 1.0
            sp0, sp1 = spc.get(dates[i-63]), spc.get(dt)
            rs = ((c[i]/c[i-63]-1) - (sp1/sp0-1))*100 if (sp0 and sp1 and c[i-63]>0) else 0.0
            mom = (c[i]/c[i-20]-1)*100 if c[i-20]>0 else 0
            score = 50 + (12 if c[i] > e50[min(i,len(e50)-1)] else 0) + max(-15,min(18,mom*0.8)) + max(-10,min(12,rs*0.4))
            stop_px = c[i] - STOP_ATR*A[i]
            fh, fl = h[i+1:i+1+HORIZON], l[i+1:i+1+HORIZON]
            sh = np.where(fl <= stop_px)[0]; stop_s = int(sh[0])+1 if len(sh) else None
            is_train = dt < a.split
            for di, D in enumerate(DIST_GRID):
                tgt = c[i] + D*A[i]*(1+COST_FRAC); th = np.where(fh >= tgt)[0]; tgt_s = int(th[0])+1 if len(th) else None
                reached = tgt_s is not None and (stop_s is None or tgt_s <= stop_s)
                key = (rg, vb(rvol), rbk(rs), qbk(score), DIST_BUCKET[di])
                if is_train:
                    cell = train.setdefault(key, [0, 0])
                    cell[1] += 1
                    if reached and tgt_s <= S: cell[0] += 1
                else:
                    test.append((key, 1 if (reached and tgt_s <= S) else 0))
        if (k_+1) % 250 == 0: print(f"  · {k_+1}/{len(syms)} · {time.time()-t0:.0f}s")

    # calibration: bin test obs by train-predicted P(reach by S)
    bins = [[] for _ in range(10)]  # decile of predicted prob -> list of actual 0/1
    covered = 0; total = 0
    for key, actual in test:
        total += 1
        cell = train.get(key)
        if not cell or cell[1] < N_MIN:  # collapse: drop qual then rs (match runtime)
            for kk in [key[:3]+("*", key[4]), key[:2]+("*","*",key[4])]:
                agg_n = agg_r = 0
                for tk, tv in train.items():
                    if all(kk[i] == "*" or kk[i] == tk[i] for i in range(5)): agg_n += tv[1]; agg_r += tv[0]
                if agg_n >= N_MIN: cell = [agg_r, agg_n]; break
        if not cell or cell[1] < N_MIN: continue
        covered += 1
        p = cell[0]/cell[1]; bins[min(9, int(p*10))].append(actual)

    print(f"\n=== Walk-forward · split {a.split} · reach-by-S{S} ===")
    print(f"train cells: {len(train)} · test obs: {total:,} · covered (n>=N_MIN after collapse): {covered:,} ({100*covered/max(1,total):.0f}%)")
    print(f"{'pred bin':>10} {'pred':>6} {'realized':>9} {'n':>7}  Wilson95")
    errs = []
    for bi, arr in enumerate(bins):
        if not arr: continue
        pred = (bi+0.5)/10; realized = sum(arr)/len(arr); lo, hi = wilson(realized, len(arr))
        inband = lo <= pred <= hi
        errs.append(abs(pred-realized))
        print(f"  {bi/10:.1f}-{(bi+1)/10:.1f} {pred:6.2f} {realized:9.3f} {len(arr):7,}  [{lo:.2f},{hi:.2f}] {'✓' if inband else '·'}")
    mae = sum(errs)/len(errs) if errs else float('nan')
    print(f"\nmean abs calibration error: {mae:.3f}  ·  coverage: {100*covered/max(1,total):.0f}%  (ship thresholds: MAE small, coverage>=70%)")


if __name__ == "__main__":
    main()
