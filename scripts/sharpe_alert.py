#!/usr/bin/env python3
"""sharpe_alert.py — Slack alert when watchlist tickers cross Sharpe thresholds.

Compares today's 126d Sharpe vs the prior snapshot (cache/sharpe_alert_state.json)
for every ticker in config.universe.custom_watchlist + any open positions.

Triggers:
  - Cross UP through high_threshold (default 1.5) → momentum building
  - Cross DOWN through low_threshold (default 0.5) → edge degrading
  - Big single-day delta (default ±0.5) → regime change

Slack messages:
  📈 SHARPE UP — TICKER crossed 1.5 (was 1.40, now 1.62)
  📉 SHARPE DOWN — TICKER crossed 0.5 (was 0.61, now 0.42)
  ⚠️  SHARPE SHIFT — TICKER moved 0.7+ in one day (1.20 → 0.50)

Usage:
  python3 scripts/sharpe_alert.py                     # check + alert
  python3 scripts/sharpe_alert.py --dry-run           # show what would be sent
  python3 scripts/sharpe_alert.py --reset             # wipe state file
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

STATE_PATH = REPO / "cache" / "sharpe_alert_state.json"

DEFAULT_HIGH = 1.5
DEFAULT_LOW = 0.5
DEFAULT_DELTA_TRIGGER = 0.5


def _load_state() -> dict:
    if not STATE_PATH.exists():
        return {"last_run_date": None, "tickers": {}}
    try:
        return json.loads(STATE_PATH.read_text())
    except Exception:
        return {"last_run_date": None, "tickers": {}}


def _save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2))


def _build_watchlist() -> list[str]:
    """Watchlist = config.universe.custom_watchlist + open positions."""
    out: set[str] = set()
    cfg = json.loads((REPO / "config" / "config.json").read_text())
    for t in (cfg.get("universe", {}).get("custom_watchlist") or []):
        out.add(t.upper())
    # Add open positions
    pos = REPO / "data" / "portfolio_state.json"
    if pos.exists():
        try:
            ps = json.loads(pos.read_text())
            for p in (ps.get("positions") or []):
                t = p.get("ticker")
                if t and (p.get("status") or "open").lower() == "open":
                    out.add(t.upper())
        except Exception:
            pass
    return sorted(out)


def _slack_post(webhook: str, text: str, blocks: list | None = None) -> bool:
    import urllib.request
    body = {"text": text}
    if blocks:
        body["blocks"] = blocks
    req = urllib.request.Request(
        webhook, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status == 200
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--high", type=float, default=DEFAULT_HIGH)
    ap.add_argument("--low", type=float, default=DEFAULT_LOW)
    ap.add_argument("--delta", type=float, default=DEFAULT_DELTA_TRIGGER)
    args = ap.parse_args()

    if args.reset:
        if STATE_PATH.exists():
            STATE_PATH.unlink()
        print("State reset.")
        return

    from data_archive import load_ticker
    from lib.sharpe_utils import sharpe_annualized

    state = _load_state()
    prior = state.get("tickers") or {}
    today = date.today().isoformat()

    watchlist = _build_watchlist()
    print(f"Watchlist: {len(watchlist)} tickers")

    alerts: list[dict] = []
    new_state: dict[str, dict] = {}
    for sym in watchlist:
        try:
            df = load_ticker(sym)
        except Exception:
            continue
        if df is None or len(df) < 127:
            continue
        closes = df["close"].astype(float).tolist() if "close" in df.columns else df["Close"].astype(float).tolist()
        sh, _, _ = sharpe_annualized(closes, lookback=126)
        if sh is None:
            continue
        new_state[sym] = {"sharpe": sh, "date": today}

        prior_sh = (prior.get(sym) or {}).get("sharpe")
        if prior_sh is None:
            continue  # first observation — no comparison yet

        # Cross-up through high threshold
        if prior_sh < args.high <= sh:
            alerts.append({
                "ticker": sym, "type": "up", "msg": f"📈 SHARPE UP — {sym} crossed {args.high} ({prior_sh:.2f} → {sh:.2f})",
                "prior": prior_sh, "now": sh,
            })
        # Cross-down through low threshold
        elif prior_sh > args.low >= sh:
            alerts.append({
                "ticker": sym, "type": "down", "msg": f"📉 SHARPE DOWN — {sym} crossed {args.low} ({prior_sh:.2f} → {sh:.2f})",
                "prior": prior_sh, "now": sh,
            })
        # Big single-snapshot delta
        elif abs(sh - prior_sh) >= args.delta:
            arrow = "↗︎" if sh > prior_sh else "↘︎"
            alerts.append({
                "ticker": sym, "type": "shift", "msg": f"⚠️  SHARPE SHIFT — {sym} {arrow} {abs(sh - prior_sh):.2f} ({prior_sh:.2f} → {sh:.2f})",
                "prior": prior_sh, "now": sh,
            })

    print(f"\n{len(alerts)} alerts triggered:")
    for a in alerts:
        print(f"  {a['msg']}")

    # Send to Slack (unless dry run)
    if alerts and not args.dry_run:
        webhook = ""
        try:
            from secrets_loader import get_secret as _gs
            webhook = _gs("SLACK_WEBHOOK_URL", default="")
        except Exception:
            pass
        if webhook:
            text = "*SwingTrade — Sharpe Alerts*"
            blocks = [
                {"type": "section", "text": {"type": "mrkdwn", "text": text}}
            ]
            for a in alerts:
                blocks.append({"type": "section",
                               "text": {"type": "mrkdwn", "text": a["msg"]}})
            ok = _slack_post(webhook, text=text, blocks=blocks)
            print(f"\nSlack: {'sent' if ok else 'FAILED'}")
        else:
            print("\nNo SLACK_WEBHOOK_URL configured — skipping Slack push.")

    # Persist state
    state["last_run_date"] = today
    state["tickers"] = new_state
    _save_state(state)
    print(f"\nState saved: {STATE_PATH}")


if __name__ == "__main__":
    main()
