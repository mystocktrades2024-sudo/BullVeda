#!/usr/bin/env python3
"""
weekly_digest.py — Sunday 06:00 PT weekly Slack summary.

Single message covering the prior 7 days:
  · Walk-forward backtest results (this week's run)
  · Options-flow R/horizon win rate (from options_flow_outcomes)
  · Top insider clusters (from cache/insider_cluster.json)
  · Notable congressional trades (from cache/congressional_picks.json)
  · Portfolio P&L for the week
"""
from __future__ import annotations
import argparse, hashlib, json, os, sys
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WF_PATH          = REPO / "cache" / "walk_forward_v2_results.json"
INSIDER_PATH     = REPO / "cache" / "insider_cluster.json"
CONGRESS_PATH    = REPO / "cache" / "congressional_picks.json"
OF_OUTCOMES_PATH = REPO / "data" / "options_flow_outcomes.jsonl"
PORT_PATH        = REPO / "data" / "portfolio_state.json"
STATE_PATH       = REPO / "data" / "weekly_digest_state.json"
DASHBOARD        = "https://trade.mystockholding.com"


def _webhook():
    env = REPO / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("SLACK_WEBHOOK_URL="):
                return line.split("=", 1)[1].strip()
    return os.environ.get("SLACK_WEBHOOK_URL")


def _slack(webhook, payload) -> bool:
    try:
        import requests
        return requests.post(webhook, json=payload, timeout=8).status_code == 200
    except Exception as e:
        print(f"slack post failed: {e}", file=sys.stderr); return False


def _safe_load(p: Path):
    try: return json.loads(p.read_text()) if p.exists() else None
    except Exception: return None


def _walk_forward_summary() -> dict:
    d = _safe_load(WF_PATH) or {}
    return {
        "n_folds": d.get("n_folds"),
        "n_trades": d.get("total_trades"),
        "wr": d.get("aggregate_wr"),
        "wr_ci": d.get("wr_95_ci"),
        "sharpe": d.get("mean_sharpe"),
        "max_dd": d.get("mean_max_dd"),
        "folds": d.get("folds", []),
    }


def _insider_top(n=5) -> list:
    d = _safe_load(INSIDER_PATH) or {}
    rows = d.get("candidates") or d.get("clusters") or []
    rows = sorted(rows, key=lambda r: -(r.get("net_count_30d") or r.get("net_amount_30d") or 0))
    return rows[:n]


def _congress_top(n=5) -> list:
    d = _safe_load(CONGRESS_PATH) or {}
    rows = d.get("picks") or d.get("rows") or []
    rows = sorted(rows, key=lambda r: -(r.get("net_amount") or 0))
    return rows[:n]


def _options_flow_weekly_wr() -> dict:
    if not OF_OUTCOMES_PATH.exists():
        return {"n": 0, "wins": 0, "win_rate": None}
    cutoff = (datetime.now() - timedelta(days=7)).isoformat()
    n = wins = 0
    sum_r = 0.0
    try:
        for line in OF_OUTCOMES_PATH.read_text().splitlines():
            if not line.strip(): continue
            try: r = json.loads(line)
            except Exception: continue
            ts = r.get("captured_at") or r.get("entry_date") or ""
            if str(ts) < cutoff: continue
            n += 1
            r_val = r.get("r") or r.get("realized_r")
            if r_val is None: continue
            if r_val > 0: wins += 1
            sum_r += r_val
    except Exception: pass
    return {
        "n": n,
        "wins": wins,
        "win_rate": (wins/n*100) if n else None,
        "avg_r":   (sum_r/n) if n else None,
    }


def _portfolio_weekly() -> dict:
    p = _safe_load(PORT_PATH) or {}
    closed = p.get("closed_trades") or []
    cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    week = [
        t for t in closed
        if str(t.get("close_date") or t.get("exit_date") or "") >= cutoff
    ]
    wins = [t for t in week if (t.get("realized_pnl") or t.get("pnl") or 0) > 0]
    pnl = sum((t.get("realized_pnl") or t.get("pnl") or 0) for t in week)
    return {
        "n": len(week),
        "wins": len(wins),
        "wr": (len(wins)/len(week)*100) if week else None,
        "pnl": pnl,
        "equity": p.get("equity"),
    }


def _build_payload(wf, of_wr, insiders, congress, port) -> dict:
    when = datetime.now().strftime("%a %b %-d · %-I:%M %p PT")
    blocks = [
        {"type": "section", "text": {"type": "mrkdwn",
            "text": f"📈 *Weekly Digest* — week ending {when}"}},
        {"type": "context", "elements": [{"type": "mrkdwn",
            "text": "7-day summary · fires Sun 06:00 PT"}]},
        {"type": "divider"},
    ]

    # Walk-forward
    if wf and wf.get("n_folds"):
        wr  = wf.get("wr") or 0
        wci = wf.get("wr_ci") or [0, 0]
        body = (
            f"Folds: *{wf['n_folds']}*  · Trades: *{wf.get('n_trades') or 0}*\n"
            f"Aggregate WR: *{wr*100:.1f}%* (95% CI {wci[0]*100:.0f}–{wci[1]*100:.0f}%)\n"
            f"Mean Sharpe: *{wf.get('sharpe', 0):.2f}*  ·  Mean max DD: *{wf.get('max_dd', 0):.1f}%*"
        )
        blocks.append({"type": "section", "text": {"type": "mrkdwn",
            "text": f"*🧪 Walk-forward backtest (4 folds, 250-train / 50-test)*\n{body}"}})

    # Portfolio week
    if port["n"]:
        wr_part = f" · WR *{port['wr']:.0f}%*" if port["wr"] is not None else ""
        body = (
            f"Closed: *{port['n']}* ({port['wins']}W){wr_part}\n"
            f"P&L: {'+' if port['pnl']>=0 else ''}${port['pnl']:.2f}  ·  "
            f"Equity now: ${port.get('equity', 0):.0f}"
        )
        blocks.append({"type": "section", "text": {"type": "mrkdwn",
            "text": f"*💰 Portfolio (last 7d)*\n{body}"}})

    # Options-flow weekly WR
    if of_wr["n"]:
        wr_pct = of_wr["win_rate"] if of_wr["win_rate"] is not None else 0
        avg_r = of_wr["avg_r"] if of_wr["avg_r"] is not None else 0
        body = (
            f"Picks resolved: *{of_wr['n']}*  ·  "
            f"WR: *{wr_pct:.0f}%* ({of_wr['wins']}W)  ·  "
            f"Avg R: *{avg_r:+.2f}*"
        )
        blocks.append({"type": "section", "text": {"type": "mrkdwn",
            "text": f"*📊 Options flow (last 7d)*\n{body}"}})

    # Insider clusters
    if insiders:
        body = "\n".join(
            f"`{c.get('ticker','—'):<5}`  buys *{c.get('net_count_30d', c.get('insiders_count', 0))}*  "
            f"· {c.get('sector','—')[:15]}"
            for c in insiders
        )
        blocks.append({"type": "section", "text": {"type": "mrkdwn",
            "text": f"*💰 Top insider clusters (30d)*\n{body}"}})

    # Congressional
    if congress:
        body = "\n".join(
            f"`{c.get('ticker','—'):<5}`  ${(c.get('net_amount', 0))/1000:.0f}k  "
            f"· {c.get('chamber','—')}  · {c.get('side','—')}"
            for c in congress
        )
        blocks.append({"type": "section", "text": {"type": "mrkdwn",
            "text": f"*🏛 Congressional trades (90d window)*\n{body}"}})

    blocks.append({"type": "context", "elements": [{"type": "mrkdwn",
        "text": f"<{DASHBOARD}|Open dashboard ↗>"}]})

    return {"text": "SwingTrade weekly digest", "blocks": blocks}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force",   action="store_true")
    args = ap.parse_args()

    wf       = _walk_forward_summary()
    of_wr    = _options_flow_weekly_wr()
    insiders = _insider_top()
    congress = _congress_top()
    port     = _portfolio_weekly()

    # Dedupe per Sunday
    h = hashlib.md5("|".join([
        datetime.now().strftime("%Y-W%V"),  # ISO week number
        str(wf.get("n_trades")), str(port["n"]), str(of_wr["n"]),
        str(len(insiders)), str(len(congress)),
    ]).encode()).hexdigest()[:16]

    state = _safe_load(STATE_PATH) or {}
    if not args.force and state.get("last_hash") == h:
        print(f"skip: dedupe hash {h} matches")
        return 0

    payload = _build_payload(wf, of_wr, insiders, congress, port)

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
    print(f"posted weekly hash={h}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
