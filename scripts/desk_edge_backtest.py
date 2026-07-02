#!/usr/bin/env python3
"""desk_edge_backtest.py — measure each Screener Desk's OWN edge from ground-truth
trade outcomes (data/signal_log.json), attributing closed trades to the desk(s) whose
selection criteria they match. Self-sustained: uses realized R-multiples (truth), not
the old scanner's score/verdict. Writes cache/desk_edge_stats.json for the desk edge
headers + trade-ticket expected value.

Desks whose defining signals are NOT in the trade log (Mean-Reversion=RSI,
Value/Quality=fundamentals) can't be attributed here and are left 'pending' — they need
a fresh signal-replay backtest, not this log-attribution.

Run: python3 scripts/desk_edge_backtest.py
"""
from __future__ import annotations

import json
import math
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
LOG = BASE / "data" / "signal_log.json"
OUT = BASE / "cache" / "desk_edge_stats.json"

DEFENSIVE_WL = {"XLU", "GLD", "JNJ", "PG", "KO", "PEP", "WMT", "COST",
                "MRK", "ABBV", "DUK", "SO", "NEE"}

PF_HAIRCUT = 0.10      # retail slippage/edge-erosion haircut
WR_HAIRCUT = 0.03      # survivorship haircut (−3pp)
MIN_N = 20             # below this, edge is 'low sample', not asserted


def _n(x, d=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


def _wilson_lb(wins, n, z=1.96):
    if n == 0:
        return 0.0
    p = wins / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)
    return max(0.0, (centre - margin) / denom)


def _attribute(e):
    """Return the set of desk keys this closed trade qualifies for, from log fields."""
    desks = set()
    rs = e.get("rs_rank")
    sf = (e.get("setup_family") or "")
    eq = (e.get("entry_quality") or "")
    ct = e.get("catalyst_tier")
    direction = (e.get("direction") or "").lower()
    tkr = (e.get("ticker") or e.get("symbol") or "").upper()

    if direction == "short":
        desks.add("short")
        return desks  # a short trade only informs the short book
    if rs is not None and _n(rs) >= 90:
        desks.add("mom")
    if rs is not None and _n(rs) >= 80:
        desks.add("qf")            # approximate (multi-factor proxy)
    if sf == "Breakout Expansion":
        desks.add("bo")
    if sf == "Trend Continuation":
        desks.add("pb")
    if ct == 1 or ct == "1":
        desks.add("cat")
    if sf in ("Insider Cluster", "Special Situation"):
        desks.add("smart")
    if tkr and tkr in DEFENSIVE_WL:
        desks.add("def")
    return desks


def _stats(rmults):
    n = len(rmults)
    wins = sum(1 for r in rmults if r > 0)
    wr = wins / n if n else 0.0
    pos = sum(r for r in rmults if r > 0)
    neg = abs(sum(r for r in rmults if r < 0))
    pf = (pos / neg) if neg > 0 else (pos if pos > 0 else 0.0)
    exp_r = sum(rmults) / n if n else 0.0
    return {
        "n": n,
        "wr": round(wr, 4),
        "wilson_lb": round(_wilson_lb(wins, n), 4),
        "pf": round(pf, 3),
        "pf_haircut": round(max(0.0, pf - PF_HAIRCUT), 3),
        "wr_haircut": round(max(0.0, wr - WR_HAIRCUT), 4),
        "expectancy_R": round(exp_r, 3),
    }


def main():
    raw = json.loads(LOG.read_text())
    arr = raw if isinstance(raw, list) else (raw.get("signals") or raw.get("entries") or [])
    closed = [e for e in arr if e.get("actual_r_multiple") is not None]

    buckets = {}
    for e in closed:
        r = _n(e.get("actual_r_multiple"))
        for d in _attribute(e):
            buckets.setdefault(d, []).append(r)

    desks = {}
    for d, rms in buckets.items():
        s = _stats(rms)
        s["approximate"] = (d == "qf")  # rs-proxy, not a true factor replay
        s["low_sample"] = s["n"] < MIN_N
        desks[d] = s

    # desks not attributable from the log (need a signal-replay backtest)
    for d in ("mr", "val", "qual", "short"):
        desks.setdefault(d, {"n": 0, "pending": True,
                             "note": "needs signal-replay (signals/direction not in trade log)"})
    # low-sample desks are shown but not asserted as proven
    for d, s in desks.items():
        if not s.get("pending") and s.get("n", 0) < MIN_N:
            s["low_sample"] = True

    out = {
        "_meta": {
            "source": "data/signal_log.json",
            "n_closed": len(closed),
            "pf_haircut": PF_HAIRCUT, "wr_haircut": WR_HAIRCUT, "min_n": MIN_N,
            "method": "ground-truth R-multiple attribution by desk criteria",
        },
        "desks": desks,
    }
    OUT.write_text(json.dumps(out, indent=2))
    print(f"wrote {OUT.name} from {len(closed)} closed trades")
    for d in ("pb", "bo", "cat", "mom", "qf", "smart", "def", "short", "mr", "val", "qual"):
        s = desks.get(d, {})
        if s.get("pending"):
            print(f"  {d:6s} pending (needs replay)")
        else:
            flag = " ~approx" if s.get("approximate") else (" low-n" if s.get("low_sample") else "")
            print(f"  {d:6s} n={s.get('n', 0):4d}  WR {s.get('wr', 0) * 100:4.1f}%  Wilson {s.get('wilson_lb', 0) * 100:4.1f}%  "
                  f"PF {s.get('pf', 0):.2f}->{s.get('pf_haircut', 0):.2f}  E[R] {s.get('expectancy_R', 0):+.2f}{flag}")


if __name__ == "__main__":
    main()
