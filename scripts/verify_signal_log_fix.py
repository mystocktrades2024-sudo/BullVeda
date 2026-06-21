#!/usr/bin/env python3
"""verify_signal_log_fix.py — confirm SIGLOG-ORDER-FIX (commit dbe025e08) held.

Before the fix, signal_log was written BEFORE the canonical compute_final_verdict
(ranker) pass, so it recorded pre-ranker buy_candidates as verdict=BUY (e.g. 27
"BUYs" when the engine emitted 1-2, including sub-60-score names that can't pass
gate_floor=60). After the fix, signal_log's BUY set should MATCH the engine's
canonical BUYs (bundle["buy_candidates"] with verdict==BUY) and contain NO
sub-60-score BUYs.

Run locally (has access to the live cache/data). Exit 0 = pass, 1 = mismatch.
Designed to be called from the morning/weekly launchd flow or by hand.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent


def _load(p):
    try:
        return json.loads((BASE / p).read_text())
    except Exception as e:
        print(f"  ! could not read {p}: {e}")
        return None


def main() -> int:
    bundle = _load("cache/last_bundle.json")
    sig = _load("data/signal_log.json")
    if bundle is None or sig is None:
        print("VERIFY: cannot run — missing bundle or signal_log")
        return 1

    run_date = bundle.get("run_date")
    # log_signals snaps weekend run-dates forward to the next trading day
    # (Sat→+2, Sun→+1), so signal_log keys on the snapped date. Mirror that here
    # or a weekend test run would compare mismatched dates and false-WARN.
    sl_date = run_date
    try:
        from datetime import datetime as _dt, timedelta as _td
        _dow = _dt.strptime(run_date, "%Y-%m-%d").weekday()  # Mon=0..Sun=6
        if _dow == 5:   sl_date = (_dt.strptime(run_date, "%Y-%m-%d") + _td(days=2)).strftime("%Y-%m-%d")
        elif _dow == 6: sl_date = (_dt.strptime(run_date, "%Y-%m-%d") + _td(days=1)).strftime("%Y-%m-%d")
    except Exception:
        pass
    # Canonical engine BUYs (post-ranker): bundle buy_candidates with verdict==BUY
    bc = bundle.get("buy_candidates") or []
    eng_buys = [r for r in bc if str((r.get("verdict")
                or (r.get("decision") or {}).get("verdict") or "")).upper() == "BUY"]
    eng_syms = sorted({r.get("ticker") for r in eng_buys})

    # signal_log BUYs logged for the (snapped) run_date (Swing, long)
    sl_buys = [x for x in sig if x.get("date") == sl_date
               and str(x.get("verdict", "")).upper() == "BUY"
               and x.get("direction", "long") == "long"
               and x.get("mode", "Swing") == "Swing"]
    sl_syms = sorted({x.get("ticker") for x in sl_buys})
    sub60 = sorted({x.get("ticker") for x in sl_buys
                    if (x.get("score") or 0) < 60})

    print(f"VERIFY signal_log fix — run_date {run_date}")
    print(f"  engine canonical BUYs   : {len(eng_syms)}  {eng_syms[:12]}")
    print(f"  signal_log BUYs (Swing) : {len(sl_syms)}  {sl_syms[:12]}")
    print(f"  sub-60-score BUYs in log: {len(sub60)}  {sub60[:12]}")

    only_log = sorted(set(sl_syms) - set(eng_syms))
    only_eng = sorted(set(eng_syms) - set(sl_syms))

    ok = (set(sl_syms) == set(eng_syms)) and not sub60
    want_slack = "--slack" in sys.argv
    if ok:
        msg = (f"signal_log matches engine: {len(sl_syms)} BUYs ({', '.join(sl_syms) or '—'}), "
               f"no sub-60 leakage. SIGLOG-ORDER-FIX holding.")
        print(f"  ✅ PASS — {msg}")
        if want_slack:
            _slack("INFO", "✅ signal_log fix verified", f"{run_date}: {msg}")
        return 0

    body = (f"{run_date}: signal_log {len(sl_syms)} BUYs vs engine {len(eng_syms)}. "
            f"Logged-not-engine: {only_log[:15]}. Sub-60 still logged: {sub60[:15]}.")
    print("  ❌ MISMATCH — fix may not have taken (or scan hasn't run post-fix):")
    if only_log:
        print(f"     in signal_log but NOT engine BUY: {only_log[:20]}")
    if only_eng:
        print(f"     engine BUY but NOT in signal_log: {only_eng[:20]}")
    if sub60:
        print(f"     sub-60-score BUYs still logged : {sub60[:20]}")
    if want_slack:
        _slack("WARN", "❌ signal_log fix NOT holding", body)
    return 1


def _slack(level: str, title: str, body: str) -> None:
    try:
        sys.path.insert(0, str(BASE))
        from alerts import send_alert
        send_alert(level, title, body, force_slack=True)
    except Exception as e:
        print(f"  (slack post skipped: {e})")


if __name__ == "__main__":
    sys.exit(main())
