#!/usr/bin/env python3
"""
model_drift_alert.py — daily check for live-vs-backtest divergence.

Compares the most-recent 30 days of CLOSED live signals (from data/signal_log.json)
to the most-recent backtest summary (cache/portfolio_backtest.json). Alerts via
Slack when live WR drops more than 5pp below backtest WR — early-warning that
the model's edge is fading or the regime has shifted.

Schedule: daily, post-market close (after positions are marked-to-market).

Usage:
    python3 model_drift_alert.py                     # check + alert if needed
    python3 model_drift_alert.py --threshold 8       # custom delta threshold
    python3 model_drift_alert.py --window 30         # custom rolling window
    python3 model_drift_alert.py --dry-run           # print, don't slack

Exit codes:
  0 = no alert (within tolerance OR insufficient data)
  1 = alert fired
  2 = error
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
SIGNAL_LOG = BASE / "data" / "signal_log.json"
BACKTEST_FILE = BASE / "cache" / "portfolio_backtest.json"
DRIFT_LOG = BASE / "data" / "drift_alerts.jsonl"


def _load_env() -> None:
    env_path = BASE / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def _send_slack(text: str) -> bool:
    _load_env()
    url = os.environ.get("SLACK_WEBHOOK_URL")
    if not url or "hooks.slack.com" not in url:
        print("[drift] no SLACK_WEBHOOK_URL — skipping send")
        return False
    try:
        body = json.dumps({"text": text}).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception as e:
        print(f"[drift] slack send failed: {e}")
        return False


def _load_live_outcomes(window_days: int) -> list[dict]:
    """Pull CLOSED live signals from last N days."""
    if not SIGNAL_LOG.exists():
        return []
    try:
        sigs = json.loads(SIGNAL_LOG.read_text())
    except Exception:
        return []
    cutoff = datetime.now() - timedelta(days=window_days)
    out = []
    for s in sigs or []:
        if s.get("status") != "CLOSED":
            continue
        exit_str = s.get("exit_date") or s.get("close_date")
        if not exit_str:
            continue
        try:
            d = datetime.fromisoformat(str(exit_str)[:10])
        except Exception:
            continue
        if d >= cutoff:
            pnl = s.get("actual_pnl_pct")
            if pnl is None:
                continue
            out.append({
                "ticker": s.get("ticker"),
                "exit_date": str(exit_str)[:10],
                "pnl_pct": float(pnl),
                "win": float(pnl) > 0,
                "strategy": s.get("strategy"),
            })
    return out


def _load_backtest_baseline() -> dict | None:
    if not BACKTEST_FILE.exists():
        return None
    try:
        d = json.loads(BACKTEST_FILE.read_text())
        return {
            "wr_pct": d.get("win_rate", 0) * 100 if d.get("win_rate", 0) <= 1 else d.get("win_rate", 0),
            "profit_factor": d.get("profit_factor", 0),
            "n_trades": d.get("total_trades") or len(d.get("trades", [])),
        }
    except Exception:
        return None


def _append_drift_log(payload: dict) -> None:
    DRIFT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with DRIFT_LOG.open("a") as f:
        f.write(json.dumps(payload) + "\n")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--threshold", type=float, default=5.0,
                   help="Alert if live WR is below backtest WR by this many pp (default 5)")
    p.add_argument("--window", type=int, default=30,
                   help="Rolling window in days for live trades (default 30)")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    print(f"[drift] window={args.window}d threshold={args.threshold}pp")

    bt = _load_backtest_baseline()
    if not bt:
        print("[drift] no backtest baseline — run backtest.py --portfolio first")
        return 2

    live = _load_live_outcomes(args.window)
    if not live:
        print(f"[drift] no closed live trades in last {args.window}d — nothing to compare")
        return 0

    n = len(live)
    wins = sum(1 for t in live if t["win"])
    live_wr = wins / n * 100
    delta = live_wr - bt["wr_pct"]

    payload = {
        "timestamp": datetime.now().isoformat(),
        "window_days": args.window,
        "n_live": n,
        "live_wr_pct": round(live_wr, 1),
        "backtest_wr_pct": round(bt["wr_pct"], 1),
        "delta_pp": round(delta, 1),
        "alert_threshold_pp": args.threshold,
        "alert_fired": delta < -args.threshold,
    }
    _append_drift_log(payload)

    print(f"[drift] live: {n} trades / WR {live_wr:.1f}% | backtest: WR {bt['wr_pct']:.1f}%")
    print(f"[drift] delta: {delta:+.1f}pp")

    if delta < -args.threshold:
        rule = "—" * 21
        msg = (f"🚨  Model drift detected  ·  {delta:+.1f}pp\n"
               f"{rule}\n"
               f"Live     {n} trades · WR {live_wr:.1f}%  (last {args.window}d)\n"
               f"Baseline WR {bt['wr_pct']:.1f}%  (backtest)\n"
               f"Delta    {delta:+.1f}pp  (threshold ±{args.threshold}pp)\n"
               f"💡 Check regime shift · recent kill-list/threshold changes · "
               f"data quality → http://localhost:7432/v2/backtest-report")
        print(f"\n*** ALERT *** delta {delta:+.1f}pp below threshold")
        if args.dry_run:
            print(f"[dry-run] would send:\n{msg}")
        else:
            sent = _send_slack(msg)
            print(f"[drift] slack sent: {sent}")
        return 1
    print(f"[drift] within tolerance — no alert")
    return 0


if __name__ == "__main__":
    sys.exit(main())
