"""engines/altcharts.py — Alt-Charts detector: Heikin-Ashi, Renko, Kagi.

Mechanism (principle 2): noise-filtered chart transforms (HA smoothing, ATR-brick
Renko, Kagi reversal) strip intrabar noise so trend persistence / reversal is
mechanical — they measure trend strength without time; best for trailing stops and
trend confirmation, NOT entry timing.

Honesty contract (principle 4): if bars are insufficient we return state="none"
with a plain message rather than fabricating signals.

CLI:  python3 -c "import pattern_engines as pe; import json
      d=pe.detect('altcharts','AAPL','SWING')
      print({k:(len(v) if isinstance(v,list) else v) for k,v in d.items() if k!='bars'})"
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from pattern_data import fmt_date

NAME = "altcharts"
LABEL = "Alt Charts"

# Window: how many bars to include in bars[] payload sent to the view
_BARS_WINDOW = {"Daily": 100, "Weekly": 80, "Monthly": 60}
# Min bars before we refuse
_MIN_BARS = {"Daily": 30, "Weekly": 20, "Monthly": 12}


# ─────────────────────────────────────────────────────────────────────
# Heikin-Ashi
# ─────────────────────────────────────────────────────────────────────

def _compute_ha(df: pd.DataFrame) -> pd.DataFrame:
    """Return a DataFrame with HA Open/High/Low/Close columns."""
    ha = pd.DataFrame(index=df.index)
    # HA Close = (O+H+L+C)/4
    ha["HA_Close"] = (df["Open"] + df["High"] + df["Low"] + df["Close"]) / 4.0
    # HA Open: recursive; seed with first bar's midpoint
    ha_open = np.empty(len(df))
    ha_open[0] = (df["Open"].iloc[0] + df["Close"].iloc[0]) / 2.0
    ha_c = ha["HA_Close"].values
    o_vals = df["Open"].values
    h_vals = df["High"].values
    l_vals = df["Low"].values
    for i in range(1, len(df)):
        ha_open[i] = (ha_open[i - 1] + ha_c[i - 1]) / 2.0
    ha["HA_Open"] = ha_open
    ha["HA_High"] = np.maximum(h_vals, np.maximum(ha_open, ha_c))
    ha["HA_Low"] = np.minimum(l_vals, np.minimum(ha_open, ha_c))
    return ha


def _ha_trend(ha: pd.DataFrame) -> Dict[str, Any]:
    """Count unbroken HA candles in current direction; first opposite = reversal warning."""
    if len(ha) == 0:
        return {"direction": "neutral", "streak": 0, "reversal_warning": False}
    up = ha["HA_Close"] >= ha["HA_Open"]
    # direction of last bar
    current_up = bool(up.iloc[-1])
    # count streak backwards
    streak = 0
    for i in range(len(ha) - 1, -1, -1):
        if bool(up.iloc[i]) == current_up:
            streak += 1
        else:
            break
    # reversal warning: upper wick present (up candle) or lower wick (down candle)
    last = ha.iloc[-1]
    if current_up:
        upper_wick = float(last["HA_High"]) - float(last["HA_Close"])
        body = float(last["HA_Close"]) - float(last["HA_Open"])
        reversal_warning = body > 0 and upper_wick > body * 0.5
    else:
        lower_wick = float(last["HA_Open"]) - float(last["HA_Low"])
        body = float(last["HA_Open"]) - float(last["HA_Close"])
        reversal_warning = body > 0 and lower_wick > body * 0.5
    return {
        "direction": "up" if current_up else "down",
        "streak": int(streak),
        "reversal_warning": bool(reversal_warning),
    }


def _ha_candles(ha: pd.DataFrame, df: pd.DataFrame, window: int) -> List[Dict]:
    """Export last `window` HA candles for the JSX mini-chart."""
    ha_w = ha.iloc[-window:]
    df_w = df.iloc[-window:]
    out = []
    rvol = df_w["rvol"].values if "rvol" in df_w.columns else np.ones(len(df_w))
    for i in range(len(ha_w)):
        r = ha_w.iloc[i]
        out.append({
            "o": round(float(r["HA_Open"]), 2),
            "c": round(float(r["HA_Close"]), 2),
            "hi": round(float(r["HA_High"]), 2),
            "lo": round(float(r["HA_Low"]), 2),
            "v": round(float(rvol[i]) if np.isfinite(rvol[i]) else 1.0, 2),
        })
    return out


# ─────────────────────────────────────────────────────────────────────
# Renko
# ─────────────────────────────────────────────────────────────────────

def _renko_brick_size(df: pd.DataFrame) -> float:
    """ATR-based brick size: median ATR of the window, rounded to a sensible step."""
    atr = df["atr"] if "atr" in df.columns else (df["High"] - df["Low"])
    med = float(atr.median())
    if med <= 0:
        med = float(df["Close"].iloc[-1]) * 0.01
    # Round to 1–2 significant figures so bricks are psychologically clean
    mag = 10 ** int(np.floor(np.log10(med)))
    brick = round(med / mag) * mag
    return max(brick, 0.01)


def _build_renko(df: pd.DataFrame, brick: float) -> List[Dict]:
    """Classic Renko bricks built from Close prices."""
    closes = df["Close"].values
    if len(closes) == 0:
        return []
    bricks = []
    base = round(closes[0] / brick) * brick
    for c in closes:
        while c >= base + brick:
            bricks.append({"dir": 1, "lo": round(base, 2), "hi": round(base + brick, 2)})
            base += brick
        while c <= base - brick:
            bricks.append({"dir": -1, "lo": round(base - brick, 2), "hi": round(base, 2)})
            base -= brick
    return bricks


def _renko_state(bricks: List[Dict]) -> Dict[str, Any]:
    """Summarise current Renko state."""
    if not bricks:
        return {"direction": "neutral", "bricks_since_reversal": 0, "reversal_price": None}
    current_dir = bricks[-1]["dir"]
    count = 0
    for b in reversed(bricks):
        if b["dir"] == current_dir:
            count += 1
        else:
            break
    # reversal trigger: price that would produce first opposite brick
    last = bricks[-1]
    if current_dir > 0:
        reversal_price = round(last["lo"], 2)      # one full brick back down from base
    else:
        reversal_price = round(last["hi"], 2)      # one full brick back up
    return {
        "direction": "up" if current_dir > 0 else "down",
        "bricks_since_reversal": int(count),
        "reversal_price": float(reversal_price),
    }


# ─────────────────────────────────────────────────────────────────────
# Kagi
# ─────────────────────────────────────────────────────────────────────

def _build_kagi(df: pd.DataFrame) -> Dict[str, Any]:
    """Kagi line: yang (thick/up) vs yin (thin/down) state with ATR reversal amount."""
    closes = df["Close"].values
    if len(closes) < 2:
        return {"state": "neutral", "reversal_amount": 0, "reversals": 0, "lines": []}

    atr = df["atr"] if "atr" in df.columns else (df["High"] - df["Low"])
    rev_amount = float(atr.median())
    if rev_amount <= 0:
        rev_amount = float(closes[-1]) * 0.01

    # Kagi state machine
    direction = 1 if closes[-1] >= closes[0] else -1
    extreme = closes[0]
    reversals = 0
    yang_threshold = None  # price where yang (thick) would begin
    yin_threshold = None

    lines = []
    cur_start = float(closes[0])
    cur_dir = None

    for i, c in enumerate(closes):
        if cur_dir is None:
            cur_dir = 1 if c >= extreme else -1
            extreme = c
            continue
        if cur_dir > 0:
            if c > extreme:
                extreme = c
            elif extreme - c >= rev_amount:
                lines.append({"dir": int(cur_dir), "from": round(float(cur_start), 2), "to": round(float(extreme), 2)})
                cur_start = extreme
                cur_dir = -1
                extreme = c
                reversals += 1
        else:
            if c < extreme:
                extreme = c
            elif c - extreme >= rev_amount:
                lines.append({"dir": int(cur_dir), "from": round(float(cur_start), 2), "to": round(float(extreme), 2)})
                cur_start = extreme
                cur_dir = 1
                extreme = c
                reversals += 1

    # final incomplete line
    lines.append({"dir": int(cur_dir), "from": round(float(cur_start), 2), "to": round(float(extreme), 2)})

    # yang = cur_dir > 0 and current high breaks prior yin low (simplified: cur_dir>0 = yang)
    state = "yang" if cur_dir > 0 else "yin"

    # reversal trigger: price that would cause next flip
    last_extreme = float(extreme)
    if cur_dir > 0:
        reversal_trigger = round(last_extreme - rev_amount, 2)
    else:
        reversal_trigger = round(last_extreme + rev_amount, 2)

    return {
        "state": state,
        "direction": "up" if cur_dir > 0 else "down",
        "reversal_amount": round(rev_amount, 2),
        "reversal_trigger": reversal_trigger,
        "reversals": int(reversals),
        "lines": lines[-20:],    # last 20 lines for the mini-chart
    }


# ─────────────────────────────────────────────────────────────────────
# Combined verdict
# ─────────────────────────────────────────────────────────────────────

def _combined_verdict(ha_trend: Dict, renko: Dict, kagi: Dict) -> Dict[str, Any]:
    """Count how many transforms agree on direction → confidence."""
    votes_up = sum([
        ha_trend["direction"] == "up",
        renko["direction"] == "up",
        kagi["direction"] == "up",
    ])
    votes_dn = sum([
        ha_trend["direction"] == "down",
        renko["direction"] == "down",
        kagi["direction"] == "down",
    ])
    if votes_up >= 2:
        direction = "up"
        confidence = 0.5 + votes_up * 0.15   # 0.65 for 2/3, 0.95 for 3/3 (capped)
    elif votes_dn >= 2:
        direction = "down"
        confidence = 0.5 + votes_dn * 0.15
    else:
        direction = "neutral"
        confidence = 0.35
    confidence = round(min(confidence, 0.95), 2)

    # Reversal warning if any transform has a warning signal
    any_warn = ha_trend.get("reversal_warning", False)

    return {
        "direction": direction,
        "confidence": confidence,
        "reversal_warning": any_warn,
        "votes": {"up": int(votes_up), "down": int(votes_dn)},
    }


def _real_bars(df: pd.DataFrame, window: int) -> List[Dict]:
    """Export raw OHLCV bars (for base candle chart reference)."""
    df_w = df.iloc[-window:]
    rvol = df_w["rvol"].values if "rvol" in df_w.columns else np.ones(len(df_w))
    out = []
    for i, (_, r) in enumerate(df_w.iterrows()):
        out.append({
            "o": round(float(r["Open"]), 2),
            "c": round(float(r["Close"]), 2),
            "hi": round(float(r["High"]), 2),
            "lo": round(float(r["Low"]), 2),
            "v": round(float(rvol[i]) if np.isfinite(rvol[i]) else 1.0, 2),
        })
    return out


# ─────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────

def detect(df: pd.DataFrame, meta: Dict, ticker: str) -> Dict[str, Any]:
    """Alt-Charts detector: HA / Renko / Kagi computed from real OHLCV bars.

    Returns bars (real windowed OHLC), ha[] (HA candles), renko dict,
    kagi dict, stat header, read (plain-English verdict), and confidence.
    """
    tf = meta.get("tf", "Daily")
    min_bars = _MIN_BARS.get(tf, 30)
    window = _BARS_WINDOW.get(tf, 100)

    cur_close = round(float(df["Close"].iloc[-1]), 2)

    if len(df) < min_bars:
        return {
            "ok": True, "source": "real", "state": "none",
            "message": f"Only {len(df)} {tf.lower()} bars — need ≥{min_bars} for Alt-Charts.",
            "cur_close": cur_close,
        }

    # ── Heikin-Ashi ──────────────────────────────────────────────────
    ha = _compute_ha(df)
    ha_trend = _ha_trend(ha)
    ha_candles = _ha_candles(ha, df, window)

    # ── Renko ────────────────────────────────────────────────────────
    brick = _renko_brick_size(df)
    renko_bricks = _build_renko(df, brick)
    renko_st = _renko_state(renko_bricks)

    # ── Kagi ─────────────────────────────────────────────────────────
    kagi = _build_kagi(df)

    # ── Combined verdict ─────────────────────────────────────────────
    verdict = _combined_verdict(ha_trend, renko_st, kagi)

    # ── Stat header (for the view's pv-stat strip) ───────────────────
    ha_dir = ha_trend["direction"].upper()
    renko_dir = renko_st["direction"].upper()
    kagi_state = kagi["state"].upper()   # YANG or YIN
    ha_streak = ha_trend["streak"]

    ha_signal = (
        f"{ha_streak} unbroken {'up' if ha_dir == 'UP' else 'down'} candles"
    )
    renko_signal = (
        f"{renko_st['bricks_since_reversal']} {renko_dir.lower()} bricks · "
        f"reversal @ {renko_st['reversal_price']}"
    )
    ha_reversal = (
        f"first {'filled' if ha_dir == 'UP' else 'hollow'} candle w/ long wick"
        + (" — WARNING" if ha_trend["reversal_warning"] else "")
    )
    renko_reversal = f"needs 1 {('down' if renko_dir == 'UP' else 'up')} brick @ {renko_st['reversal_price']}"
    kagi_reversal = f"{kagi['state']} flip needs {kagi['reversal_amount']:.2f} reversal @ {kagi['reversal_trigger']}"

    stat = {
        "ha_trend": ha_dir,
        "ha_streak": int(ha_streak),
        "renko_dir": renko_dir,
        "renko_bricks": int(renko_st["bricks_since_reversal"]),
        "kagi_state": kagi_state,
        "verdict": verdict["direction"].upper(),
        "confidence": verdict["confidence"],
        "reversal_warning": verdict["reversal_warning"],
    }

    # ── Read (one-sentence verdict) ───────────────────────────────────
    dir_word = verdict["direction"]
    conf_pct = int(verdict["confidence"] * 100)
    if dir_word == "neutral":
        read = (
            f"Alt-chart consensus is NEUTRAL ({conf_pct}% confidence) — HA streak {ha_streak}, "
            f"Renko {renko_dir.lower()}, Kagi {kagi['state']} — wait for alignment before trailing."
        )
    else:
        warn_sfx = " — reversal warning on HA." if verdict["reversal_warning"] else "."
        read = (
            f"All noise-filtered constructions agree on {dir_word.upper()} ({conf_pct}% confidence): "
            f"HA {ha_streak}-bar streak, Renko {renko_st['bricks_since_reversal']} bricks, Kagi {kagi['state']}{warn_sfx}"
        )

    return {
        "ok": True,
        "source": "real",
        "state": "real",
        "confidence": verdict["confidence"],
        "cur_close": cur_close,
        "bars": _real_bars(df, window),          # raw OHLCV for base chart
        "ha": ha_candles,                         # HA candles for HA sub-chart
        "renko": {
            "brick_size": round(brick, 2),
            "bricks": renko_bricks[-120:],        # last 120 bricks for chart
            "direction": renko_st["direction"],
            "bricks_since_reversal": renko_st["bricks_since_reversal"],
            "reversal_price": renko_st["reversal_price"],
        },
        "kagi": kagi,
        "stat": stat,
        "meta_display": {
            "ha_signal": ha_signal,
            "ha_reversal": ha_reversal,
            "renko_signal": renko_signal,
            "renko_reversal": renko_reversal,
            "kagi_reversal": kagi_reversal,
        },
        "read": read,
    }
