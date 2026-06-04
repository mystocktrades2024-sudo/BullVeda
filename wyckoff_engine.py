"""wyckoff_engine.py — rule-based Wyckoff schematic detector over REAL bars.

Mode-aware via pattern_data.get_bars: SWING=daily, POSITION=weekly,
INVEST=monthly. The detector is timeframe-agnostic — the same climax → range →
spring/SOS logic on weekly bars yields the position-horizon read.

  Accumulation:  PS → SC → AR → ST → Spring → Test → SOS → LPS → (mark-up)
  Distribution:  PSY → BC → AR → ST → UTAD → SOW → LPSY → (mark-down)

Mechanism (principle 2): a Selling Climax is the Composite Operator absorbing
panic supply on extreme effort; the Spring removes the last weak holders; the
Sign-of-Strength is the first proof demand dominates. Volume (effort) vs
spread/close (result) is the lie-detector throughout.

Honesty contract (principle 4): when no climactic base is present we return
``schematic="none"`` with a plain message rather than fabricating a count.

CLI:  python3 wyckoff_engine.py AAPL [SWING|POSITION|INVESTMENT] [--json]
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from pattern_data import fmt_date, get_bars, mode_meta, norm_mode

_LEAD = 6  # bars of context shown before the climax

# timeframe-relative search windows — a 40-bar AR window makes sense on daily
# bars but is a year and a half on weekly; everything scales with the bar size.
_TFW = {
    "Daily":   {"min": 40, "region": 160, "ar": 38, "near": 45, "fwd": 60, "test": 25, "lps": 25, "win": 120},
    "Weekly":  {"min": 28, "region": 110, "ar": 16, "near": 20, "fwd": 26, "test": 12, "lps": 12, "win": 90},
    "Monthly": {"min": 20, "region": 64,  "ar": 10, "near": 14, "fwd": 18, "test": 8,  "lps": 8,  "win": 72},
}


def _tfw(tf: str) -> dict:
    return _TFW.get(tf, _TFW["Daily"])


def _max_window(tf: str) -> int:
    return _tfw(tf)["win"]


# ════════════════════════════════════════════════════════════════════
# climax detection — the seed of the schematic
# ════════════════════════════════════════════════════════════════════
def _find_climax(df: pd.DataFrame, tf: str = "Daily") -> Optional[Dict[str, Any]]:
    w = _tfw(tf)
    n = len(df)
    if n < w["min"]:
        return None
    start = max(12, n - w["region"])
    end = n - max(3, w["ar"] // 6)
    if end - start < 10:
        return None
    region = df.iloc[start:end]
    effort = (region["rvol"].clip(upper=6) * region["spread_atr"].clip(upper=6))
    effort = effort.where(region["rvol"] >= 1.3)
    if effort.dropna().empty:
        effort = region["rvol"]
    cidx = int(np.argmax(effort.fillna(0).values)) + start
    bar = df.iloc[cidx]
    look = df.iloc[max(0, cidx - 20):cidx + 1]
    trend_into = bar["Close"] - look["Close"].iloc[0]
    is_low = trend_into < 0 or bar["Low"] <= look["Low"].min() * 1.01
    return {"idx": cidx, "is_low": bool(is_low), "rvol": float(bar["rvol"]),
            "spread_atr": float(bar["spread_atr"])}


def _rvol_lbl(v: float) -> str:
    return f"{v:.1f}× vol"


def _bar_payload(df: pd.DataFrame) -> List[Dict[str, float]]:
    out = []
    for _, r in df.iterrows():
        out.append({
            "o": round(float(r["Open"]), 2), "c": round(float(r["Close"]), 2),
            "hi": round(float(r["High"]), 2), "lo": round(float(r["Low"]), 2),
            "v": round(float(r["rvol"]) if np.isfinite(r["rvol"]) else 1.0, 2),
        })
    return out


def _px(v: float) -> int:
    return 2 if v < 30 else 0


# ════════════════════════════════════════════════════════════════════
# accumulation schematic
# ════════════════════════════════════════════════════════════════════
def _build_accumulation(df, climax, tf) -> Dict[str, Any]:
    w = _tfw(tf)
    g = max(1, w["ar"] // 13)
    sc_i = climax["idx"]
    n = len(df)
    sc = df.iloc[sc_i]
    sc_low = float(sc["Low"])

    ar_region = df.iloc[sc_i + g: min(n, sc_i + g + w["ar"])]
    if ar_region.empty:
        return {"schematic": "none"}
    ar_i = sc_i + g + int(np.argmax(ar_region["High"].values))
    resistance = float(df.iloc[ar_i]["High"])
    support = sc_low
    range_h = resistance - support
    if range_h <= 0:
        return {"schematic": "none"}

    ps_i = None
    pre = df.iloc[max(0, sc_i - max(6, w["test"])):sc_i]
    if not pre.empty:
        cand = pre[pre["rvol"] >= 1.2]
        if not cand.empty:
            ps_i = df.index.get_loc(cand.index[0])

    st_i = None
    st_region = df.iloc[ar_i + g: min(n, ar_i + g + w["near"])]
    for pos in range(len(st_region)):
        b = st_region.iloc[pos]
        gi = ar_i + g + pos
        if b["Low"] <= support + 0.4 * range_h and b["rvol"] < max(1.0, df.iloc[sc_i]["rvol"] * 0.8):
            st_i = gi
            break

    spring_i, spring_lo = None, support
    spr_start = (st_i + 1) if st_i else (ar_i + g)
    spr_region = df.iloc[spr_start: min(n, spr_start + w["fwd"])]
    for pos in range(len(spr_region)):
        b = spr_region.iloc[pos]
        gi = spr_start + pos
        if b["Low"] < support and b["Close"] > support * 0.997:
            spring_i, spring_lo = gi, float(b["Low"])
            break

    test_i = None
    if spring_i is not None:
        t_region = df.iloc[spring_i + 1: min(n, spring_i + 1 + w["test"])]
        for pos in range(len(t_region)):
            b = t_region.iloc[pos]
            gi = spring_i + 1 + pos
            if b["Low"] > spring_lo and b["rvol"] < 1.0:
                test_i = gi
                break

    sos_i = None
    sos_start = (test_i or spring_i or st_i or ar_i) + 1
    sos_region = df.iloc[sos_start: min(n, sos_start + w["fwd"])]
    for pos in range(len(sos_region)):
        b = sos_region.iloc[pos]
        gi = sos_start + pos
        if (b["Close"] > b["Open"] and b["spread_atr"] >= 1.2 and b["rvol"] >= 1.3
                and b["clv"] >= 0.6 and b["High"] >= resistance * 0.985):
            sos_i = gi
            break

    lps_i = None
    if sos_i is not None:
        l_region = df.iloc[sos_i + 1: min(n, sos_i + 1 + w["lps"])]
        for pos in range(len(l_region)):
            b = l_region.iloc[pos]
            gi = sos_i + 1 + pos
            if b["Close"] < df.iloc[sos_i]["Close"] and b["Low"] >= support + 0.5 * range_h:
                lps_i = gi
                break

    broke_out = float(df.iloc[-1]["Close"]) > resistance

    def ev(i, code, name, phase, place, tone, note, wick=None):
        b = df.iloc[i]
        d = {"abs": int(i), "code": code, "name": name, "phase": phase, "place": place,
             "tone": tone, "price": round(float(b["Close"]), 2),
             "date": fmt_date(df.index[i], tf), "note": note}
        if wick is not None:
            d["wick"] = round(float(wick), 2)
        return d

    events: List[Dict[str, Any]] = []
    if ps_i is not None and ps_i < sc_i:
        events.append(ev(ps_i, "PS", "Preliminary Support", "A", "below", "ink-2",
                         "First sizeable buying after the down-move — supply still dominant."))
    events.append(ev(sc_i, "SC", "Selling Climax", "A", "below", "gn",
                     "Panic low on extreme volume; demand appears as supply is absorbed.", wick=sc_low))
    events.append(ev(ar_i, "AR", "Automatic Rally", "A", "above", "gn",
                     "Supply exhausted; rally defines the top of the trading range."))
    if st_i is not None:
        events.append(ev(st_i, "ST", "Secondary Test", "B", "below", "gn",
                         "Re-tests the SC zone on lighter volume — supply diminishing."))
    if spring_i is not None:
        events.append(ev(spring_i, "Spring", "Spring (Shakeout)", "C", "below", "copper",
                         "Undercuts range support then snaps back inside — last supply absorbed.", wick=spring_lo))
    if test_i is not None:
        events.append(ev(test_i, "Test", "Test of Spring", "C", "below", "gn",
                         "Higher low on the lowest volume of the base — no sellers left."))
    if sos_i is not None:
        events.append(ev(sos_i, "SOS", "Sign of Strength", "D", "above", "gn",
                         "Wide-spread advance on expanding volume clears the range top."))
    if lps_i is not None:
        events.append(ev(lps_i, "LPS", "Last Point of Support", "D", "below", "gn",
                         "Pullback holds above resistance-turned-support on light volume."))

    if broke_out and sos_i is not None:
        phase, phase_label = "E", "Mark-up / trend"
    elif sos_i is not None:
        phase, phase_label = "D", "Mark-up begins"
    elif spring_i is not None:
        phase, phase_label = "C", "Test"
    elif st_i is not None:
        phase, phase_label = "B", "Building cause"
    else:
        phase, phase_label = "A", "Stopping action"

    found = sum(x is not None for x in [sc_i, ar_i, st_i, spring_i, test_i, sos_i, lps_i])
    conf = min(0.85, 0.30 + 0.075 * found + (0.05 if broke_out else 0))

    return _finalize(df, tf, "accumulation", events, support, resistance, range_h, phase,
                     phase_label, conf, sc_i, broke_out,
                     invalid_price=spring_lo if spring_i is not None else support,
                     invalid_label="Spring low" if spring_i is not None else "range support")


# ════════════════════════════════════════════════════════════════════
# distribution schematic (mirror)
# ════════════════════════════════════════════════════════════════════
def _build_distribution(df, climax, tf) -> Dict[str, Any]:
    w = _tfw(tf)
    g = max(1, w["ar"] // 13)
    bc_i = climax["idx"]
    n = len(df)
    bc_hi = float(df.iloc[bc_i]["High"])

    ar_region = df.iloc[bc_i + g: min(n, bc_i + g + w["ar"])]
    if ar_region.empty:
        return {"schematic": "none"}
    ar_i = bc_i + g + int(np.argmin(ar_region["Low"].values))
    support = float(df.iloc[ar_i]["Low"])
    resistance = bc_hi
    range_h = resistance - support
    if range_h <= 0:
        return {"schematic": "none"}

    st_i = None
    st_region = df.iloc[ar_i + g: min(n, ar_i + g + w["near"])]
    for pos in range(len(st_region)):
        b = st_region.iloc[pos]
        gi = ar_i + g + pos
        if b["High"] >= resistance - 0.4 * range_h and b["rvol"] < max(1.0, df.iloc[bc_i]["rvol"] * 0.8):
            st_i = gi
            break

    utad_i, utad_hi = None, resistance
    u_start = (st_i + 1) if st_i else (ar_i + g)
    u_region = df.iloc[u_start: min(n, u_start + w["fwd"])]
    for pos in range(len(u_region)):
        b = u_region.iloc[pos]
        gi = u_start + pos
        if b["High"] > resistance and b["Close"] < resistance * 1.003:
            utad_i, utad_hi = gi, float(b["High"])
            break

    sow_i = None
    sow_start = (utad_i or st_i or ar_i) + 1
    sow_region = df.iloc[sow_start: min(n, sow_start + w["fwd"])]
    for pos in range(len(sow_region)):
        b = sow_region.iloc[pos]
        gi = sow_start + pos
        if (b["Close"] < b["Open"] and b["spread_atr"] >= 1.2 and b["rvol"] >= 1.3
                and b["clv"] <= 0.4 and b["Low"] <= support * 1.015):
            sow_i = gi
            break

    lpsy_i = None
    if sow_i is not None:
        l_region = df.iloc[sow_i + 1: min(n, sow_i + 1 + w["lps"])]
        for pos in range(len(l_region)):
            b = l_region.iloc[pos]
            gi = sow_i + 1 + pos
            if b["Close"] > df.iloc[sow_i]["Close"] and b["High"] <= support + 0.5 * range_h:
                lpsy_i = gi
                break

    broke_down = float(df.iloc[-1]["Close"]) < support

    def ev(i, code, name, phase, place, tone, note, wick=None):
        b = df.iloc[i]
        d = {"abs": int(i), "code": code, "name": name, "phase": phase, "place": place,
             "tone": tone, "price": round(float(b["Close"]), 2),
             "date": fmt_date(df.index[i], tf), "note": note}
        if wick is not None:
            d["wick"] = round(float(wick), 2)
        return d

    events: List[Dict[str, Any]] = []
    events.append(ev(bc_i, "BC", "Buying Climax", "A", "above", "rd",
                     "Euphoric high on extreme volume; supply enters as demand is exhausted.", wick=bc_hi))
    events.append(ev(ar_i, "AR", "Automatic Reaction", "A", "below", "rd",
                     "Demand exhausted; reaction defines the bottom of the range."))
    if st_i is not None:
        events.append(ev(st_i, "ST", "Secondary Test", "B", "above", "rd",
                         "Re-tests the BC zone on lighter volume — demand diminishing."))
    if utad_i is not None:
        events.append(ev(utad_i, "UTAD", "Upthrust After Distribution", "C", "above", "copper",
                         "Pokes above resistance then fails back inside — last demand trapped.", wick=utad_hi))
    if sow_i is not None:
        events.append(ev(sow_i, "SOW", "Sign of Weakness", "D", "below", "rd",
                         "Wide-spread decline on expanding volume breaks the range floor."))
    if lpsy_i is not None:
        events.append(ev(lpsy_i, "LPSY", "Last Point of Supply", "D", "above", "rd",
                         "Feeble rally fails below resistance — supply in control."))

    if broke_down and sow_i is not None:
        phase, phase_label = "E", "Mark-down / trend"
    elif sow_i is not None:
        phase, phase_label = "D", "Mark-down begins"
    elif utad_i is not None:
        phase, phase_label = "C", "Test"
    elif st_i is not None:
        phase, phase_label = "B", "Building cause"
    else:
        phase, phase_label = "A", "Stopping action"

    found = sum(x is not None for x in [bc_i, ar_i, st_i, utad_i, sow_i, lpsy_i])
    conf = min(0.85, 0.30 + 0.085 * found + (0.05 if broke_down else 0))

    return _finalize(df, tf, "distribution", events, support, resistance, range_h, phase,
                     phase_label, conf, bc_i, broke_down,
                     invalid_price=utad_hi if utad_i is not None else resistance,
                     invalid_label="UTAD high" if utad_i is not None else "range resistance")


# ════════════════════════════════════════════════════════════════════
# finalize — window, phases, targets, effort, stat
# ════════════════════════════════════════════════════════════════════
def _finalize(df, tf, schematic, events, support, resistance, range_h, phase, phase_label,
              conf, climax_i, broke, invalid_price, invalid_label) -> Dict[str, Any]:
    n = len(df)
    accum = schematic == "accumulation"

    w_start = max(0, climax_i - _LEAD)
    if n - w_start > _max_window(tf):
        w_start = n - _max_window(tf)
    win = df.iloc[w_start:]
    bars = _bar_payload(win)

    win_events = []
    for e in events:
        ri = int(e["abs"] - w_start)
        if 0 <= ri < len(bars):
            ee = dict(e)
            ee["i"] = ri
            ee.pop("abs", None)
            win_events.append(ee)

    phase_order = ["A", "B", "C", "D", "E"]
    if accum:
        phase_names = {"A": "Stopping action", "B": "Building cause", "C": "Test",
                       "D": "Mark-up begins", "E": "Trend"}
        phase_notes = {"A": "PS · SC · AR — the down-move is halted",
                       "B": "ST · ranging — cause accumulates",
                       "C": "Spring + Test — supply removed",
                       "D": "SOS · LPS — demand in control",
                       "E": "Mark-up out of the range"}
    else:
        phase_names = {"A": "Stopping action", "B": "Building cause", "C": "Test",
                       "D": "Mark-down begins", "E": "Trend"}
        phase_notes = {"A": "PSY · BC · AR — the up-move is halted",
                       "B": "ST · ranging — cause distributes",
                       "C": "UTAD — demand trapped",
                       "D": "SOW · LPSY — supply in control",
                       "E": "Mark-down out of the range"}

    first_of: Dict[str, int] = {}
    for e in win_events:
        first_of.setdefault(e["phase"], e["i"])
    cur_idx = phase_order.index(phase)
    phases = []
    for k, p in enumerate(phase_order):
        if phase_order.index(p) > cur_idx and p not in first_of:
            continue
        nxt = None
        for q in phase_order[k + 1:]:
            if q in first_of:
                nxt = first_of[q]
                break
        start_i = first_of.get(p, 0 if p == "A" else None)
        if start_i is None:
            continue
        end_i = (nxt - 1) if nxt is not None else (len(bars) - 1)
        phases.append({
            "id": p, "label": f"{p} · {phase_names[p]}",
            "from": int(max(0, start_i)), "to": int(min(len(bars) - 1, max(start_i, end_i))),
            "done": phase_order.index(p) < cur_idx, "current": p == phase, "note": phase_notes[p],
        })

    cur_close = float(df.iloc[-1]["Close"])
    targets = []
    sign = 1 if accum else -1
    base = resistance if accum else support
    for lbl, mult, tone in [("T1 · conservative", 1.0, "gn" if accum else "rd"),
                            ("T2 · measured", 1.6, "gn" if accum else "rd"),
                            ("T3 · full count", 2.0, "amb")]:
        px = base + sign * range_h * mult
        rr = (px / cur_close - 1) * 100 if accum else (1 - px / cur_close) * 100
        targets.append({"label": lbl, "basis": f"range height ({range_h:.1f}) × {mult:.1f} {'above' if accum else 'below'} {base:.1f}",
                        "price": f"{px:.{_px(px)}f}", "rr": f"{'+' if accum else '-'}{abs(rr):.1f}%",
                        "conf": round(conf * (1 - 0.18 * len(targets)), 2), "tone": tone})

    effort = []
    for e in win_events:
        if e["code"] in ("PS", "LPS", "LPSY"):
            continue
        b = df.iloc[w_start + e["i"]]
        up = b["Close"] >= b["Open"]
        spread_desc = "wide" if b["spread_atr"] >= 1.3 else "narrow" if b["spread_atr"] < 0.8 else "avg"
        close_desc = "closes high" if b["clv"] >= 0.66 else "closes low" if b["clv"] <= 0.33 else "closes mid"
        read = {"SC": "Demand absorbs climactic supply", "BC": "Supply absorbs climactic demand",
                "AR": "Auto-reaction defines the range", "ST": "Test on diminishing effort",
                "Spring": "Effort to push down → no result", "UTAD": "Effort to push up → no result",
                "SOS": "Effort = result — markup confirmed", "SOW": "Effort = result — markdown confirmed",
                "Test": "No supply on the reaction"}.get(e["code"], "")
        effort.append({"ev": e["code"], "name": e["name"], "effort": _rvol_lbl(float(b["rvol"])),
                       "result": f"{spread_desc} {'▲' if up else '▼'}, {close_desc}", "read": read, "tone": e["tone"]})

    operator = "ACCUMULATING" if accum else "DISTRIBUTING"
    stat = {"schematic": "Accumulation" if accum else "Distribution",
            "phase": f"{phase} · {phase_label.lower()}", "range": f"{support:.{_px(support)}f} – {resistance:.{_px(resistance)}f}",
            "operator": operator, "confidence": round(conf, 2)}

    invalidation = {
        "price": round(float(invalid_price), 2),
        "note": (f"Close back below the {invalid_label} ${invalid_price:.2f} — re-distribution risk, stand aside."
                 if accum else
                 f"Close back above the {invalid_label} ${invalid_price:.2f} — re-accumulation risk, cover shorts."),
    }

    return {
        "schematic": schematic, "phase": phase, "phase_label": phase_label,
        "confidence": round(conf, 2), "composite_operator": operator,
        "range": {"support": round(support, 2), "resistance": round(resistance, 2), "height": round(range_h, 2)},
        "bars": bars, "n_real": len(bars), "cur_close": round(cur_close, 2),
        "events": win_events, "phases": phases, "targets": targets, "effort": effort,
        "invalidation": invalidation, "stat": stat, "broke_out": bool(broke),
    }


# ════════════════════════════════════════════════════════════════════
# core: detect from a pre-enriched df  +  public entry
# ════════════════════════════════════════════════════════════════════
def detect_from_df(df: pd.DataFrame, meta: Dict[str, Any], ticker: str = "") -> Dict[str, Any]:
    """Core detector on a pre-enriched bar frame (df from pattern_data.get_bars)."""
    tf = (meta or {}).get("tf", "Daily")
    base = {"ticker": ticker, "ok": False, "schematic": "none", "source": "real"}
    if df is None or len(df) < _tfw(tf)["min"]:
        return {**base, "ok": True, "message": f"Not enough {tf.lower()} bars for a Wyckoff read."}
    climax = _find_climax(df, tf)
    if climax is None:
        return {**base, "ok": True,
                "message": f"No climactic base on the {tf.lower()} — price is trending or unstructured.",
                "cur_close": round(float(df.iloc[-1]["Close"]), 2)}
    try:
        res = _build_accumulation(df, climax, tf) if climax["is_low"] else _build_distribution(df, climax, tf)
    except Exception as e:  # pragma: no cover
        return {**base, "ok": True, "message": f"Detector error: {e}"}
    if res.get("schematic") in (None, "none") or not res.get("events"):
        return {**base, "ok": True,
                "message": "Climax found but no developed range — structure too weak to label.",
                "cur_close": round(float(df.iloc[-1]["Close"]), 2)}
    res.update({"ticker": ticker, "ok": True, "source": "real"})
    return res


def detect_wyckoff(ticker: str, mode: str = "SWING") -> Dict[str, Any]:
    """Fetch real bars at the mode timeframe and return a Wyckoff read."""
    ticker = (ticker or "").upper().strip()
    mode = norm_mode(mode)
    if not ticker:
        return {"ticker": ticker, "ok": False, "schematic": "none", "source": "real", "message": "No ticker."}
    df, tier, meta = get_bars(ticker, mode)
    if df is None:
        return {"ticker": ticker, "ok": False, "schematic": "none", "source": "real",
                "message": f"No {meta['tf'].lower()} OHLCV available ({tier}).", "tier": tier, "meta": meta}
    out = detect_from_df(df, meta, ticker)
    out["tier"] = tier
    out["meta"] = meta
    return out


if __name__ == "__main__":  # pragma: no cover
    import json
    import sys
    sym = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    mode = "SWING"
    for a in sys.argv[2:]:
        if a.upper() in ("SWING", "POSITION", "INVEST", "INVESTMENT"):
            mode = a.upper()
    out = detect_wyckoff(sym, mode)
    print(f"\n=== Wyckoff · {sym} · {norm_mode(mode)} ({out.get('meta', {}).get('tf')}) ===")
    print(f"schematic={out.get('schematic')} phase={out.get('phase')} conf={out.get('confidence')} "
          f"tier={out.get('tier')} events={len(out.get('events', []))} bars={out.get('n_real')}")
    if out.get("message"):
        print("message:", out["message"])
    for e in out.get("events", []):
        print(f"  i={e['i']:>3} {e['code']:<6} {e['date']:<8} ${e['price']:<9} ph={e['phase']} :: {e['name']}")
    if out.get("stat"):
        print("stat:", out["stat"])
    if "--json" in sys.argv:
        print(json.dumps(out, indent=2))
