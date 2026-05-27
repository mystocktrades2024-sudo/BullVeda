#!/usr/bin/env python3
"""
morning_catalyst_digest.py — pre-scan Slack digest of today's catalysts.

Fires at 05:55 PT (after dq-checks + thematic + corporate-events + earnings +
beatpredict; before daily-scan at 06:00). Single Slack message covering:
  · Today's earnings reports (BMO / AMC)
  · STRONG-tier beat predictions
  · IPOs starting today
  · Splits today
  · Open positions in earnings blackout window
  · Insider clusters (when output is available)

Idempotent per day via data/morning_catalyst_state.json hash.

Usage:
  python3 scripts/morning_catalyst_digest.py
  python3 scripts/morning_catalyst_digest.py --dry-run
  python3 scripts/morning_catalyst_digest.py --force      # ignore dedupe
"""
from __future__ import annotations
import argparse, hashlib, json, os, sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WL_PATH      = REPO / "data" / "earnings_watchlist.json"
BEAT_PATH    = REPO / "data" / "earnings_beat_predictions.json"
EVENTS_PATH  = REPO / "cache" / "corporate_events.json"
PORT_PATH    = REPO / "data" / "portfolio_state.json"
INSIDER_PATH = REPO / "cache" / "insider_clusters.json"
STATE_PATH   = REPO / "data" / "morning_catalyst_state.json"
DASHBOARD    = "https://trade.mystockholding.com"


def _webhook() -> str | None:
    env = REPO / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line.startswith("SLACK_WEBHOOK_URL="):
                return line.split("=", 1)[1].strip()
    return os.environ.get("SLACK_WEBHOOK_URL")


def _slack(webhook: str, payload: dict) -> bool:
    try:
        import requests
        return requests.post(webhook, json=payload, timeout=8).status_code == 200
    except Exception as e:
        print(f"slack post failed: {e}", file=sys.stderr)
        return False


def _safe_load(p: Path) -> dict | list | None:
    try: return json.loads(p.read_text()) if p.exists() else None
    except Exception: return None


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _todays_earnings() -> list:
    d = _safe_load(WL_PATH) or {}
    wl = d.get("watchlist") or []
    today = _today()
    return sorted(
        [w for w in wl if w.get("report_date") == today],
        key=lambda r: (r.get("before_after_market") != "BeforeMarket", r.get("ticker") or ""),
    )


def _strong_beat_picks(max_days: int = 14) -> list:
    d = _safe_load(BEAT_PATH) or {}
    preds = d.get("predictions") or []
    rows = [p for p in preds
            if (p.get("tier") or "").upper() == "STRONG"
            and 0 <= (p.get("days_to_earnings") or 99) <= max_days]
    rows.sort(key=lambda r: (r.get("days_to_earnings") or 99, -(r.get("beat_score") or 0)))
    return rows[:10]


def _todays_ipos_splits() -> tuple[list, list]:
    d = _safe_load(EVENTS_PATH) or {}
    today = _today()
    ipos = [i for i in (d.get("ipos") or []) if i.get("start_date") == today]
    splits = [s for s in (d.get("splits") or []) if s.get("split_date") == today]
    return ipos, splits


def _blackout_positions(max_days: int = 3) -> list:
    """Open positions with earnings ≤ N days out."""
    pos = (_safe_load(PORT_PATH) or {}).get("positions") or []
    if not pos: return []
    wl = (_safe_load(WL_PATH) or {}).get("watchlist") or []
    earn = {w["ticker"]: w for w in wl if w.get("ticker") and w.get("days_to_earnings") is not None}
    out = []
    for p in pos:
        tk = p.get("ticker")
        w = earn.get(tk)
        if w and 0 <= w.get("days_to_earnings", 99) <= max_days:
            out.append({**p, "report_date": w.get("report_date"),
                       "days_to_earnings": w.get("days_to_earnings"),
                       "before_after_market": w.get("before_after_market")})
    return out


def _insider_clusters() -> list:
    """Read insider-cluster output. Empty list until weekly job has fired."""
    d = _safe_load(INSIDER_PATH) or {}
    rows = d.get("clusters") or d.get("rows") or []
    # Top 5 by net buy count or amount
    rows.sort(key=lambda r: -(r.get("net_count_30d") or r.get("net_amount_30d") or 0))
    return rows[:5]


def _fmt_dollar(v):
    if v is None: return "—"
    try: v = float(v)
    except Exception: return "—"
    if v >= 1e9: return f"${v/1e9:.1f}B"
    if v >= 1e6: return f"${v/1e6:.1f}M"
    if v >= 1e3: return f"${v/1e3:.0f}k"
    return f"${v:.0f}"


def _build_payload(earnings, beats, ipos, splits, blackout, insiders) -> dict:
    when = datetime.now().strftime("%a %b %-d · %-I:%M %p PT")
    blocks = [
        {"type": "section", "text": {"type": "mrkdwn",
            "text": f"🌅 *Morning Catalyst Digest* — {when}"}},
        {"type": "context", "elements": [{"type": "mrkdwn",
            "text": "Today's catalysts · fires before 06:00 PT swing scan"}]},
        {"type": "divider"},
    ]

    # Section: today's earnings
    if earnings:
        bmo = [e for e in earnings if e.get("before_after_market") == "BeforeMarket"]
        amc = [e for e in earnings if e.get("before_after_market") == "AfterMarket"]
        body_lines = []
        if bmo:
            body_lines.append("*Before market (BMO):* "
                + ", ".join(f"`{e['ticker']}` est ${e.get('estimate'):.2f}"
                            if e.get("estimate") is not None else f"`{e['ticker']}`"
                            for e in bmo[:12]))
        if amc:
            body_lines.append("*After market (AMC):* "
                + ", ".join(f"`{e['ticker']}` est ${e.get('estimate'):.2f}"
                            if e.get("estimate") is not None else f"`{e['ticker']}`"
                            for e in amc[:12]))
        blocks.append({"type": "section", "text": {"type": "mrkdwn",
            "text": f"*📊 Earnings today ({len(earnings)})*\n" + "\n".join(body_lines)}})

    # Section: STRONG beat predictions
    if beats:
        body = "\n".join(
            f"`{b['ticker']:<5}` *{b['beat_score']:.0f}* · {b['days_to_earnings']}d to earnings · {b.get('before_after','')}"
            for b in beats[:8]
        )
        blocks.append({"type": "section", "text": {"type": "mrkdwn",
            "text": f"*🎯 STRONG beat predictions ({len(beats)})*\n{body}"}})

    # Section: IPOs / Splits
    if ipos or splits:
        body_lines = []
        if ipos:
            body_lines.append(f"*IPOs ({len(ipos)}):* " +
                ", ".join(f"`{i['code'].replace('.US','')}` ({_fmt_dollar(i.get('price_from'))}–{_fmt_dollar(i.get('price_to'))})"
                          for i in ipos[:8]))
        if splits:
            body_lines.append(f"*Splits ({len(splits)}):* " +
                ", ".join(f"`{s['code'].replace('.US','')}` {s.get('_ratio','')}{'⚠ rev' if s.get('_is_reverse') else ''}"
                          for s in splits[:10]))
        blocks.append({"type": "section", "text": {"type": "mrkdwn",
            "text": f"*📅 Corporate events today*\n" + "\n".join(body_lines)}})

    # Section: blackout positions (most actionable — exit BEFORE earnings)
    if blackout:
        body = "\n".join(
            f"⚠️ `{p['ticker']:<5}` reports *in {p['days_to_earnings']}d* ({p.get('before_after_market','?')}) — review exit"
            for p in blackout
        )
        blocks.append({"type": "section", "text": {"type": "mrkdwn",
            "text": f"*🛑 Open positions in earnings blackout ({len(blackout)})*\n{body}"}})

    # Section: insider clusters (when available)
    if insiders:
        body = "\n".join(
            f"`{c.get('ticker','—'):<5}` net buys *{c.get('net_count_30d',0)}* · {_fmt_dollar(c.get('net_amount_30d',0))}"
            for c in insiders
        )
        blocks.append({"type": "section", "text": {"type": "mrkdwn",
            "text": f"*💰 Top insider clusters*\n{body}"}})

    blocks.append({"type": "context", "elements": [{"type": "mrkdwn",
        "text": f"<{DASHBOARD}|Open dashboard ↗>"}]})

    text_fallback = f"Morning catalysts: {len(earnings)} earnings · {len(beats)} strong beats · {len(ipos)} IPOs · {len(splits)} splits · {len(blackout)} blackout positions"
    return {"text": text_fallback, "blocks": blocks}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force",   action="store_true")
    args = ap.parse_args()

    earnings = _todays_earnings()
    beats    = _strong_beat_picks()
    ipos, splits = _todays_ipos_splits()
    blackout = _blackout_positions()
    insiders = _insider_clusters()

    if not (earnings or beats or ipos or splits or blackout or insiders):
        print("nothing actionable today — skip post")
        return 0

    # Dedupe per day
    h = hashlib.md5(("|".join(
        [_today()]
        + [e.get("ticker","") for e in earnings]
        + [b.get("ticker","") for b in beats]
        + [i.get("code","") for i in ipos]
        + [s.get("code","") for s in splits]
        + [p.get("ticker","") for p in blackout]
        + [c.get("ticker","") for c in insiders]
    )).encode()).hexdigest()[:16]

    state = {}
    if STATE_PATH.exists():
        try: state = json.loads(STATE_PATH.read_text())
        except Exception: pass
    if not args.force and state.get("last_hash") == h:
        print(f"skip: dedupe hash {h} matches prior")
        return 0

    payload = _build_payload(earnings, beats, ipos, splits, blackout, insiders)

    if args.dry_run:
        print(json.dumps(payload, indent=2, default=str))
        return 0

    webhook = _webhook()
    if not webhook:
        print("SLACK_WEBHOOK_URL not set", file=sys.stderr)
        return 2

    if not _slack(webhook, payload):
        print("slack post failed", file=sys.stderr)
        return 1

    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps({
        "last_hash": h,
        "last_posted_at": datetime.now().isoformat(),
    }, indent=2))
    print(f"posted morning-catalyst hash={h}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
