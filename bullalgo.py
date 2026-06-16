"""bullalgo.py — transparent, ownable reproduction of the LuxAlgo-style
"Confirmation" signal + "Signals & Overlays" multi-timeframe screener.

Why this exists: BullVeda currently pushes to a logged-in LuxAlgo chart (the
`tv` lens) — a black box we don't control. BullAlgo is the in-house, fully
inspectable equivalent: every layer is a standard, auditable indicator, and the
output is BOTH human-readable (verdict strings) AND machine-rankable (0..1
scores) so it can later feed a ranking/Trader lens as features.

Two engines:
  1. confirmation_signals(df) — layered trend-following confirmation signal
     (trend filter → vol-adaptive momentum trigger → strong/normal → exit hint
     + a continuous conf_feature). Non-repainting (uses shift(1) + rolling).
  2. screen_row(ticker, tf, df) — one row of the multi-timeframe screener grid
     (signal / smart-trail / reversal-zone / catcher-tracer-neocloud / trend-
     strength / volatility / squeeze / volume-sentiment / confluence).

bullalgo_state(ticker, mode) ties them to real data via pattern_data.get_bars:
the Confirmation panel runs on the mode's primary timeframe; the screener grid
spans 4H / 1D / 1W / 1M (honest "—" when a timeframe's bars are unavailable).

Display + shadow-feature only — ZERO scoring impact until OOS-validated
(see ENTRY-WATCH-class discipline: composite/momentum reads are anti-predictive
here until proven otherwise).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# ───────────────────────── building blocks ─────────────────────────
def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    pc = c.shift(1)
    tr = pd.concat([(h - l), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(span=n, adjust=False).mean()


def rsi(s: pd.Series, n: int = 14) -> pd.Series:
    d = s.diff()
    g = d.clip(lower=0).ewm(span=n, adjust=False).mean()
    ls = (-d.clip(upper=0)).ewm(span=n, adjust=False).mean()
    rs = g / ls.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def linreg_slope(s: pd.Series, n: int) -> pd.Series:
    x = np.arange(n)
    xm = x.mean()
    den = ((x - xm) ** 2).sum() or 1.0
    return s.rolling(n).apply(lambda y: ((x - xm) * (y - y.mean())).sum() / den, raw=True)


def _f(v, default=0.0):
    """JSON-safe float (NaN/inf → default)."""
    try:
        v = float(v)
        return v if np.isfinite(v) else default
    except (TypeError, ValueError):
        return default


# ───────────────────────── engine 1: confirmation ─────────────────────────
def confirmation_signals(df: pd.DataFrame, *, fast=20, slow=50, trend_len=50,
                         rsi_len=14, rsi_trigger=50.0, atr_len=14,
                         vol_adaptive=True) -> pd.DataFrame:
    out = df.copy()
    out["ema_fast"] = ema(out["close"], fast)
    out["ema_slow"] = ema(out["close"], slow)
    out["slope"] = linreg_slope(out["close"], min(trend_len, max(2, len(out) - 1)))
    out["trend_up"] = (out["ema_fast"] > out["ema_slow"]) & (out["slope"] > 0)
    out["trend_dn"] = (out["ema_fast"] < out["ema_slow"]) & (out["slope"] < 0)

    out["atr"] = atr(out, atr_len)
    out["atr_pct"] = out["atr"] / out["close"]
    if vol_adaptive and len(out) >= 30:
        w = min(100, len(out))
        vol_z = (out["atr_pct"] - out["atr_pct"].rolling(w).mean()) / out["atr_pct"].rolling(w).std()
        out["rsi_thr_long"] = rsi_trigger + (vol_z.clip(-2, 2) * 4).fillna(0)
        out["rsi_thr_short"] = (100 - rsi_trigger) - (vol_z.clip(-2, 2) * 4).fillna(0)
    else:
        out["rsi_thr_long"] = rsi_trigger
        out["rsi_thr_short"] = 100 - rsi_trigger

    out["rsi"] = rsi(out["close"], rsi_len)
    cross_up = (out["rsi"] > out["rsi_thr_long"]) & (out["rsi"].shift(1) <= out["rsi_thr_long"].shift(1))
    cross_dn = (out["rsi"] < out["rsi_thr_short"]) & (out["rsi"].shift(1) >= out["rsi_thr_short"].shift(1))
    long_trig = cross_up & out["trend_up"]
    short_trig = cross_dn & out["trend_dn"]

    aligned_long = out["close"] > out["ema_slow"]
    aligned_short = out["close"] < out["ema_slow"]

    out["signal"] = 0
    out.loc[long_trig, "signal"] = 1
    out.loc[short_trig, "signal"] = -1
    out["strength"] = ""
    out.loc[long_trig & aligned_long, "strength"] = "strong"
    out.loc[long_trig & ~aligned_long, "strength"] = "normal"
    out.loc[short_trig & aligned_short, "strength"] = "strong"
    out.loc[short_trig & ~aligned_short, "strength"] = "normal"

    out["exit_long"] = (out["rsi"] < 50) & (out["rsi"].shift(1) >= 50)
    out["exit_short"] = (out["rsi"] > 50) & (out["rsi"].shift(1) <= 50)

    trend_dir = out["trend_up"].astype(int) - out["trend_dn"].astype(int)
    mom = ((out["rsi"] - 50) / 50).clip(-1, 1)
    out["conf_feature"] = (0.5 + 0.5 * trend_dir * mom).clip(0, 1)
    return out


def _confirmation_latest(df: pd.DataFrame) -> dict:
    """Latest confirmation state + recent fired markers, as a JSON-safe dict."""
    sig = confirmation_signals(df)
    last = sig.iloc[-1]
    s = int(last["signal"])
    label = "Bullish" if s > 0 else "Bearish" if s < 0 else "Neutral"
    if last["trend_up"]:
        trend = "uptrend"
    elif last["trend_dn"]:
        trend = "downtrend"
    else:
        trend = "neutral"
    fired = sig[sig["signal"] != 0].tail(5)
    recent = [{"date": str(i.date()) if hasattr(i, "date") else str(i),
               "signal": int(r["signal"]), "strength": r["strength"],
               "price": _f(r["close"])} for i, r in fired.iterrows()]
    return {
        "signal": s, "signal_label": label, "strength": last["strength"] or "",
        "trend": trend,
        "conf_feature": round(_f(last["conf_feature"], 0.5), 3),
        "rsi": round(_f(last["rsi"], 50), 1),
        "rsi_thr_long": round(_f(last["rsi_thr_long"], 50), 1),
        "rsi_thr_short": round(_f(last["rsi_thr_short"], 50), 1),
        "ema_fast": round(_f(last["ema_fast"]), 2),
        "ema_slow": round(_f(last["ema_slow"]), 2),
        "slope": round(_f(last["slope"]), 4),
        "close": round(_f(last["close"]), 2),
        "exit_long": bool(last["exit_long"]),
        "exit_short": bool(last["exit_short"]),
        "recent": recent,
    }


# ───────────────────────── engine 2: screener columns ─────────────────────────
def _col_signal(df):
    ef, es = ema(df["close"], 20), ema(df["close"], 50)
    slope = linreg_slope(df["close"], min(50, max(2, len(df) - 1)))
    r = rsi(df["close"], 14)
    rv = _f(r.iloc[-1], 50)
    up = (ef.iloc[-1] > es.iloc[-1]) and (slope.iloc[-1] > 0)
    dn = (ef.iloc[-1] < es.iloc[-1]) and (slope.iloc[-1] < 0)
    aligned = df["close"].iloc[-1] > es.iloc[-1]
    score = float(np.clip(0.5 + 0.5 * ((rv - 50) / 50) * (1 if up else -1 if dn else 0), 0, 1))
    if up and aligned and rv > 55: return "Strong Bullish", "strong", score
    if up: return "Bullish", "normal", score
    if dn and not aligned and rv < 45: return "Strong Bearish", "strong", score
    if dn: return "Bearish", "normal", score
    return "Neutral", "", score


def _col_trail(df):
    line = ema(df["close"], 20) - 2 * atr(df, 14)
    bull = df["close"].iloc[-1] > line.iloc[-1]
    return ("Bullish" if bull else "Bearish"), (1.0 if bull else 0.0)


def _col_reversal_zone(df):
    win = df.tail(60)
    hi, lo, c = win["high"].max(), win["low"].min(), df["close"].iloc[-1]
    rng = (hi - lo) if hi > lo else 1
    pos = (c - lo) / rng
    if pos >= 0.66: return "Near resistance", 0.25
    if pos <= 0.34: return "Near support", 0.75
    return "Mid-range", 0.5


def _col_overlay(df, length):
    line = ema(df["close"], length)
    bull = df["close"].iloc[-1] > line.iloc[-1]
    return ("Bullish" if bull else "Bearish"), (1.0 if bull else 0.0)


def _col_trend_strength(df):
    up = df["high"].diff(); dn = -df["low"].diff()
    plus = np.where((up > dn) & (up > 0), up, 0.0)
    minus = np.where((dn > up) & (dn > 0), dn, 0.0)
    a = atr(df, 14)
    pdi = 100 * pd.Series(plus, index=df.index).ewm(span=14, adjust=False).mean() / a
    mdi = 100 * pd.Series(minus, index=df.index).ewm(span=14, adjust=False).mean() / a
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    adx = _f(dx.ewm(span=14, adjust=False).mean().iloc[-1])
    return round(adx, 1), float(np.clip(adx / 100, 0, 1))


def _col_volatility(df):
    ap = (atr(df, 14) / df["close"])
    cur = _f(ap.iloc[-1])
    hist = ap.tail(min(120, len(ap)))
    rank = float((hist < cur).mean()) if len(hist) else 0.5
    if rank > 0.66: return "High", rank
    if rank < 0.34: return "Low", rank
    return "Moderate", rank


def _col_squeeze(df):
    c = df["close"]
    w = min(20, max(2, len(df) - 1))
    bb = 2 * c.rolling(w).std()
    kc = 1.5 * atr(df, w)
    width = (kc - bb).clip(lower=0)
    tail = width.tail(min(120, len(width)))
    pct = _f(tail.rank(pct=True).iloc[-1]) * 100 if len(tail) else 0.0
    return round(pct, 1), float(np.clip(pct / 100, 0, 1))


def _col_volume_sentiment(df):
    clv = ((df["close"] - df["low"]) - (df["high"] - df["close"])) / (df["high"] - df["low"]).replace(0, np.nan)
    flow = (clv * df["volume"]).tail(20).sum()
    base = df["volume"].tail(20).sum()
    pct = _f(flow / base) * 100 if base else 0.0
    return round(pct, 1), float(np.clip(0.5 + pct / 200, 0, 1))


def screen_row(ticker: str, timeframe: str, df: pd.DataFrame) -> dict:
    sig, strength, sig_s = _col_signal(df)
    trail, trail_s = _col_trail(df)
    rz, rz_s = _col_reversal_zone(df)
    catch, catch_s = _col_overlay(df, 20)
    trace, trace_s = _col_overlay(df, 50)
    neo, neo_s = _col_overlay(df, 100)
    ts, ts_s = _col_trend_strength(df)
    vol, vol_s = _col_volatility(df)
    sq, sq_s = _col_squeeze(df)
    vs, vs_s = _col_volume_sentiment(df)
    confluence = float(np.mean([sig_s, trail_s, catch_s, trace_s, neo_s, vs_s]))
    return {
        "ticker": ticker, "timeframe": timeframe, "available": True,
        "signal": sig, "strength": strength, "signal_score": round(sig_s, 3),
        "smart_trail": trail, "reversal_zone": rz,
        "catcher": catch, "tracer": trace, "neo_cloud": neo,
        "trend_strength": ts, "volatility": vol,
        "squeeze": sq, "volume_sentiment": vs,
        "confluence": round(confluence, 3),
    }


# ───────────────────────── engine 3: price action concepts (SMC) ─────────────────────────
def _swings(df: pd.DataFrame, left=5, right=5):
    h, l = df["high"].values, df["low"].values
    n = len(df)
    sh = np.full(n, np.nan); sl = np.full(n, np.nan)
    for i in range(left, n - right):
        wh = h[i - left:i + right + 1]; wl = l[i - left:i + right + 1]
        if h[i] == wh.max() and (wh == h[i]).sum() == 1: sh[i] = h[i]
        if l[i] == wl.min() and (wl == l[i]).sum() == 1: sl[i] = l[i]
    return pd.Series(sh, index=df.index), pd.Series(sl, index=df.index)


def _last_two(series):
    v = series.dropna()
    a = (v.iloc[-1], v.index[-1]) if len(v) else (None, None)
    b = (v.iloc[-2], v.index[-2]) if len(v) > 1 else (None, None)
    return a, b


def _pac_structure(df, sh, sl):
    """Most recent structural event if price just broke a swing (BOS/CHoCH),
    else the STANDING structure (HH·HL / LH·LL / Range) so the column is always
    populated — not just at the instant of a break. Score encodes direction
    (>0.5 bullish-leaning, <0.5 bearish)."""
    close = df["close"].iloc[-1]
    (lh, _), (ph, _) = _last_two(sh)
    (ll, _), (pl, _) = _last_two(sl)
    if None in (lh, ph, ll, pl): return "—", 0.5
    up = lh > ph and ll > pl
    dn = lh < ph and ll < pl
    if close > lh: return ("BOS ↑" if up else "CHoCH ↑"), (0.8 if up else 0.65)
    if close < ll: return ("BOS ↓" if dn else "CHoCH ↓"), (0.2 if dn else 0.35)
    # no fresh break — report the standing structure bias
    if up: return "HH · HL", 0.62
    if dn: return "LH · LL", 0.38
    return "Range", 0.5


def _pac_order_blocks(df, lookback=60):
    recent = df.tail(lookback)
    body_up = recent["close"] > recent["open"]
    fwd = recent["close"].shift(-3) / recent["close"] - 1
    bull_ob = (~body_up) & (fwd > 0.01)
    bear_ob = (body_up) & (fwd < -0.01)
    buy_v = _f(recent.loc[bull_ob, "volume"].sum())
    sell_v = _f(recent.loc[bear_ob, "volume"].sum())
    total = buy_v + sell_v
    last = df["close"].iloc[-1]
    within = False
    if bull_ob.any():
        z = recent.loc[bull_ob].iloc[-1]; within = within or (z["low"] <= last <= z["high"])
    if bear_ob.any():
        z = recent.loc[bear_ob].iloc[-1]; within = within or (z["low"] <= last <= z["high"])
    score = float(np.clip(buy_v / total, 0, 1)) if total else 0.5
    return ("Within" if within else "Outside"), buy_v, sell_v, total, score


def _pac_fvg(df, lookback=40):
    r = df.tail(lookback).reset_index(drop=True)
    last = df["close"].iloc[-1]
    for i in range(len(r) - 1, 1, -1):
        hi2, lo0 = r["high"].iloc[i - 2], r["low"].iloc[i]
        lo2, hi0 = r["low"].iloc[i - 2], r["high"].iloc[i]
        if lo0 > hi2 and hi2 <= last <= lo0: return "Within", 0.65
        if hi0 < lo2 and hi0 <= last <= lo2: return "Within", 0.35
    return "Outside", 0.5


def _pac_premium_discount(df, lookback=60):
    win = df.tail(lookback)
    hi, lo, c = win["high"].max(), win["low"].min(), df["close"].iloc[-1]
    eq = (hi + lo) / 2
    rng = (hi - lo) if hi > lo else 1
    pos = (c - eq) / (rng / 2)
    if c > eq * 1.001: return "Premium", float(np.clip(0.5 - pos / 2, 0, 1))
    if c < eq * 0.999: return "Discount", float(np.clip(0.5 - pos / 2, 0, 1))
    return "Equilibrium", 0.5


def _pac_liquidity_grab(df, sh, sl, lookback=20):
    recent = df.tail(lookback)
    (lh, _), _ = _last_two(sh)
    (ll, _), _ = _last_two(sl)
    hi = recent["high"].max(); lo = recent["low"].min(); last = df["close"].iloc[-1]
    if lh and hi > lh and last < lh: return "Bearish", 0.35
    if ll and lo < ll and last > ll: return "Bullish", 0.65
    return "—", 0.5


def _pac_equal_hl(df, sh, sl, n_recent=4):
    """Equal highs/lows = a liquidity pool: ANY two recent swings at nearly the
    same level (not just the consecutive pair). Tolerance is ATR-relative — 5-bar
    fractal swings can sit 10-20% apart in a trend, so a fixed 0.3% almost never
    matched; equal-highs are non-consecutive swings that retest a level."""
    price = _f(df["close"].iloc[-1])
    av = _f(atr(df, 14).iloc[-1])
    tol = max(0.0025, 0.25 * av / price) if price else 0.003   # ≥0.25%, scaled by vol

    def _has_equal(series):
        vals = series.dropna().tail(n_recent).values
        for i in range(len(vals)):
            for j in range(i + 1, len(vals)):
                base = vals[j] or 1
                if abs(vals[i] - vals[j]) / base <= tol:
                    return True
        return False

    eqh, eql = _has_equal(sh), _has_equal(sl)
    if eqh and eql: return "EQH+EQL", 0.5
    if eqh: return "EQH", 0.4
    if eql: return "EQL", 0.6
    return "—", 0.5


def _fmt_vol(v):
    v = _f(v)
    if v >= 1e9: return f"{v/1e9:.2f}B"
    if v >= 1e6: return f"{v/1e6:.2f}M"
    if v >= 1e3: return f"{v/1e3:.1f}K"
    return f"{v:.0f}"


def pac_row(ticker: str, timeframe: str, df: pd.DataFrame) -> dict:
    sh, sl = _swings(df)
    struct, struct_s = _pac_structure(df, sh, sl)
    ob_place, buy_v, sell_v, ob_total, ob_s = _pac_order_blocks(df)
    fvg_state, fvg_s = _pac_fvg(df)
    pd_zone, pd_s = _pac_premium_discount(df)
    grab, grab_s = _pac_liquidity_grab(df, sh, sl)
    eq, eq_s = _pac_equal_hl(df, sh, sl)
    smc_conf = float(np.mean([struct_s, ob_s, fvg_s, pd_s, grab_s]))
    return {
        "ticker": ticker, "timeframe": timeframe, "available": True,
        "structure": struct, "structure_score": round(struct_s, 3),
        "order_block": ob_place,
        "buy_ob_vol": _fmt_vol(buy_v), "sell_ob_vol": _fmt_vol(sell_v),
        "ob_buy_score": round(ob_s, 3),
        "fvg": fvg_state, "pd_zone": pd_zone,
        "liquidity_grab": grab, "eqhl": eq,
        "smc_confluence": round(smc_conf, 3),
    }


# ───────────────────────── engine 4: chart series (LuxAlgo-style overlays) ─────────────────────────
def _supertrend(df, period=10, mult=3.0):
    """Flipping ATR trailing stop = the 'Smart Trail' step-line. Returns
    (trail Series, dir Series[+1 long / -1 short])."""
    hl2 = (df["high"] + df["low"]) / 2
    a = atr(df, period)
    up = hl2 + mult * a
    lo = hl2 - mult * a
    fu = up.copy().values; fl = lo.copy().values
    c = df["close"].values
    for i in range(1, len(df)):
        fu[i] = up.iloc[i] if (up.iloc[i] < fu[i - 1] or c[i - 1] > fu[i - 1]) else fu[i - 1]
        fl[i] = lo.iloc[i] if (lo.iloc[i] > fl[i - 1] or c[i - 1] < fl[i - 1]) else fl[i - 1]
    trail = np.full(len(df), np.nan); direc = np.ones(len(df), dtype=int)
    d = 1
    for i in range(len(df)):
        if i and c[i] > fu[i - 1]: d = 1
        elif i and c[i] < fl[i - 1]: d = -1
        direc[i] = d
        trail[i] = fl[i] if d == 1 else fu[i]
    return pd.Series(trail, index=df.index), pd.Series(direc, index=df.index)


def chart_series(ticker: str, tf_mode: str, bars_out: int = 180) -> dict:
    """OHLCV + LuxAlgo-style overlay series + signal markers + stats for ONE
    timeframe, shaped for lightweight-charts. All series share UNIX-second time."""
    from pattern_data import get_bars, mode_meta, norm_mode
    nmode = norm_mode(tf_mode)
    df, tier, meta = get_bars(ticker, nmode, enriched=False)
    if df is None or len(df) < 40:
        return {"available": False, "tier": tier, "tf": meta.get("tf")}
    d = _lc(df)
    sig = confirmation_signals(d)
    a = atr(d, 14)
    # Catcher = fast supertrend step-line; Tracer = slower supertrend step-line.
    ct, ctdir = _supertrend(d, period=10, mult=1.5)
    tr, trdir = _supertrend(d, period=20, mult=2.5)

    tail = d.tail(bars_out)
    idx = tail.index

    def _t(ts):
        try: return int(ts.timestamp())
        except Exception: return int(pd.Timestamp(ts).timestamp())

    def _ser(s):  # [{time,value}] dropping NaN
        out = []
        for ix in idx:
            v = s.get(ix)
            if v is not None and np.isfinite(v):
                out.append({"time": _t(ix), "value": round(float(v), 4)})
        return out

    def _split(line, up_bool):
        """Bi-color split: full-length up/dn arrays, WHITESPACE ({time}) where the
        other direction is active so the line actually breaks (lightweight-charts
        connects across plain gaps). Flip boundary point goes in both so segments
        meet — not one continuous color."""
        up, dn, prev = [], [], None
        for ix in idx:
            v = line.get(ix); t = _t(ix)
            if v is None or not np.isfinite(v):
                up.append({"time": t}); dn.append({"time": t}); prev = None; continue
            u = bool(up_bool.get(ix)); pt = {"time": t, "value": round(float(v), 4)}
            if u:
                up.append(pt); dn.append(pt if prev is False else {"time": t})
            else:
                dn.append(pt); up.append(pt if prev is True else {"time": t})
            prev = u
        return up, dn

    def _band(top, bot):
        out = []
        for ix in idx:
            tv, bv = top.get(ix), bot.get(ix)
            if tv is None or bv is None or not (np.isfinite(tv) and np.isfinite(bv)):
                continue
            out.append({"time": _t(ix), "top": round(float(tv), 4), "bot": round(float(bv), 4)})
        return out

    def _dirline(line, up_bool):
        """Single line tagged with per-bar direction → one continuous line that
        changes color at the flip (drawn client-side), not two parallel series."""
        out = []
        for ix in idx:
            v = line.get(ix)
            if v is None or not np.isfinite(v):
                continue
            out.append({"time": _t(ix), "value": round(float(v), 4), "up": bool(up_bool.get(ix))})
        return out

    def _dirband(top, bot, up_bool):
        """Filled band with per-bar direction (for flipping-color ribbons)."""
        out = []
        for ix in idx:
            tv, bv = top.get(ix), bot.get(ix)
            if tv is None or bv is None or not (np.isfinite(tv) and np.isfinite(bv)):
                continue
            out.append({"time": _t(ix), "top": round(float(tv), 4),
                        "bot": round(float(bv), 4), "up": bool(up_bool.get(ix))})
        return out

    bars = [{"time": _t(ix), "open": round(float(r.open), 4), "high": round(float(r.high), 4),
             "low": round(float(r.low), 4), "close": round(float(r.close), 4),
             "value": float(r.get("volume", 0) or 0)}
            for ix, r in tail.iterrows()]

    close_s = d["close"]
    catcher = _dirline(ct, ctdir > 0)        # one line, green↔red on flip
    tracer = _dirline(tr, trdir > 0)         # one line, green↔orange on flip
    # Smart Trail: filled ribbon hugging EMA21, flips blue(bull)/red(bear)
    st_mid = ema(close_s, 21)
    smart_trail = _dirband(st_mid + 0.6 * a, st_mid - 0.6 * a, close_s > st_mid)
    # Neo Cloud: slower/wider filled band around EMA50, teal/maroon
    neo_mid = ema(close_s, 50)
    neo_band = _dirband(neo_mid + 1.1 * a, neo_mid - 1.1 * a, close_s > neo_mid)
    # Reversal Zones: static resistance(red)/support(green) clouds, further out
    rz_mid = ema(close_s, 50)
    rz_res = _band(rz_mid + 3.4 * a, rz_mid + 2.3 * a)
    rz_sup = _band(rz_mid - 2.3 * a, rz_mid - 3.4 * a)

    # Confirmation signal markers.
    markers = []
    fired = sig[sig["signal"] != 0]
    fired = fired[fired.index.isin(idx)]
    for ix, r in fired.iterrows():
        up = r["signal"] > 0
        markers.append({"time": _t(ix), "position": "belowBar" if up else "aboveBar",
                        "color": "#34e3a4" if up else "#ff5d6c",
                        "shape": "arrowUp" if up else "arrowDown",
                        "text": ("▲" if up else "▼") + (" ★" if r["strength"] == "strong" else "")})

    # Stats panel (reuse the screener column computations).
    ts_v, _ = _col_trend_strength(d)
    vol_v, _ = _col_volatility(d)
    sq_v, _ = _col_squeeze(d)
    vs_v, _ = _col_volume_sentiment(d)
    trend_label = "Trending" if ts_v >= 25 else "Ranging"

    return {
        "available": True, "ticker": ticker, "tf": meta.get("tf"), "tier": tier,
        "bars": bars,
        "catcher": catcher, "tracer": tracer,
        "smart_trail": smart_trail, "neo_band": neo_band,
        "rz_res": rz_res, "rz_sup": rz_sup,
        "markers": markers,
        "stats": {"trend_strength": ts_v, "trend_label": trend_label,
                  "volatility": vol_v, "squeeze": sq_v, "volume_sentiment": vs_v},
    }


def pac_chart_series(ticker: str, tf_mode: str, bars_out: int = 180) -> dict:
    """Price Action Concepts chart geometry — candles + order-block boxes +
    HH/HL/LH/LL structure labels + BOS/CHoCH breaks + premium/discount/
    equilibrium zones, shaped for lightweight-charts (boxes via a client box
    primitive). The drawable companion to the PAC screener grid."""
    from pattern_data import get_bars, norm_mode
    nmode = norm_mode(tf_mode)
    df, tier, meta = get_bars(ticker, nmode, enriched=False)
    if df is None or len(df) < 40:
        return {"available": False, "tier": tier, "tf": meta.get("tf")}
    d = _lc(df)
    sh, sl = _swings(d)
    tail = d.tail(bars_out); idx = tail.index
    t0 = idx[0]

    def _t(ts):
        try: return int(ts.timestamp())
        except Exception: return int(pd.Timestamp(ts).timestamp())
    t_right = _t(idx[-1])

    bars = [{"time": _t(ix), "open": round(float(r.open), 4), "high": round(float(r.high), 4),
             "low": round(float(r.low), 4), "close": round(float(r.close), 4)}
            for ix, r in tail.iterrows()]

    # structure labels: HH/LH on swing highs, HL/LL on swing lows (vs prior of same kind)
    markers = []
    prev = None
    for ix, v in sh.dropna().items():
        if ix >= t0:
            lbl = "HH" if (prev is not None and v > prev) else "LH"
            markers.append({"time": _t(ix), "position": "aboveBar", "color": "#8fa3ad",
                            "shape": "circle", "text": lbl})
        prev = v
    prev = None
    for ix, v in sl.dropna().items():
        if ix >= t0:
            lbl = "HL" if (prev is not None and v > prev) else "LL"
            markers.append({"time": _t(ix), "position": "belowBar", "color": "#8fa3ad",
                            "shape": "circle", "text": lbl})
        prev = v

    # BOS / CHoCH break events: close breaks the last swing high/low.
    # BOS = break in trend direction (continuation); CHoCH = break against it.
    last_sh = last_sl = None; trend = 0
    for ix, row in d.iterrows():
        c = float(row["close"])
        if last_sh is not None and c > last_sh:
            lbl = "BOS" if trend >= 0 else "CHoCH"; trend = 1
            if ix >= t0:
                markers.append({"time": _t(ix), "position": "aboveBar",
                                "color": "#34e3a4", "shape": "arrowUp", "text": lbl})
            last_sh = None
        if last_sl is not None and c < last_sl:
            lbl = "BOS" if trend <= 0 else "CHoCH"; trend = -1
            if ix >= t0:
                markers.append({"time": _t(ix), "position": "belowBar",
                                "color": "#ff5d6c", "shape": "arrowDown", "text": lbl})
            last_sl = None
        if not np.isnan(sh.get(ix, np.nan)): last_sh = float(sh[ix])
        if not np.isnan(sl.get(ix, np.nan)): last_sl = float(sl[ix])
    markers.sort(key=lambda m: m["time"])

    # order-block zones: down-candle before >1.5% up (bull) / up-candle before >1.5% down (bear)
    look = d.tail(min(140, len(d)))
    body_up = look["close"] > look["open"]
    fwd = look["close"].shift(-3) / look["close"] - 1
    avg_vol = float(look["volume"].tail(60).mean()) or 1.0
    cands = []
    for i in range(len(look) - 4):
        ix = look.index[i]
        if ix < t0:
            continue
        bull = (not bool(body_up.iloc[i])) and fwd.iloc[i] > 0.015
        bear = bool(body_up.iloc[i]) and fwd.iloc[i] < -0.015
        if not (bull or bear):
            continue
        row = look.iloc[i]
        vol = float(row["volume"])
        cands.append({"time": _t(ix), "time_right": t_right,
                      "top": round(float(row["high"]), 4), "bot": round(float(row["low"]), 4),
                      "kind": "bull" if bull else "bear", "_vol": vol,
                      "vol_label": _fmt_vol(vol) + f" ({vol/avg_vol*100:.0f}%)"})
    # Dedupe by price overlap — keep the highest-volume block per price cluster so
    # boxes sit at DISTINCT levels instead of stacking on the right. Cap to 4.
    cands.sort(key=lambda o: -o["_vol"])
    obs = []
    for c in cands:
        if any(not (c["top"] < k["bot"] or c["bot"] > k["top"]) for k in obs):
            continue   # price range intersects an already-kept (stronger) block
        obs.append(c)
        if len(obs) >= 4:
            break
    obs.sort(key=lambda o: o["time"])
    for o in obs:
        o.pop("_vol", None)

    # premium / discount / equilibrium over the visible dealing range
    hi = float(tail["high"].max()); lo = float(tail["low"].min()); eq = (hi + lo) / 2
    zones = {"high": round(hi, 4), "low": round(lo, 4), "eq": round(eq, 4),
             "t_left": _t(idx[0]), "t_right": t_right}

    return {"available": True, "ticker": ticker, "tf": meta.get("tf"), "tier": tier,
            "bars": bars, "markers": markers, "order_blocks": obs, "zones": zones}


def mcdx_series(ticker: str, tf_mode: str, bars_out: int = 180, n: int = 34) -> dict:
    """Transparent MCDX reproduction — 'Banker / Hot Money / Retail' bands.

    HONEST NOTE: MCDX's 'smart money / banker' labels are MARKETING on standard
    momentum math — there is NO real order-flow feed behind it. This computes the
    stochastic RSV = (close - LLV) / (HHV - LLV) and smooths it at three speeds:
      Banker  = slow EMA (persistent)   Hot Money = medium EMA   Retail = fast EMA.
    Interpretive, not institutional flow. Returned 0..100; banker as columns."""
    from pattern_data import get_bars, norm_mode
    nmode = norm_mode(tf_mode)
    df, tier, meta = get_bars(ticker, nmode, enriched=False)
    if df is None or len(df) < n + 10:
        return {"available": False, "tier": tier, "tf": meta.get("tf")}
    d = _lc(df)
    low_n = d["low"].rolling(n).min()
    high_n = d["high"].rolling(n).max()
    rng = (high_n - low_n).replace(0, np.nan)
    rsv = ((d["close"] - low_n) / rng * 100).clip(0, 100)
    hot = rsv.ewm(span=5, adjust=False).mean()       # histogram height (money-flow magnitude)
    banker = rsv.ewm(span=13, adjust=False).mean()    # slow "banker" line (blue)

    tail = d.tail(bars_out); idx = tail.index

    def _t(ts):
        try: return int(ts.timestamp())
        except Exception: return int(pd.Timestamp(ts).timestamp())

    # histogram bars colored by money-flow state: green accumulation / red distribution / yellow neutral
    #
    # ALIGNMENT (2026-06-15): emit ONE point per tail bar — including the rolling
    # warm-up bars where hot/banker are still NaN — as lightweight-charts
    # "whitespace" points ({time} only, no value). Previously these warm-up bars
    # were `continue`-skipped, so the histogram had FEWER points (e.g. 173) than
    # the price chart (180); the two charts sync by LOGICAL range (bar index), so
    # 0..180 mapped onto a 173-bar series left the MCDX bars compressed/left-
    # shifted (badly so on weekly/monthly where the 34-bar warm-up eats a large
    # fraction). Whitespace keeps the time axis identical → exact alignment.
    GREEN, YELLOW, RED = "#16c784", "#e8c170", "#ff5d6c"
    hist, bline = [], []
    for ix in idx:
        t = _t(ix)
        v = hot.get(ix)
        if v is None or not np.isfinite(v):
            hist.append({"time": t})  # whitespace — preserves time-axis alignment
        else:
            col = GREEN if v >= 55 else RED if v <= 45 else YELLOW
            hist.append({"time": t, "value": round(float(v), 2), "color": col})
        b = banker.get(ix)
        if b is None or not np.isfinite(b):
            bline.append({"time": t})  # whitespace
        else:
            bline.append({"time": t, "value": round(float(b), 2)})

    bv = round(_f(banker.iloc[-1]), 1); hv = round(_f(hot.iloc[-1]), 1)
    state = "Accumulation" if hv >= 55 else "Distribution" if hv <= 45 else "Neutral"
    return {"available": True, "ticker": ticker, "tf": meta.get("tf"), "tier": tier,
            "hist": hist, "banker_line": bline,
            "current": {"banker": bv, "hot": hv, "state": state}}


# ─────────────────────── REAL institutional footprint ───────────────────────
# Honest counterweight to the MCDX panel: MCDX is momentum math wearing a
# "banker/smart money" costume (no order-flow input exists for ANY retail feed).
# This strip surfaces the institutional footprints that are GENUINELY observable
# from the existing stack (EODHD + SEC) — no new data license:
#   1. Accumulation (OBV + A/D line)  — the LEGITIMATE volume-accumulation signal
#      MCDX only pretends to be. Computed live from bars. Real, same-day.
#   2. Insider Form 4 (SEC)           — named insiders, real $ buy/sell, ~2d lag.
#   3. Institutional 13F (EODHD)      — real named holders + QoQ share change,
#      45-day lag (the structural latency of 13F — disclosed, not hidden).
# Every block degrades to {"available": False} honestly when its feed is absent.
def _obv_ad_accumulation(df: pd.DataFrame, lookback: int = 40) -> dict:
    """OBV + Accumulation/Distribution line trend over the last `lookback` bars.
    Returns slope-based state — the real volume-accumulation read (vs MCDX's fake)."""
    d = _lc(df)
    c, h, l, v = d["close"], d["high"], d["low"], d["volume"]
    obv = (np.sign(c.diff().fillna(0.0)) * v).cumsum()
    rng = (h - l).replace(0, np.nan)
    mfm = (((c - l) - (h - c)) / rng).fillna(0.0)   # money-flow multiplier
    ad = (mfm * v).cumsum()

    def _slope_pct(s):
        s = s.dropna().tail(lookback)
        if len(s) < 5:
            return None
        x = np.arange(len(s), dtype=float)
        m = np.polyfit(x, s.values.astype(float), 1)[0]   # units/bar
        denom = abs(s.values).mean() or 1.0
        return float(m * len(s) / denom * 100.0)          # % rise across the window

    obv_t = _slope_pct(obv); ad_t = _slope_pct(ad)
    votes = [t for t in (obv_t, ad_t) if t is not None]
    if not votes:
        return {"available": False}
    avg = sum(votes) / len(votes)
    state = "Accumulation" if avg > 4 else "Distribution" if avg < -4 else "Neutral"
    return {"available": True, "state": state,
            "obv_trend_pct": None if obv_t is None else round(obv_t, 1),
            "ad_trend_pct":  None if ad_t  is None else round(ad_t, 1),
            "lookback": lookback}


def _insider_footprint(ticker: str, days: int = 90) -> dict:
    """Real SEC Form 4 net buy/sell over `days`. Filters to dollar-valued insider
    transactions (drops the zero-value / non-Form-4 noise EODHD interleaves)."""
    try:
        import eodhd_client as ec
        import datetime as _dt
        end = _dt.date.today(); start = end - _dt.timedelta(days=days)
        rows = ec.insider_transactions(ticker.upper(), from_date=start.isoformat(),
                                       to_date=end.isoformat()) or []
    except Exception as e:
        return {"available": False, "error": str(e)}
    buy_val = sell_val = 0.0; buys = sells = 0; top = []
    for r in rows:
        code = str(r.get("transactionCode") or r.get("type") or "").upper()
        shares = _f(r.get("transactionAmount") or r.get("shares"))
        price = _f(r.get("transactionPrice") or r.get("price"))
        val = shares * price
        if val <= 0:
            continue                       # skip zero-value rows (data noise)
        if code.startswith("P"):
            buy_val += val; buys += 1; sgn = 1
        elif code.startswith("S"):
            sell_val += val; sells += 1; sgn = -1
        else:
            continue
        top.append({"date": r.get("transactionDate") or r.get("date") or "",
                    "name": r.get("ownerName") or r.get("name") or "",
                    "side": "BUY" if sgn > 0 else "SELL",
                    "value": round(val, 0)})
    if buys == 0 and sells == 0:
        return {"available": False, "window_days": days}
    top.sort(key=lambda x: x["value"], reverse=True)
    return {"available": True, "window_days": days,
            "net_value": round(buy_val - sell_val, 0),
            "buy_value": round(buy_val, 0), "sell_value": round(sell_val, 0),
            "buys": buys, "sells": sells, "top": top[:5]}


def _institutional_footprint(ticker: str) -> dict:
    """Real 13F institutional ownership from EODHD: total %, named top holders,
    net QoQ share change (45-day structural lag — disclosed)."""
    try:
        import eodhd_client as ec
        f = ec.fundamentals(ticker.upper()) or {}
    except Exception as e:
        return {"available": False, "error": str(e)}
    ss = f.get("SharesStats") or {}
    holders = list(((f.get("Holders") or {}).get("Institutions") or {}).values())
    if not holders and ss.get("PercentInstitutions") is None:
        return {"available": False}
    net_change = sum(_f(h.get("change")) for h in holders)
    holders_sorted = sorted(holders, key=lambda h: _f(h.get("totalShares")), reverse=True)
    top = [{"name": h.get("name"), "pct": round(_f(h.get("totalShares")), 2),
            "change_p": round(_f(h.get("change_p")), 2), "date": h.get("date")}
           for h in holders_sorted[:5]]
    as_of = holders_sorted[0].get("date") if holders_sorted else None
    return {"available": True,
            "own_pct": _f(ss.get("PercentInstitutions")) or None,
            "insider_own_pct": _f(ss.get("PercentInsiders")) or None,
            "n_holders": len(holders), "net_share_change": round(net_change, 0),
            "net_state": "Adding" if net_change > 0 else "Trimming" if net_change < 0 else "Flat",
            "top": top, "as_of": as_of}


def footprint(ticker: str, mode: str = "SWING") -> dict:
    """REAL institutional-footprint strip (accumulation + insider + 13F).
    The honest, attributable counterpart to the interpretive MCDX panel."""
    from pattern_data import get_bars, norm_mode
    ticker = ticker.upper()
    df, tier, meta = get_bars(ticker, norm_mode(mode), enriched=False)
    accumulation = {"available": False}
    if df is not None and len(df) >= 20:
        try:
            accumulation = _obv_ad_accumulation(df)
        except Exception as e:
            accumulation = {"available": False, "error": str(e)}
    return {"ticker": ticker, "mode": norm_mode(mode), "tier": tier,
            "tf": meta.get("tf") if isinstance(meta, dict) else None,
            "accumulation": accumulation,
            "insider": _insider_footprint(ticker),
            "institutional": _institutional_footprint(ticker)}


# ───────────────────────── real-data wrapper ─────────────────────────
# (timeframe label, pattern_data mode)
_GRID_TFS = [("1H", "SWING_1H"), ("4H", "SWING_4H"), ("1D", "SWING"),
             ("1W", "POSITION"), ("1M", "INVESTMENT")]


def _lc(df: pd.DataFrame) -> pd.DataFrame:
    """pattern_data returns capitalized OHLCV; engines use lowercase."""
    ren = {c: c.lower() for c in df.columns if c.lower() in ("open", "high", "low", "close", "volume")}
    return df.rename(columns=ren)


def bullalgo_state(ticker: str, mode: str = "SWING") -> dict:
    """Confirmation panel (mode's primary TF) + multi-TF screener grid."""
    from pattern_data import get_bars, norm_mode
    ticker = ticker.upper()
    nmode = norm_mode(mode)

    # Confirmation — primary timeframe for the selected mode.
    confirmation, conf_meta = None, {}
    df, tier, meta = get_bars(ticker, nmode, enriched=False)
    if df is not None and len(df) >= 30:
        try:
            confirmation = _confirmation_latest(_lc(df))
            conf_meta = {"tf": meta.get("tf"), "tier": tier}
        except Exception as e:
            conf_meta = {"error": str(e)}
    else:
        conf_meta = {"error": f"no_bars:{tier}", "tf": meta.get("tf")}

    # Screener + PAC grids — 4H / 1D / 1W / 1M. One bar-fetch per TF feeds both.
    grid, pac = [], []
    for label, gmode in _GRID_TFS:
        try:
            gdf, gtier, _ = get_bars(ticker, gmode, enriched=False)
            if gdf is not None and len(gdf) >= 30:
                lc = _lc(gdf)
                r = screen_row(ticker, label, lc); r["tier"] = gtier; grid.append(r)
                p = pac_row(ticker, label, lc); p["tier"] = gtier; pac.append(p)
            else:
                grid.append({"ticker": ticker, "timeframe": label, "available": False, "tier": gtier})
                pac.append({"ticker": ticker, "timeframe": label, "available": False, "tier": gtier})
        except Exception as e:
            grid.append({"ticker": ticker, "timeframe": label, "available": False, "error": str(e)})
            pac.append({"ticker": ticker, "timeframe": label, "available": False, "error": str(e)})

    return {"ticker": ticker, "mode": nmode,
            "confirmation": confirmation, "confirmation_meta": conf_meta,
            "screener": grid, "pac": pac}


if __name__ == "__main__":
    import sys, json
    t = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    m = sys.argv[2] if len(sys.argv) > 2 else "SWING"
    print(json.dumps(bullalgo_state(t, m), indent=2, default=str))
