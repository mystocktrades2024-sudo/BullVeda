"""engines/mlforecast.py — ML Forecast meta-model engine for the BullVeda Patterns lens.

Mechanism (principle 2): a meta-model that stacks the independent theory signals
+ price/volume features produces a calibrated probability that is more reliable
than any single method's point call — size by the confidence band, not the point
estimate.  Each sibling theory's detect() output is treated as an opaque feature
(its implicit directional vote + confidence), combined with raw bar-derived
features into a transparent logistic-style weighted-sum → sigmoid.  The weights
are documented here and explained feature-by-feature so the output is falsifiable
(principle 4).

Honesty (principle 4): we never fabricate a probability when bars are too short.
If fewer than 30 bars exist, state="none" is returned immediately.

Timeframe-aware (principle 5): window sizes and the horizon over which the
band is computed all scale with meta["tf"].

Deterministic / cache-safe: pure numpy, no network calls, no per-run randomness.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

NAME  = "mlforecast"
LABEL = "ML Forecast"

# ── timeframe parameters ───────────────────────────────────────────────────────
_TFW = {
    #                roc_n  rsi_n  rvol_n  hl_n  chart_bars  horizon_bars  horizon_label
    "Daily":   dict(roc=10,  rsi=14, rvol=20, hl=20, chart=80,  hz=10,  hz_label="10-day"),
    "Weekly":  dict(roc=8,   rsi=14, rvol=10, hl=13, chart=80,  hz=13,  hz_label="13-week"),
    "Monthly": dict(roc=6,   rsi=14, rvol=6,  hl=12, chart=60,  hz=12,  hz_label="12-month"),
}

def _tfw(tf: str) -> dict:
    return _TFW.get(tf, _TFW["Daily"])


# ── feature weights (documented — subject to walk-forward revision) ───────────
# These are directional-contribution weights; each feature maps to a signed
# contribution score in [-1, +1] before weighting.
#
# Price-structure features (45% total):
#   ema_trend      0.12  — ema20 vs ema50 trend alignment
#   ema_proximity  0.08  — distance of price from ema20 (pullback quality)
#   roc            0.10  — rate-of-change momentum
#   hl_position    0.08  — position within recent high-low range
#   rsi_feature    0.07  — RSI-like momentum calibration
#
# Volume / volatility features (25% total):
#   rvol           0.10  — relative volume (institutional attention proxy)
#   vol_contraction 0.08 — volatility drying up before breakout (classic VCP signal)
#   realized_vol   0.07  — recent realized vol (inverse: high vol = mean-reversion risk)
#
# Sibling theory votes (30% total, shared equally among votes received):
#   Each theory's directional vote contributes up to 0.30 / n_theories_available
#   — guarded with try/except so one failing engine never kills the meta-model.

_PRICE_WEIGHTS: Dict[str, float] = {
    "ema_trend":       0.12,
    "ema_proximity":   0.08,
    "roc":             0.10,
    "hl_position":     0.08,
    "rsi_feature":     0.07,
}
_VOL_WEIGHTS: Dict[str, float] = {
    "rvol":            0.10,
    "vol_contraction": 0.08,
    "realized_vol":    0.07,
}
_THEORY_POOL_WEIGHT = 0.30  # shared pool for all available theory votes


# ── helpers ────────────────────────────────────────────────────────────────────

def _bar_payload(df: pd.DataFrame) -> List[Dict[str, float]]:
    out = []
    for _, r in df.iterrows():
        out.append({
            "o":  round(float(r["Open"]),  2),
            "c":  round(float(r["Close"]), 2),
            "hi": round(float(r["High"]),  2),
            "lo": round(float(r["Low"]),   2),
            "v":  round(float(r.get("rvol", 1.0)), 2),
        })
    return out


def _sigmoid(x: float) -> float:
    """Stable sigmoid squishing raw ensemble score to (0, 1)."""
    return 1.0 / (1.0 + math.exp(-x))


def _rsi(closes: np.ndarray, n: int = 14) -> float:
    """Simple RSI from close array (last n+1 bars used)."""
    if len(closes) < n + 1:
        return 50.0
    deltas = np.diff(closes[-(n + 1):])
    gains  = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = gains.mean()
    avg_loss = losses.mean()
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return float(100.0 - 100.0 / (1.0 + rs))


def _realized_vol(closes: np.ndarray, n: int = 20) -> float:
    """Annualised realized vol from last n log-returns."""
    if len(closes) < n + 1:
        return 0.20
    lr = np.diff(np.log(closes[-(n + 1):]))
    lr = lr[np.isfinite(lr)]
    if len(lr) < 3:
        return 0.20
    return float(lr.std(ddof=1) * math.sqrt(252))


# ── price-structure features ───────────────────────────────────────────────────

def _compute_price_features(df: pd.DataFrame, tf: str) -> List[Dict[str, Any]]:
    """Return list of feature dicts with {name, value, contribution, note}."""
    w       = _tfw(tf)
    closes  = df["Close"].values.astype(float)
    highs   = df["High"].values.astype(float)
    lows    = df["Low"].values.astype(float)
    cur     = closes[-1]

    feats: List[Dict[str, Any]] = []

    # 1. EMA trend: ema20 vs ema50
    ema20 = float(df["ema20"].iloc[-1]) if "ema20" in df.columns else float(pd.Series(closes).ewm(span=20, adjust=False).mean().iloc[-1])
    ema50 = float(df["ema50"].iloc[-1]) if "ema50" in df.columns else float(pd.Series(closes).ewm(span=50, adjust=False).mean().iloc[-1])
    ema_bull     = (ema20 > ema50) and (cur > ema20)
    ema_bear     = (ema20 < ema50) and (cur < ema20)
    ema_raw      = 1.0 if ema_bull else (-1.0 if ema_bear else 0.0)
    # partial credit for price vs ema20 only
    if not ema_bull and not ema_bear:
        ema_raw = 0.5 if cur > ema20 else -0.5
    contrib_ema_trend = round(ema_raw * _PRICE_WEIGHTS["ema_trend"], 4)
    feats.append({
        "name":         "EMA trend",
        "value":        round(ema20 / ema50 - 1.0, 4),
        "contribution": contrib_ema_trend,
        "note":         f"ema20 {'>' if ema20 > ema50 else '<'} ema50 · price {'above' if cur > ema20 else 'below'} ema20",
    })

    # 2. EMA proximity: how extended is price above ema20?
    # Bull: slight pullback to ema20 is ideal (FRESH/PULLBACK entry quality)
    atr_val = float(df["atr"].iloc[-1]) if "atr" in df.columns else cur * 0.015
    dist_ema20_atr = (cur - ema20) / max(atr_val, 1e-6)
    # optimum is 0.5–1.5 ATR above ema20 (fresh / valid);  >3 ATR = extended
    prox_score = 0.5 - abs(dist_ema20_atr - 1.0) * 0.3
    prox_score = max(-1.0, min(1.0, prox_score))
    contrib_prox = round(prox_score * _PRICE_WEIGHTS["ema_proximity"], 4)
    feats.append({
        "name":         "EMA proximity",
        "value":        round(dist_ema20_atr, 3),
        "contribution": contrib_prox,
        "note":         f"{abs(dist_ema20_atr):.1f} ATR from ema20 ({'above' if dist_ema20_atr >= 0 else 'below'})",
    })

    # 3. Rate-of-change (momentum)
    n_roc  = min(w["roc"], len(closes) - 1)
    roc    = float((closes[-1] / closes[-n_roc - 1]) - 1.0) if n_roc > 0 else 0.0
    # map roc to [-1, +1]: 0 = 0%, ±5% → ±1 (logistic-ish)
    roc_score = math.tanh(roc / 0.05)
    contrib_roc = round(roc_score * _PRICE_WEIGHTS["roc"], 4)
    feats.append({
        "name":         "Rate-of-change",
        "value":        round(roc * 100, 2),
        "contribution": contrib_roc,
        "note":         f"{n_roc}-bar ROC {'+' if roc >= 0 else ''}{roc * 100:.1f}%",
    })

    # 4. High-low range position (where is price in the recent range?)
    n_hl   = min(w["hl"], len(closes))
    hi_n   = highs[-n_hl:].max()
    lo_n   = lows[-n_hl:].min()
    hl_rng = hi_n - lo_n
    hl_pos = (cur - lo_n) / max(hl_rng, 1e-6)   # 0=at low, 1=at high
    # 0.6–1.0 (upper range) is bullish; 0–0.3 is distressed
    hl_score = (hl_pos - 0.5) * 2.0   # maps to [-1, +1]
    hl_score = max(-1.0, min(1.0, hl_score))
    contrib_hl = round(hl_score * _PRICE_WEIGHTS["hl_position"], 4)
    feats.append({
        "name":         "Range position",
        "value":        round(hl_pos, 3),
        "contribution": contrib_hl,
        "note":         f"{n_hl}-bar range · {hl_pos * 100:.0f}th percentile",
    })

    # 5. RSI-like momentum
    rsi_val   = _rsi(closes, n=w["rsi"])
    # RSI 50–70 = modest bullish; >70 = extended; <50 = bear; 70–80 optimal zone
    rsi_score = math.tanh((rsi_val - 55.0) / 20.0)
    contrib_rsi = round(rsi_score * _PRICE_WEIGHTS["rsi_feature"], 4)
    feats.append({
        "name":         "RSI momentum",
        "value":        round(rsi_val, 1),
        "contribution": contrib_rsi,
        "note":         f"RSI({w['rsi']}) = {rsi_val:.1f}",
    })

    return feats


# ── volume / volatility features ───────────────────────────────────────────────

def _compute_vol_features(df: pd.DataFrame, tf: str) -> List[Dict[str, Any]]:
    w = _tfw(tf)
    closes = df["Close"].values.astype(float)
    feats: List[Dict[str, Any]] = []

    # 6. Relative volume (rvol)
    rvol_now  = float(df["rvol"].iloc[-1]) if "rvol" in df.columns else 1.0
    # >1.5 is notable; >2 is strong accumulation signal; <0.5 = drying up (could be VCP)
    rvol_score = math.tanh((rvol_now - 1.0) * 1.2)
    contrib_rvol = round(rvol_score * _VOL_WEIGHTS["rvol"], 4)
    feats.append({
        "name":         "Relative volume",
        "value":        round(rvol_now, 2),
        "contribution": contrib_rvol,
        "note":         f"rvol {rvol_now:.2f}× avg",
    })

    # 7. Volatility contraction (vol drying up = VCP-style setup)
    n_vc = min(w["rvol"], len(df))
    recent_vol = df["rvol"].iloc[-max(n_vc // 3, 3):].mean() if "rvol" in df.columns else 1.0
    older_vol  = df["rvol"].iloc[-n_vc:-max(n_vc // 3, 3)].mean() if "rvol" in df.columns else 1.0
    if older_vol > 0:
        vc_ratio = float(recent_vol / older_vol)
    else:
        vc_ratio = 1.0
    # vc_ratio < 1 = contraction (bullish setup), > 1 = expansion
    vc_score = math.tanh((1.0 - vc_ratio) * 3.0)
    contrib_vc = round(vc_score * _VOL_WEIGHTS["vol_contraction"], 4)
    feats.append({
        "name":         "Vol contraction",
        "value":        round(vc_ratio, 3),
        "contribution": contrib_vc,
        "note":         f"recent/prior rvol ratio {vc_ratio:.2f} ({'contracting' if vc_ratio < 0.9 else 'expanding' if vc_ratio > 1.1 else 'flat'})",
    })

    # 8. Realized volatility (inverse: high vol = mean-reversion risk)
    rv = _realized_vol(closes, n=min(w["rvol"], len(closes) - 1))
    # 15–25% annualised is normal swing-trade terrain; >40% = jittery
    rv_score = -math.tanh((rv - 0.25) / 0.20)  # negative: high vol is bearish for continuation
    contrib_rv = round(rv_score * _VOL_WEIGHTS["realized_vol"], 4)
    feats.append({
        "name":         "Realized vol",
        "value":        round(rv * 100, 1),
        "contribution": contrib_rv,
        "note":         f"ann. realised vol {rv * 100:.1f}% ({'low' if rv < 0.20 else 'high' if rv > 0.35 else 'normal'})",
    })

    return feats


# ── sibling theory votes ───────────────────────────────────────────────────────

# Mapping from engine name → function to extract directional bias from its payload.
# Each returns a float in [-1, +1] (negative = bearish, positive = bullish)
# and a short label for the JSX votes[] array.

def _vote_from_wyckoff(payload: dict) -> Tuple[float, str]:
    """Accumulation → bullish; distribution → bearish; none → neutral."""
    sch = (payload.get("schematic") or "").lower()
    phase = (payload.get("phase") or payload.get("stat", {}).get("phase") or "").lower()
    if "accum" in sch:
        # phase D/E (markup) = strong bull; C = moderate
        if any(p in phase for p in ["d", "e", "markup"]):
            return 0.8, "Wyckoff · Phase D/E accumulation"
        if "c" in phase or "spring" in phase:
            return 0.5, "Wyckoff · Phase C (test)"
        return 0.2, "Wyckoff · Phase A/B accumulation"
    if "distrib" in sch:
        if any(p in phase for p in ["d", "e"]):
            return -0.8, "Wyckoff · Phase D/E distribution"
        return -0.3, "Wyckoff · distribution forming"
    return 0.0, "Wyckoff · no clear schematic"


def _vote_from_ichimoku(payload: dict) -> Tuple[float, str]:
    verdict = payload.get("verdict") or ""
    bull    = payload.get("bull_count") or 0
    bear    = payload.get("bear_count") or 0
    if "strong_bull" in verdict:
        return 0.9, f"Ichimoku · {bull}/5 bull signals"
    if verdict == "bull":
        return 0.55, f"Ichimoku · {bull}/5 bull signals"
    if "strong_bear" in verdict:
        return -0.9, f"Ichimoku · {bear}/5 bear signals"
    if verdict == "bear":
        return -0.55, f"Ichimoku · {bear}/5 bear signals"
    if "inside" in verdict:
        return 0.0, "Ichimoku · price inside cloud (neutral)"
    return 0.0, "Ichimoku · mixed"


def _vote_from_td(payload: dict) -> Tuple[float, str]:
    state = (payload.get("state") or "").lower()
    if state == "none":
        return 0.0, "TD Sequential · no active count"
    setup = payload.get("setup") or payload.get("stat", {})
    if isinstance(setup, dict):
        kind = (setup.get("kind") or "").lower()
        count = setup.get("count") or 0
        if kind == "buy" and count >= 9:
            return 0.65, f"TD Sequential · completed buy setup ({count})"
        if kind == "sell" and count >= 9:
            return -0.65, f"TD Sequential · completed sell setup ({count})"
        if kind == "buy":
            return 0.3, f"TD Sequential · buy setup count {count}/9"
        if kind == "sell":
            return -0.3, f"TD Sequential · sell setup count {count}/9"
    return 0.0, "TD Sequential · counting"


def _vote_from_fibonacci(payload: dict) -> Tuple[float, str]:
    swing = payload.get("swing") or {}
    direction = swing.get("direction") or ""
    cur = payload.get("cur_close") or 0
    levels = payload.get("levels") or []
    if not direction:
        return 0.0, "Fibonacci · no dominant swing"
    # If near a respected support level and swing is up → bullish
    support_levels = [lv for lv in levels if lv.get("role") == "support" and lv.get("hit")]
    near_support = any(abs((lv.get("price") or 0) - cur) < cur * 0.02 for lv in support_levels) if cur else False
    if direction == "up":
        score = 0.7 if near_support else 0.35
        return score, f"Fibonacci · upswing {'at support' if near_support else 'in play'}"
    elif direction == "down":
        return -0.35, "Fibonacci · downswing"
    return 0.0, "Fibonacci · flat"


def _vote_from_montecarlo(payload: dict) -> Tuple[float, str]:
    """P(T1 first) vs P(stop first) gives the net bias."""
    t1f   = payload.get("t1First") or 0
    stopf = payload.get("stopFirst") or 0
    if t1f + stopf == 0:
        return 0.0, "Monte Carlo · no paths"
    # positive if P(T1) > P(stop)
    net = t1f - stopf
    label = f"Monte Carlo · P(T1) {t1f * 100:.0f}% vs P(stop) {stopf * 100:.0f}%"
    return float(np.clip(net * 2.0, -1.0, 1.0)), label


def _vote_from_classical(payload: dict) -> Tuple[float, str]:
    pattern = (payload.get("pattern") or "").lower()
    if not pattern or pattern == "none":
        return 0.0, "Classical · no base detected"
    bull_patterns = {"vcp", "asc. triangle", "ascending triangle", "bull flag", "cup", "base"}
    bear_patterns = {"h&s", "head and shoulders", "descending triangle", "double top"}
    for bp in bull_patterns:
        if bp in pattern:
            return 0.6, f"Classical · {pattern}"
    for bp in bear_patterns:
        if bp in pattern:
            return -0.6, f"Classical · {pattern}"
    return 0.2, f"Classical · {pattern}"


_THEORY_VOTERS = {
    "wyckoff":    _vote_from_wyckoff,
    "ichimoku":   _vote_from_ichimoku,
    "td":         _vote_from_td,
    "fibonacci":  _vote_from_fibonacci,
    "montecarlo": _vote_from_montecarlo,
    "classical":  _vote_from_classical,
}


def _collect_theory_votes(df: pd.DataFrame, meta: dict, ticker: str) -> List[Dict[str, Any]]:
    """Call each sibling detector, extract directional vote.  Guard every call."""
    votes: List[Dict[str, Any]] = []
    for engine_name, voter_fn in _THEORY_VOTERS.items():
        try:
            import importlib
            mod = importlib.import_module(f"engines.{engine_name}")
            payload = mod.detect(df, meta, ticker) or {}
            if not payload.get("ok"):
                continue
            if payload.get("state") == "none":
                votes.append({
                    "theory": engine_name.title(),
                    "bias":   0.0,
                    "label":  f"{engine_name.title()} · no structure",
                    "weight": 0.0,   # populated after pool division
                    "contribution": 0.0,
                })
                continue
            bias, label = voter_fn(payload)
            votes.append({
                "theory": engine_name.title(),
                "bias":   round(float(bias), 3),
                "label":  label,
                "weight": 0.0,
                "contribution": 0.0,
            })
        except Exception:
            # one failing engine must never kill the meta-model (principle 4)
            pass
    return votes


def _assign_theory_weights(votes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Distribute _THEORY_POOL_WEIGHT equally among votes with non-zero bias.
    Votes from engines that returned state="none" get weight=0."""
    active = [v for v in votes if v["weight"] == 0.0 and v["bias"] != 0.0]
    per_engine = _THEORY_POOL_WEIGHT / max(len(active), 1)
    for v in votes:
        if v["bias"] != 0.0:
            v["weight"] = round(per_engine, 4)
            v["contribution"] = round(v["bias"] * per_engine, 4)
    return votes


# ── band computation ──────────────────────────────────────────────────────────

def _compute_band(cur_close: float, rv: float, hz: int,
                  pUp: float) -> Dict[str, float]:
    """Confidence band (lo / mid / hi) based on directional drift + realized vol.

    mid is the mean-expected return (drift * horizon).
    lo/hi are ±1 std-dev using sqrt(horizon) vol scaling.
    All expressed as percentage move from current price (not absolute price).
    """
    # Convert pUp to an implied expected drift per bar.
    # pUp = 0.5 → 0 drift; pUp = 0.8 → ~0.8 std/bar drift
    daily_vol = rv / math.sqrt(252)
    drift_per_bar = (pUp - 0.5) * 2.0 * daily_vol   # scales +/- 1 std
    med_pct  = drift_per_bar * hz
    band_pct = daily_vol * math.sqrt(hz)
    return {
        "lo":  round((med_pct - band_pct) * 100, 2),
        "mid": round(med_pct * 100, 2),
        "hi":  round((med_pct + band_pct) * 100, 2),
    }


# ── calibration note ─────────────────────────────────────────────────────────

def _calibration_note(n_bars: int, n_theories: int, tf: str) -> str:
    note_parts = []
    if n_bars < 60:
        note_parts.append(f"short history ({n_bars} {tf.lower()} bars — increase bars for higher confidence)")
    if n_theories < 3:
        note_parts.append(f"only {n_theories} theory engines available — wider confidence interval")
    if not note_parts:
        return f"Meta-model computed from {n_bars} {tf.lower()} bars + {n_theories} theory votes."
    return "Calibration caveat: " + "; ".join(note_parts) + "."


# ── read sentence ─────────────────────────────────────────────────────────────

def _build_read(pUp: float, verdict: str, confidence: float, agree: int,
                n_theories: int, tf: str, band: Dict[str, float],
                hz_label: str) -> str:
    conf_label = "HIGH" if confidence > 0.70 else ("MEDIUM" if confidence > 0.45 else "LOW")
    dir_word   = "bullish" if pUp >= 0.55 else ("bearish" if pUp <= 0.45 else "neutral")
    return (
        f"Meta-model ({n_theories} theory votes + 8 price/volume features) leans "
        f"{dir_word}: P(up · {hz_label}) = {round(pUp * 100)}%, "
        f"{agree}/{n_theories} theories aligned — "
        f"{conf_label} confidence. "
        f"Expected move band: {band['lo']:+.1f}% / {band['mid']:+.1f}% / {band['hi']:+.1f}%."
    )


# ── main detect() ─────────────────────────────────────────────────────────────

def detect(df: pd.DataFrame, meta: Dict[str, Any], ticker: str) -> Dict[str, Any]:
    """ML Forecast meta-model — transparent weighted-sum → sigmoid ensemble.

    Returns the payload consumed by MLForecastView.  MUST NOT raise.
    """
    tf   = meta.get("tf", "Daily")
    mode = meta.get("mode", "SWING")
    w    = _tfw(tf)

    if df is None or len(df) < 30:
        return {
            "ok": True, "source": "real", "state": "none",
            "message": "Insufficient bar history for ML Forecast (need ≥30 bars).",
            "cur_close": None,
        }

    cur_close = round(float(df["Close"].iloc[-1]), 2)
    closes    = df["Close"].values.astype(float)

    # ── feature computation ────────────────────────────────────────────────────
    price_feats = _compute_price_features(df, tf)
    vol_feats   = _compute_vol_features(df, tf)

    # ── theory votes (guarded) ────────────────────────────────────────────────
    votes = _collect_theory_votes(df, meta, ticker)
    votes = _assign_theory_weights(votes)

    # ── ensemble: weighted sum of all contributions ────────────────────────────
    all_feats   = price_feats + vol_feats
    feat_sum    = float(sum(f["contribution"] for f in all_feats))
    theory_sum  = float(sum(v["contribution"] for v in votes))
    raw_ens     = feat_sum + theory_sum
    # raw_ens is in roughly [-1, +1]; scale by 3.0 before sigmoid for sharper curve
    pUp         = round(float(_sigmoid(raw_ens * 3.0)), 3)

    # ── verdict ────────────────────────────────────────────────────────────────
    if pUp >= 0.62:
        verdict = "BUY"
    elif pUp <= 0.40:
        verdict = "AVOID"
    else:
        verdict = "HOLD"

    # ── agreement count (theories pointing up) ────────────────────────────────
    active_votes = [v for v in votes if v["weight"] > 0]
    n_theories   = len(active_votes)
    agree        = sum(1 for v in active_votes if v["bias"] > 0)

    # ── confidence: based on ensemble magnitude and bar count ─────────────────
    magnitude_conf = min(1.0, abs(raw_ens) / 0.5)          # full at |ens|=0.5
    sample_conf    = min(1.0, len(df) / 150.0)              # full at 150 bars
    theory_conf    = min(1.0, n_theories / 4.0)             # full at 4 theories
    confidence     = round(float(0.40 * magnitude_conf + 0.35 * sample_conf + 0.25 * theory_conf), 2)

    # ── realized vol (for band) ────────────────────────────────────────────────
    rv = _realized_vol(closes, n=min(w["rvol"], len(closes) - 1))

    # ── price projection band ─────────────────────────────────────────────────
    band = _compute_band(cur_close, rv, w["hz"], pUp)

    # ── read + calibration ────────────────────────────────────────────────────
    read       = _build_read(pUp, verdict, confidence, agree, n_theories, tf, band, w["hz_label"])
    calib_note = _calibration_note(len(df), n_theories, tf)

    # ── bars for chart ────────────────────────────────────────────────────────
    bars = _bar_payload(df.iloc[-w["chart"]:])

    # ── stat block ────────────────────────────────────────────────────────────
    stat = {
        "pUp":       pUp,
        "verdict":   verdict,
        "confidence": confidence,
        "agree":     agree,
        "n_theories": n_theories,
        "raw_ens":   round(float(raw_ens), 4),
        "band":      band,
        "hz_label":  w["hz_label"],
        "n_bars":    len(df),
        "rv_ann":    round(rv * 100, 1),
    }

    # ── combine features into the `features` list for JSX ────────────────────
    # Each entry: {name, value, contribution, note}
    features_out = all_feats  # price + vol, each already has the right keys

    return {
        "ok":         True,
        "source":     "real",
        "state":      "real",
        "confidence": confidence,
        "bars":       bars,
        "pUp":        pUp,
        "verdict":    verdict,
        "band":       band,
        "features":   features_out,
        "votes":      active_votes,
        "stat":       stat,
        "read":       read,
        "calibration": calib_note,
        "cur_close":  cur_close,
    }
