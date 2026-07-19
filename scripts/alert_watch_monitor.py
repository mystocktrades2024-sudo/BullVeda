#!/usr/bin/env python3
"""Emit a line whenever a NEW live alert fires today, until market close.

Watches:
  - data/alert_sent_log.json  for new  TICKER:entry_buy / TICKER:entry_zone  keys
    dated today (= entry_watch FIRM/soft alert fired to Slack)
  - cache/swing_analysis_state.json  ts change  (= a 4h digest posted)

Each new event is printed as one stdout line (an event for the Monitor tool).
Baseline is captured at startup so only NEW events fire. Exits ~13:15 PT
(after the 13:00 PT / 16:00 ET close) which ends the watch.
"""
import json
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALOG = ROOT / "data" / "alert_sent_log.json"
DST = ROOT / "cache" / "swing_analysis_state.json"


def _today():
    return datetime.now().strftime("%Y-%m-%d")


def _firm_keys():
    try:
        d = json.load(open(ALOG))
        t = _today()
        return {k for k, v in d.items()
                if (k.endswith(":entry_buy") or k.endswith(":entry_zone")) and str(v) == t}
    except Exception:
        return set()


def _digest_ts():
    try:
        return json.load(open(DST)).get("ts", "")
    except Exception:
        return ""


def main():
    seen = _firm_keys()
    dts = _digest_ts()
    print(f"WATCH-START {datetime.now():%H:%M} PT · baseline {len(seen)} firm keys · digest {dts}", flush=True)
    while True:
        now = datetime.now()
        # run through the 18:00 PT digest (covers intraday FIRM alerts +
        # the 10:00 / 14:00 / 18:00 digests), then end.
        if now.hour > 18 or (now.hour == 18 and now.minute >= 15):
            print(f"WATCH-END {now:%H:%M} PT · session done", flush=True)
            return
        cur = _firm_keys()
        for k in sorted(cur - seen):
            tk, _, tier = k.partition(":")
            label = "FIRM-BUY" if tier == "entry_buy" else "SOFT-ZONE"
            print(f"ALERT {label} {tk} · {now:%H:%M} PT", flush=True)
        seen |= cur
        nd = _digest_ts()
        if nd and nd != dts:
            dts = nd
            print(f"DIGEST posted · {now:%H:%M} PT", flush=True)
        time.sleep(120)


if __name__ == "__main__":
    main()
