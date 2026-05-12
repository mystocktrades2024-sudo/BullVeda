#!/usr/bin/env python3
"""
morning_briefing.py — daily Slack digest of in-zone trading opportunities.

Reads infra/prototype/tickers.json (refreshed by /Swing-Trade) and sends
a single Slack message at market open listing:
  - All FRESH/PULLBACK setups (act-now bucket)
  - All VALID setups (acceptable fallback)
  - Per-ticker: score · entry zone · stop · T1 · setup · sector

Designed for ~8am PT cron via launchd (before 9:30am ET market open).
Single digest per day — quieter than per-ticker real-time alerts and
matches the disciplined trader workflow of pre-placing limit orders
before the bell rings.

Roll back: delete the launchd plist, or set --dry-run.

Usage:
  python3 scripts/morning_briefing.py               # send real Slack msg
  python3 scripts/morning_briefing.py --dry-run     # print to stdout only
  python3 scripts/morning_briefing.py --min-score N # only score >= N (default 60)
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

TICKERS_PATH = REPO / "infra" / "prototype" / "tickers.json"
STATE_PATH = REPO / "data" / "morning_briefings"
STATE_PATH.mkdir(parents=True, exist_ok=True)


def _load_env_webhook() -> str | None:
    """Read SLACK_WEBHOOK_URL from .env, falling back to env var."""
    env_file = REPO / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("SLACK_WEBHOOK_URL="):
                return line.split("=", 1)[1].strip()
    return os.environ.get("SLACK_WEBHOOK_URL")


def _slack_post(webhook: str, payload: dict) -> bool:
    """POST to Slack webhook. Returns success."""
    try:
        import requests
        r = requests.post(webhook, json=payload, timeout=8)
        return r.status_code == 200
    except Exception as e:
        print(f"slack post failed: {e}", file=sys.stderr)
        return False


def _classify(tickers: dict, min_score: int) -> tuple[list, list, dict]:
    """Return (in_zone_list, near_zone_list, summary_stats).
    in_zone = entry_quality in [FRESH, PULLBACK].
    near_zone = entry_quality == VALID.
    Both exclude killed/AVOID tickers and require score >= min_score.
    """
    in_zone: list[dict] = []
    near_zone: list[dict] = []
    rank = {"FRESH": 5, "PULLBACK": 4, "VALID": 3}
    for sym, t in tickers.items():
        if not isinstance(t, dict):
            continue
        if t.get("killed") or t.get("verdict") == "AVOID" or t.get("stage") == "AVOID":
            continue
        score = t.get("score")
        if not score or score < min_score:
            continue
        eq = (t.get("entry_quality") or "").upper()
        if eq not in rank:
            continue
        row = {
            "ticker": t.get("ticker") or sym,
            "score": float(score),
            "entry_quality": eq,
            "rank": rank.get(eq, 0),
            "setup_family": (t.get("setup_family") or "").strip(),
            "sector": (t.get("sector") or "").strip(),
            "price": t.get("price"),
            "entry_low": t.get("entry_low"),
            "entry_high": t.get("entry_high"),
            "stop": t.get("stop") or (t.get("trade_plan") or {}).get("stop"),
            "target1": t.get("t1") or (t.get("trade_plan") or {}).get("target1"),
            "target2": t.get("t2") or (t.get("trade_plan") or {}).get("target2"),
            "rr": t.get("rr") or (t.get("trade_plan") or {}).get("rr_ratio"),
            "verdict": t.get("verdict"),
            "star_rating": t.get("star_rating"),
        }
        if eq == "VALID":
            near_zone.append(row)
        else:
            in_zone.append(row)
    in_zone.sort(key=lambda r: (-r["rank"], -r["score"]))
    near_zone.sort(key=lambda r: -r["score"])
    summary = {
        "n_in_zone": len(in_zone),
        "n_near_zone": len(near_zone),
        "n_universe": len(tickers),
    }
    return in_zone, near_zone, summary


def _fmt_row(r: dict) -> str:
    """One-line Slack row for a setup."""
    px = r["price"] or 0
    lo = r["entry_low"] or 0
    hi = r["entry_high"] or 0
    stop = r["stop"] or 0
    t1 = r["target1"] or 0
    rr = r["rr"] or 0
    star = ("★" * int(r["star_rating"] or 0)) + ("☆" * (5 - int(r["star_rating"] or 0)))
    setup = (r["setup_family"] or "—")[:18]
    return (
        f"`{r['ticker']:<6}` *{r['entry_quality']:<8}* "
        f"score `{int(r['score']):>3}` {star}  "
        f"${px:.2f}  zone ${lo:.2f}-${hi:.2f}  "
        f"stop ${stop:.2f}  T1 ${t1:.2f}  R:R {rr:.1f}  "
        f"_{setup}_"
    )


def _build_blocks(in_zone: list, near_zone: list, summary: dict, scan_time: str) -> list:
    """Slack Block Kit blocks for digest."""
    today = datetime.now().strftime("%Y-%m-%d %a")
    blocks: list = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"⚡ Kairos Morning Briefing · {today}"},
        },
        {
            "type": "context",
            "elements": [{
                "type": "mrkdwn",
                "text": (
                    f"*{summary['n_in_zone']}* IN-ZONE NOW (FRESH/PULLBACK) · "
                    f"*{summary['n_near_zone']}* near-zone (VALID) · "
                    f"universe {summary['n_universe']} · last scan {scan_time}"
                ),
            }],
        },
        {"type": "divider"},
    ]
    if in_zone:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*⚡ ACT NOW — FRESH/PULLBACK setups*"},
        })
        # Slack section blocks have 3000-char limit per text — chunk if needed
        chunks: list[list[str]] = [[]]
        cur_len = 0
        for r in in_zone[:25]:  # cap at 25 to avoid Slack overflow
            line = _fmt_row(r)
            if cur_len + len(line) + 2 > 2800:
                chunks.append([])
                cur_len = 0
            chunks[-1].append(line)
            cur_len += len(line) + 2
        for chunk in chunks:
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": "\n".join(chunk) or "—"},
            })
    else:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text":
                "_No FRESH/PULLBACK setups today. Wait for pullback before chasing extended leaders._"},
        })

    if near_zone:
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn",
                     "text": "*◇ Acceptable — VALID entry quality*"},
        })
        lines = [_fmt_row(r) for r in near_zone[:10]]
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "\n".join(lines) or "—"},
        })

    blocks.append({"type": "divider"})
    blocks.append({
        "type": "context",
        "elements": [{
            "type": "mrkdwn",
            "text": (
                "Discipline reminder: pre-place limit orders at `entry_low`. "
                "Hard stop = `stop` (close-based). "
                "Scale out at T1, runner with trailing stop past +2%. "
                "Skip if your stack >3 active positions."
            ),
        }],
    })
    return blocks


def _record_state(in_zone: list, near_zone: list) -> None:
    """Audit log: save today's briefing to data/morning_briefings/<date>.json."""
    today = datetime.now().strftime("%Y-%m-%d")
    p = STATE_PATH / f"{today}.json"
    p.write_text(json.dumps({
        "date": today,
        "sent_at": datetime.now().isoformat(),
        "n_in_zone": len(in_zone),
        "n_near_zone": len(near_zone),
        "in_zone_tickers": [r["ticker"] for r in in_zone],
        "near_zone_tickers": [r["ticker"] for r in near_zone],
    }, indent=2, default=str))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-score", type=int, default=60,
                    help="Minimum composite score (default 60 = WATCH-eligible floor)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print briefing to stdout, do not send Slack")
    ap.add_argument("--max-age-hours", type=int, default=24,
                    help="Refuse to send if tickers.json older than this (default 24h)")
    args = ap.parse_args()

    if not TICKERS_PATH.exists():
        print(f"ERROR: {TICKERS_PATH} not found — run /Swing-Trade first", file=sys.stderr)
        sys.exit(1)

    # Staleness check
    import time
    mtime = TICKERS_PATH.stat().st_mtime
    age_h = (time.time() - mtime) / 3600
    if age_h > args.max_age_hours and not args.dry_run:
        print(f"ERROR: tickers.json is {age_h:.1f}h old (> {args.max_age_hours}h) — abort", file=sys.stderr)
        sys.exit(2)

    tickers = json.loads(TICKERS_PATH.read_text())
    in_zone, near_zone, summary = _classify(tickers, args.min_score)
    scan_time = datetime.fromtimestamp(mtime).strftime("%m/%d %H:%M")
    blocks = _build_blocks(in_zone, near_zone, summary, scan_time)

    if args.dry_run:
        print(f"--- DRY RUN ---")
        print(f"Date: {datetime.now()}")
        print(f"In-zone: {summary['n_in_zone']}")
        print(f"Near-zone: {summary['n_near_zone']}")
        print()
        for r in in_zone[:25]:
            print(_fmt_row(r))
        print()
        if near_zone:
            print("--- NEAR ZONE ---")
            for r in near_zone[:10]:
                print(_fmt_row(r))
        return

    webhook = _load_env_webhook()
    if not webhook:
        print("ERROR: SLACK_WEBHOOK_URL not configured", file=sys.stderr)
        sys.exit(3)

    fallback_text = (
        f"⚡ Kairos Morning Briefing · {summary['n_in_zone']} in-zone · "
        f"{summary['n_near_zone']} near-zone"
    )
    payload = {"text": fallback_text, "blocks": blocks}
    if _slack_post(webhook, payload):
        _record_state(in_zone, near_zone)
        print(f"Briefing sent: {summary['n_in_zone']} in-zone + {summary['n_near_zone']} near-zone")
    else:
        print("ERROR: Slack post failed", file=sys.stderr)
        sys.exit(4)


if __name__ == "__main__":
    main()
