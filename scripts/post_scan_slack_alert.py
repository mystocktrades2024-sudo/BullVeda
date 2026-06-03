#!/usr/bin/env python3
"""
post_scan_slack_alert.py — single Slack digest fired after every daily scan.

Sections:
  1. SWING — top 5 BUY candidates from cache/last_bundle.json (buy_candidates[])
  2. OPTIONS FLOW — top 5 from infra/prototype/options_flow.json (top30[])
  3. MOMENTUM — top 5 by rank from data/momentum_snapshots.jsonl (today's date)
  4. ML EDGE — top 5 by verdict.edge from cache/ml_edge_predictions.json

Idempotent per scan-run: keeps a hash of (run_timestamp + top tickers) in
data/slack_alert_state.json so re-running within the same scan window won't
duplicate messages.

Usage:
  python3 scripts/post_scan_slack_alert.py                  # post real Slack msg
  python3 scripts/post_scan_slack_alert.py --dry-run        # stdout only
  python3 scripts/post_scan_slack_alert.py --scan-tag 06:30 # label scan window
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BUNDLE_PATH = REPO / "cache" / "last_bundle.json"
OPTIONS_PATH = REPO / "infra" / "prototype" / "options_flow.json"
MOMENTUM_PATH = REPO / "data" / "momentum_snapshots.jsonl"
ML_EDGE_PATH = REPO / "cache" / "ml_edge_predictions.json"
SMC_PATH = REPO / "cache" / "smc_scan.json"
STATE_PATH = REPO / "data" / "slack_alert_state.json"
DASHBOARD_URL = "https://trade.mystockholding.com"


def _load_env_webhook() -> str | None:
    env_file = REPO / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("SLACK_WEBHOOK_URL="):
                return line.split("=", 1)[1].strip()
    return os.environ.get("SLACK_WEBHOOK_URL")


def _slack_post(webhook: str, payload: dict) -> bool:
    try:
        import requests
        r = requests.post(webhook, json=payload, timeout=8)
        return r.status_code == 200
    except Exception as e:
        print(f"slack post failed: {e}", file=sys.stderr)
        return False


def _swing_picks() -> tuple[list, str, dict]:
    try:
        b = json.loads(BUNDLE_PATH.read_text())
    except Exception:
        return [], "", {}
    buys = sorted(b.get("buy_candidates") or [], key=lambda r: -(r.get("score") or 0))[:5]
    rows = []
    for p in buys:
        tp = p.get("trade_plan") or {}
        rows.append({
            "ticker": p.get("ticker", ""),
            "price": p.get("price"),
            "score": p.get("score"),
            "rs": p.get("rs_rank_63d") or p.get("rs_rank"),
            "setup": p.get("setup_family") or p.get("setup") or "—",
            "sector": (p.get("sector") or "—")[:14],
            "entry": tp.get("entry_zone") or p.get("entry") or "—",
            "stop":  tp.get("stop") or tp.get("stop_loss"),
            "t1":    tp.get("target1") or tp.get("t1"),
        })
    regime = (b.get("regime") or {})
    regime4 = regime.get("regime4", "—")
    vix = (regime.get("vix") or {}).get("vix_current", "—")
    return rows, b.get("run_timestamp", "—"), {"regime4": regime4, "vix": vix}


def _options_picks() -> list:
    try:
        d = json.loads(OPTIONS_PATH.read_text())
    except Exception:
        return []
    top = d.get("top30") or []
    # Sort by status STRONG → SOLID → BUILDING then by total premium, take 5
    rank = {"STRONG": 3, "SOLID": 2, "BUILDING": 1}
    top = sorted(top, key=lambda r: (-rank.get(r.get("status", ""), 0),
                                      -(r.get("premium_total_$") or 0)))[:5]
    rows = []
    for o in top:
        rows.append({
            "ticker": o.get("ticker", ""),
            "price": o.get("price"),
            "status": o.get("status", ""),
            "iv_pct": o.get("iv_percentile"),
            "pcr": o.get("put_call_ratio"),
            "atm_strike": o.get("atm_strike"),
            "atm_dte": o.get("atm_dte"),
            "premium": o.get("premium_total_$"),
            "rr": o.get("rr"),
            "target": o.get("target"),
            "stop": o.get("stop"),
            "sector": (o.get("sector") or "—")[:14],
        })
    return rows


def _momentum_picks() -> list:
    if not MOMENTUM_PATH.exists(): return []
    today = datetime.now().strftime("%Y-%m-%d")
    rows = []
    try:
        for line in MOMENTUM_PATH.read_text().splitlines():
            if not line.strip(): continue
            try: r = json.loads(line)
            except Exception: continue
            if r.get("date") == today and r.get("rank"):
                rows.append(r)
    except Exception:
        return []
    if not rows:
        return []
    # The jsonl is APPEND-only — each scan writes a fresh top-N batch, so a single
    # day holds several batches (all stamped with that scan's _written_at). Taking
    # rank<=5 across the whole day produced duplicate ranks/tickers (e.g. two #1s).
    # Keep ONLY the latest batch (max _written_at), then dedup by ticker as a safety.
    latest_ts = max((r.get("_written_at") or "") for r in rows)
    if latest_ts:
        rows = [r for r in rows if (r.get("_written_at") or "") == latest_ts]
    seen: dict = {}
    for r in rows:
        t = (r.get("ticker") or "").upper()
        if not t:
            continue
        if t not in seen or (r.get("rank") or 99) < (seen[t].get("rank") or 99):
            seen[t] = r
    out = sorted(seen.values(), key=lambda r: r.get("rank") or 99)
    return out[:5]


def _ml_edge_picks() -> list:
    try:
        d = json.loads(ML_EDGE_PATH.read_text())
    except Exception:
        return []
    swing = (d.get("predictions") or {}).get("swing") or {}
    rows = []
    for tk, v in swing.items():
        if not isinstance(v, dict): continue
        # `predictions.swing` is {ticker: {A: {...} | ...}} OR a flat dict
        verdict = v.get("verdict") if "verdict" in v else (v.get("A") or {}).get("verdict")
        if not isinstance(verdict, dict): continue
        edge = verdict.get("edge")
        if edge is None: continue
        rows.append({
            "ticker": tk,
            "edge": edge,
            "verdict": verdict.get("text", "—"),
            "level": verdict.get("level", "—"),
            "conf": verdict.get("confidence", "—"),
        })
    # Top 5 by edge magnitude — bullish-leaning takes priority
    rows.sort(key=lambda r: -(r["edge"] or 0))
    return rows[:5]


def _smc_picks() -> list:
    """Top 5 SMC confluence candidates from cache/smc_scan.json (build_smc_scan.py)."""
    if not SMC_PATH.exists():
        return []
    try:
        d = json.loads(SMC_PATH.read_text())
    except Exception:
        return []
    cands = d.get("candidates") or []
    cands.sort(key=lambda r: -(r.get("smc_score") or 0))
    return cands[:5]


def _fmt_money(v):
    if v is None: return "—"
    try: v = float(v)
    except Exception: return "—"
    if v >= 1e6: return f"${v/1e6:.1f}M"
    if v >= 1e3: return f"${v/1e3:.0f}k"
    return f"${v:.0f}"


def _fmt_px(v):
    if v is None: return "—"
    try: return f"${float(v):.2f}"
    except Exception: return str(v)


def _build_payload(scan_tag: str, swing, swing_ts, regime_info,
                   options, momentum, ml_edge, smc) -> dict:
    # Header
    when = datetime.now().strftime("%a %b %-d · %-I:%M %p PT")
    header = f"📊 *SwingTrade · {scan_tag} scan* — {when}"
    sub = f"Regime: *{regime_info.get('regime4','—')}* · VIX *{regime_info.get('vix','—')}* · " \
          f"Bundle ts: {swing_ts}"

    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": header}},
        {"type": "context", "elements": [{"type": "mrkdwn", "text": sub}]},
        {"type": "divider"},
    ]

    # 1) Swing top 5
    if swing:
        body = "\n".join(
            f"`{p['ticker']:<5}` {_fmt_px(p['price']):>8}  sc *{p['score']:.0f}*  "
            f"RS {p['rs'] if p['rs'] is not None else '—'}  · "
            f"{p['setup'][:22]}  ({p['sector']})\n"
            f"          entry {p['entry']}  stop {_fmt_px(p['stop'])}  T1 {_fmt_px(p['t1'])}"
            for p in swing
        )
    else:
        body = "_no BUY candidates this scan_"
    blocks.append({"type": "section", "text": {"type": "mrkdwn",
        "text": f"*🎯 SWING — top {len(swing)} BUY*\n{body}"}})

    # 2) Options flow top 5
    if options:
        body = "\n".join(
            f"`{o['ticker']:<5}` {_fmt_px(o['price']):>8}  *{o['status']}*  "
            f"PCR {o['pcr']:.2f}  ATM {_fmt_px(o['atm_strike'])} ({int(o['atm_dte'] or 0)}d)  · "
            f"{_fmt_money(o['premium'])}  RR {o['rr']:.1f}x  ({o['sector']})"
            for o in options if o.get("pcr") is not None
        )
    else:
        body = "_no options flow data_"
    blocks.append({"type": "section", "text": {"type": "mrkdwn",
        "text": f"*📈 OPTIONS FLOW — top {len(options)}*\n{body}"}})

    # 3) Momentum top 5
    if momentum:
        body = "\n".join(
            f"`{m['ticker']:<5}` {_fmt_px(m['price']):>8}  comp *{m['composite']:.1f}*  "
            f"Sh126d {m['sharpe_126d']:.2f}  RS {m['rs_rank']:.0f}  · "
            f"{m.get('setup','—')[:22]}  ({m.get('sector','—')[:14]})"
            for m in momentum
        )
    else:
        body = "_no momentum snapshot yet today_"
    blocks.append({"type": "section", "text": {"type": "mrkdwn",
        "text": f"*🚀 MOMENTUM — top {len(momentum)}*\n{body}"}})

    # 4) ML Edge top 5
    if ml_edge:
        body = "\n".join(
            f"`{r['ticker']:<5}`  edge *{r['edge']:+.1f}*  "
            f"{r['verdict']}/{r['level']}  conf {r['conf']}"
            for r in ml_edge
        )
    else:
        body = "_no ML edge predictions_"
    blocks.append({"type": "section", "text": {"type": "mrkdwn",
        "text": f"*🤖 ML EDGE — top {len(ml_edge)} (5d horizon)*\n{body}"}})

    # 5) SMC / Patterns top 5 (server-side smc_engine confluence — 0 EODHD)
    if smc:
        body = "\n".join(
            f"`{s['ticker']:<5}` {_fmt_px(s.get('price')):>8}  smc *{s.get('smc_score',0):.0f}*  · "
            f"{', '.join(s.get('factors') or []) or '—'}"
            for s in smc
        )
    else:
        body = "_no SMC scan yet today_"
    blocks.append({"type": "section", "text": {"type": "mrkdwn",
        "text": f"*🧩 SMC / PATTERNS — top {len(smc)}*\n{body}"}})

    blocks.append({"type": "context", "elements": [{"type": "mrkdwn",
        "text": f"<{DASHBOARD_URL}|Open dashboard ↗>"}]})

    return {"text": f"SwingTrade {scan_tag} scan — {when}", "blocks": blocks}


def _dedupe_hash(swing, options, momentum, ml_edge, bundle_ts: str, smc=None) -> str:
    """Hash top-ticker symbols + bundle timestamp → don't double-post same scan."""
    keys = [bundle_ts]
    keys += [p["ticker"] for p in swing]
    keys += [o["ticker"] for o in options]
    keys += [m["ticker"] for m in momentum]
    keys += [r["ticker"] for r in ml_edge]
    keys += [s["ticker"] for s in (smc or [])]
    return hashlib.md5("|".join(keys).encode()).hexdigest()[:16]


def _load_state() -> dict:
    if not STATE_PATH.exists(): return {}
    try: return json.loads(STATE_PATH.read_text())
    except Exception: return {}


def _save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, default=str))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan-tag", default="manual",
                    help="Label for this scan run (e.g. '06:30', '11:00')")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print payload to stdout instead of posting")
    ap.add_argument("--force", action="store_true",
                    help="Post even if dedupe hash matches prior run")
    args = ap.parse_args()

    swing, bundle_ts, regime_info = _swing_picks()
    options = _options_picks()
    momentum = _momentum_picks()
    ml_edge = _ml_edge_picks()
    smc = _smc_picks()

    if not (swing or options or momentum or ml_edge or smc):
        print("nothing to post — all sources empty", file=sys.stderr)
        return 0

    h = _dedupe_hash(swing, options, momentum, ml_edge, bundle_ts, smc)
    state = _load_state()
    if not args.force and state.get("last_hash") == h:
        print(f"skip: dedupe hash {h} matches prior — use --force to override")
        return 0

    payload = _build_payload(args.scan_tag, swing, bundle_ts, regime_info,
                             options, momentum, ml_edge, smc)

    if args.dry_run:
        print(json.dumps(payload, indent=2, default=str))
        return 0

    webhook = _load_env_webhook()
    if not webhook:
        print("SLACK_WEBHOOK_URL not set", file=sys.stderr)
        return 2

    ok = _slack_post(webhook, payload)
    if not ok:
        print("slack post failed", file=sys.stderr)
        return 1

    state["last_hash"] = h
    state["last_posted_at"] = datetime.now().isoformat()
    state["last_scan_tag"] = args.scan_tag
    _save_state(state)
    print(f"posted scan={args.scan_tag} hash={h}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
