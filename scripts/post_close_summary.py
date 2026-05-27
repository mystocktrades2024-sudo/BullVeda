#!/usr/bin/env python3
"""
post_close_summary.py — 17:00 PT digest after market close + snapshot cluster.

Single Slack message covering:
  · Equity / P&L delta today (vs start of day)
  · Closed trades today (winners / losers)
  · Sharpe-kill verdict
  · Closed earnings positions today (beat / miss)
  · Drift verdict (RR, WR, volume compliance)

Idempotent per day via data/post_close_state.json hash.
"""
from __future__ import annotations
import argparse, hashlib, json, os, sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PORT_PATH      = REPO / "data" / "portfolio_state.json"
SHARPE_PATH    = REPO / "cache" / "sharpe_kill_state.json"
DRIFT_PATH     = REPO / "cache" / "drift_report.json"
OUTCOMES_PATH  = REPO / "data" / "earnings_outcomes.jsonl"
BUNDLE_PATH    = REPO / "cache" / "last_bundle.json"
STATE_PATH     = REPO / "data" / "post_close_state.json"
DASHBOARD      = "https://trade.mystockholding.com"


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
        print(f"slack post failed: {e}", file=sys.stderr); return False


def _safe_load(p: Path):
    try: return json.loads(p.read_text()) if p.exists() else None
    except Exception: return None


def _today() -> str: return datetime.now().strftime("%Y-%m-%d")


def _portfolio_today() -> dict:
    p = _safe_load(PORT_PATH) or {}
    today = _today()
    closed_all = p.get("closed_trades") or []
    closed_today = [
        t for t in closed_all
        if str(t.get("close_date") or t.get("exit_date") or "").startswith(today)
    ]
    wins   = [t for t in closed_today if (t.get("realized_pnl") or t.get("pnl") or 0) > 0]
    losses = [t for t in closed_today if (t.get("realized_pnl") or t.get("pnl") or 0) < 0]
    pnl_today = sum((t.get("realized_pnl") or t.get("pnl") or 0) for t in closed_today)
    equity_curve = p.get("equity_curve") or []
    eq_today_open = next((e.get("equity") for e in reversed(equity_curve)
                          if str(e.get("date","")).startswith(today)), None)
    return {
        "equity":   p.get("equity"),
        "starting": p.get("starting_equity"),
        "n_closed_today": len(closed_today),
        "wins": wins, "losses": losses,
        "pnl_today": pnl_today,
        "eq_today_open": eq_today_open,
        "open_positions": len(p.get("positions") or []),
    }


def _sharpe_state() -> dict:
    s = _safe_load(SHARPE_PATH) or {}
    return {
        "active": bool(s.get("active")),
        "sharpe": s.get("sharpe"),
        "n":      s.get("n"),
        "avg_pnl": s.get("avg_pnl"),
        "reason": s.get("reason"),
    }


def _drift_state() -> dict:
    d = _safe_load(DRIFT_PATH) or {}
    comp = d.get("compliance") or {}
    return {
        "wr_pass":  (comp.get("wr") or {}).get("pass"),
        "wr_actual": (comp.get("wr") or {}).get("actual"),
        "rr_pass":  (comp.get("rr") or {}).get("pass"),
        "rr_actual": (comp.get("rr") or {}).get("actual"),
        "vol_pass": (comp.get("volume") or {}).get("pass"),
        "vol_actual": (comp.get("volume") or {}).get("actual"),
        "as_of":    d.get("as_of"),
    }


def _earnings_outcomes_today() -> list:
    if not OUTCOMES_PATH.exists(): return []
    today = _today()
    rows = []
    try:
        for line in OUTCOMES_PATH.read_text().splitlines():
            if not line.strip(): continue
            try: r = json.loads(line)
            except Exception: continue
            captured = str(r.get("captured_at") or r.get("report_date") or "")
            if captured.startswith(today):
                rows.append(r)
    except Exception: pass
    return rows


def _scan_summary() -> dict:
    b = _safe_load(BUNDLE_PATH) or {}
    return {
        "regime": (b.get("regime") or {}).get("regime4", "—"),
        "buy_count": len(b.get("buy_candidates") or []),
        "watch_count": len(b.get("watch_list") or []),
        "vix": (b.get("regime") or {}).get("vix", {}).get("vix_current"),
    }


def _build_payload(port, sharpe, drift, outcomes, scan) -> dict:
    when = datetime.now().strftime("%a %b %-d · %-I:%M %p PT")
    blocks = [
        {"type": "section", "text": {"type": "mrkdwn",
            "text": f"🌆 *Post-Close Summary* — {when}"}},
        {"type": "context", "elements": [{"type": "mrkdwn",
            "text": f"After-market view · Regime *{scan.get('regime','—')}* · VIX *{scan.get('vix','—')}*"}]},
        {"type": "divider"},
    ]

    # P&L
    pnl_arrow = "🟢" if (port["pnl_today"] or 0) >= 0 else "🔴"
    total_pnl = (port["equity"] or 0) - (port["starting"] or 0) if port["equity"] and port["starting"] else None
    body = (
        f"*Equity now:* ${port['equity']:.2f}" if port["equity"] else "*Equity now:* —"
    )
    if total_pnl is not None:
        body += f"  (lifetime {'+'  if total_pnl>=0 else ''}{total_pnl:.2f})"
    body += f"\n*P&L today:* {pnl_arrow} {'+' if port['pnl_today']>=0 else ''}${port['pnl_today']:.2f}"
    body += f"\n*Closed today:* {port['n_closed_today']} ({len(port['wins'])}W / {len(port['losses'])}L)"
    body += f"\n*Open positions:* {port['open_positions']}"
    blocks.append({"type": "section", "text": {"type": "mrkdwn",
        "text": f"*💰 Portfolio*\n{body}"}})

    # Winners / Losers
    if port["wins"] or port["losses"]:
        win_lines = "\n".join(
            f"  ✅ `{t.get('ticker','—')}` +${(t.get('realized_pnl') or t.get('pnl') or 0):.2f}  "
            f"({((t.get('realized_pnl') or t.get('pnl') or 0) / (t.get('entry') or 1) * 100 if t.get('entry') else 0):.1f}%)"
            for t in sorted(port["wins"], key=lambda x: -(x.get("realized_pnl") or x.get("pnl") or 0))[:5]
        )
        loss_lines = "\n".join(
            f"  ❌ `{t.get('ticker','—')}` ${(t.get('realized_pnl') or t.get('pnl') or 0):.2f}  "
            f"({((t.get('realized_pnl') or t.get('pnl') or 0) / (t.get('entry') or 1) * 100 if t.get('entry') else 0):.1f}%)"
            for t in sorted(port["losses"], key=lambda x: (x.get("realized_pnl") or x.get("pnl") or 0))[:5]
        )
        body = (win_lines or "  (none)") + ("\n\n" + loss_lines if loss_lines else "")
        blocks.append({"type": "section", "text": {"type": "mrkdwn",
            "text": f"*🎯 Today's exits*\n{body}"}})

    # Sharpe kill
    if sharpe["sharpe"] is not None or sharpe["active"]:
        st = "🛑 KILL ACTIVE" if sharpe["active"] else "✅ Healthy"
        line = f"{st} · Sharpe: {sharpe['sharpe']:.2f}" if sharpe['sharpe'] is not None else f"{st} · {sharpe['reason']}"
        if sharpe["n"]: line += f" · n={sharpe['n']}"
        blocks.append({"type": "section", "text": {"type": "mrkdwn",
            "text": f"*📈 Rolling Sharpe gate*\n{line}"}})

    # Drift
    if drift["wr_actual"] is not None or drift["rr_actual"] is not None:
        def chk(p, a, label, fmt="{:.1f}"):
            if a is None: return f"  · {label}: —"
            icon = "✅" if p else "⚠️"
            return f"  {icon} {label}: " + fmt.format(a)
        body = "\n".join([
            chk(drift["wr_pass"],  drift["wr_actual"],  "Win rate", "{:.1f}%"),
            chk(drift["rr_pass"],  drift["rr_actual"],  "R:R",      "{:.2f}"),
            chk(drift["vol_pass"], drift["vol_actual"], "Trades/mo", "{:.1f}"),
        ])
        blocks.append({"type": "section", "text": {"type": "mrkdwn",
            "text": f"*📊 Drift compliance* (as of {drift.get('as_of','—')})\n{body}"}})

    # Earnings outcomes
    if outcomes:
        beats   = [o for o in outcomes if o.get("beat") is True]
        misses  = [o for o in outcomes if o.get("beat") is False]
        body = (
            f"  Beats: {len(beats)}  Misses: {len(misses)}\n"
            + ", ".join(f"`{o['ticker']}` " + ("✅" if o.get("beat") else "❌")
                        + (f"+{o.get('surprise_pct'):.1f}%" if o.get('surprise_pct') is not None else "")
                        for o in outcomes[:12])
        )
        blocks.append({"type": "section", "text": {"type": "mrkdwn",
            "text": f"*📰 Today's earnings outcomes ({len(outcomes)})*\n{body}"}})

    # End-of-day scan
    body = (
        f"BUY *{scan['buy_count']}* · WATCH *{scan['watch_count']}* · "
        f"Regime *{scan['regime']}*"
    )
    blocks.append({"type": "section", "text": {"type": "mrkdwn",
        "text": f"*🌅 EOD scan (15:00 PT)*\n{body}"}})

    blocks.append({"type": "context", "elements": [{"type": "mrkdwn",
        "text": f"<{DASHBOARD}|Open dashboard ↗>"}]})

    text_fallback = (
        f"Post-close: equity ${port.get('equity', 0):.0f} · "
        f"{port['n_closed_today']} closed today · "
        f"{('SHARPE KILL ACTIVE' if sharpe['active'] else 'sharpe ok')}"
    )
    return {"text": text_fallback, "blocks": blocks}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force",   action="store_true")
    args = ap.parse_args()

    port = _portfolio_today()
    sharpe = _sharpe_state()
    drift = _drift_state()
    outcomes = _earnings_outcomes_today()
    scan = _scan_summary()

    h = hashlib.md5("|".join([
        _today(),
        str(port["equity"]), str(port["n_closed_today"]),
        str(sharpe["active"]), str(sharpe["sharpe"]),
        str(len(outcomes)), str(scan["buy_count"]),
    ]).encode()).hexdigest()[:16]

    state = _safe_load(STATE_PATH) or {}
    if not args.force and state.get("last_hash") == h:
        print(f"skip: dedupe hash {h} matches")
        return 0

    payload = _build_payload(port, sharpe, drift, outcomes, scan)

    if args.dry_run:
        print(json.dumps(payload, indent=2, default=str))
        return 0

    webhook = _webhook()
    if not webhook:
        print("SLACK_WEBHOOK_URL not set", file=sys.stderr); return 2

    if not _slack(webhook, payload):
        return 1

    STATE_PATH.write_text(json.dumps({
        "last_hash": h, "last_posted_at": datetime.now().isoformat(),
    }, indent=2))
    print(f"posted post-close hash={h}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
