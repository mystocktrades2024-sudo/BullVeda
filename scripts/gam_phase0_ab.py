#!/usr/bin/env python3
"""Phase 0 — consistency A/B: GAM v2 Pine-port ladder vs /api/trade_engine (swing).

Runs on TODAY's bars only (no historical outcomes needed). Reports per-ticker
T1/T2 deltas and source composition so divergences point at the loose
approximation (HVN vs real volume profile, MC reachability, etc.).

Usage: python3 scripts/gam_phase0_ab.py [T1 T2 ...]   (default 10-ticker basket)
"""
from __future__ import annotations

import json
import sys

import requests

sys.path.insert(0, ".")
import data_fetcher                      # noqa: E402
from scripts.gam_target_v2 import compute_ladder  # noqa: E402

BASE = "http://localhost:7432"
AUTH = ("gari", "Swing2026")
DEFAULT = ["LQDA", "NVDA", "AAPL", "MSFT", "AMD", "META", "AMZN", "GOOGL", "TSLA", "SPY"]


def engine_ladder(tk: str) -> dict:
    try:
        r = requests.get(f"{BASE}/api/trade_engine", params={"t": tk, "mode": "swing"},
                         auth=AUTH, timeout=60)
        j = r.json()
        out = {"decision": j.get("decision"), "entry": (j.get("entry") or {}).get("price")}
        for k in ("t1", "t2", "t3"):
            t = j.get(k)
            out[k] = None if not t else {
                "price": t.get("price"), "conf": t.get("confluence"),
                "behavior": t.get("behavior"),
                "srcs": sorted({s.get("type") for s in (t.get("sources") or [])}),
            }
        return out
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def fmt_t(t, key="price"):
    if not t:
        return "  —  "
    return f"{t[key]:7.2f}" if isinstance(t.get(key), (int, float)) else "  —  "


def main() -> None:
    tickers = sys.argv[1:] or DEFAULT
    rows = []
    for tk in tickers:
        bars, tier = data_fetcher.fetch_ohlcv_with_failover(tk, days=400)
        if bars is None or len(bars) < 80:
            rows.append((tk, None, None, f"no bars ({tier})"))
            continue
        mine = compute_ladder(bars)
        eng = engine_ladder(tk)
        rows.append((tk, mine, eng, None))

    print(f"{'ticker':7} {'pine T1':>8} {'engine T1':>9} {'ΔT1%':>6}  "
          f"{'pine T2':>8} {'engine T2':>9} {'ΔT2%':>6}  notes")
    print("─" * 88)
    for tk, mine, eng, err in rows:
        if err:
            print(f"{tk:7} {err}")
            continue
        note = []
        if eng.get("decision") == "reject":
            note.append("engine:reject")
        if eng.get("error"):
            note.append(f"engine:{eng['error'][:30]}")

        def delta(a, b):
            if a and b and a.get("price") and b.get("price"):
                return f"{100*(a['price']-b['price'])/b['price']:+5.1f}"
            return "  —  "

        m1, m2 = mine.get("t1"), mine.get("t2")
        e1, e2 = eng.get("t1"), eng.get("t2")
        if m1 and m1.get("sources"):
            note.append("p1:" + "+".join(m1["sources"][:3]))
        if e1 and e1.get("srcs"):
            note.append("e1:" + "+".join(e1["srcs"][:3]))
        print(f"{tk:7} {fmt_t(m1):>8} {fmt_t(e1):>9} {delta(m1, e1):>6}  "
              f"{fmt_t(m2):>8} {fmt_t(e2):>9} {delta(m2, e2):>6}  {' '.join(note)}")

    print("\nraw detail → cache/gam_phase0_ab.json")
    with open("cache/gam_phase0_ab.json", "w") as f:
        json.dump([{"ticker": tk, "pine": m, "engine": e, "err": err}
                   for tk, m, e, err in rows], f, indent=2, default=str)


if __name__ == "__main__":
    main()
