#!/usr/bin/env python3
"""
alert_beat_strong.py — Slack-alert when a ticker enters STRONG tier.

Compares today's earnings_beat_predictions.json against yesterday's
snapshot. Fires when:
  - A new ticker is now STRONG (was MODERATE/SOLID/missing yesterday)
  - An existing STRONG name's score jumped ≥5 points

Stores prior snapshot in cache/beat_predictions_prior.json so we only
alert on transitions, not repeats.

Schedule: daily 5:45am PT (after predictor runs at 5:40).
"""
from __future__ import annotations
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
LOG_FILE = BASE / "cache" / "logs" / "alert_beat_strong.log"
PRIOR_PATH = BASE / "cache" / "beat_predictions_prior.json"
CURRENT_PATH = BASE / "data" / "earnings_beat_predictions.json"

LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [beat_alert] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


def _load_env() -> None:
    p = BASE / ".env"
    if not p.exists(): return
    for line in p.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def main(score_jump_threshold: float = 5.0) -> int:
    _load_env()

    if not CURRENT_PATH.exists():
        log.warning("No earnings_beat_predictions.json — predictor hasn't run yet")
        return 0

    cur = json.loads(CURRENT_PATH.read_text())
    cur_preds = {p["ticker"]: p for p in (cur.get("predictions") or [])}
    cur_strong = {t: p for t, p in cur_preds.items() if p.get("tier") == "STRONG"}

    # Load prior snapshot (may not exist on first run)
    prior_strong: dict = {}
    if PRIOR_PATH.exists():
        try:
            prior_data = json.loads(PRIOR_PATH.read_text())
            prior_strong = {p["ticker"]: p
                            for p in (prior_data.get("predictions") or [])
                            if p.get("tier") == "STRONG"}
        except Exception as ex:
            log.debug(f"prior parse: {ex}")

    # Detect new STRONG entries + significant score jumps within STRONG
    new_strong = []
    big_jumps = []
    for t, p in cur_strong.items():
        if t not in prior_strong:
            new_strong.append(p)
        else:
            old_score = prior_strong[t].get("beat_score", 0)
            new_score = p.get("beat_score", 0)
            if new_score - old_score >= score_jump_threshold:
                big_jumps.append({**p, "_old_score": old_score})

    # Snapshot today's predictions for tomorrow's comparison
    PRIOR_PATH.parent.mkdir(parents=True, exist_ok=True)
    PRIOR_PATH.write_text(json.dumps(cur, default=str))

    if not new_strong and not big_jumps:
        log.info(f"No STRONG transitions today (cur STRONG: {len(cur_strong)})")
        return 0

    lines = []
    for p in new_strong:
        bd = p.get("breakdown") or {}
        runup = bd.get("runup_10d", {}).get("value", "n/a")
        sec = bd.get("sector_beats", {}).get("sector", "?")
        lines.append(
            f"*{p['ticker']}* — score *{p['beat_score']:.0f}* · "
            f"reports {p['report_date']} ({p['days_to_earnings']}d, {p['before_after'] or '—'}) · "
            f"runup {runup}% · sector {sec}"
        )
    for p in big_jumps:
        lines.append(
            f"⬆ *{p['ticker']}* — score climbed *{p['_old_score']:.0f} → {p['beat_score']:.0f}* · "
            f"reports {p['report_date']} ({p['days_to_earnings']}d)"
        )

    n = len(new_strong) + len(big_jumps)
    title = f"🎯  New STRONG beat-prediction{'s' if n > 1 else ''}  ·  {n}"
    body = ("—" * 21 + "\n" + "\n".join(lines)
            + "\n💡 V2 dashboard → 📅 Earnings → 'STRONG only' filter")

    log.info(title); log.info(body)
    try:
        from alerts import send_alert
        send_alert("WARN", title, body, force_slack=True)
    except Exception as ex:
        log.warning(f"Slack failed: {ex}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
