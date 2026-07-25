#!/usr/bin/env python3
"""gam_target_v2 — Python port of indicators/gam_price_target_v2.pine.

Exact same math as the Pine script (Swing preset defaults) so the ladder can be
A/B'd against /api/trade_engine (Phase 0) and forward-logged (Phase 2).

Sources (weight · behavior):
  swing pivots 1.5 wall · HVN(approx) 2.0 wall · order blocks 1.5 wall ·
  anchored VWAP 1.25 wall · PDH/PWH/PMH 1.0 magnet · rounds 1.0 magnet ·
  measured move 1.0 magnet · fib ext 1.0 magnet
Confluence capped 4.0; wall if wall-weight within tol >= 1.5; reachability
decays past ATR*horizon; T1 may not leapfrog nearest strong wall.
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np
import pandas as pd

# ── Swing-preset defaults (mirror Pine inputs) ──────────────────────────────
ATR_LEN = 14
ATR_STOP_MULT = 1.5
PV_LEN = 10
FIB_LB = 60
CONF_TOL_ATR = 0.5
MIN_CONF = 1.0          # Swing preset
MIN_SCORE = 0.4
HORIZON = 4             # Swing preset
CAP_ATR = 6.0           # Swing preset
MIN_GAP_ATR = 0.5
SPACE_ATR = 0.6
VP_LB = 150
VP_BINS = 24
HVN_MULT = 1.6
OB_IMP_ATR = 0.5
CONF_CAP = 4.0
WALL_WT = 1.5


def _norm(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d.columns = [str(c).lower() for c in d.columns]
    need = {"open", "high", "low", "close", "volume"}
    missing = need - set(d.columns)
    if missing:
        raise ValueError(f"bars missing columns: {missing}")
    d = d.dropna(subset=["open", "high", "low", "close"])
    if not isinstance(d.index, pd.DatetimeIndex):
        for c in ("date", "datetime", "timestamp"):
            if c in d.columns:
                d.index = pd.to_datetime(d[c])
                break
    return d


def _atr_series(d: pd.DataFrame) -> pd.Series:
    pc = d["close"].shift(1)
    tr = pd.concat([
        d["high"] - d["low"],
        (d["high"] - pc).abs(),
        (d["low"] - pc).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / ATR_LEN, adjust=False).mean()  # Wilder RMA


def compute_ladder(df: pd.DataFrame, entry: Optional[float] = None,
                   stop: Optional[float] = None, is_long: bool = True) -> dict:
    """Compute the v2 structural ladder from daily bars (last bar = 'today')."""
    d = _norm(df)
    n = len(d)
    if n < 80:
        return {"error": f"insufficient bars ({n})"}

    h = d["high"].to_numpy(float)
    l = d["low"].to_numpy(float)
    o = d["open"].to_numpy(float)
    c = d["close"].to_numpy(float)
    v = d["volume"].to_numpy(float)
    hlc3 = (h + l + c) / 3.0
    atr_s = _atr_series(d).to_numpy(float)
    atr = float(atr_s[-1])

    px_entry = float(entry) if entry else float(c[-1])
    px_stop = float(stop) if stop else (
        px_entry - ATR_STOP_MULT * atr if is_long else px_entry + ATR_STOP_MULT * atr)
    risk = abs(px_entry - px_stop)

    cand: list[tuple[float, float, bool, str]] = []  # (price, wt, wall, src)

    def add(p, w, wall, src):
        if p is None or not np.isfinite(p):
            return
        if (is_long and p > px_entry) or ((not is_long) and p < px_entry):
            cand.append((float(p), float(w), bool(wall), src))

    # 1) swing pivots (confirmed, last 50) — wall 1.5
    piv_hi, piv_lo = [], []
    for i in range(PV_LEN, n - PV_LEN):
        win_h = h[i - PV_LEN:i + PV_LEN + 1]
        win_l = l[i - PV_LEN:i + PV_LEN + 1]
        if h[i] >= win_h.max() and (win_h == h[i]).sum() == 1:
            piv_hi.append(h[i])
        if l[i] <= win_l.min() and (win_l == l[i]).sum() == 1:
            piv_lo.append(l[i])
    for p in (piv_hi if is_long else piv_lo)[-50:]:
        add(p, 1.5, True, "swing")

    # 2) HVN approx — wall 2.0 (hlc3-binned volume over VP_LB bars)
    lb = min(VP_LB, n)
    vp_hi, vp_lo = h[-lb:].max(), l[-lb:].min()
    if vp_hi > vp_lo:
        bins = np.zeros(VP_BINS)
        bw = (vp_hi - vp_lo) / VP_BINS
        idx = np.clip(((hlc3[-lb:] - vp_lo) / bw).astype(int), 0, VP_BINS - 1)
        for k, vol in zip(idx, v[-lb:]):
            bins[k] += vol
        avg = bins.mean()
        for k in range(VP_BINS):
            if bins[k] > HVN_MULT * avg:
                add(vp_lo + (k + 0.5) * bw, 2.0, True, "hvn")

    # 3) order blocks — wall 1.5 (running state, mitigation on close-through)
    ob_bear: list[float] = []
    ob_bull: list[float] = []
    for i in range(15, n):
        a = atr_s[i]
        lo3 = l[i - 3:i].min()
        hi3 = h[i - 3:i].max()
        if c[i] < lo3 and (o[i] - c[i]) > OB_IMP_ATR * a:
            for j in range(i - 1, max(i - 7, -1), -1):
                if c[j] > o[j]:
                    ob_bear.append(h[j])
                    break
        if c[i] > hi3 and (c[i] - o[i]) > OB_IMP_ATR * a:
            for j in range(i - 1, max(i - 7, -1), -1):
                if c[j] < o[j]:
                    ob_bull.append(l[j])
                    break
        ob_bear = [x for x in ob_bear if c[i] <= x][-20:]
        ob_bull = [x for x in ob_bull if c[i] >= x][-20:]
    for p in (ob_bear if is_long else ob_bull):
        add(p, 1.5, True, "ob")

    # 4) anchored VWAP from 60-bar swing low + swing high — wall 1.25
    lbf = min(FIB_LB, n)
    off_lo = lbf - 1 - int(np.argmin(l[-lbf:]))
    off_hi = lbf - 1 - int(np.argmax(h[-lbf:]))
    for off in (off_lo, off_hi):
        if off > 0:
            vv = v[-(off + 1):]
            pp = hlc3[-(off + 1):]
            if vv.sum() > 0:
                add(float((vv * pp).sum() / vv.sum()), 1.25, True, "avwap")

    # 5) prior-period liquidity — magnet 1.0 (prev day/week/month H or L)
    di = d.index
    try:
        add(h[-2] if is_long else l[-2], 1.0, False, "pdh")
        wk = di.to_period("W")
        prev_w = wk != wk[-1]
        if prev_w.any():
            last_prev_w = wk[prev_w][-1]
            m = wk == last_prev_w
            add(h[m].max() if is_long else l[m].min(), 1.0, False, "pwh")
        mo = di.to_period("M")
        prev_m = mo != mo[-1]
        if prev_m.any():
            last_prev_m = mo[prev_m][-1]
            m2 = mo == last_prev_m
            add(h[m2].max() if is_long else l[m2].min(), 1.0, False, "pmh")
    except Exception:
        pass

    # 6) rounds — magnet 1.0
    e = px_entry
    step = 0.5 if e < 5 else 1.0 if e < 20 else 2.5 if e < 50 else 5.0 if e < 100 \
        else 10.0 if e < 250 else 25.0 if e < 1000 else 50.0
    cap_dist = CAP_ATR * atr
    if is_long:
        rp = math.ceil(e / step) * step
        g = 0
        while rp <= e + cap_dist and g < 80:
            add(rp, 1.0, False, "round")
            rp += step
            g += 1
    else:
        rp = math.floor(e / step) * step
        g = 0
        while rp >= e - cap_dist and g < 80:
            add(rp, 1.0, False, "round")
            rp -= step
            g += 1

    # 7) measured move — magnet 1.0 (20-bar range ending [1])
    rng_h = h[-21:-1].max()
    rng_l = l[-21:-1].min()
    if rng_h > rng_l:
        add(rng_h + (rng_h - rng_l) if is_long else rng_l - (rng_h - rng_l),
            1.0, False, "mm")

    # 8) fib extensions — magnet 1.0 (60-bar leg)
    sw_lo, sw_hi = l[-lbf:].min(), h[-lbf:].max()
    leg = sw_hi - sw_lo
    if leg > 0:
        for r in (1.272, 1.618, 2.0):
            add(sw_lo + leg * r if is_long else sw_hi - leg * r, 1.0, False, "fib")

    if not cand:
        return {"entry": px_entry, "stop": px_stop, "atr": atr,
                "t1": None, "t2": None, "t3": None}

    # ── confluence (capped) + wall + reachability ──
    tol = CONF_TOL_ATR * atr
    budget = atr * HORIZON
    prices = np.array([x[0] for x in cand])
    wts = np.array([x[1] for x in cand])
    walls = np.array([x[2] for x in cand])
    conf = np.zeros(len(cand))
    wallwt = np.zeros(len(cand))
    for i, p in enumerate(prices):
        near = np.abs(prices - p) <= tol
        conf[i] = min(wts[near].sum(), CONF_CAP)
        wallwt[i] = wts[near & walls].sum()
    dist = np.abs(prices - px_entry)
    reach = np.where(dist <= budget, 1.0,
                     np.maximum(0.15, 1.0 - (dist / budget - 1.0) * 0.6))
    score = conf * reach
    is_wall = wallwt >= WALL_WT

    def find_next(from_px):
        best = None
        for i, p in enumerate(prices):
            ok = p > from_px if is_long else p < from_px
            if ok and conf[i] >= MIN_CONF and score[i] >= MIN_SCORE:
                if best is None or (p < prices[best] if is_long else p > prices[best]):
                    best = i
        return best

    min_gap = MIN_GAP_ATR * atr
    space = SPACE_ATR * atr
    base = px_entry + min_gap if is_long else px_entry - min_gap
    i1 = find_next(base)
    f2 = base if i1 is None else (prices[i1] + space if is_long else prices[i1] - space)
    i2 = find_next(f2)
    f3 = f2 if i2 is None else (prices[i2] + space if is_long else prices[i2] - space)
    i3 = find_next(f3)

    # overhead-supply guard
    strong = is_wall & (conf >= 1.5)
    if is_long:
        above = strong & (prices > base)
        near_wall = prices[above].min() if above.any() else None
    else:
        below = strong & (prices < base)
        near_wall = prices[below].max() if below.any() else None

    def pack(i):
        if i is None:
            return None
        p = float(prices[i])
        srcs = sorted({cand[j][3] for j in range(len(cand))
                       if abs(prices[j] - p) <= tol})
        return {"price": round(p, 2), "conf": round(float(conf[i]), 2),
                "wall": bool(is_wall[i]),
                "r": round(abs(p - px_entry) / risk, 2) if risk > 0 else None,
                "sources": srcs}

    t1, t2, t3 = pack(i1), pack(i2), pack(i3)
    if t1 and near_wall is not None:
        if (is_long and t1["price"] > near_wall + 0.05 * atr) or \
           ((not is_long) and t1["price"] < near_wall - 0.05 * atr):
            j = int(np.argmin(np.abs(prices - near_wall)))
            t1 = pack(j)

    return {"entry": round(px_entry, 2), "stop": round(px_stop, 2),
            "atr": round(atr, 2), "risk": round(risk, 2),
            "t1": t1, "t2": t2, "t3": t3, "n_candidates": len(cand)}


if __name__ == "__main__":
    import sys
    sys.path.insert(0, ".")
    import data_fetcher
    tk = sys.argv[1] if len(sys.argv) > 1 else "LQDA"
    bars, tier = data_fetcher.fetch_ohlcv_with_failover(tk, days=400)
    if bars is None:
        print(f"{tk}: no bars")
    else:
        import json
        print(f"{tk} (bars via {tier}):")
        print(json.dumps(compute_ladder(bars), indent=2))
