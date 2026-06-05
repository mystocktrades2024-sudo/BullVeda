#!/usr/bin/env python3
"""Dedicated SMC-only Slack ping — posts the top Smart-Money-Concepts confluence
candidates (from cache/smc_scan.json, built by build_smc_scan.py) as a focused
message, separate from the combined scan digest. Fired once after the morning SMC
scan. Reads SLACK_WEBHOOK_URL from .env. No API cost.
"""
from __future__ import annotations
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SMC = ROOT / "cache" / "smc_scan.json"
DASH = "https://trade.mystockholding.com"


def _webhook() -> str | None:
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("SLACK_WEBHOOK_URL="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def main() -> int:
    if not SMC.exists():
        print("no smc_scan.json — skipping SMC ping", file=sys.stderr)
        return 0
    d = json.loads(SMC.read_text())
    cands = sorted(d.get("candidates") or [], key=lambda r: -(r.get("smc_score") or 0))[:10]
    if not cands:
        print("no SMC candidates — skipping", file=sys.stderr)
        return 0
    gen = (d.get("_meta") or {}).get("generated_at", "")
    lines = []
    for i, c in enumerate(cands, 1):
        px = c.get("price")
        pxs = f"${px:.2f}" if isinstance(px, (int, float)) else "—"
        fac = ", ".join(c.get("factors") or []) or "—"
        lines.append(f"`{c['ticker']:<5}` {pxs:>8}  smc *{c.get('smc_score',0):.0f}*  · {fac}")
    body = "\n".join(lines)
    payload = {
        "blocks": [
            {"type": "section", "text": {"type": "mrkdwn",
             "text": f"*🧩 SMC / PATTERNS — top {len(cands)}*  _(order blocks · BoS/CHoCH · sweeps · MTF)_\n{body}"}},
            {"type": "context", "elements": [{"type": "mrkdwn",
             "text": f"smc_engine confluence · {gen} · <{DASH}|Open dashboard ↗>"}]},
        ],
        "text": f"SMC top {len(cands)}",
    }
    wh = _webhook()
    if not wh:
        print("SLACK_WEBHOOK_URL not set", file=sys.stderr)
        return 1
    req = urllib.request.Request(wh, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        r = urllib.request.urlopen(req, timeout=8)
        print(f"SMC ping posted (HTTP {r.status}) · {len(cands)} candidates")
        return 0
    except Exception as e:
        print(f"SMC ping failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
