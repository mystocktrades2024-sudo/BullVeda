#!/usr/bin/env python3
"""Real-time intraday entry-zone watcher for Screener-Desk picks -> Slack.

The desk engine (screener_desks.py) logs the day's picks to
data/desk_signal_log.jsonl — each with a desk, direction, entry/stop/t1, EV and
size. This watcher polls live Schwab quotes (zero EODHD) every few minutes and
pings the moment a pick pulls into its entry zone with live R:R clearing the
floor. Alerts are grouped PER DESK and annotated with that desk's edge stats
(WR / PF / n from desk_edge_stats.json) so you see whether the desk is proven.

Mirrors entry_watch.py discipline:
  - Schwab batch + throttle reused from position_alerts (zero EODHD).
  - config gate: {"desk_watch": {"send_enabled": true}} (default False = shadow).
  - one alert per ticker per day (throttled).
  - ALWAYS dry-run from the CLI unless --send.

Usage:
    python3 scripts/desk_entry_watch.py            # dry-run (no Slack)
    python3 scripts/desk_entry_watch.py --send     # live (respects config gate)
"""
from __future__ import annotations
import argparse
import json
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from position_alerts import (          # noqa: E402  reuse zero-EODHD plumbing
    _already_sent_today, _mark_sent, _is_market_hours, _get_schwab_batch,
)

SIGLOG = ROOT / "data" / "desk_signal_log.jsonl"
EDGE = ROOT / "cache" / "desk_edge_stats.json"
CONFIG = ROOT / "config" / "config.json"
SHADOW = ROOT / "cache" / "desk_entry_watch_shadow.jsonl"

DESK_NAMES = {"mom": "Momentum", "bo": "Breakout", "pb": "Pullback",
              "cat": "Catalyst", "mr": "Mean-Reversion", "val": "Value",
              "qual": "Quality", "short": "Short"}
RR_FLOOR = 2.0        # desk picks run lower R:R than the 3:1 swing floor
ZONE_ATR = 0.30       # "in zone" = within 0.30 ATR of the desk entry level


def _cfg() -> dict:
    try:
        return (json.load(open(CONFIG)).get("desk_watch") or {})
    except Exception:
        return {}


def _webhook() -> str | None:
    try:
        for ln in (ROOT / ".env").read_text().splitlines():
            if ln.startswith("SLACK_WEBHOOK_URL="):
                return ln.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return None


def _f(x):
    try:
        return float(x)
    except Exception:
        return None


def _latest_signals() -> list[dict]:
    """Unresolved picks from the most recent logged date, with a full plan."""
    rows = []
    try:
        for ln in SIGLOG.read_text().splitlines():
            if ln.strip():
                rows.append(json.loads(ln))
    except Exception:
        return []
    if not rows:
        return []
    last = max(r.get("date", "") for r in rows)
    out = []
    for r in rows:
        if r.get("date") != last or r.get("resolved"):
            continue
        if all(_f(r.get(k)) for k in ("entry", "stop", "t1")):
            out.append(r)
    return out


def _edge() -> dict:
    try:
        return (json.load(open(EDGE)).get("desks") or {})
    except Exception:
        return {}


def _live_rr(price, sig) -> float | None:
    entry, stop, t1 = _f(sig["entry"]), _f(sig["stop"]), _f(sig["t1"])
    if sig.get("dir") == "short":
        risk = stop - price
        reward = price - t1
    else:
        risk = price - stop
        reward = t1 - price
    if risk and risk > 0 and reward is not None:
        return reward / risk
    return None


def _in_zone(price, sig) -> bool:
    entry = _f(sig["entry"])
    stop = _f(sig["stop"])
    atr = (_f(sig.get("atr_pct")) or 3.0) / 100.0 * entry
    band = ZONE_ATR * atr
    near = abs(price - entry) <= band
    if sig.get("dir") == "short":
        return near and price < stop            # rallied to entry, below stop level
    return near and price > stop                # pulled to entry, above stop


def _edge_str(desk: str, edge: dict) -> str:
    e = edge.get(desk) or {}
    pf = _f(e.get("pf_haircut")) or _f(e.get("pf"))
    wr = _f(e.get("wr_haircut")) or _f(e.get("wr"))
    n = e.get("n")
    if pf is None and wr is None:
        return "edge n/a"
    proven = (pf or 0) >= 1.0 and not e.get("low_sample")
    tag = "✅ proven" if proven else "⚠️ unproven"
    parts = [tag]
    if wr is not None:
        parts.append(f"WR {wr*100:.0f}%")
    if pf is not None:
        parts.append(f"PF {pf:.2f}")
    if n is not None:
        parts.append(f"n={n}")
    return " · ".join(parts)


def build(dry_run: bool):
    if not _is_market_hours() and not dry_run:
        return None, {"skipped": "outside_market_hours"}
    sigs = _latest_signals()
    if not sigs:
        return None, {"skipped": "no_desk_signals"}
    edge = _edge()
    quotes = _get_schwab_batch([s["ticker"] for s in sigs])
    if not quotes:
        return None, {"error": "no_schwab_quotes (token expired? run schwab_auth.py oauth)"}

    triggered, checked, inzone = [], 0, 0
    for s in sigs:
        q = quotes.get(s["ticker"])
        price = _f(q.get("price")) if q else None
        if not price:
            continue
        checked += 1
        if not _in_zone(price, s):
            continue
        inzone += 1
        rr = _live_rr(price, s)
        if not rr or rr < RR_FLOOR:
            continue
        s = {**s, "_price": price, "_rr": rr}
        if not dry_run and _already_sent_today(s["ticker"], f"desk_{s['desk']}"):
            continue
        triggered.append(s)

    stats = {"signals": len(sigs), "checked": checked, "in_zone": inzone,
             "triggered": len(triggered)}
    if not triggered:
        return None, stats

    # group per desk
    by_desk: dict[str, list] = {}
    for s in triggered:
        by_desk.setdefault(s["desk"], []).append(s)

    when = datetime.now().strftime("%a %b %-d · %-I:%M %p PT")
    blocks = [{"type": "section", "text": {"type": "mrkdwn",
               "text": f"🖥️ *Screener-Desk picks entering zone* — {when}\n_{len(triggered)} pick(s) live-triggered on Schwab quotes_"}},
              {"type": "divider"}]
    for desk in sorted(by_desk, key=lambda d: -len(by_desk[d])):
        name = DESK_NAMES.get(desk, desk)
        lines = [f"*{name} desk*  ·  {_edge_str(desk, edge)}"]
        for s in sorted(by_desk[desk], key=lambda x: -(x.get("ev") or 0)):
            arrow = "🔻 SHORT" if s.get("dir") == "short" else "🎯 BUY"
            lines.append(
                f"{arrow} *{s['ticker']}* ${s['_price']:.2f} — entry ${_f(s['entry']):.2f} · "
                f"stop ${_f(s['stop']):.2f} · T1 ${_f(s['t1']):.2f} · R:R {s['_rr']:.1f} · "
                f"EV {s.get('ev', 0):+.2f} · size {s.get('size', 0):.0f}% · {s.get('sector', '')}")
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(lines)}})
        blocks.append({"type": "divider"})
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn",
                   "text": "live Schwab quotes · per-desk edge from desk_edge_stats.json · not advice"}]})
    return {"blocks": blocks, "text": "Desk picks entering zone", "_triggered": triggered}, stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--send", action="store_true", help="actually post (still respects config gate)")
    args = ap.parse_args()
    dry = not args.send

    payload, stats = build(dry_run=dry)
    print(f"desk-watch: {stats}", file=sys.stderr)
    if not payload:
        return 0

    triggered = payload.pop("_triggered")
    if dry:
        print("[DRY-RUN] would post:")
        for b in payload["blocks"]:
            if b["type"] == "section":
                print(b["text"]["text"]); print("-" * 50)
        return 0

    # config gate (shadow unless send_enabled)
    if not bool(_cfg().get("send_enabled", False)):
        for s in triggered:                       # shadow: record, no Slack
            with open(SHADOW, "a") as f:
                f.write(json.dumps({"ts": datetime.now().isoformat(timespec="minutes"),
                                    "ticker": s["ticker"], "desk": s["desk"], "dir": s.get("dir"),
                                    "price": s["_price"], "rr": round(s["_rr"], 2), "ev": s.get("ev")}) + "\n")
        print("shadow mode (desk_watch.send_enabled=false) — logged, no Slack", file=sys.stderr)
        return 0

    wh = _webhook()
    if not wh:
        print("SLACK_WEBHOOK_URL not set", file=sys.stderr)
        return 1
    req = urllib.request.Request(wh, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        r = urllib.request.urlopen(req, timeout=10)
        for s in triggered:
            _mark_sent(s["ticker"], f"desk_{s['desk']}")
        print(f"posted (HTTP {r.status}) · {len(triggered)} picks", file=sys.stderr)
        return 0
    except Exception as e:
        print(f"post failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
