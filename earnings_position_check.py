#!/usr/bin/env python3
"""
earnings_position_check.py — daily risk alert for open positions about
to report earnings.

Cross-references portfolio_state.json open positions × earnings_watchlist.
For each position reporting in <=3 days, sends a CRITICAL Slack alert
with position size and a decision prompt.

Schedule: daily 5:35am PT (5 min after build_earnings_watchlist refreshes
the list).
"""
from __future__ import annotations
import json
import logging
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
LOG_FILE = BASE / "cache" / "logs" / "earnings_position_check.log"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [earn_pos_check] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


def main(warning_days: int = 3) -> int:
    # Load .env so SLACK_WEBHOOK_URL is in os.environ
    env_path = BASE / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

    # Open positions
    pf_path = BASE / "data" / "portfolio_state.json"
    if not pf_path.exists():
        log.info("No portfolio_state.json — nothing to check")
        return 0
    pf = json.loads(pf_path.read_text())
    positions = [p for p in (pf.get("positions") or []) if p.get("status") == "OPEN"]
    if not positions:
        log.info("0 open positions")
        return 0

    # Earnings watchlist
    ew_path = BASE / "data" / "earnings_watchlist.json"
    if not ew_path.exists():
        log.warning("No earnings_watchlist.json — run build_earnings_watchlist.py first")
        return 1
    ew = json.loads(ew_path.read_text())
    by_ticker = {x["ticker"]: x for x in (ew.get("watchlist") or [])}

    # Cross-reference
    risks = []
    for p in positions:
        t = p.get("ticker", "").upper()
        ew_entry = by_ticker.get(t)
        if not ew_entry:
            continue
        days = ew_entry.get("days_to_earnings")
        if days is None or days > warning_days:
            continue
        risks.append({**p, **ew_entry, "_days": days})

    if not risks:
        log.info(f"All {len(positions)} positions clear of earnings within {warning_days}d")
        return 0

    # Build Slack alert
    lines = []
    for r in risks:
        t = r.get("ticker")
        shares = r.get("shares") or 0
        entry = r.get("entry") or r.get("entry_price") or 0
        size = shares * entry
        rep_date = r.get("report_date")
        when = r.get("before_after_market") or ""
        when_short = "BMO" if when == "BeforeMarket" else "AMC" if when == "AfterMarket" else (when or "?")
        lines.append(
            f"*{t}* — reports {rep_date} ({r['_days']}d, {when_short})  ·  "
            f"{shares} shares @ ${entry:.2f}  ·  size ${size:,.0f}"
        )

    body = (
        "Open positions reporting in next "
        f"{warning_days}d:\n\n" + "\n".join(lines) +
        "\n\nDecision: hold through, trim half, or hedge with options."
    )
    title = f"⚠️ EARNINGS RISK ({len(risks)} position{'s' if len(risks) != 1 else ''})"

    log.info(f"Slack: {title}")
    log.info(body)

    try:
        from alerts import send_alert
        send_alert("CRITICAL", title, body)
        log.info("Slack alert sent")
    except Exception as e:
        log.warning(f"Slack failed: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main(warning_days=3))
