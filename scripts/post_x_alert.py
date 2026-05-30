#!/usr/bin/env python3
"""
post_x_alert.py — Slack alert when a tracked X handle mentions a ticker we
hold (live position) or that the engine ranks top-100 in the latest scan.

Idempotent: state stored in data/x_alert_state.json holds the set of
(handle, ticker, post_link) tuples already alerted on. Re-running won't
duplicate.

Source-of-truth files:
  cache/x_signal.json              — tracked X chatter (built by build_x_signal.py)
  cache/portfolio.json             — held positions (live + paper)
  cache/last_bundle.json           — top-100 ranked tickers (all_scored sorted)

Usage:
  python3 scripts/post_x_alert.py
  python3 scripts/post_x_alert.py --dry-run        # stdout only
  python3 scripts/post_x_alert.py --top-n 50       # tighter watchlist
"""
from __future__ import annotations
import argparse, hashlib, json, os, sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
XS_PATH        = REPO / "cache" / "x_signal.json"
PORTFOLIO_PATH = REPO / "cache" / "portfolio.json"
BUNDLE_PATH    = REPO / "cache" / "last_bundle.json"
STATE_PATH     = REPO / "data" / "x_alert_state.json"
DASHBOARD_URL  = "https://trade.mystockholding.com"


def _load_env_webhook():
    env_file = REPO / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("SLACK_WEBHOOK_URL="):
                return line.split("=", 1)[1].strip()
    return os.environ.get("SLACK_WEBHOOK_URL")


def _slack_post(webhook, payload):
    try:
        import requests
        r = requests.post(webhook, json=payload, timeout=8)
        return r.status_code in (200, 201)
    except Exception as e:
        print(f"slack post failed: {e}", file=sys.stderr)
        return False


def _load_held_tickers():
    if not PORTFOLIO_PATH.exists(): return set()
    try:
        p = json.loads(PORTFOLIO_PATH.read_text())
        held = set()
        for pos in p.get("positions", []) or []:
            t = (pos.get("ticker") or pos.get("symbol") or "").upper()
            if t: held.add(t)
        return held
    except Exception:
        return set()


def _load_top_ranked(top_n):
    if not BUNDLE_PATH.exists(): return set(), {}
    try:
        b = json.loads(BUNDLE_PATH.read_text())
        scored = b.get("all_scored", []) or []
        ranked = sorted(scored, key=lambda x: -(x.get("score") or 0))[:top_n]
        return (set(x.get("ticker") for x in ranked if x.get("ticker")),
                {x.get("ticker"): (x.get("score"), x.get("verdict")) for x in ranked})
    except Exception:
        return set(), {}


def _load_state():
    if not STATE_PATH.exists():
        return {"alerted_keys": [], "_meta": {}}
    try:
        return json.loads(STATE_PATH.read_text())
    except Exception:
        return {"alerted_keys": [], "_meta": {}}


def _save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--top-n", type=int, default=100)
    args = ap.parse_args()

    if not XS_PATH.exists():
        print(f"no x_signal cache at {XS_PATH}; nothing to alert on", file=sys.stderr)
        sys.exit(0)
    xs = json.loads(XS_PATH.read_text())
    recent = xs.get("recent_posts", []) or []
    if not recent:
        print("no recent posts; nothing to alert on")
        sys.exit(0)

    held    = _load_held_tickers()
    top, top_map = _load_top_ranked(args.top_n)
    state   = _load_state()
    seen    = set(tuple(k) if isinstance(k, list) else k for k in state.get("alerted_keys", []))

    # Build candidate alerts — each (handle, ticker, link) is a unique key
    alerts = []
    for post in recent:
        ticker  = (post.get("ticker") or "").upper()
        handle  = post.get("handle", "")
        link    = post.get("link", "")
        excerpt = post.get("title", "")
        key = f"{handle}|{ticker}|{link}"
        if key in seen: continue
        in_held = ticker in held
        in_top  = ticker in top
        if not (in_held or in_top): continue
        rank_info = ""
        if in_top:
            sc, vd = top_map.get(ticker, (None, None))
            rank_info = f" · scan {sc or '—'} {vd or ''}"
        alerts.append({
            "ticker": ticker, "handle": handle, "link": link, "excerpt": excerpt[:200],
            "ts": post.get("ts", ""),
            "tag": "💼 HELD" if in_held else "🎯 TOP",
            "rank_info": rank_info,
            "_key": key,
        })

    if not alerts:
        print("no new tracked-handle hits on held/top-ranked tickers")
        sys.exit(0)

    # Build Slack payload — single message with all new hits
    lines = [f"🐦 *X CHATTER ALERT — {len(alerts)} new hit{'s' if len(alerts)!=1 else ''}*"]
    by_ticker = {}
    for a in alerts: by_ticker.setdefault(a["ticker"], []).append(a)
    for t in sorted(by_ticker, key=lambda x: -len(by_ticker[x])):
        rows = by_ticker[t]
        tag = rows[0]["tag"]; ri = rows[0]["rank_info"]
        lines.append(f"\n*{tag}  ${t}*{ri}")
        for a in rows[:3]:
            lines.append(f"   @{a['handle']}: {a['excerpt'][:120]}")
        if len(rows) > 3:
            lines.append(f"   …+{len(rows)-3} more from {len(set(r['handle'] for r in rows))} handles")
    lines.append(f"\n<{DASHBOARD_URL}|Open dashboard →>")

    payload = {"text": "\n".join(lines), "username": "Kairos · X Chatter", "icon_emoji": ":bird:"}

    if args.dry_run:
        print("DRY RUN — would post:\n" + "\n".join(lines))
        sys.exit(0)

    webhook = _load_env_webhook()
    if not webhook:
        print("no SLACK_WEBHOOK_URL; printing instead:")
        print("\n".join(lines))
        sys.exit(0)
    ok = _slack_post(webhook, payload)
    if ok:
        for a in alerts: seen.add(a["_key"])
        state["alerted_keys"] = sorted(seen)
        state["_meta"] = {"last_post_at": datetime.now(timezone.utc).isoformat(), "alerts_count": len(alerts)}
        _save_state(state)
        print(f"posted {len(alerts)} alerts across {len(by_ticker)} tickers")
    else:
        print("slack post failed", file=sys.stderr); sys.exit(2)


if __name__ == "__main__":
    main()
