#!/usr/bin/env python3
"""real_buy_gate.py — single source of truth for the LIVE "real buy" verdict.

Both the CLI validator (schwab_real_buy_validator.py) and the Screener-Desks pipeline
(screener_desks._tag → desk cards) call `evaluate()` so the gate never drifts between
the two surfaces. It re-decides a candidate off LIVE signals (price vs live EMA stack,
live RSI/ADX, time-adjusted RVOL, today's move, halt) cross-checked against the scan's
bias / bear-score / ATR entry-zone and the desk's *validated* forward-edge tier.

Verdicts:
  REAL BUY   — live-bullish, in/near zone, real participation, clean momentum
  MARGINAL   — bullish but one soft flaw (thin RVOL, weak ADX, extended, unproven desk)
  UNVERIFIED — no live EMA structure to confirm (missing cached history)
  NOT REAL   — hard fail: halted, bearish/AVOID, below live EMA21, dumping, broken RSI

Thresholds live in config.json → "real_buy_gate" (tune there; defaults below).
"""
from __future__ import annotations

import json
from pathlib import Path

_BASE = Path(__file__).parent
_CFG_CACHE = None

_DEFAULTS = {
    "rvol_hard": 0.50,     # below = no participation (hard fail)
    "rvol_soft": 0.80,     # below = thin (soft)
    "rsi_floor": 40.0,     # below = momentum broken (hard fail)
    "rsi_blowoff": 82.0,   # above = blow-off (soft)
    "adx_min": 15.0,       # below = no trend (soft)
    "ext_atr_zone": 1.0,   # within N ATR above EMA21 = in zone
    "ext_atr_max": 1.8,    # beyond N ATR above EMA21 = extended (soft)
    "dump_pct": -3.0,      # down more than this today = hard fail
    "below_atr": 0.4,      # below EMA21 by > N ATR = broken structure (hard fail)
    "bear_hard": 0.60,     # bear sub-score ratio >= this = hard fail
    "bear_soft": 0.47,     # bear sub-score ratio >= this = soft flag
}

# desk key -> forward-edge tier (from cache/desk_edge_stats.json + track record)
DESK_EDGE_TIER = {
    "pb": "validated", "mr": "validated",
    "mom": "marginal", "qf": "marginal",
    "val": "unmeasured", "qual": "unmeasured",
    "smart": "no_edge", "bo": "no_edge", "cat": "no_edge",
    "def": "no_edge", "short": "no_edge",
}
_EDGE_DESC = {
    "pb": "Pullback PF-haircut 1.38 (n=2699)", "mr": "Mean-Rev PF-haircut 1.12 (n=1342)",
    "mom": "Momentum PF-haircut ~1.02", "qf": "Quant PF-haircut ~0.99",
    "val": "Value n=0 backtest — UNPROVEN", "qual": "Quality n=0 backtest — UNPROVEN",
    "smart": "Smart-Money FAILED PF-haircut 0.41", "bo": "Breakout FAILED PF-haircut 0.79",
    "cat": "Catalyst FAILED PF-haircut 0.75", "def": "Defensive FAILED PF-haircut 0.14",
    "short": "Short (not a long desk)",
}


def _cfg():
    global _CFG_CACHE
    if _CFG_CACHE is None:
        c = dict(_DEFAULTS)
        try:
            raw = json.loads((_BASE / "config" / "config.json").read_text())
            blk = raw.get("real_buy_gate") or {}
            for k in _DEFAULTS:
                if isinstance(blk.get(k), (int, float)):
                    c[k] = float(blk[k])
        except Exception:
            pass
        _CFG_CACHE = c
    return _CFG_CACHE


def _f(x, d=None):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def evaluate(sig, desk_edge_tier=None):
    """sig: normalized signal dict. Keys (all optional; missing → check skipped):
      price, ema8, ema21, ema50, rsi, adx, live_rvol, atr_pct, net_pct,
      bias (str), bear_ratio (0..1), scan_action (str), reason_class (str),
      entry_quality (str), rs, sharpe, status (str), ema_stack_bull (bool)
    Returns: {verdict, tier, fails[], warns[], ext_atr_vs_ema21, edge_tier, edge_desc}
    """
    t = _cfg()
    fails, warns = [], []
    price = _f(sig.get("price"))
    ema21 = _f(sig.get("ema21"))
    ema8, ema50 = _f(sig.get("ema8")), _f(sig.get("ema50"))
    rsi, adx = _f(sig.get("rsi")), _f(sig.get("adx"))
    rvol = _f(sig.get("live_rvol"))
    atr_pct = _f(sig.get("atr_pct"), 2.0) or 2.0
    net_pct = _f(sig.get("net_pct"))
    bias = str(sig.get("bias") or "").lower()
    bear_ratio = _f(sig.get("bear_ratio"))
    scan_action = str(sig.get("scan_action") or "").upper()
    reason_class = str(sig.get("reason_class") or "").lower()
    entry_q = str(sig.get("entry_quality") or "").upper()
    rs = _f(sig.get("rs"))
    sharpe = _f(sig.get("sharpe"))
    status = str(sig.get("status") or "").lower()
    edge_tier = desk_edge_tier or "unknown"
    edge_desc = ""

    # ---- HARD gates ----
    if status and any(k in status for k in ("halt", "news pending", "deleted")):
        fails.append(f"halted/untradable ({status})")
    if bias == "bearish" or reason_class == "bear_setup" or scan_action in ("AVOID", "SHORT") \
            or (bear_ratio is not None and bear_ratio >= t["bear_hard"]):
        why = f"bias={bias or '?'}"
        if scan_action in ("AVOID", "SHORT"):
            why += f", scan={scan_action}"
        if bear_ratio is not None and bear_ratio >= t["bear_hard"]:
            why += f", bear {bear_ratio*15:.0f}/15"
        fails.append(f"bearish read ({why})")
    ext_atr = None
    if price and ema21:
        ext_atr = ((price - ema21) / price * 100.0) / max(atr_pct, 0.5)
        if ext_atr < -t["below_atr"]:
            fails.append(f"price {((price-ema21)/ema21*100):+.1f}% BELOW live EMA21 — broken structure")
    if net_pct is not None and net_pct < t["dump_pct"]:
        fails.append(f"dumping today {net_pct:+.1f}%")
    if rvol is not None and rvol < t["rvol_hard"]:
        fails.append(f"no participation (live RVOL {rvol:.2f})")
    if rsi is not None and rsi < t["rsi_floor"]:
        fails.append(f"momentum broken (live RSI {rsi:.0f})")

    # ---- SOFT gates (REAL -> MARGINAL) ----
    if ext_atr is not None and ext_atr > t["ext_atr_max"]:
        warns.append(f"EXTENDED: {ext_atr:.1f} ATR above EMA21 (chasing)")
    elif entry_q in ("EXTENDED", "MISSED"):
        warns.append(f"entry_quality={entry_q}")
    stack_bull = sig.get("ema_stack_bull")
    if stack_bull is None and ema8 and ema21 and ema50:
        stack_bull = ema8 >= ema21 >= ema50
    if stack_bull is False:
        warns.append("EMA stack not fully bullish (8/21/50)")
    if rvol is not None and t["rvol_hard"] <= rvol < t["rvol_soft"]:
        warns.append(f"thin participation (live RVOL {rvol:.2f})")
    if adx is not None and adx < t["adx_min"]:
        warns.append(f"weak trend (live ADX {adx:.0f})")
    if rsi is not None and rsi > t["rsi_blowoff"]:
        warns.append(f"blow-off (live RSI {rsi:.0f})")
    if bear_ratio is not None and t["bear_soft"] <= bear_ratio < t["bear_hard"]:
        warns.append(f"elevated bear score {bear_ratio*15:.0f}/15")
    if edge_tier == "no_edge":
        edge_desc = _EDGE_DESC.get(sig.get("desk"), "")
        warns.append(f"desk has NO validated edge{(' — ' + edge_desc) if edge_desc else ''}")
    elif edge_tier == "unmeasured":
        edge_desc = _EDGE_DESC.get(sig.get("desk"), "")
        warns.append(f"desk UNPROVEN (n=0 backtest){(' — ' + edge_desc) if edge_desc else ''}")
    if rs is not None and rs < 40:
        warns.append(f"weak RS rank {rs:.0f}")
    if sharpe is not None and sharpe < 0:
        warns.append(f"negative 126d Sharpe {sharpe:.2f}")

    # ---- verdict ----
    live_unverifiable = price is None or ema21 is None
    if fails:
        verdict = "NOT REAL"
    elif live_unverifiable:
        verdict = "UNVERIFIED"
    elif warns:
        verdict = "MARGINAL"
    else:
        verdict = "REAL BUY"
    tier = ""
    if verdict == "REAL BUY":
        tier = "STRONG" if edge_tier == "validated" else "LIVE-CONFIRMED"

    return {
        "verdict": verdict, "tier": tier, "edge_tier": edge_tier, "edge_desc": edge_desc,
        "ext_atr_vs_ema21": round(ext_atr, 2) if ext_atr is not None else None,
        "fails": fails, "warns": warns,
    }
