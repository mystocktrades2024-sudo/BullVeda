#!/usr/bin/env python3
"""Daily 5pm EOD summary → Slack. A lightweight end-of-day wrap that reads existing
state (cache/last_bundle.json + data/portfolio_state.json) — NO scan, NO EODHD/API
cost. Posts: regime, top BUY/Elite picks, portfolio equity + day P&L + open positions.
Reads SLACK_WEBHOOK_URL from .env. Fired by com.swingtrade.eod-summary at 17:00 PT.
"""
from __future__ import annotations
import json
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "cache" / "last_bundle.json"
PORT = ROOT / "data" / "portfolio_state.json"
DASH = "https://trade.mystockholding.com"


def _webhook() -> str | None:
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("SLACK_WEBHOOK_URL="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def _load(p):
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def main() -> int:
    b = _load(BUNDLE)
    p = _load(PORT)
    when = datetime.now().strftime("%a %b %-d · %-I:%M %p PT")

    regime = (b.get("market") or {}).get("regime4") or b.get("regime4") or "—"
    vix = (b.get("market") or {}).get("vix") or "—"
    buys = sorted((b.get("buy_candidates") or []), key=lambda r: -(r.get("score") or 0))
    elite = b.get("elite_picks") or []
    buy_str = " · ".join(f"{x.get('ticker')}({x.get('score')})" for x in buys[:5]) or "_none_"
    elite_str = " · ".join((e.get("ticker") if isinstance(e, dict) else str(e)) for e in elite[:5]) or "_none_"

    equity = p.get("equity")
    cash = p.get("cash")
    positions = p.get("positions") or []
    day_pnl = p.get("day_pnl") or p.get("daily_pnl")
    pos_str = ", ".join(f"{x.get('ticker')}" for x in positions[:8]) or "_flat_"
    eq_str = f"${equity:,.0f}" if isinstance(equity, (int, float)) else "—"
    pnl_str = (f"{'+' if (day_pnl or 0) >= 0 else ''}${day_pnl:,.0f}"
               if isinstance(day_pnl, (int, float)) else "—")

    blocks = [
        {"type": "section", "text": {"type": "mrkdwn",
         "text": f"🌆 *EOD Summary* — {when}\nRegime *{regime}* · VIX {vix}"}},
        {"type": "section", "text": {"type": "mrkdwn",
         "text": f"*🎯 BUY ({len(buys)})*: {buy_str}\n*⭐ Elite*: {elite_str}"}},
        {"type": "section", "text": {"type": "mrkdwn",
         "text": f"*💼 Portfolio*: equity {eq_str} · day P&L {pnl_str} · {len(positions)} open\n{pos_str}"}},
        {"type": "context", "elements": [{"type": "mrkdwn",
         "text": f"end-of-day wrap (no scan) · <{DASH}|Open dashboard ↗>"}]},
    ]
    wh = _webhook()
    if not wh:
        print("SLACK_WEBHOOK_URL not set", file=sys.stderr)
        return 1
    req = urllib.request.Request(wh, data=json.dumps({"blocks": blocks, "text": "EOD summary"}).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        r = urllib.request.urlopen(req, timeout=8)
        print(f"EOD summary posted (HTTP {r.status})")
        return 0
    except Exception as e:
        print(f"EOD summary failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
