#!/usr/bin/env python3
"""
iv_elevation_alert.py — detect IV jumps that signal earnings-priced-in.

Reads data/iv_history.jsonl (built daily by snapshot_iv.py) and flags
tickers where current IV is >20% above the 5-day baseline. Cross-
references with earnings_watchlist to confirm an upcoming catalyst.

Slack-alerts the top 5 jumps with their earnings date.

Schedule: daily 1:00pm PT (after market close + IV snapshot fresh).
"""
from __future__ import annotations
import json
import logging
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
LOG_FILE = BASE / "cache" / "logs" / "iv_elevation_alert.log"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [iv_elev] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


def _load_env() -> None:
    env_path = BASE / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def main(threshold_pct: float = 20.0, baseline_days: int = 5,
         min_history: int = 5, top_n: int = 5) -> int:
    _load_env()

    hist_path = BASE / "data" / "iv_history.jsonl"
    if not hist_path.exists():
        log.warning("No iv_history.jsonl — snapshot_iv.py hasn't run yet, or no captures")
        return 0

    # Group history by ticker
    by_ticker: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for line in hist_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
            t = e.get("ticker")
            iv = e.get("current_iv")
            d = e.get("date")
            if t and iv is not None and d:
                by_ticker[t].append((d, float(iv)))
        except Exception:
            continue

    today = date.today().isoformat()
    cutoff = (date.today() - timedelta(days=baseline_days)).isoformat()

    # Build delta for each ticker
    deltas = []
    for t, samples in by_ticker.items():
        samples.sort(key=lambda x: x[0])
        if len(samples) < min_history:
            continue
        # Today's IV — most recent sample dated today (or most recent overall)
        latest = samples[-1]
        if latest[0] < today:
            # Stale snapshot — skip
            continue
        cur_iv = latest[1]
        # Baseline: average IV over the prior 5 days (excluding today)
        prior = [iv for d, iv in samples if cutoff <= d < today]
        if len(prior) < 2:
            continue
        baseline = sum(prior) / len(prior)
        if baseline <= 0:
            continue
        pct_change = (cur_iv - baseline) / baseline * 100
        if pct_change >= threshold_pct:
            deltas.append({
                "ticker":     t,
                "current_iv": round(cur_iv, 1),
                "baseline":   round(baseline, 1),
                "pct_change": round(pct_change, 1),
            })

    deltas.sort(key=lambda x: -x["pct_change"])
    if not deltas:
        log.info("No IV elevation events today")
        return 0

    # Cross-reference with earnings watchlist for context
    ew_path = BASE / "data" / "earnings_watchlist.json"
    earnings_map = {}
    if ew_path.exists():
        try:
            ew = json.loads(ew_path.read_text())
            earnings_map = {x["ticker"]: x for x in (ew.get("watchlist") or [])}
        except Exception:
            pass

    top = deltas[:top_n]
    log.info(f"Found {len(deltas)} IV-elevation events; alerting on top {len(top)}")

    lines = []
    for d in top:
        t = d["ticker"]
        em = earnings_map.get(t)
        earn = (f"earnings {em['report_date']} ({em['days_to_earnings']}d)"
                if em else "no earnings catalyst found")
        lines.append(
            f"*{t}* — IV {d['baseline']}% → {d['current_iv']}% "
            f"(+{d['pct_change']}%)  ·  {earn}"
        )
    body = (
        f"IV jumped >{threshold_pct}% vs {baseline_days}d baseline:\n\n"
        + "\n".join(lines)
        + "\n\nElevated IV before a known catalyst = market is pricing in a move. "
          "Useful for timing entries (premium expensive) and exit hedges."
    )
    title = f"📈 IV ELEVATION ({len(top)} ticker{'s' if len(top) != 1 else ''})"

    log.info(title); log.info(body)
    try:
        from alerts import send_alert
        send_alert("WARN", title, body)
    except Exception as e:
        log.warning(f"Slack failed: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
