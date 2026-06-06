"""engines/smc.py — Smart Money Concepts detector for the BullVeda SMC lens.

Mechanism (principle 2): institutions can't fill size at one price, so they
engineer liquidity — push price into resting stop clusters (equal highs/lows,
prior day/week extremes), absorb the fills (order block = the last opposite
candle before a displacement that breaks structure), and leave inefficiencies
(fair-value gaps) the market later rebalances. Edge = read the dealing range
(buy discount / sell premium), enter at the unmitigated OB / FVG in line with
the higher-timeframe break of structure, target the opposite untapped liquidity.

EVERYTHING here is computed from real OHLCV bars — no hardcoded levels. Mode-aware
via get_bars: SWING=daily, POSITION=weekly, INVEST=monthly. Returns a structured
payload the lens renders section-by-section; absent data → empty lists, never mock.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Any, Dict, List, Optional, Tuple

from pattern_data import fmt_date, mode_meta, norm_mode

NAME = "smc"
LABEL = "Smart Money Concepts"


# ── swing pivots (fractal) ───────────────────────────────────────────────────
def _pivots(df: pd.DataFrame, k: int = 2) -> Tuple[List[int], List[int]]:
    highs = df["High"].values
    lows = df["Low"].values
    n = len(df)
    ph, pl = [], []
    for i in range(k, n - k):
        wh = highs[i - k:i + k + 1]
        wl = lows[i - k:i + k + 1]
        if highs[i] == wh.max() and (wh == highs[i]).sum() == 1:
            ph.append(i)
        if lows[i] == wl.min() and (wl == lows[i]).sum() == 1:
            pl.append(i)
    return ph, pl


def _atr(df: pd.DataFrame) -> float:
    if "atr" in df.columns:
        v = df["atr"].dropna()
        if len(v):
            return float(v.iloc[-1])
    rng = (df["High"] - df["Low"]).tail(14).mean()
    return float(rng) if rng == rng else 0.0


# ── structure: BoS / CHoCH event log + current bias ──────────────────────────
def _structure(df: pd.DataFrame, ph: List[int], pl: List[int], tf: str) -> Dict[str, Any]:
    piv = sorted(
        [(i, "H", float(df["High"].iloc[i])) for i in ph]
        + [(i, "L", float(df["Low"].iloc[i])) for i in pl]
    )
    closes = df["Close"].values
    idx = df.index
    events: List[Dict[str, Any]] = []
    ref_high = ref_high_i = None
    ref_low = ref_low_i = None
    last_dir = None
    pj = 0
    for i in range(len(df)):
        # absorb any pivots that completed at/before bar i
        while pj < len(piv) and piv[pj][0] <= i:
            _pi, _pt, _pp = piv[pj]
            if _pt == "H":
                ref_high, ref_high_i = _pp, _pi
            else:
                ref_low, ref_low_i = _pp, _pi
            pj += 1
        c = closes[i]
        if ref_high is not None and c > ref_high and i > (ref_high_i or 0):
            d = "up"
            evt = "CHoCH" if last_dir == "down" else "BoS"
            events.append({"i": i, "date": fmt_date(idx[i], tf), "evt": evt, "dir": d,
                           "price": round(ref_high, 2), "tf": tf})
            last_dir = "up"
            ref_high = None  # consumed until a fresh pivot high forms
        elif ref_low is not None and c < ref_low and i > (ref_low_i or 0):
            d = "down"
            evt = "CHoCH" if last_dir == "up" else "BoS"
            events.append({"i": i, "date": fmt_date(idx[i], tf), "evt": evt, "dir": d,
                           "price": round(ref_low, 2), "tf": tf})
            last_dir = "down"
            ref_low = None
    # bias from last two highs + lows
    hs = [float(df["High"].iloc[i]) for i in ph][-2:]
    ls = [float(df["Low"].iloc[i]) for i in pl][-2:]
    bias = "range"
    if len(hs) == 2 and len(ls) == 2:
        if hs[-1] > hs[-2] and ls[-1] > ls[-2]:
            bias = "bull"
        elif hs[-1] < hs[-2] and ls[-1] < ls[-2]:
            bias = "bear"
        elif last_dir == "up":
            bias = "bull"
        elif last_dir == "down":
            bias = "bear"
    elif last_dir:
        bias = "bull" if last_dir == "up" else "bear"
    last_bos = next((e for e in reversed(events) if e["evt"] == "BoS"), None)
    last_choch = next((e for e in reversed(events) if e["evt"] == "CHoCH"), None)
    return {"bias": bias, "events": events[-8:], "last_bos": last_bos, "last_choch": last_choch,
            "last_dir": last_dir}


# ── order blocks: last opposite candle before a structure-breaking displacement ─
def _order_blocks(df: pd.DataFrame, events: List[Dict[str, Any]], atr: float) -> List[Dict[str, Any]]:
    o = df["Open"].values; h = df["High"].values; l = df["Low"].values; c = df["Close"].values
    idx = df.index
    n = len(df)
    obs: List[Dict[str, Any]] = []
    for e in events:
        bi = e["i"]
        if e["dir"] == "up":
            # last down candle before the up-break
            j = bi - 1
            while j > 0 and c[j] >= o[j]:
                j -= 1
            if j <= 0:
                continue
            lo, hi = float(l[j]), float(max(o[j], c[j]))
            typ = "demand"
        else:
            j = bi - 1
            while j > 0 and c[j] <= o[j]:
                j -= 1
            if j <= 0:
                continue
            lo, hi = float(min(o[j], c[j])), float(h[j])
            typ = "supply"
        # mitigation: did price re-enter the zone after formation?
        after_lo = l[j + 1:].min() if j + 1 < n else lo
        after_hi = h[j + 1:].max() if j + 1 < n else hi
        touched = (typ == "demand" and after_lo <= hi) or (typ == "supply" and after_hi >= lo)
        cur = float(c[-1])
        held = touched and ((typ == "demand" and cur > hi) or (typ == "supply" and cur < lo))
        state = "held" if held else ("mitigated" if touched else "fresh")
        obs.append({"lo": round(lo, 2), "hi": round(hi, 2), "type": typ, "state": state,
                    "date": fmt_date(idx[j], ""), "i": j})
    # de-dup overlapping, keep most recent 6
    obs = sorted(obs, key=lambda x: -x["i"])
    out: List[Dict[str, Any]] = []
    for ob in obs:
        if any(abs(ob["lo"] - p["lo"]) < atr * 0.25 and ob["type"] == p["type"] for p in out):
            continue
        out.append(ob)
        if len(out) >= 6:
            break
    return out


# ── fair-value gaps (3-bar imbalance) ────────────────────────────────────────
def _fvgs(df: pd.DataFrame, atr: float) -> List[Dict[str, Any]]:
    h = df["High"].values; l = df["Low"].values; c = df["Close"].values
    idx = df.index
    n = len(df)
    out: List[Dict[str, Any]] = []
    for i in range(2, n):
        # bullish gap: high[i-2] < low[i]
        if h[i - 2] < l[i]:
            lo, hi, typ = float(h[i - 2]), float(l[i]), "bull"
        elif l[i - 2] > h[i]:
            lo, hi, typ = float(h[i]), float(l[i - 2]), "bear"
        else:
            continue
        if (hi - lo) < atr * 0.25:
            continue  # ignore trivial gaps
        # filled if later price traded back through the gap mid
        mid = (lo + hi) / 2
        later = c[i + 1:]
        filled = bool(((later <= mid).any() and typ == "bull") or ((later >= mid).any() and typ == "bear")) if len(later) else False
        out.append({"lo": round(lo, 2), "hi": round(hi, 2), "type": typ,
                    "state": "filled" if filled else "unfilled", "date": fmt_date(idx[i], ""), "i": i})
    out = sorted(out, key=lambda x: -x["i"])
    # prefer unfilled, then recent
    unfilled = [g for g in out if g["state"] == "unfilled"][:5]
    filled = [g for g in out if g["state"] == "filled"][:3]
    return (unfilled + filled)[:6]


# ── liquidity: equal highs/lows + prior extremes, swept vs untapped ──────────
def _liquidity(df: pd.DataFrame, ph: List[int], pl: List[int], atr: float) -> Dict[str, Any]:
    cur = float(df["Close"].iloc[-1])
    tol = max(atr * 0.20, cur * 0.002)

    def _equal(idxs, kind):
        prices = sorted({round(float(df["High"].iloc[i] if kind == "H" else df["Low"].iloc[i]), 2) for i in idxs})
        clusters = []
        for p in prices:
            placed = False
            for cl in clusters:
                if abs(cl["price"] - p) <= tol:
                    cl["price"] = (cl["price"] * cl["n"] + p) / (cl["n"] + 1)
                    cl["n"] += 1
                    placed = True
                    break
            if not placed:
                clusters.append({"price": p, "n": 1})
        return [{"price": round(c["price"], 2), "touches": c["n"]} for c in clusters if c["n"] >= 2]

    eqh = _equal(ph, "H")
    eql = _equal(pl, "L")
    hi_all = float(df["High"].max())
    lo_all = float(df["Low"].max() if False else df["Low"].min())
    buyside, sellside = [], []
    # untapped buyside above current = nearest swing/equal highs above price
    for i in ph[-6:]:
        p = round(float(df["High"].iloc[i]), 2)
        if p > cur:
            buyside.append({"price": p, "state": "untapped"})
    for cl in eqh:
        if cl["price"] > cur:
            buyside.append({"price": cl["price"], "state": "untapped", "equal": cl["touches"]})
    for i in pl[-6:]:
        p = round(float(df["Low"].iloc[i]), 2)
        if p < cur:
            sellside.append({"price": p, "state": "resting"})
    # dedup + sort
    def _dedup(rows, rev):
        seen = []
        for r in sorted(rows, key=lambda x: x["price"], reverse=rev):
            if any(abs(r["price"] - s["price"]) <= tol for s in seen):
                continue
            seen.append(r)
        return seen[:4]
    return {"buyside": _dedup(buyside, False), "sellside": _dedup(sellside, True),
            "equal_highs": eqh[-3:], "equal_lows": eql[-3:]}


# ── premium / discount dealing range + OTE ───────────────────────────────────
def _range(df: pd.DataFrame, ph: List[int], pl: List[int], bias: str) -> Dict[str, Any]:
    # Dealing range = the recent swing structure (last ~6 pivots) — tight enough to
    # be actionable, wide enough to bracket the current leg. Avoids both the single-
    # leg inversion bug and the over-wide 60-bar window. cur clamp only nudges at a
    # genuine new extreme (correctly → 0%/100%).
    cur = float(df["Close"].iloc[-1])
    piv = sorted(ph + pl)[-6:]
    if len(piv) >= 2:
        lo = min(float(df["Low"].iloc[i]) for i in piv)
        hi = max(float(df["High"].iloc[i]) for i in piv)
    else:
        seg = df.tail(20)
        lo, hi = float(seg["Low"].min()), float(seg["High"].max())
    lo = min(lo, cur)
    hi = max(hi, cur)
    eq = (lo + hi) / 2
    span = max(hi - lo, 1e-6)
    pct = max(0.0, min(100.0, (cur - lo) / span * 100))
    zone = "discount" if pct < 45 else ("premium" if pct > 55 else "equilibrium")
    # OTE 0.62–0.79 retrace — bias-aware: discount side for longs, premium side for shorts
    if bias == "bear":
        ote_lo = lo + span * 0.62
        ote_hi = lo + span * 0.79
    else:
        ote_lo = lo + span * 0.21
        ote_hi = lo + span * 0.38
    return {"lo": round(lo, 2), "hi": round(hi, 2), "eq": round(eq, 2), "pct": round(pct, 1),
            "zone": zone, "ote_lo": round(ote_lo, 2), "ote_hi": round(ote_hi, 2),
            "ote_active": ote_lo <= cur <= ote_hi}


# ── HTF reference levels (prior period extremes + monthly 50%) ───────────────
def _htf_levels(df: pd.DataFrame, tf: str) -> List[Dict[str, Any]]:
    cur = float(df["Close"].iloc[-1])
    out: List[Dict[str, Any]] = []

    def _prev(rule, label):
        try:
            r = df.resample(rule).agg({"High": "max", "Low": "min", "Close": "last"}).dropna()
            if len(r) >= 2:
                return float(r["High"].iloc[-2]), float(r["Low"].iloc[-2])
        except Exception:
            pass
        return None, None

    # for daily bars give prior week/month; for weekly give prior month/quarter
    specs = ([("W", "Prior week high", "Prior week low"),
              ("ME", "Prior month high", "Prior month low")]
             if tf == "Daily" else
             [("ME", "Prior month high", "Prior month low"),
              ("QE", "Prior quarter high", "Prior quarter low")])
    for rule, hlab, llab in specs:
        ph_, pl_ = _prev(rule, hlab)
        if ph_ is not None:
            out.append({"label": hlab, "price": round(ph_, 2), "type": "buy-side liq",
                        "state": "swept" if cur > ph_ else "untapped"})
            out.append({"label": llab, "price": round(pl_, 2), "type": "sell-side liq",
                        "state": "swept" if cur < pl_ else "untapped"})
    return out


# ── multi-timeframe bias (primary tf + one higher via resample) ──────────────
def _mtf(df: pd.DataFrame, tf: str) -> List[Dict[str, Any]]:
    def _bias(d):
        if len(d) < 30:
            return "—"
        e20 = d["Close"].ewm(span=20, adjust=False).mean().iloc[-1]
        e50 = d["Close"].ewm(span=50, adjust=False).mean().iloc[-1]
        c = d["Close"].iloc[-1]
        if c > e20 > e50:
            return "BULL"
        if c < e20 < e50:
            return "BEAR"
        return "RANGE"
    rows = [{"tf": tf, "bias": _bias(df), "note": "primary timeframe"}]
    higher = {"Daily": ("W", "Weekly"), "Weekly": ("ME", "Monthly"), "Monthly": ("QE", "Quarterly")}.get(tf)
    if higher:
        try:
            hd = df.resample(higher[0]).agg({"Open": "first", "High": "max", "Low": "min",
                                             "Close": "last", "Volume": "sum"}).dropna()
            rows.append({"tf": higher[1], "bias": _bias(hd), "note": "higher timeframe"})
        except Exception:
            pass
    return rows


# ── per-zone respect hit-rate, replayed over the real bars ───────────────────
def _zone_stats(df: pd.DataFrame) -> Dict[str, Any]:
    o = df["Open"].values; h = df["High"].values; l = df["Low"].values; c = df["Close"].values
    n = len(df)
    dem_t = dem_r = sup_t = sup_r = 0
    for j in range(1, n - 2):
        if c[j] < o[j] and c[j + 1] > h[j]:           # demand OB (down candle → up displacement)
            hi = max(o[j], c[j])
            for k in range(j + 2, n):
                if l[k] <= hi:                          # price re-entered the zone
                    dem_t += 1
                    if any(c[k + x] > hi for x in range(0, min(4, n - k))):
                        dem_r += 1
                    break
        if c[j] > o[j] and c[j + 1] < l[j]:           # supply OB (up candle → down displacement)
            lo = min(o[j], c[j])
            for k in range(j + 2, n):
                if h[k] >= lo:
                    sup_t += 1
                    if any(c[k + x] < lo for x in range(0, min(4, n - k))):
                        sup_r += 1
                    break
    fvg_t = fvg_f = 0
    for i in range(2, n):
        if h[i - 2] < l[i]:
            fvg_t += 1; mid = (h[i - 2] + l[i]) / 2
            if (c[i + 1:] <= mid).any(): fvg_f += 1
        elif l[i - 2] > h[i]:
            fvg_t += 1; mid = (h[i] + l[i - 2]) / 2
            if (c[i + 1:] >= mid).any(): fvg_f += 1
    pct = lambda a, b: round(a / b * 100) if b else None
    return {
        "demand": {"tested": dem_t, "respected": dem_r, "rate": pct(dem_r, dem_t)},
        "supply": {"tested": sup_t, "respected": sup_r, "rate": pct(sup_r, sup_t)},
        "fvg": {"total": fvg_t, "filled": fvg_f, "rate": pct(fvg_f, fvg_t)},
    }


# ── SMT divergence vs a reference (SPY): relative-strength tell ───────────────
def _smt(df: pd.DataFrame, ref_df: Optional[pd.DataFrame], ref_name: str, ticker: str) -> Optional[Dict[str, Any]]:
    if ref_df is None or len(ref_df) < 30:
        return None
    def lh(d):
        ph, pl = _pivots(d, 2)
        return ([float(d["Low"].iloc[i]) for i in pl][-2:], [float(d["High"].iloc[i]) for i in ph][-2:])
    tl, th = lh(df); rl, rh = lh(ref_df)
    if len(tl) == 2 and len(rl) == 2:
        if tl[-1] > tl[-2] and rl[-1] < rl[-2]:
            return {"type": "bullish", "ref": ref_name, "note": f"{ticker} held a higher low while {ref_name} made a lower low — relative strength"}
        if tl[-1] < tl[-2] and rl[-1] > rl[-2]:
            return {"type": "bearish", "ref": ref_name, "note": f"{ticker} made a lower low while {ref_name} held higher — relative weakness"}
    if len(th) == 2 and len(rh) == 2:
        if th[-1] < th[-2] and rh[-1] > rh[-2]:
            return {"type": "bearish", "ref": ref_name, "note": f"{ticker} made a lower high while {ref_name} pushed higher — relative weakness"}
        if th[-1] > th[-2] and rh[-1] < rh[-2]:
            return {"type": "bullish", "ref": ref_name, "note": f"{ticker} pushed a higher high while {ref_name} stalled — relative strength"}
    return {"type": "aligned", "ref": ref_name, "note": f"moving in line with {ref_name} — no divergence"}


# SPDR sector ETF map — SMT vs the stock's OWN sector is sharper than vs SPY
_SECTOR_ETF = {
    "technology": "XLK", "financial": "XLF", "financial services": "XLF",
    "healthcare": "XLV", "health care": "XLV", "energy": "XLE", "industrials": "XLI",
    "basic materials": "XLB", "materials": "XLB", "real estate": "XLRE",
    "utilities": "XLU", "communication services": "XLC", "communication": "XLC",
    "consumer defensive": "XLP", "consumer staples": "XLP",
    "consumer cyclical": "XLY", "consumer discretionary": "XLY",
}
def _sector_etf(ticker: str) -> str:
    try:
        import eodhd_client as _e
        f = _e.fundamentals(ticker) or {}
        sec = ((f.get("General") or {}).get("Sector") or "").lower().strip()
        for k, v in _SECTOR_ETF.items():
            if k in sec:
                return v
    except Exception:
        pass
    return "SPY"


def detect(df: pd.DataFrame, meta: Dict[str, Any], ticker: str) -> Dict[str, Any]:
    tf = meta.get("tf", "Daily")
    if df is None or len(df) < 30:
        return {"ok": False, "message": "insufficient bars for SMC", "bars": 0}
    atr = _atr(df) or (float(df["Close"].iloc[-1]) * 0.02)
    k = {"Daily": 3, "Weekly": 2, "Monthly": 2}.get(tf, 2)   # higher TF = fewer bars → smaller k
    ph, pl = _pivots(df, k)
    struct = _structure(df, ph, pl, tf)
    obs = _order_blocks(df, struct["events"], atr)
    fvgs = _fvgs(df, atr)
    liq = _liquidity(df, ph, pl, atr)
    rng = _range(df, ph, pl, struct["bias"])
    htf = _htf_levels(df, tf)
    mtf = _mtf(df, tf)
    cur = float(df["Close"].iloc[-1])

    # draw on liquidity: nearest untapped target in the bias direction
    draw = None
    if struct["bias"] == "bull" and liq["buyside"]:
        draw = {"price": min(b["price"] for b in liq["buyside"]), "side": "buy-side"}
    elif struct["bias"] == "bear" and liq["sellside"]:
        draw = {"price": max(s["price"] for s in liq["sellside"]), "side": "sell-side"}

    # composite SMC score (0-100): bias conviction + discount/premium alignment +
    # unmitigated OB present + structure freshness. Transparent, bar-derived.
    score = 50
    if struct["bias"] == "bull":
        score += 12
        if rng["zone"] == "discount":
            score += 14
        elif rng["zone"] == "premium":
            score -= 8
    elif struct["bias"] == "bear":
        score += 8
        if rng["zone"] == "premium":
            score += 10
    if any(o["state"] in ("fresh", "held") for o in obs):
        score += 8
    if struct["last_bos"]:
        score += 6
    if draw:
        score += 4
    score = int(max(1, min(99, score)))

    bos = struct["last_bos"]
    choch = struct["last_choch"]
    headline = "BULL BoS" if (struct["bias"] == "bull" and bos and bos["dir"] == "up") else \
               "BEAR BoS" if (struct["bias"] == "bear" and bos and bos["dir"] == "down") else \
               ("CHoCH " + (struct["last_dir"] or "").upper() if choch else struct["bias"].upper())

    spark = [round(float(x), 2) for x in df["Close"].tail(48).tolist()]

    zone_stats = _zone_stats(df)
    smt = None
    etf = _sector_etf(ticker)
    if (ticker or "").upper() == etf:
        etf = "SPY"
    if (ticker or "").upper() != etf:
        try:
            from pattern_data import get_bars as _gb
            ref_df, _t, _m = _gb(etf, meta.get("mode", "SWING"))
            smt = _smt(df, ref_df, etf, ticker)
        except Exception:
            smt = None

    return {
        "ok": True,
        "zone_stats": zone_stats,
        "smt": smt,
        "bars": int(len(df)),
        "cur_close": round(cur, 2),
        "spark": spark,
        "atr": round(atr, 2),
        "bias": struct["bias"],
        "headline": headline,
        "smc_score": score,
        "structure": {"last_bos": bos, "last_choch": choch, "events": struct["events"]},
        "order_blocks": obs,
        "fvgs": fvgs,
        "liquidity": liq,
        "range": rng,
        "htf_levels": htf,
        "mtf": mtf,
        "draw_on_liquidity": draw,
        "tf": tf,
    }
