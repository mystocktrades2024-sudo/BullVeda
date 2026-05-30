#!/usr/bin/env python3
"""
ml_alert_slack.py — post ML pipeline status to Slack with detail.

Modes:
  --mode close-loop      summary of label resolution (daily 7pm PT)
  --mode weekly-retrain  summary of train + gate decisions (Sundays 3am PT)
  --mode swing-stale     ad-hoc alert if any model goes >7 days stale

Auto-detects what changed by reading the latest artifacts:
  cache/ml/close_loop_report.json
  cache/ml/champion_metrics.json
  cache/ml/promotion_log.jsonl   (last entry)
  cache/ml/calibration_report_historical.json

Reads SLACK_WEBHOOK_URL from .env (fail-soft if missing).

Usage:
    python3 scripts/ml_alert_slack.py --mode close-loop
    python3 scripts/ml_alert_slack.py --mode weekly-retrain
    python3 scripts/ml_alert_slack.py --mode close-loop --always   (force even if 0 resolved)
    python3 scripts/ml_alert_slack.py --dry-run --mode weekly-retrain
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ART = ROOT / "cache" / "ml"


def _load_dotenv() -> None:
    p = ROOT / ".env"
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip().strip('"').strip("'")
        os.environ.setdefault(k.strip(), v)


def _slack_post(text: str, blocks: list | None = None, dry_run: bool = False) -> bool:
    webhook = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    if not webhook:
        print("[ml-alert] no SLACK_WEBHOOK_URL — skipping post")
        return False
    payload = {"text": text}
    if blocks:
        payload["blocks"] = blocks
    if dry_run:
        print("[ml-alert] DRY RUN — would post:")
        print(json.dumps(payload, indent=2))
        return True
    req = urllib.request.Request(
        webhook,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return 200 <= r.status < 300
    except urllib.error.HTTPError as e:
        print(f"[ml-alert] slack HTTP {e.code}: {e.reason}")
        return False
    except Exception as e:
        print(f"[ml-alert] slack post failed: {e}")
        return False


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _read_last_jsonl(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        last = None
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        last = json.loads(line)
                    except json.JSONDecodeError:
                        continue
        return last
    except Exception:
        return None


def _sample_resolved(n: int = 3) -> list[dict]:
    """Read the N most recently resolved picks for a 'flavor' sample."""
    p = ROOT / "cache" / "ml_edge_picks_history.jsonl"
    if not p.exists():
        return []
    out = []
    try:
        with open(p) as f:
            for line in f:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if r.get("status") == "resolved" and r.get("realized_pct") is not None:
                    out.append({
                        "t":    r.get("ticker"),
                        "mode": r.get("mode"),
                        "pct":  r.get("realized_pct"),
                    })
    except Exception:
        return []
    # Sort by abs(pct) descending — show biggest moves
    out.sort(key=lambda x: abs(x.get("pct") or 0), reverse=True)
    return out[:n]


def _check_model_staleness() -> dict:
    """Return {mode: days_stale} for each of 3 modes."""
    today = datetime.now(timezone.utc)
    out = {}
    for mode in ("swing", "position", "invest"):
        p = ART / f"{mode}_direction.pkl"
        if not p.exists():
            out[mode] = -1
            continue
        days = (today - datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)).days
        out[mode] = days
    return out


# ─── Mode: close-loop ───────────────────────────────────────────────────────

def alert_close_loop(dry_run: bool, always: bool) -> bool:
    report = _read_json(ART / "close_loop_report.json")
    if not report:
        print("[ml-alert] no close_loop_report.json — skip")
        return False

    resolved = report.get("resolved_now", 0)
    if resolved == 0 and not always:
        print("[ml-alert] 0 picks resolved — skip (use --always to force)")
        return False

    by_mode = report.get("by_mode", {})
    samples = _sample_resolved(3)

    # Build block kit message
    header = f"🔁 ML close-loop · {resolved} picks resolved"
    fields = []
    for m in ("swing", "position", "invest"):
        if by_mode.get(m, 0) > 0:
            fields.append(f"*{m}*\n{by_mode[m]}")
    if not fields:
        fields = [f"*resolved*\n{resolved}"]

    sample_lines = []
    for s in samples:
        pct = s.get("pct") or 0
        emoji = "📈" if pct >= 0 else "📉"
        sample_lines.append(f"{emoji} `{s['t']}` ({s['mode']}) *{pct:+.2f}%*")
    sample_block = "\n".join(sample_lines) if sample_lines else "_no samples_"

    skipped = report.get("skipped_reasons", {})
    pending = skipped.get("too_fresh", 0)

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": header}},
        {"type": "section", "fields": [
            {"type": "mrkdwn", "text": f"*ran*\n{report.get('today', '?')}"},
            {"type": "mrkdwn", "text": f"*pending*\n{pending} (still in horizon)"},
        ] + [{"type": "mrkdwn", "text": f"*{m} resolved*\n{by_mode[m]}"}
             for m in ("swing","position","invest") if by_mode.get(m,0) > 0]},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Biggest moves*\n{sample_block}"}},
        {"type": "context", "elements": [
            {"type": "mrkdwn", "text": f"elapsed {report.get('elapsed_sec','?')}s · feeds the Sunday 3am retrain"}
        ]},
    ]
    return _slack_post(header, blocks=blocks, dry_run=dry_run)


# ─── Mode: weekly-retrain ───────────────────────────────────────────────────

def alert_weekly_retrain(dry_run: bool) -> bool:
    promo = _read_last_jsonl(ART / "promotion_log.jsonl")
    cal = _read_json(ART / "calibration_report_historical.json")
    champion = _read_json(ART / "champion_metrics.json") or {}
    cl = _read_json(ART / "close_loop_report.json") or {}

    if not promo:
        # First-run baseline OR trainer failed
        header = "⚠️ ML weekly retrain · no promotion log"
        blocks = [
            {"type": "header", "text": {"type": "plain_text", "text": header}},
            {"type": "section", "text": {"type": "mrkdwn",
              "text": "_No `promotion_log.jsonl` entry — trainer may have failed before gate. "
                      "Check `/tmp/ml-retrain-weekly.err`._"}},
        ]
        return _slack_post(header, blocks=blocks, dry_run=dry_run)

    decisions = promo.get("decisions", [])
    promoted = [d for d in decisions if d.get("promoted")]
    rejected = [d for d in decisions if not d.get("promoted")]

    if rejected:
        header = f"⚠️ ML retrain · {len(promoted)} promoted, {len(rejected)} REJECTED"
    else:
        header = f"✅ ML retrain · all {len(promoted)} modes promoted"

    # Per-mode detail
    detail_lines = []
    for d in decisions:
        mode = d.get("mode", "?")
        ch_acc = d.get("challenger", {}).get("direction_accuracy", 0)
        ch_auc = d.get("challenger", {}).get("hit_net_auc", 0)
        b_acc = d.get("champion_baseline", {}).get("direction_accuracy", 0)
        b_auc = d.get("champion_baseline", {}).get("hit_net_auc", 0)
        d_acc = ch_acc - b_acc
        d_auc = ch_auc - b_auc
        emoji = "✅" if d.get("promoted") else "❌"
        verdict = "PROMOTED" if d.get("promoted") else "REJECTED"
        reason = d.get("reason", "")
        detail_lines.append(
            f"{emoji} *{mode.upper()}* {verdict}  "
            f"acc {ch_acc:.4f} ({d_acc:+.4f})  "
            f"auc {ch_auc:.4f} ({d_auc:+.4f})  "
            f"_{reason}_"
        )

    # Close-loop snapshot (labels fed into THIS training)
    cl_lines = []
    cl_resolved = cl.get("resolved_now", 0)
    cl_by_mode = cl.get("by_mode", {})
    cl_lines.append(f"*New labels this week:* {cl_resolved} picks  "
                    f"(s={cl_by_mode.get('swing',0)}  p={cl_by_mode.get('position',0)}  i={cl_by_mode.get('invest',0)})")

    # Training dataset
    if cal:
        modes = cal.get("modes", {})
        sw = modes.get("swing", {})
        n_total = sw.get("n_total", 0)
        dr = sw.get("date_range", ["?","?"])
        cl_lines.append(f"*Training window:* {dr[0]} → {dr[1]}  ({n_total:,} rows)")

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": header}},
        {"type": "section", "text": {"type": "mrkdwn",
          "text": "*Per-mode decision*\n" + "\n".join(detail_lines)}},
        {"type": "divider"},
        {"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(cl_lines)}},
        {"type": "context", "elements": [
            {"type": "mrkdwn",
             "text": f"gate ε_acc={promo.get('eps_acc',0.005)}  ε_auc={promo.get('eps_auc',0.005)}  "
                     f"elapsed {promo.get('elapsed_s','?')}s · "
                     f"log: `/tmp/ml-retrain-weekly.log`"}
        ]},
    ]

    # Add staleness check
    stale = _check_model_staleness()
    bad = {m: d for m, d in stale.items() if d > 14}
    if bad:
        bad_lines = [f"`{m}`: {d}d stale" for m, d in bad.items()]
        blocks.insert(-1, {"type": "section", "text": {"type": "mrkdwn",
          "text": "⚠️ *Stale models after retrain:* " + "  ".join(bad_lines)}})

    return _slack_post(header, blocks=blocks, dry_run=dry_run)


# ─── Mode: swing-stale (ad-hoc) ─────────────────────────────────────────────

def alert_swing_stale(dry_run: bool) -> bool:
    stale = _check_model_staleness()
    bad = {m: d for m, d in stale.items() if d > 7}
    if not bad:
        print("[ml-alert] all models < 7d fresh — no alert")
        return False
    header = f"⚠️ ML model staleness · {len(bad)} mode(s) need retrain"
    lines = [f"`{m}_direction.pkl`: *{d} days stale*" for m, d in bad.items()]
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": header}},
        {"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(lines)}},
        {"type": "context", "elements": [
            {"type": "mrkdwn",
             "text": "Run: `bash scripts/ml_weekly_retrain.sh` (5 min) or wait for Sunday 3am PT"}
        ]},
    ]
    return _slack_post(header, blocks=blocks, dry_run=dry_run)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["close-loop", "weekly-retrain", "swing-stale"], required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--always", action="store_true", help="Force send even on no-op")
    args = ap.parse_args()

    _load_dotenv()

    if args.mode == "close-loop":
        ok = alert_close_loop(args.dry_run, args.always)
    elif args.mode == "weekly-retrain":
        ok = alert_weekly_retrain(args.dry_run)
    else:
        ok = alert_swing_stale(args.dry_run)

    print(f"[ml-alert] mode={args.mode} sent={ok}")
    sys.exit(0 if ok else 0)  # Don't fail the calling shell on Slack errors


if __name__ == "__main__":
    main()
