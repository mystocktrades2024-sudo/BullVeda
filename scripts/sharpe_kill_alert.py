#!/usr/bin/env python3
"""Slack alert when rolling Sharpe kill gate transitions blocked → clear.

Run after every scan (wired in run_daily_scan.sh). Writes state to
cache/sharpe_kill_state.json so it can detect transitions across runs.

Also prints a one-line status to stdout for the log.
"""
from __future__ import annotations
import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).parent.parent
STATE_PATH = BASE / "cache" / "sharpe_kill_state.json"


def _slack(url: str, text: str) -> None:
    payload = json.dumps({"text": text}).encode()
    try:
        req = urllib.request.Request(url, data=payload,
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"[sharpe_kill_alert] Slack post failed: {e}", file=sys.stderr)


def run() -> None:
    # Load config
    cfg_path = BASE / "config" / "config.json"
    config = json.loads(cfg_path.read_text()) if cfg_path.exists() else {}

    # Compute current state
    try:
        sys.path.insert(0, str(BASE))
        import decision_engine as de
        state = de.compute_rolling_sharpe_kill_state(config)
    except Exception as e:
        print(f"[sharpe_kill_alert] compute_rolling_sharpe_kill_state failed: {e}")
        return

    now = datetime.now().isoformat(timespec="seconds")
    state["_checked_at"] = now

    # Load previous state
    prev: dict = {}
    if STATE_PATH.exists():
        try:
            prev = json.loads(STATE_PATH.read_text())
        except Exception:
            prev = {}

    was_active = prev.get("active", False)
    is_active = state.get("active", False)
    sharpe = state.get("sharpe")
    n = state.get("n", 0)
    threshold = state.get("threshold", -0.5)

    # Slack URL from env / .env file
    slack_url = os.environ.get("SLACK_WEBHOOK_URL", "")
    if not slack_url:
        env_path = BASE / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line.startswith("SLACK_WEBHOOK_URL="):
                    slack_url = line.split("=", 1)[1].strip()
                    break

    # Detect transition: blocked → clear
    if was_active and not is_active:
        sharpe_str = f"{sharpe:+.3f}" if sharpe is not None else "n/a"
        msg = (
            f":green_circle: *Rolling Sharpe Kill CLEARED* — gate is no longer blocking BUYs.\n"
            f"Rolling Sharpe={sharpe_str} (threshold {threshold:+.1f}) · n={n} closed BUYs\n"
            f"System can now emit BUYs normally. Check dashboard before sizing in."
        )
        print(f"[sharpe_kill_alert] TRANSITION blocked→clear — Slack fired")
        if slack_url:
            _slack(slack_url, msg)
        else:
            print(f"[sharpe_kill_alert] No SLACK_WEBHOOK_URL — message would be: {msg}")

    # Detect transition: clear → blocked
    elif not was_active and is_active:
        sharpe_str = f"{sharpe:+.3f}" if sharpe is not None else "n/a"
        reason = state.get("reason", "")
        msg = (
            f":red_circle: *Rolling Sharpe Kill ACTIVATED* — new BUYs paused.\n"
            f"Rolling Sharpe={sharpe_str} (threshold {threshold:+.1f}) · n={n} closed BUYs\n"
            f"Reason: {reason}\n"
            f"System routes candidates to WATCH until Sharpe recovers."
        )
        print(f"[sharpe_kill_alert] TRANSITION clear→blocked — Slack fired")
        if slack_url:
            _slack(slack_url, msg)
        else:
            print(f"[sharpe_kill_alert] No SLACK_WEBHOOK_URL — message would be: {msg}")

    # Status log line (always printed)
    status = "BLOCKED" if is_active else ("ACCUMULATING" if n < config.get("rolling_sharpe_kill", {}).get("min_sample_n", 10) else "CLEAR")
    sharpe_str = f"{sharpe:+.3f}" if sharpe is not None else "n/a"
    print(f"[sharpe_kill_alert] status={status} Sharpe={sharpe_str} n={n} threshold={threshold:+.1f}")

    # Save current state
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))


if __name__ == "__main__":
    run()
