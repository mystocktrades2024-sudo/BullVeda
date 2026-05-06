#!/usr/bin/env python3
"""Weekly performance review — trades, WR, PF, drift, per-setup attribution.

Run every Friday 4pm ET (launchd entry or cron). Writes
cache/weekly_review_YYYY-WW.md with a human-readable summary and
optionally emails/slacks the summary.

Usage:
  python3 weekly_review.py                  # summarize, write file
  python3 weekly_review.py --slack          # also POST to SLACK_WEBHOOK_URL
  python3 weekly_review.py --weeks-back 4   # trailing 4 weeks instead of 1
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path

_ROOT = Path(__file__).parent


def _load_history() -> dict:
    try:
        from tracker import _load_history as _lh
        return _lh()
    except Exception:
        return {"trades": [], "runs": []}


def _week_filter(trades: list, weeks_back: int) -> list:
    cutoff = datetime.now() - timedelta(days=7 * weeks_back)
    filtered = []
    for t in trades:
        dt_s = str(t.get("exit_date") or t.get("entry_date") or "")[:10]
        if not dt_s:
            continue
        try:
            dt = datetime.fromisoformat(dt_s)
            if dt >= cutoff:
                filtered.append(t)
        except Exception:
            continue
    return filtered


def _summarize(trades: list) -> dict:
    if not trades:
        return {"n": 0}
    wins = [t for t in trades if t.get("win")]
    losses = [t for t in trades if not t.get("win")]
    wp = [t.get("pct_chg", 0) for t in wins]
    lp = [t.get("pct_chg", 0) for t in losses]
    gw = sum(wp)
    gl = abs(sum(lp))
    return {
        "n": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "wr": round(len(wins) / len(trades) * 100, 1),
        "avg_win": round(sum(wp) / len(wp), 2) if wp else 0,
        "avg_loss": round(sum(lp) / len(lp), 2) if lp else 0,
        "pf": round(gw / gl, 2) if gl > 0 else float("inf"),
        "gross_pnl": round(gw - gl, 2),
        "best": max(trades, key=lambda t: t.get("pct_chg", 0)) if trades else None,
        "worst": min(trades, key=lambda t: t.get("pct_chg", 0)) if trades else None,
    }


def _by_dimension(trades: list, key: str) -> dict:
    out: dict = {}
    for t in trades:
        k = t.get(key, "Unknown") or "Unknown"
        out.setdefault(k, []).append(t)
    return {k: _summarize(v) for k, v in out.items() if len(v) >= 2}


def build_report(weeks_back: int = 1) -> str:
    history = _load_history()
    trades = _week_filter(history.get("trades", []), weeks_back)
    overall = _summarize(trades)
    by_setup = _by_dimension(trades, "setup_type")
    by_direction = _by_dimension(trades, "direction")
    by_regime = _by_dimension(trades, "regime4")

    # Backtest baseline for drift context
    try:
        cfg = json.loads((_ROOT / "config" / "config.json").read_text())
        bt_wr = cfg.get("_meta", {}).get("last_backtest_wr")
        bt_wr = bt_wr * 100 if isinstance(bt_wr, (int, float)) else None
    except Exception:
        bt_wr = None

    # Compose markdown
    today = date.today()
    week = today.isocalendar()[1]
    header = f"# SwingTrade Weekly Review — {today} (Week {week})"
    lines = [header, "", f"**Window:** trailing {weeks_back} week(s) · **Trades:** {overall.get('n', 0)}", ""]

    if overall.get("n", 0) == 0:
        lines += ["No closed trades in window. Nothing to review.", ""]
        return "\n".join(lines)

    lines += ["## Overall"]
    lines += [f"- WR: **{overall['wr']}%** ({overall['wins']}W / {overall['losses']}L)"]
    if bt_wr is not None:
        delta = overall["wr"] - bt_wr
        marker = "✓" if abs(delta) <= 5 else "⚠" if abs(delta) <= 15 else "🔴"
        lines += [f"- Drift vs backtest ({bt_wr:.1f}%): {marker} {delta:+.1f} pts"]
    lines += [f"- Profit factor: **{overall['pf']}**"]
    lines += [f"- Avg win: +{overall['avg_win']}% · avg loss: {overall['avg_loss']}%"]
    lines += [f"- Gross P&L: {overall['gross_pnl']}%"]
    if overall.get("best"):
        b = overall["best"]
        lines += [f"- Best: **{b.get('ticker')}** +{b.get('pct_chg', 0):.1f}% ({b.get('setup_type', '')})"]
    if overall.get("worst"):
        w = overall["worst"]
        lines += [f"- Worst: **{w.get('ticker')}** {w.get('pct_chg', 0):.1f}% ({w.get('setup_type', '')})"]
    lines += [""]

    def _section(title: str, data: dict):
        if not data:
            return []
        out = [f"## {title}", "", "| Bucket | N | WR | PF | Avg Win | Avg Loss |", "|---|---|---|---|---|---|"]
        for k, s in sorted(data.items(), key=lambda kv: -kv[1]["n"]):
            out.append(f"| {k} | {s['n']} | {s['wr']}% | {s['pf']} | +{s['avg_win']}% | {s['avg_loss']}% |")
        return out + [""]

    lines += _section("By Setup", by_setup)
    lines += _section("By Direction", by_direction)
    lines += _section("By Regime (regime4)", by_regime)

    # Suggestions
    lines += ["## Suggested Actions"]
    if overall["wr"] < 55:
        lines += ["- 🔴 WR below 55% — tighten entry criteria before next week"]
    if overall["pf"] < 1.5 and overall["pf"] != float("inf"):
        lines += ["- ⚠ Profit factor weak (<1.5) — losses are too big relative to wins"]
    low_setups = [k for k, s in by_setup.items() if s["wr"] < 50 and s["n"] >= 3]
    if low_setups:
        lines += [f"- ⚠ Underperforming setups: {', '.join(low_setups)} — consider disabling or reducing size"]
    if not (overall["wr"] < 55 or overall["pf"] < 1.5 or low_setups):
        lines += ["- ✓ Performance in range — continue mechanical execution"]

    return "\n".join(lines)


def _post_slack(msg: str) -> None:
    try:
        from secrets_loader import get_secret
        url = get_secret("SLACK_WEBHOOK_URL", default="") or os.environ.get("SLACK_WEBHOOK_URL", "")
    except Exception:
        url = os.environ.get("SLACK_WEBHOOK_URL", "")
    if not url:
        print("[slack] SLACK_WEBHOOK_URL not set — skipping")
        return
    try:
        import urllib.request
        data = json.dumps({"text": msg}).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
        print("[slack] posted")
    except Exception as e:
        print(f"[slack] error: {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weeks-back", type=int, default=1)
    ap.add_argument("--slack", action="store_true")
    args = ap.parse_args()

    report = build_report(args.weeks_back)
    print(report)

    out = _ROOT / "cache" / f"weekly_review_{date.today()}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report)
    print(f"\n→ written to {out}")

    if args.slack:
        _post_slack(report[:3000])  # Slack has 4KB limit per message


if __name__ == "__main__":
    main()
