"""engines/td.py — TD Sequential detector for the BullVeda Patterns lens.

Mechanism (principle 2): DeMark's TD Sequential counts exhaustion — a completed
9-setup or 13-countdown marks where a trend has run out of incremental
buyers/sellers, flagging mean-reversion risk at price zones where prior
exhaustion counts coincide (TDST). The count is an ordinal clock, not a price
pattern; it fires ONLY when the defined comparison bar offset is met strictly.

Honesty contract (principle 4): returns state="none" when fewer than 14 bars
exist or there is no active / recently completed setup or countdown.

CLI:
  python3 -c "import pattern_engines as pe; d=pe.detect('td','AAPL','SWING');
              print({k:(len(v) if isinstance(v,list) else v) for k,v in d.items() if k!='bars'})"
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from pattern_data import fmt_date, mode_meta, norm_mode

NAME = "td"
LABEL = "TD Sequential"

# ────────────────────────────────────────────────────────────────────────────
# timeframe-relative window sizes
# ────────────────────────────────────────────────────────────────────────────
_TFW = {
    "Daily":   {"bars": 100, "lookback": 80},
    "Weekly":  {"bars": 100, "lookback": 80},
    "Monthly": {"bars": 80,  "lookback": 64},
}


def _tfw(tf: str) -> dict:
    return _TFW.get(tf, _TFW["Daily"])


# ────────────────────────────────────────────────────────────────────────────
# Classic DeMark TD Setup engine
# ────────────────────────────────────────────────────────────────────────────
def _compute_td(df: pd.DataFrame) -> pd.DataFrame:
    """Add td_buy, td_sell, td_cd_buy, td_cd_sell columns to df in one pass.

    td_buy  : 1–9 for each bar in a consecutive buy-setup run, else 0
    td_sell : 1–9 for each bar in a consecutive sell-setup run, else 0
    td_cd_buy / td_cd_sell: countdown 1–13, else 0
    """
    n = len(df)
    closes = df["Close"].values
    highs  = df["High"].values
    lows   = df["Low"].values

    td_buy  = np.zeros(n, dtype=int)
    td_sell = np.zeros(n, dtype=int)

    buy_count  = 0
    sell_count = 0

    # We need close[i] vs close[i-4]: start at bar 4
    for i in range(4, n):
        c    = closes[i]
        c_4  = closes[i - 4]
        if c < c_4:
            buy_count  = min(buy_count + 1, 9)
            sell_count = 0
        elif c > c_4:
            sell_count = min(sell_count + 1, 9)
            buy_count  = 0
        else:
            # equal — neither side continues (strict DeMark rule)
            buy_count  = 0
            sell_count = 0
        td_buy[i]  = buy_count
        td_sell[i] = sell_count

    # ── Countdown: triggered after a completed 9-setup ───────────────────────
    # Buy Countdown: close ≤ low[i-2]  (after buy setup 9 completes)
    # Sell Countdown: close ≥ high[i-2] (after sell setup 9 completes)
    td_cd_buy  = np.zeros(n, dtype=int)
    td_cd_sell = np.zeros(n, dtype=int)

    buy_cd  = 0  # 0 = inactive
    sell_cd = 0

    for i in range(2, n):
        # Did we just COMPLETE a 9-setup this bar?
        if td_buy[i] == 9:
            buy_cd  = 0  # reset / start fresh countdown
            sell_cd = 0  # cancel any opposing countdown

        if td_sell[i] == 9:
            sell_cd = 0
            buy_cd  = 0

        # Advance countdown if active (< 13)
        if buy_cd > 0 and buy_cd < 13:
            if closes[i] <= lows[i - 2]:
                buy_cd = min(buy_cd + 1, 13)
            td_cd_buy[i] = buy_cd

        if sell_cd > 0 and sell_cd < 13:
            if closes[i] >= highs[i - 2]:
                sell_cd = min(sell_cd + 1, 13)
            td_cd_sell[i] = sell_cd

        # After a completed 9-setup, arm the countdown on the NEXT bar
        if i > 0 and td_buy[i - 1] == 9 and buy_cd == 0:
            buy_cd = 1
        if i > 0 and td_sell[i - 1] == 9 and sell_cd == 0:
            sell_cd = 1

    # ── Second pass to capture bar-after-setup initialisation properly ───────
    # Re-run countdown state machine cleanly (two-state machine, one pass is
    # enough but the initialisation above mixes i and i-1 reads — redo clearly).
    buy_cd  = 0
    sell_cd = 0
    td_cd_buy  = np.zeros(n, dtype=int)
    td_cd_sell = np.zeros(n, dtype=int)

    for i in range(2, n):
        # If PREVIOUS bar completed a 9, arm the countdown
        if i >= 1 and td_buy[i - 1] == 9:
            buy_cd  = 1
            sell_cd = 0
        if i >= 1 and td_sell[i - 1] == 9:
            sell_cd = 1
            buy_cd  = 0

        # Advance if conditions met
        if 1 <= buy_cd < 13:
            if closes[i] <= lows[i - 2]:
                buy_cd += 1
        if 1 <= sell_cd < 13:
            if closes[i] >= highs[i - 2]:
                sell_cd += 1

        td_cd_buy[i]  = buy_cd  if buy_cd  >= 1 else 0
        td_cd_sell[i] = sell_cd if sell_cd >= 1 else 0

        # Cap at 13
        buy_cd  = min(buy_cd,  13)
        sell_cd = min(sell_cd, 13)

        # Reset if opposing setup fires
        if td_buy[i] == 9:
            sell_cd = 0
        if td_sell[i] == 9:
            buy_cd = 0

    df2 = df.copy()
    df2["td_buy"]    = td_buy
    df2["td_sell"]   = td_sell
    df2["td_cd_buy"] = td_cd_buy
    df2["td_cd_sell"] = td_cd_sell
    return df2


# ────────────────────────────────────────────────────────────────────────────
# Perfection check (DeMark classic rules)
# ────────────────────────────────────────────────────────────────────────────
def _is_perfected_buy(df: pd.DataFrame, setup_end_i: int) -> bool:
    """Bar-8 or bar-9 low ≤ bar-6 and bar-7 lows."""
    if setup_end_i < 9:
        return False
    lows = df["Low"].values
    lo_8 = lows[setup_end_i - 1]
    lo_9 = lows[setup_end_i]
    lo_6 = lows[setup_end_i - 3]
    lo_7 = lows[setup_end_i - 2]
    return bool(lo_8 <= lo_6 and lo_8 <= lo_7) or bool(lo_9 <= lo_6 and lo_9 <= lo_7)


def _is_perfected_sell(df: pd.DataFrame, setup_end_i: int) -> bool:
    """Bar-8 or bar-9 high ≥ bar-6 and bar-7 highs."""
    if setup_end_i < 9:
        return False
    highs = df["High"].values
    hi_8 = highs[setup_end_i - 1]
    hi_9 = highs[setup_end_i]
    hi_6 = highs[setup_end_i - 3]
    hi_7 = highs[setup_end_i - 2]
    return bool(hi_8 >= hi_6 and hi_8 >= hi_7) or bool(hi_9 >= hi_6 and hi_9 >= hi_7)


# ────────────────────────────────────────────────────────────────────────────
# TDST levels: support = lowest low of buy-setup; resistance = highest high
# ────────────────────────────────────────────────────────────────────────────
def _compute_tdst(df: pd.DataFrame) -> Tuple[Optional[float], Optional[float]]:
    """Return (tdst_support, tdst_resistance) from the most recent completed
    buy-setup 9 and sell-setup 9 within the frame, respectively."""
    n = len(df)
    lows  = df["Low"].values
    highs = df["High"].values
    buy   = df["td_buy"].values
    sell  = df["td_sell"].values

    tdst_support    = None
    tdst_resistance = None

    # Walk backwards to find most-recent completed setups
    i = n - 1
    while i >= 9 and (tdst_support is None or tdst_resistance is None):
        if buy[i] == 9 and tdst_support is None:
            # Low of bars 1–9 of this setup (9 bars ending at i)
            tdst_support = float(np.min(lows[i - 8: i + 1]))
        if sell[i] == 9 and tdst_resistance is None:
            tdst_resistance = float(np.max(highs[i - 8: i + 1]))
        i -= 1

    return tdst_support, tdst_resistance


# ────────────────────────────────────────────────────────────────────────────
# Bar payload for the chart (windowed to last ~100 bars)
# ────────────────────────────────────────────────────────────────────────────
def _bar_payload(df: pd.DataFrame) -> List[Dict[str, float]]:
    out = []
    for _, r in df.iterrows():
        rvol = float(r["rvol"]) if np.isfinite(float(r.get("rvol", 1.0))) else 1.0
        out.append({
            "o":  round(float(r["Open"]),  2),
            "c":  round(float(r["Close"]), 2),
            "hi": round(float(r["High"]),  2),
            "lo": round(float(r["Low"]),   2),
            "v":  round(rvol, 2),
        })
    return out


# ────────────────────────────────────────────────────────────────────────────
# Build the per-bar markers list for the chart
# Only milestone bars are labelled to keep the chart legible:
#   Setup:    bars 1, 5, 9 (and any in-progress last bar)
#   Countdown: bars 1, 7, 13 (and any in-progress last bar)
# The completed-9 / completed-13 bar always gets the checkmark.
# ────────────────────────────────────────────────────────────────────────────
_SETUP_SHOW    = {1, 5, 9}
_COUNTDOWN_SHOW = {1, 7, 13}


def _build_markers(df_win: pd.DataFrame, offset: int) -> List[Dict[str, Any]]:
    """Produce {i, label, tone, place} for milestone TD bars.

    Rules:
    - Setup: show bars 1, 5, and the FIRST bar the count reaches 9.
    - Countdown: show bars 1, 7, and the FIRST bar the count reaches 13.
    - Always label the last bar in the window if it has any active count.
    """
    markers = []
    n = len(df_win)
    buy  = df_win["td_buy"].values
    sell = df_win["td_sell"].values
    cd_b = df_win["td_cd_buy"].values
    cd_s = df_win["td_cd_sell"].values
    last = n - 1

    # Track whether we already placed the "9-complete" / "13-complete" marker
    # for the current run, to avoid repeating it across consecutive identical bars.
    emitted_b9 = False
    emitted_s9 = False
    emitted_bc13 = False
    emitted_sc13 = False

    for idx in range(n):
        b, s, cb, cs = int(buy[idx]), int(sell[idx]), int(cd_b[idx]), int(cd_s[idx])
        is_last = (idx == last)

        # Reset emission flags when the run ends
        if b == 0:
            emitted_b9 = False
        if s == 0:
            emitted_s9 = False
        if cb == 0:
            emitted_bc13 = False
        if cs == 0:
            emitted_sc13 = False

        label = None
        tone  = "ink-3"
        place = "below"

        if b > 0:
            if b == 9 and not emitted_b9:
                label, tone, place = "B9✓", "gn", "below"
                emitted_b9 = True
            elif b in _SETUP_SHOW and b < 9:
                label, tone, place = f"B{b}", "cy", "below"
            elif is_last and label is None:
                label, tone, place = f"B{b}", "cy", "below"
        elif s > 0:
            if s == 9 and not emitted_s9:
                label, tone, place = "S9✓", "rd", "above"
                emitted_s9 = True
            elif s in _SETUP_SHOW and s < 9:
                label, tone, place = f"S{s}", "amb", "above"
            elif is_last and label is None:
                label, tone, place = f"S{s}", "amb", "above"
        elif cb > 0:
            if cb == 13 and not emitted_bc13:
                label, tone, place = "BC13✓", "cy", "below"
                emitted_bc13 = True
            elif cb in _COUNTDOWN_SHOW and cb < 13:
                label, tone, place = f"BC{cb}", "ink-2", "below"
            elif is_last and label is None:
                label, tone, place = f"BC{cb}", "ink-2", "below"
        elif cs > 0:
            if cs == 13 and not emitted_sc13:
                label, tone, place = "SC13✓", "rd", "above"
                emitted_sc13 = True
            elif cs in _COUNTDOWN_SHOW and cs < 13:
                label, tone, place = f"SC{cs}", "ink-2", "above"
            elif is_last and label is None:
                label, tone, place = f"SC{cs}", "ink-2", "above"

        if label:
            markers.append({"i": idx, "label": label, "tone": tone, "place": place})

    return markers


# ────────────────────────────────────────────────────────────────────────────
# Human-readable state string
# ────────────────────────────────────────────────────────────────────────────
def _current_state(df: pd.DataFrame, tf: str) -> Dict[str, Any]:
    """Inspect the last bar and recent history to build the current state dict."""
    n = len(df)
    last = df.iloc[-1]
    buy   = int(last["td_buy"])
    sell  = int(last["td_sell"])
    cd_b  = int(last["td_cd_buy"])
    cd_s  = int(last["td_cd_sell"])

    state_str   = "none"
    phase       = "none"
    count       = 0
    direction   = "none"
    rule        = "—"
    tone        = "ink-3"
    timing      = "no exhaustion signal"

    if sell > 0:
        direction = "sell"
        count     = sell
        phase     = "setup"
        rule      = "close > close[−4]"
        tone      = "rd" if sell == 9 else "amb"
        state_str = f"Sell Setup {sell} of 9"
        timing    = "exhaustion near" if sell >= 8 else "building"
    elif buy > 0:
        direction = "buy"
        count     = buy
        phase     = "setup"
        rule      = "close < close[−4]"
        tone      = "gn" if buy == 9 else "cy"
        state_str = f"Buy Setup {buy} of 9"
        timing    = "exhaustion near" if buy >= 8 else "building"
    elif cd_s > 0:
        direction = "sell"
        count     = cd_s
        phase     = "countdown"
        rule      = "close ≥ high[−2]"
        tone      = "rd" if cd_s >= 11 else "amb"
        state_str = f"Sell Countdown {cd_s} of 13"
        timing    = "countdown complete" if cd_s == 13 else "exhaustion building"
    elif cd_b > 0:
        direction = "buy"
        count     = cd_b
        phase     = "countdown"
        rule      = "close ≤ low[−2]"
        tone      = "gn" if cd_b >= 11 else "cy"
        state_str = f"Buy Countdown {cd_b} of 13"
        timing    = "countdown complete" if cd_b == 13 else "exhaustion building"

    # Perfection — only relevant for completed setups
    perfected = False
    if phase == "setup" and count == 9:
        end_i = n - 1
        if direction == "buy":
            perfected = _is_perfected_buy(df, end_i)
        else:
            perfected = _is_perfected_sell(df, end_i)

    # Look back for recently completed setup
    ladder = _build_ladder(df)

    return {
        "state_str": state_str,
        "phase":     phase,
        "direction": direction,
        "count":     count,
        "rule":      rule,
        "perfected": perfected,
        "tone":      tone,
        "timing":    timing,
        "ladder":    ladder,
    }


# ────────────────────────────────────────────────────────────────────────────
# Build the sequence ladder (timeline of completed/active phases)
# ────────────────────────────────────────────────────────────────────────────
def _build_ladder(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Walk backwards through df to find up to 4 recent setup/countdown events."""
    n = len(df)
    buy  = df["td_buy"].values
    sell = df["td_sell"].values
    cd_b = df["td_cd_buy"].values
    cd_s = df["td_cd_sell"].values

    events = []
    seen_cd_buy  = False
    seen_cd_sell = False
    seen_9_buy   = False
    seen_9_sell  = False

    for i in range(n - 1, max(0, n - 120), -1):
        b, s, cb, cs = int(buy[i]), int(sell[i]), int(cd_b[i]), int(cd_s[i])

        if cs == 13 and not seen_cd_sell:
            events.append({"stage": "Sell Countdown 13", "state": "✓ complete",
                           "tone": "rd", "note": "sell exhaustion — mean-reversion risk"})
            seen_cd_sell = True
        elif cs > 0 and cs < 13 and not seen_cd_sell:
            events.append({"stage": "Sell Countdown 13", "state": f"{cs} of 13 · in progress",
                           "tone": "amb", "note": "sell exhaustion building"})
            seen_cd_sell = True

        if cb == 13 and not seen_cd_buy:
            events.append({"stage": "Buy Countdown 13", "state": "✓ complete",
                           "tone": "gn", "note": "buy exhaustion — mean-reversion risk"})
            seen_cd_buy = True
        elif cb > 0 and cb < 13 and not seen_cd_buy:
            events.append({"stage": "Buy Countdown 13", "state": f"{cb} of 13 · in progress",
                           "tone": "cy", "note": "buy exhaustion building"})
            seen_cd_buy = True

        if s == 9 and not seen_9_sell:
            events.append({"stage": "Sell Setup 9", "state": "✓ complete",
                           "tone": "rd", "note": "9 consecutive closes > close[−4]"})
            seen_9_sell = True
        elif s > 0 and s < 9 and not seen_9_sell:
            events.append({"stage": "Sell Setup", "state": f"{s} of 9 · in progress",
                           "tone": "amb", "note": "momentum building into exhaustion"})
            seen_9_sell = True

        if b == 9 and not seen_9_buy:
            events.append({"stage": "Buy Setup 9", "state": "✓ complete",
                           "tone": "gn", "note": "9 consecutive closes < close[−4]"})
            seen_9_buy = True
        elif b > 0 and b < 9 and not seen_9_buy:
            events.append({"stage": "Buy Setup", "state": f"{b} of 9 · in progress",
                           "tone": "cy", "note": "selling pressure building"})
            seen_9_buy = True

        if len(events) >= 4:
            break

    # Reverse to chronological order
    events.reverse()
    if not events:
        events.append({"stage": "No active sequence", "state": "scanning…",
                       "tone": "ink-3", "note": "no consecutive 9-bar count found in recent bars"})
    return events


# ────────────────────────────────────────────────────────────────────────────
# Confidence score (0–1)
# ────────────────────────────────────────────────────────────────────────────
def _confidence(cur: Dict[str, Any], count: int, phase: str, perfected: bool) -> float:
    base = 0.0
    if phase == "setup":
        base = 0.30 + 0.05 * (count - 1)   # 0.30 at count=1 → 0.70 at count=9
        if perfected:
            base = min(base + 0.15, 0.92)
    elif phase == "countdown":
        base = 0.55 + 0.025 * (count - 1)  # 0.55 at cd=1 → 0.85 at cd=13
    return round(min(base, 0.92), 2)


# ────────────────────────────────────────────────────────────────────────────
# Main entry point
# ────────────────────────────────────────────────────────────────────────────
def detect(df: pd.DataFrame, meta: Dict[str, Any], ticker: str) -> Dict[str, Any]:
    tf = meta.get("tf", "Daily")
    w  = _tfw(tf)

    if df is None or len(df) < 14:
        return {
            "ok": True, "source": "real", "state": "none",
            "message": f"Not enough {tf.lower()} bars for TD Sequential (need ≥ 14).",
            "cur_close": None,
        }

    # Compute TD columns on the full frame
    df_td = _compute_td(df)

    # Window to last N bars for display
    n_bars = w["bars"]
    df_win = df_td.iloc[-n_bars:].copy()
    offset = max(0, len(df_td) - n_bars)

    cur_close = round(float(df_td["Close"].iloc[-1]), 2)

    # Per-bar markers for the chart
    markers = _build_markers(df_win, offset)

    # TDST levels
    tdst_support, tdst_resistance = _compute_tdst(df_td)

    # Current state
    cur = _current_state(df_td, tf)
    state_str = cur["state_str"]
    phase     = cur["phase"]
    count     = cur["count"]
    direction = cur["direction"]
    perfected = cur["perfected"]
    ladder    = cur["ladder"]

    if phase == "none":
        return {
            "ok": True, "source": "real", "state": "none",
            "message": f"No active TD Setup or Countdown on {tf.lower()} bars — price isn't in a sustained count.",
            "cur_close": cur_close,
            "bars":      _bar_payload(df_win),
            "markers":   [],
            "tdst":      _build_tdst_levels(tdst_support, tdst_resistance),
            "ladder":    ladder,
            "stat":      _build_stat(state_str, phase, tdst_support, tdst_resistance, cur_close, 0.0),
            "current":   cur,
            "setup_table": _build_setup_table(cur),
            "read":      f"No active TD count on {tf.lower()} bars.",
        }

    conf = _confidence(cur, count, phase, perfected)

    # Build hlines from TDST
    hlines = _build_tdst_levels(tdst_support, tdst_resistance)

    bars_out = _bar_payload(df_win)

    stat = _build_stat(state_str, phase, tdst_support, tdst_resistance, cur_close, conf)

    read = _build_read(cur, tdst_support, tdst_resistance, cur_close, tf)

    return {
        "ok":         True,
        "source":     "real",
        "state":      "real",
        "confidence": conf,
        "bars":       bars_out,
        "markers":    markers,
        "tdst":       hlines,
        "stat":       stat,
        "current":    cur,
        "setup_table": _build_setup_table(cur),
        "ladder":     ladder,
        "read":       read,
        "cur_close":  cur_close,
    }


# ────────────────────────────────────────────────────────────────────────────
# Sub-builders for structured output
# ────────────────────────────────────────────────────────────────────────────
def _build_tdst_levels(
    support: Optional[float], resistance: Optional[float]
) -> List[Dict[str, Any]]:
    hlines = []
    if resistance is not None:
        hlines.append({
            "price": round(resistance, 2),
            "label": f"TDST resistance {resistance:.2f}",
            "tone": "rd",
            "dash": "4 4",
        })
    if support is not None:
        hlines.append({
            "price": round(support, 2),
            "label": f"TDST support {support:.2f}",
            "tone": "cy",
            "dash": "4 4",
            "labelBelow": True,
        })
    return hlines


def _build_stat(
    state_str: str,
    phase: str,
    tdst_support: Optional[float],
    tdst_resistance: Optional[float],
    cur_close: float,
    conf: float,
) -> Dict[str, Any]:
    tdst_str = "—"
    if tdst_support is not None and tdst_resistance is not None:
        tdst_str = f"{tdst_support:.2f} / {tdst_resistance:.2f}"
    elif tdst_support is not None:
        tdst_str = f"{tdst_support:.2f} support"
    elif tdst_resistance is not None:
        tdst_str = f"{tdst_resistance:.2f} resistance"

    cd_str = "not started" if phase != "countdown" else state_str
    setup_str = state_str if phase == "setup" else "—"

    return {
        "setup":      setup_str,
        "countdown":  cd_str,
        "tdst":       tdst_str,
        "timing":     "exhaustion signal" if conf >= 0.65 else ("building" if conf > 0 else "no signal"),
        "confidence": conf,
    }


def _build_setup_table(cur: Dict[str, Any]) -> List[Dict[str, Any]]:
    phase     = cur["phase"]
    direction = cur["direction"]
    count     = cur["count"]
    perfected = cur["perfected"]
    rule      = cur["rule"]
    state_str = cur["state_str"]

    if phase == "none":
        return [
            {"k": "Phase",      "v": "None",   "tone": "ink-3"},
            {"k": "Count",      "v": "—",      "tone": "ink-3"},
            {"k": "Rule",       "v": "—",      "tone": "ink-1"},
            {"k": "Perfected?", "v": "—",      "tone": "ink-3"},
        ]

    cap_dir = direction.capitalize()
    if phase == "setup":
        perf_v  = ("yes ✓" if perfected else "pending") if count == 9 else "n/a"
        tone_v  = "gn" if direction == "buy" else "rd"
    else:
        perf_v  = "n/a"
        tone_v  = "cy" if direction == "buy" else "amb"

    return [
        {"k": "Phase",      "v": f"{cap_dir} {phase.capitalize()}", "tone": tone_v},
        {"k": "Count",      "v": f"{count} of {'9' if phase == 'setup' else '13'}", "tone": tone_v},
        {"k": "Rule",       "v": rule,    "tone": "ink-1"},
        {"k": "Perfected?", "v": perf_v, "tone": "gn" if (perfected and count == 9) else "ink-3"},
    ]


def _build_read(
    cur: Dict[str, Any],
    tdst_support: Optional[float],
    tdst_resistance: Optional[float],
    cur_close: float,
    tf: str,
) -> str:
    phase     = cur["phase"]
    direction = cur["direction"]
    count     = cur["count"]
    perfected = cur["perfected"]
    state_str = cur["state_str"]

    if phase == "none":
        return f"No active TD count on {tf.lower()} bars — no exhaustion signal."

    dir_word = "buy" if direction == "buy" else "sell"

    if phase == "setup":
        perf_str = " (perfected)" if (perfected and count == 9) else ""
        if count == 9:
            tdst_pin = f" TDST support at {tdst_support:.2f}." if (direction == "buy" and tdst_support) else \
                       (f" TDST resistance at {tdst_resistance:.2f}." if (direction == "sell" and tdst_resistance) else "")
            return (
                f"{dir_word.capitalize()} Setup 9{perf_str} complete — exhaustion risk active.{tdst_pin} "
                f"Watch for a 1–4 bar pause/reversal; countdown armed on next bar."
            )
        return (
            f"{dir_word.capitalize()} Setup {count} of 9 in progress — {9 - count} bar{'s' if 9 - count != 1 else ''} "
            f"remaining to signal exhaustion."
        )

    # Countdown
    rem = 13 - count
    if count == 13:
        return (
            f"{dir_word.capitalize()} Countdown 13 complete — full DeMark exhaustion signal on {tf.lower()} bars. "
            f"Mean-reversion risk is elevated; align with support/resistance before fading."
        )
    return (
        f"{dir_word.capitalize()} Countdown {count} of 13 — {rem} bar{'s' if rem != 1 else ''} to full exhaustion signal."
    )
