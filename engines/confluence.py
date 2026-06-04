"""engines/confluence.py — Confluence / Ensemble engine for the BullVeda Patterns lens.

Mechanism (principle 2): no single technical method is reliable alone; when
independent theories (context, structure, projection, timing) agree on direction
AND price, the confluence is real edge — multi-method agreement suppresses
method-specific noise and signals institutional conviction. Disagreement is an
honest warning to stand aside.

Approach: call every sibling engine on the SAME already-fetched bars (no
re-fetch), extract a normalised directional vote from each, compute a weighted
composite score, and build a confluence price map where levels from multiple
theories stack at the same price zone.

Safe subset that returns directional reads:
  wyckoff, fibonacci, volprofile, ichimoku, td, classical, candles,
  montecarlo, elliott

Each theory is wrapped in try/except — one failure cannot break the ensemble.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

NAME  = "ensemble"
LABEL = "Confluence"

# ── theory roster with per-theory weights (sum to 1.0) ──────────────────────
# Weight rationale: context/structure theories carry more weight than exhaustion
# counters (td) or distribution models (montecarlo).
_THEORY_WEIGHTS: Dict[str, float] = {
    "wyckoff":    0.18,   # context: supply/demand schematic (highest structural weight)
    "elliott":    0.16,   # structure: wave position
    "fibonacci":  0.14,   # projection: price target clusters
    "ichimoku":   0.14,   # multi-period trend alignment
    "volprofile": 0.12,   # auction: value area position
    "classical":  0.10,   # pattern: base quality
    "candles":    0.08,   # timing: recent reversal signals
    "td":         0.08,   # timing: exhaustion count
    "montecarlo": 0.10,   # simulation: path probability
}

# Display names
_THEORY_NAMES: Dict[str, str] = {
    "wyckoff":    "Wyckoff",
    "elliott":    "Elliott Wave",
    "fibonacci":  "Fibonacci",
    "ichimoku":   "Ichimoku",
    "volprofile": "Volume Profile",
    "classical":  "Classical",
    "candles":    "Candlesticks",
    "td":         "TD Sequential",
    "montecarlo": "Monte Carlo",
}

# Composite signal threshold: ensemble must clear this to be BUY/SHORT
_THRESHOLD = 60  # out of 100

# Price band tolerance for confluence map (% of price)
_BAND_PCT = 0.008   # 0.8% — levels within this band of each other are "stacked"


# ── per-theory bias extractors ──────────────────────────────────────────────
# Each returns (bias: +1/0/-1, conf: 0-1, note: str, levels: list[float])

def _bias_wyckoff(d: Dict) -> Tuple[int, float, str, List[float]]:
    # wyckoff_engine does not set state= key; check schematic presence instead
    schematic = (d.get("schematic") or "").lower()
    if not schematic or schematic == "none":
        return 0, 0.0, "no structure", []
    conf = float(d.get("confidence") or 0)
    phase = d.get("phase") or d.get("phase_label") or ""
    broke_out = bool(d.get("broke_out"))
    operator = (d.get("composite_operator") or "").upper()
    r = d.get("range") or {}
    levels = []
    if r.get("support"):
        levels.append(float(r["support"]))
    if r.get("resistance"):
        levels.append(float(r["resistance"]))
    # targets
    for t in (d.get("targets") or []):
        try:
            tp = float(str(t.get("price", "") or "").replace("$", ""))
            if tp > 0:
                levels.append(tp)
        except Exception:
            pass

    if schematic == "accumulation":
        bias = +1
        note = f"Phase {str(phase)[:12]} · ACCUMULATING" + (" · broke out" if broke_out else "")
    elif schematic == "distribution":
        bias = -1
        note = f"Phase {str(phase)[:12]} · DISTRIBUTING"
    else:
        bias = 0
        note = "schematic unclear"
    return bias, conf, note, levels


def _bias_elliott(d: Dict) -> Tuple[int, float, str, List[float]]:
    if d.get("state") != "real":
        return 0, 0.0, "no wave count", []
    bullish = bool(d.get("bullish"))
    conf = float(d.get("confidence") or 0)
    cur_wave = d.get("cur_wave") or ""
    levels = []
    for h in (d.get("hlines") or []):
        try:
            levels.append(float(h["price"]))
        except Exception:
            pass
    for t in (d.get("targets") or []):
        try:
            levels.append(float(t["price"]))
        except Exception:
            pass
    bias = +1 if bullish else -1
    note = f"{cur_wave} · {'bullish' if bullish else 'bearish'} impulse"
    return bias, conf, note, levels


def _bias_fibonacci(d: Dict) -> Tuple[int, float, str, List[float]]:
    if d.get("state") != "real":
        return 0, 0.0, "no swing", []
    conf = float(d.get("confidence") or 0)
    swing = d.get("swing") or {}
    direction = swing.get("direction", "")
    levels = []
    for lv in (d.get("levels") or []):
        try:
            levels.append(float(lv["price"]))
        except Exception:
            pass
    # golden pocket
    gp = d.get("golden_pocket") or {}
    if gp.get("lo"):
        levels.append(float(gp["lo"]))
    if gp.get("hi"):
        levels.append(float(gp["hi"]))
    if direction == "up":
        bias = +1
        note = f"up-swing · T1 {(d.get('stat') or {}).get('next_target', '—')}"
    elif direction == "down":
        bias = -1
        note = f"down-swing · support retrace"
    else:
        bias = 0
        note = "no dominant swing"
    return bias, conf, note, levels


def _bias_ichimoku(d: Dict) -> Tuple[int, float, str, List[float]]:
    if d.get("state") != "real":
        return 0, 0.0, "no ichimoku", []
    verdict = d.get("verdict") or ""
    conf = float(d.get("confidence") or 0)
    bull_count = int(d.get("bull_count") or 0)
    bear_count = int(d.get("bear_count") or 0)
    levels = []
    for h in (d.get("hlines") or []):
        try:
            levels.append(float(h["price"]))
        except Exception:
            pass
    kijun = d.get("kijun")
    if kijun:
        levels.append(float(kijun))
    tgt = (d.get("targets") or {})
    if tgt.get("kumo_target"):
        levels.append(float(tgt["kumo_target"]))

    if verdict in ("strong_bull", "bull"):
        bias = +1
        note = f"{bull_count}/5 bullish signals · TK {d.get('tk_cross','?')}"
    elif verdict in ("strong_bear", "bear"):
        bias = -1
        note = f"{bear_count}/5 bearish signals · TK {d.get('tk_cross','?')}"
    else:
        bias = 0
        note = f"mixed — {bull_count}b/{bear_count}s · inside cloud"
    return bias, conf, note, levels


def _bias_volprofile(d: Dict) -> Tuple[int, float, str, List[float]]:
    if d.get("state") != "real":
        return 0, 0.0, "no profile", []
    conf = float(d.get("confidence") or 0)
    pvs  = d.get("price_vs_va") or ""
    poc  = d.get("poc")
    vah  = d.get("vah")
    val  = d.get("val")
    levels = []
    if poc:
        levels.append(float(poc))
    if vah:
        levels.append(float(vah))
    if val:
        levels.append(float(val))
    lvn_a = d.get("lvn_above")
    lvn_b = d.get("lvn_below")
    if lvn_a:
        levels.append(float(lvn_a))
    if lvn_b:
        levels.append(float(lvn_b))

    if "above VAH" in pvs:
        bias = +1
        note = f"above VAH {vah} · auction favours continuation"
    elif "below VAL" in pvs:
        bias = -1
        note = f"below VAL {val} · auction favours decline"
    else:
        bias = 0
        note = f"inside VA · rotation play · POC {poc}"
    return bias, conf, note, levels


def _bias_classical(d: Dict) -> Tuple[int, float, str, List[float]]:
    if d.get("state") != "real":
        return 0, 0.0, "no pattern", []
    conf = float(d.get("confidence") or 0)
    pattern = d.get("pattern") or ""
    levels = []
    pivot = d.get("pivot")
    if pivot:
        try:
            levels.append(float(pivot))
        except Exception:
            pass
    target = d.get("target")
    if target:
        try:
            levels.append(float(target))
        except Exception:
            pass
    for z in (d.get("zones") or []):
        for k in ("lo", "hi"):
            try:
                levels.append(float(z[k]))
            except Exception:
                pass
    # classical is generally bullish pattern (VCP, ascending tri, etc.)
    pat_lower = pattern.lower()
    if "distribution" in pat_lower or "head" in pat_lower or "double top" in pat_lower:
        bias = -1
        note = f"{pattern[:30]} · bearish breakdown"
    elif pattern and pattern != "none":
        bias = +1
        note = f"{pattern[:30]} · base breakout"
    else:
        bias = 0
        note = "no clean base"
    return bias, conf, note, levels


def _bias_candles(d: Dict) -> Tuple[int, float, str, List[float]]:
    if d.get("state") != "real":
        return 0, 0.0, "no patterns", []
    detected = d.get("detected") or []
    if not detected:
        return 0, 0.1, "no recent candle signals", []
    # aggregate by recency (most recent = index 0 after engine sorting)
    # compute net bull/bear score from detected patterns
    bull_score = 0.0
    bear_score = 0.0
    levels = []
    for pat in detected[:4]:
        kind = pat.get("kind", "")
        c = float(pat.get("confidence") or 0)
        if "↑" in kind or kind == "Reversal ↑":
            bull_score += c
        elif "↓" in kind or kind == "Reversal ↓":
            bear_score += c
        # extract hlines
    for h in (d.get("hlines") or []):
        try:
            levels.append(float(h["price"]))
        except Exception:
            pass

    # Use mean conf of the leading pattern
    top = detected[0]
    conf = float(top.get("confidence") or 0)
    top_kind = top.get("kind", "")

    if bull_score > bear_score and bull_score > 0.3:
        bias = +1
        note = f"{top.get('name','?')} · {top_kind}"
    elif bear_score > bull_score and bear_score > 0.3:
        bias = -1
        note = f"{top.get('name','?')} · {top_kind}"
    else:
        bias = 0
        note = f"{top.get('name','?')} · indecision"
    return bias, conf, note, levels


def _bias_td(d: Dict) -> Tuple[int, float, str, List[float]]:
    if d.get("state") not in ("real", None):
        pass
    # TD tells exhaustion, not trend direction — use to moderate bias
    conf = float(d.get("confidence") or 0)
    cur = d.get("current") or {}
    direction = cur.get("direction", "none")
    phase = cur.get("phase", "none")
    count = int(cur.get("count") or 0)
    levels = []
    for h in (d.get("tdst") or []):
        try:
            levels.append(float(h["price"]))
        except Exception:
            pass

    if phase == "none" or direction == "none":
        return 0, 0.0, "no active TD count", levels

    # TD signals exhaustion in the CURRENT direction → bias opposite when near 9/13
    if direction == "sell" and count >= 7:
        # sell exhaustion → potential bullish reversal
        bias = +1
        note = f"Sell {phase} {count}/{'9' if phase=='setup' else '13'} · exhaustion → potential reversal"
    elif direction == "buy" and count >= 7:
        # buy exhaustion → potential bearish reversal
        bias = -1
        note = f"Buy {phase} {count}/{'9' if phase=='setup' else '13'} · exhaustion → potential reversal"
    elif direction == "sell" and count < 7:
        # early sell setup → trend momentum still down
        bias = -1
        note = f"Sell setup {count}/9 · building exhaustion"
        conf = conf * 0.5   # low confidence early in the count
    elif direction == "buy" and count < 7:
        bias = +1
        note = f"Buy setup {count}/9 · building exhaustion"
        conf = conf * 0.5
    else:
        bias = 0
        note = "TD neutral"
    return bias, conf, note, levels


def _bias_montecarlo(d: Dict) -> Tuple[int, float, str, List[float]]:
    if d.get("state") != "real":
        return 0, 0.0, "no simulation", []
    conf = float(d.get("confidence") or 0)
    t1_first  = float(d.get("t1First") or 0)
    stop_first = float(d.get("stopFirst") or 0)
    median = d.get("median")
    start  = d.get("start")
    t1     = d.get("t1")
    stop   = d.get("stop")

    levels = []
    if t1 is not None:
        try:
            levels.append(float(t1))
        except Exception:
            pass
    if stop is not None:
        try:
            levels.append(float(stop))
        except Exception:
            pass

    if t1_first > stop_first + 0.05:
        bias = +1
        note = f"P(T1 first) {t1_first:.0%} > P(stop) {stop_first:.0%}"
    elif stop_first > t1_first + 0.05:
        bias = -1
        note = f"P(stop first) {stop_first:.0%} > P(T1) {t1_first:.0%}"
    else:
        bias = 0
        note = f"balanced · T1 {t1_first:.0%} / stop {stop_first:.0%}"
    return bias, conf, note, levels


# ── bias extractor registry ──────────────────────────────────────────────────
_BIAS_FN = {
    "wyckoff":    _bias_wyckoff,
    "elliott":    _bias_elliott,
    "fibonacci":  _bias_fibonacci,
    "ichimoku":   _bias_ichimoku,
    "volprofile": _bias_volprofile,
    "classical":  _bias_classical,
    "candles":    _bias_candles,
    "td":         _bias_td,
    "montecarlo": _bias_montecarlo,
}


# ── level clustering: build confluence price map ─────────────────────────────
def _build_level_map(
    all_levels: Dict[str, List[float]],
    cur_close: float,
    price_range: float,
) -> List[Dict[str, Any]]:
    """Cluster price levels from all theories into stacked zones.

    Returns list of {price, sources, strength, kind} sorted by price desc.
    """
    if price_range <= 0 or cur_close <= 0:
        return []

    band = cur_close * _BAND_PCT   # absolute tolerance

    # Flatten all levels with their source labels
    flat: List[Tuple[float, str]] = []
    for method, lvs in all_levels.items():
        for lv in lvs:
            if lv > 0 and abs(lv - cur_close) / cur_close < 0.25:  # within ±25%
                flat.append((lv, _THEORY_NAMES.get(method, method)))

    if not flat:
        return []

    # Sort by price, then cluster
    flat.sort(key=lambda x: x[0])
    clusters: List[Dict[str, Any]] = []
    used = [False] * len(flat)

    for i, (price, src) in enumerate(flat):
        if used[i]:
            continue
        group_prices = [price]
        sources = [src]
        for j in range(i + 1, len(flat)):
            if used[j]:
                continue
            if abs(flat[j][0] - price) <= band:
                group_prices.append(flat[j][0])
                sources.append(flat[j][1])
                used[j] = True
        used[i] = True
        center = round(float(np.mean(group_prices)), 2)
        unique_sources = list(dict.fromkeys(sources))  # preserve order, dedupe
        strength = round(min(1.0, len(unique_sources) / 5.0), 2)  # 5 sources = 100%
        # classify
        if center > cur_close * 1.005:
            kind = "target"
        elif center < cur_close * 0.995:
            kind = "support"
        else:
            kind = "current"
        clusters.append({
            "price": center,
            "sources": unique_sources,
            "strength": strength,
            "kind": kind,
            "n": len(unique_sources),
        })

    # Sort descending (highest price first), current price near middle
    clusters.sort(key=lambda c: -c["price"])

    # Cap to top 12 entries (focus on near-term relevant levels)
    return clusters[:12]


# ── composite score ──────────────────────────────────────────────────────────
def _compute_composite(
    methods: List[Dict[str, Any]],
    weights: Dict[str, float],
) -> Dict[str, Any]:
    """Weighted composite score (0–100) and consensus tally."""
    total_w = 0.0
    score_sum = 0.0
    bull_w = 0.0
    bear_w = 0.0
    neutral_w = 0.0
    contributing = 0

    for m in methods:
        w = float(weights.get(m.get("engine", ""), weights.get(m["method"], 0)))
        if w <= 0 or not m.get("active"):
            continue
        bias = int(m["bias"])
        conf = float(m["conf"])
        # Per-method score contribution: scale conf to 0–100, direction adjusts
        # Bull: score > threshold contributes positively
        # Bear: score contribution is negative relative to center
        method_score = round(conf * 100, 1)   # 0–100
        weight_contrib = w * method_score
        score_sum += weight_contrib
        total_w += w
        if bias == +1:
            bull_w += w
        elif bias == -1:
            bear_w += w
        else:
            neutral_w += w
        contributing += 1

    if total_w <= 0:
        return {
            "score": 0, "threshold": _THRESHOLD, "contributing": 0,
            "bull_count": 0, "bear_count": 0, "neutral_count": 0,
            "bias": 0, "pct_agree": 0.0,
        }

    raw_score = round(score_sum / total_w, 1)

    # Direction: net weight of bull vs bear active methods
    if bull_w > bear_w + 0.05:
        bias = +1
    elif bear_w > bull_w + 0.05:
        bias = -1
    else:
        bias = 0

    # Agreement: fraction of active methods that share the majority direction
    majority_w = max(bull_w, bear_w, neutral_w)
    pct_agree = round(majority_w / total_w, 2) if total_w > 0 else 0.0

    # Consensus score: confidence-weighted, direction-adjusted
    # Bull composite: (bull_w / total_w) drives score up; bear drives down
    direction_mult = (bull_w - bear_w) / total_w   # -1 to +1
    composite = round(raw_score * (0.5 + 0.5 * direction_mult), 1)
    composite = max(0.0, min(100.0, composite))

    bull_count   = sum(1 for m in methods if m.get("active") and m["bias"] == +1)
    bear_count   = sum(1 for m in methods if m.get("active") and m["bias"] == -1)
    neutral_count = sum(1 for m in methods if m.get("active") and m["bias"] == 0)

    return {
        "score":          round(composite, 0),
        "threshold":      _THRESHOLD,
        "contributing":   contributing,
        "bull_count":     bull_count,
        "bear_count":     bear_count,
        "neutral_count":  neutral_count,
        "bias":           bias,
        "pct_agree":      pct_agree,
        "raw_score":      raw_score,
        "direction_mult": round(direction_mult, 3),
    }


# ── p-success proxy (based on composite + pct_agree) ────────────────────────
def _p_success(composite: Dict, methods: List[Dict]) -> float:
    """Empirical proxy for P(success): composite score × agreement × avg conf."""
    score = float(composite.get("score", 0)) / 100.0
    agree = float(composite.get("pct_agree", 0))
    active = [m for m in methods if m.get("active")]
    avg_conf = float(np.mean([m["conf"] for m in active])) if active else 0.0
    p = round(score * 0.50 + agree * 0.30 + avg_conf * 0.20, 2)
    return min(0.97, max(0.05, p))


# ── plain-English read ────────────────────────────────────────────────────────
def _build_read(composite: Dict, methods: List[Dict], cur_close: float,
                ticker: str, tf: str) -> str:
    bias = composite["bias"]
    score = composite["score"]
    bull  = composite["bull_count"]
    bear  = composite["bear_count"]
    total = composite["contributing"]
    agree = composite["pct_agree"]

    dir_word = "bullish" if bias == +1 else "bearish" if bias == -1 else "mixed"
    gate_word = "above threshold" if score >= _THRESHOLD else "below threshold"

    # find the two highest-confidence active methods
    top2 = sorted([m for m in methods if m.get("active") and m["bias"] == bias],
                  key=lambda m: -m["conf"])[:2]
    top_names = " + ".join(m["method"] for m in top2) if top2 else "—"

    return (
        f"{ticker} ({tf}): {bull}/{total} theories {dir_word} — "
        f"composite {score}/100 ({gate_word}, threshold {_THRESHOLD}), "
        f"{round(agree*100)}% agreement. "
        f"Leading: {top_names}."
    )


# ── MTF consensus placeholder (single-TF engine — fill with available) ──────
def _build_mtf(composite: Dict, tf: str) -> List[Dict]:
    """Builds a pseudo-MTF consensus row from the single-TF composite."""
    score = float(composite.get("score", 0))
    bias  = composite.get("bias", 0)
    tone  = "gn" if bias == +1 else ("rd" if bias == -1 else "ink-3")
    return [{
        "tf":    tf,
        "w":     1.0,
        "score": int(score),
        "tone":  tone,
        "note":  f"{composite['bull_count']}b/{composite['bear_count']}s/{composite['neutral_count']}n",
    }]


# ── bar payload (for the chart) ───────────────────────────────────────────────
def _bar_payload(df: pd.DataFrame, n: int = 100) -> List[Dict[str, float]]:
    sub = df.iloc[-n:] if len(df) > n else df
    out = []
    for _, r in sub.iterrows():
        rvol = float(r["rvol"]) if "rvol" in r.index and np.isfinite(r["rvol"]) else 1.0
        out.append({
            "o":  round(float(r["Open"]),  2),
            "c":  round(float(r["Close"]), 2),
            "hi": round(float(r["High"]),  2),
            "lo": round(float(r["Low"]),   2),
            "v":  round(rvol, 2),
        })
    return out


# ── stat block ────────────────────────────────────────────────────────────────
def _build_stat(composite: Dict, p_succ: float, methods: List[Dict]) -> Dict:
    active = [m for m in methods if m.get("active")]
    total  = len(active)
    aligned = sum(1 for m in active if m["bias"] == composite["bias"]) if composite["bias"] != 0 else 0
    return {
        "composite":       int(composite["score"]),
        "threshold":       _THRESHOLD,
        "theories_aligned": f"{aligned}/{total}",
        "consensus":       int(round(composite["pct_agree"] * 100)),
        "p_success":       p_succ,
        "bias":            composite["bias"],
        "contributing":    total,
        "bull_count":      composite["bull_count"],
        "bear_count":      composite["bear_count"],
    }


# ── main detect() ─────────────────────────────────────────────────────────────
def detect(df: pd.DataFrame, meta: Dict[str, Any], ticker: str) -> Dict[str, Any]:
    """Confluence / Ensemble detector.

    Imports and calls every sibling engine on the SAME df (no re-fetch).
    Returns the full payload consumed by ConfluenceView. MUST NOT raise.
    """
    tf = meta.get("tf", "Daily")
    mode = meta.get("mode", "SWING")

    if df is None or len(df) < 30:
        return {
            "ok": True, "source": "real", "state": "none",
            "message": f"Insufficient {tf.lower()} bars for ensemble ({len(df) if df is not None else 0} < 30).",
            "cur_close": None,
        }

    cur_close = round(float(df["Close"].iloc[-1]), 2)
    price_range = float(df["High"].max() - df["Low"].min())

    # ── call all sibling engines, shared df ─────────────────────────────────
    engine_results: Dict[str, Dict] = {}

    _ENGINE_MODULES = {
        "wyckoff":    "engines.wyckoff",
        "fibonacci":  "engines.fibonacci",
        "volprofile": "engines.volprofile",
        "ichimoku":   "engines.ichimoku",
        "td":         "engines.td",
        "classical":  "engines.classical",
        "candles":    "engines.candles",
        "montecarlo": "engines.montecarlo",
        "elliott":    "engines.elliott",
    }

    import importlib
    for eng_name, mod_path in _ENGINE_MODULES.items():
        try:
            mod = importlib.import_module(mod_path)
            result = mod.detect(df, meta, ticker)
            engine_results[eng_name] = result or {}
        except Exception as e:
            engine_results[eng_name] = {
                "ok": False, "state": "error",
                "message": str(e), "confidence": None,
            }

    # ── extract directional votes ────────────────────────────────────────────
    methods: List[Dict[str, Any]] = []
    all_levels: Dict[str, List[float]] = {}

    for eng_name, d in engine_results.items():
        fn = _BIAS_FN.get(eng_name)
        if fn is None:
            continue
        try:
            bias, conf, note, levels = fn(d)
        except Exception as e:
            bias, conf, note, levels = 0, 0.0, f"extractor error: {e}", []

        # wyckoff does not emit a "state" key — treat conf > 0 as the usability signal
        engine_state = d.get("state") or ""
        active = (engine_state == "real" or (not engine_state and d.get("ok") and conf > 0)) and conf > 0
        methods.append({
            "method":  _THEORY_NAMES.get(eng_name, eng_name),
            "engine":  eng_name,
            "bias":    bias,        # +1 / 0 / -1
            "conf":    round(conf, 2),
            "note":    note,
            "levels":  levels,
            "state":   d.get("state") or "none",
            "active":  active,
            "weight":  _THEORY_WEIGHTS.get(eng_name, 0.0),
            "read_snip": (d.get("read") or "")[:80],
        })
        all_levels[eng_name] = levels

    # ── composite score + consensus ──────────────────────────────────────────
    composite = _compute_composite(methods, _THEORY_WEIGHTS)
    p_succ    = _p_success(composite, methods)

    # ── confluence price map ─────────────────────────────────────────────────
    level_map = _build_level_map(all_levels, cur_close, price_range)

    # ── bars for chart ───────────────────────────────────────────────────────
    bars = _bar_payload(df, n=100)

    # hlines from the top 6 stacked levels
    hlines = []
    for lm in sorted(level_map, key=lambda x: -x["strength"])[:6]:
        tone = "gn" if lm["kind"] == "target" else ("cy" if lm["kind"] == "support" else "copper")
        hlines.append({
            "price": lm["price"],
            "label": f"{', '.join(lm['sources'][:2])} ${lm['price']:.2f} ({lm['n']} src)",
            "tone":  tone,
            "dash":  "5 4" if lm["kind"] == "target" else "4 4",
        })

    # ── stat block ───────────────────────────────────────────────────────────
    stat = _build_stat(composite, p_succ, methods)
    read = _build_read(composite, methods, cur_close, ticker, tf)

    # ── mtf row (single-TF ensemble read) ───────────────────────────────────
    mtf = _build_mtf(composite, tf)

    # Determine overall state
    active_count = sum(1 for m in methods if m.get("active"))
    state = "real" if active_count >= 3 else "none"

    # invalidation: from the strongest support level below current price
    support_levels = [lm for lm in level_map if lm["kind"] == "support"]
    inv_price = support_levels[-1]["price"] if support_levels else round(cur_close * 0.95, 2)
    inv_note  = (
        f"Close below ${inv_price:.2f} (strongest support cluster, "
        f"{len((support_levels or [{}])[-1].get('sources', [])) if support_levels else 0} theories agree) — "
        f"confluence breaks; stand aside."
    )
    if not support_levels:
        inv_note = f"No support cluster identified; invalidation estimated at -5% (${inv_price:.2f})."

    return {
        "ok":           True,
        "source":       "real",
        "state":        state,
        "confidence":   p_succ,
        "bars":         bars,
        "methods":      methods,
        "composite":    composite,
        "level_map":    level_map,
        "hlines":       hlines,
        "mtf":          mtf,
        "stat":         stat,
        "p_success":    p_succ,
        "threshold":    _THRESHOLD,
        "read":         read,
        "cur_close":    cur_close,
        "invalidation": {"price": inv_price, "note": inv_note},
        "engine_results": {k: {"state": v.get("state"), "conf": v.get("confidence")}
                           for k, v in engine_results.items()},
    }
