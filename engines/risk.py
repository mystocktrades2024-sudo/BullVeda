"""engines/risk.py — real position/asset risk metrics from live bars.

Everything is computed from real OHLCV (no hardcoded vol): realized volatility,
parametric + historical VaR / CVaR, annualized Sharpe / Sortino, max drawdown,
beta vs SPY, and horizon-scaled loss cones. Mode-aware via get_bars. Consumed by
the BullVeda Risk lens at /api/pattern/risk/{ticker}.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Any, Dict, Optional

from pattern_data import get_bars, mode_meta, norm_mode

NAME = "risk"
LABEL = "Risk"


def _beta(a: np.ndarray, ref: np.ndarray) -> Optional[float]:
    n = min(len(a), len(ref))
    if n < 40:
        return None
    a, ref = a[-n:], ref[-n:]
    vb = np.var(ref)
    if vb <= 0:
        return None
    return float(np.cov(a, ref)[0, 1] / vb)


def detect(df: pd.DataFrame, meta: Dict[str, Any], ticker: str) -> Dict[str, Any]:
    tf = meta.get("tf", "Daily")
    if df is None or len(df) < 40:
        return {"ok": False, "message": "insufficient bars for risk", "bars": 0}
    c = df["Close"].astype(float)
    rets = c.pct_change().dropna().values
    if len(rets) < 30:
        return {"ok": False, "message": "insufficient returns", "bars": int(len(df))}
    win = rets[-126:] if len(rets) >= 126 else rets
    sd = float(np.std(win, ddof=1))
    mean = float(np.mean(win))
    cur = float(c.iloc[-1])

    # VaR / CVaR — parametric (normal) + historical (empirical tail)
    var95_p = 1.645 * sd
    var99_p = 2.326 * sd
    p5 = float(np.percentile(win, 5))
    tail = win[win <= p5]
    cvar95 = float(-np.mean(tail)) if len(tail) else -p5
    var95_h = float(-p5)

    # annualized Sharpe / Sortino (rf≈0)
    ann = np.sqrt(252.0)
    sharpe = float(mean / sd * ann) if sd > 0 else 0.0
    downside = win[win < 0]
    dsd = float(np.std(downside, ddof=1)) if len(downside) > 1 else sd
    sortino = float(mean / dsd * ann) if dsd > 0 else 0.0

    # max drawdown over the last ~year
    cc = c.iloc[-252:] if len(c) >= 252 else c
    roll = cc.cummax()
    maxdd = float((cc / roll - 1.0).min())

    # beta vs SPY
    beta = None
    if (ticker or "").upper() != "SPY":
        try:
            ref, _t, _m = get_bars("SPY", meta.get("mode", "SWING"))
            if ref is not None and len(ref) > 40:
                rr = ref["Close"].astype(float).pct_change().dropna().values
                beta = _beta(rets, rr)
                if beta is not None:
                    beta = round(beta, 2)
        except Exception:
            beta = None

    # horizon scaling for cones / VaR (1 = daily for swing)
    hd = {"Daily": 1, "Weekly": 5, "Monthly": 21}.get(tf, 1)
    sig_h = sd * np.sqrt(hd) if hd > 1 else sd

    cones = []
    for k in (1, 2, 3):
        cones.append({"k": k, "pct": round(sig_h * k * 100, 1),
                      "lo": round(cur * (1 - sig_h * k), 2), "hi": round(cur * (1 + sig_h * k), 2)})

    return {
        "ok": True,
        "bars": int(len(df)),
        "cur_close": round(cur, 2),
        "tf": tf,
        "vol_1d_pct": round(sd * 100, 2),
        "vol_ann_pct": round(sd * ann * 100, 1),
        "var95_pct": round(var95_p * 100, 2),
        "var99_pct": round(var99_p * 100, 2),
        "var95_hist_pct": round(var95_h * 100, 2),
        "cvar95_pct": round(cvar95 * 100, 2),
        "sharpe_126d": round(sharpe, 2),
        "sortino_126d": round(sortino, 2),
        "max_dd_pct": round(maxdd * 100, 1),
        "beta": beta,
        "hd": hd,
        "cones": cones,
    }
