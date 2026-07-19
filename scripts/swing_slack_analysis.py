#!/usr/bin/env python3
"""4-hourly swing analysis -> Slack.

Reads the latest scan bundle (cache/last_bundle.json), takes the top-N swing
candidates, enriches each with LIVE analyst ratings from the web (yfinance,
free), computes rule-based decision flags (the same reads a human analyst would
surface: momentum-factor gate, extended entry, low volume, price-vs-PT, R:R,
beta, earnings proximity), and posts a detailed block message to Slack.

NO scan, NO EODHD cost. Reuses SLACK_WEBHOOK_URL from .env.
Fired by com.swingtrade.swing-analysis (market days, ~every 4h).

Usage:
    python3 scripts/swing_slack_analysis.py [--top 5] [--min-score 70] [--dry-run]
"""
from __future__ import annotations
import argparse
import json
import re
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "cache" / "last_bundle.json"
STATE = ROOT / "cache" / "swing_analysis_state.json"
DASH = "https://trade.mystockholding.com"
RR_FLOOR = 3.0
ACTIONABLE = {"FRESH", "PULLBACK", "VALID"}

CRYPTO = {"BTC", "ETH", "XRP", "SOL", "XLM", "ZEC", "LINK", "XMR", "HYPE", "DOGE",
          "ADA", "AVAX", "LTC", "BCH", "DOT", "MATIC", "SHIB", "TRX", "UNI", "ATOM"}


# --------------------------------------------------------------------------- io
def _webhook() -> str | None:
    try:
        for line in (ROOT / ".env").read_text().splitlines():
            if line.startswith("SLACK_WEBHOOK_URL="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return None


def _extract_array(data: str, key: str):
    """Balanced-bracket extract of a top-level array without json.load-ing 337MB."""
    n = len(data)
    for m in re.finditer(r'"%s"\s*:\s*\[' % re.escape(key), data):
        j = data.index("[", m.start())
        depth = 0; k = j; instr = False; esc = False
        while k < n:
            c = data[k]
            if instr:
                if esc: esc = False
                elif c == "\\": esc = True
                elif c == '"': instr = False
            else:
                if c == '"': instr = True
                elif c == "[": depth += 1
                elif c == "]":
                    depth -= 1
                    if depth == 0:
                        try:
                            a = json.loads(data[j:k + 1])
                            if isinstance(a, list) and a:
                                return a
                        except Exception:
                            pass
                        break
            k += 1
    return []


def _num(x, d=None):
    try:
        return float(x)
    except Exception:
        return d


def _g(d, *ks, default=""):
    for k in ks:
        if isinstance(d, dict) and d.get(k) not in (None, "", [], {}):
            return d[k]
    return default


# ------------------------------------------------------------------ diff state
def _load_state() -> dict:
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return {}


def _save_state(snapshot: dict):
    try:
        STATE.write_text(json.dumps(snapshot, indent=2))
    except Exception as e:
        print(f"state save failed: {e}", file=sys.stderr)


def _snapshot(cands: list[dict]) -> dict:
    out = {}
    for r in cands:
        t = r.get("ticker")
        if not t:
            continue
        conv = _g(r, "conviction", default={})
        out[t] = {
            "score": _num(r.get("score"), 0),
            "eq": str(_g(r, "entry_quality")),
            "tier": (conv.get("label") if isinstance(conv, dict) else str(conv)) or "",
            "price": _num(r.get("price")),
        }
    return {"ts": datetime.now().isoformat(timespec="minutes"), "tickers": out}


def _diff_text(prev: dict, cur: dict) -> str:
    """Human 'what changed since last post' line block."""
    p = (prev or {}).get("tickers") or {}
    if not p:
        return ""  # first run — nothing to diff
    lines = []
    new = [t for t in cur if t not in p]
    dropped = [t for t in p if t not in cur]
    if new:
        lines.append("🆕 New: " + ", ".join(f"{t}({cur[t]['score']:.0f})" for t in new))
    if dropped:
        lines.append("❌ Dropped: " + ", ".join(dropped))
    for t in cur:
        if t not in p:
            continue
        a, b = p[t], cur[t]
        # entry pulled into the buy zone = the actionable trigger
        if a["eq"] not in ACTIONABLE and b["eq"] in ACTIONABLE:
            lines.append(f"⭐ *{t} now actionable* — entry {a['eq']}→{b['eq']} (pulled into zone)")
        elif a["eq"] in ACTIONABLE and b["eq"] not in ACTIONABLE:
            lines.append(f"↗️ {t} extended away — entry {a['eq']}→{b['eq']}")
        if a["tier"] != b["tier"] and b["tier"]:
            lines.append(f"🎚️ {t} tier {a['tier'] or '—'}→{b['tier']}")
        ds = (b["score"] or 0) - (a["score"] or 0)
        if abs(ds) >= 3:
            lines.append(f"{'🔼' if ds > 0 else '🔽'} {t} score {a['score']:.0f}→{b['score']:.0f} ({'+' if ds>0 else ''}{ds:.0f})")
    if not lines:
        prev_when = (prev or {}).get("ts", "")
        return f"📌 *Since last post* ({prev_when}): _no material change_"
    return "📌 *Since last post:*\n" + "\n".join("   " + x for x in lines)


# ------------------------------------------------------------------ web analyst
def _analyst_web(sym: str) -> dict:
    """Live analyst rating + targets from yfinance (free). Best-effort."""
    try:
        import yfinance as yf
        info = yf.Ticker(sym).info or {}
        return {
            "rating": info.get("recommendationKey"),
            "n": info.get("numberOfAnalystOpinions"),
            "mean": info.get("targetMeanPrice"),
            "high": info.get("targetHighPrice"),
            "low": info.get("targetLowPrice"),
            "price": info.get("currentPrice") or info.get("regularMarketPrice"),
        }
    except Exception:
        return {}


# ----------------------------------------------------------------- analysis
def _candidates(data: str, top: int, min_score: float):
    rows = _extract_array(data, "buy_candidates") or []
    rows += _extract_array(data, "watch_list") or []
    if not rows:
        rows = _extract_array(data, "all_scored") or []
    seen, out = set(), []
    for r in rows:
        if not isinstance(r, dict):
            continue
        t = r.get("ticker") or r.get("symbol")
        if not t or t in seen or t in CRYPTO or str(t).endswith("USD"):
            continue
        if (_num(r.get("score"), 0) or 0) < min_score:
            continue
        seen.add(t)
        out.append(r)
    out.sort(key=lambda r: -(_num(r.get("score"), 0) or 0))
    return out[:top]


def _flags(r: dict, aw: dict) -> list[str]:
    f = []
    price = _num(r.get("price"))
    eq = str(_g(r, "entry_quality"))
    rvol = _num(r.get("rvol"))
    rsi = _num(r.get("rsi"))
    beta = _num(r.get("beta"))
    tp = _g(r, "canonical_trade_plan", "trade_plan", default={})
    dec = _g(r, "decision", default={})
    reason = dec.get("reason", "") if isinstance(dec, dict) else ""
    # momentum-factor gate
    if "momentum_condition_gate" in str(reason):
        f.append("⚠️ Momentum factor *paused* (QQQ-SPY spread below threshold) — system demotes to WATCH")
    # entry timing
    if eq in ("MISSED", "EXTENDED"):
        lo = (tp.get("entry") or {}).get("low") if isinstance(tp.get("entry"), dict) else tp.get("entry_low")
        f.append(f"⚠️ Entry *{eq}* — chasing; wait for pullback" + (f" to ~${lo}" if lo else ""))
    elif eq in ("FRESH", "PULLBACK"):
        f.append(f"✅ Entry *{eq}* — in/near the buy zone")
    # analyst PT (web)
    mean = _num(aw.get("mean")) or _num((_g(r, "analyst", default={}) or {}).get("target_mean"))
    if price and mean:
        up = (mean / price - 1) * 100
        if up < 0:
            f.append(f"⚠️ ${price:.2f} is *{-up:.0f}% ABOVE* analyst mean PT ${mean:.2f} — consensus says overvalued")
        else:
            f.append(f"✅ {up:.0f}% upside to analyst mean PT ${mean:.2f}")
    # volume
    if rvol is not None and rvol < 1.0:
        f.append(f"⚠️ RVOL {rvol:.2f}x — below-avg volume, no accumulation")
    # R:R
    rr = _num(_g(tp, "rr", "risk_reward")) or _rr_from_plan(tp, price)
    if rr and rr < RR_FLOOR:
        f.append(f"⚠️ R:R {rr:.1f} below {RR_FLOOR:.0f}:1 floor")
    # beta / overbought / earnings
    if beta and beta >= 2.0:
        f.append(f"⚠️ High beta {beta:.1f} — outsized risk")
    if rsi and rsi >= 75:
        f.append(f"⚠️ RSI {rsi:.0f} overbought")
    ea = _g(r, "earnings", default={})
    dte = ea.get("days_to_earnings") if isinstance(ea, dict) else None
    if isinstance(dte, (int, float)) and dte <= 7:
        f.append(f"⚠️ Earnings in {int(dte)}d — blackout risk")
    return f


def _rr_from_plan(tp: dict, price) -> float | None:
    try:
        entry = tp.get("entry")
        entry = entry.get("mid") if isinstance(entry, dict) else entry
        entry = _num(entry) or _num(price)
        stop = _num(tp.get("stop") or tp.get("stop_loss"))
        t2 = _num(tp.get("target2") or tp.get("t2"))
        if entry and stop and t2 and entry > stop:
            return (t2 - entry) / (entry - stop)
    except Exception:
        pass
    return None


def _ticker_block(r: dict, aw: dict) -> str:
    t = r.get("ticker")
    name = _g(r, "name", default=t)
    price = _num(r.get("price"))
    score = _num(r.get("score"), 0)
    conv = _g(r, "conviction", default={})
    tier = conv.get("label") if isinstance(conv, dict) else conv
    setup = _g(r, "setup_family")
    sector = _g(r, "sector")
    rs = _g(r, "rs_rank")
    rsi = _num(r.get("rsi"))
    rvol = _num(r.get("rvol"))
    tp = _g(r, "canonical_trade_plan", "trade_plan", default={})
    entry = tp.get("entry")
    entry = entry.get("mid") if isinstance(entry, dict) else entry
    stop = tp.get("stop") or tp.get("stop_loss")
    t1 = tp.get("target1") or tp.get("t1")
    t2 = tp.get("target2") or tp.get("t2")
    rr = _num(_g(tp, "rr", "risk_reward")) or _rr_from_plan(tp, price)
    # analyst line (web)
    rating = aw.get("rating")
    mean, hi, lo, na = aw.get("mean"), aw.get("high"), aw.get("low"), aw.get("n")
    if mean:
        an = f"*Analyst:* {rating or '—'} · PT ${_num(mean):.0f} (${_num(lo):.0f}–${_num(hi):.0f})" + (f" · {int(na)} analysts" if na else "")
    else:
        an = f"*Analyst:* {rating or 'n/a from web'}"
    hdr = f"*{t}* ({name}) — ${price:.2f} · Score {score:.0f}" + (f" · {tier}" if tier else "")
    tech = f"{setup} · {sector} · RS {rs} · RSI {rsi:.0f} · RVOL {rvol:.2f}x" if rsi and rvol is not None else f"{setup} · {sector}"
    plan = (f"*Plan:* entry ${_num(entry):.2f} → stop ${_num(stop):.2f} → T1 ${_num(t1):.2f} / T2 ${_num(t2):.2f}"
            + (f" · R:R {rr:.1f}" if rr else "")) if entry and stop else ""
    flags = "\n".join(f"   {x}" for x in _flags(r, aw))
    parts = [hdr, tech, an]
    if plan:
        parts.append(plan)
    if flags:
        parts.append(flags)
    return "\n".join(parts)


def build_blocks(data: str, top: int, min_score: float, prev_state: dict | None = None):
    run_date = ""
    mo = re.search(r'"run_date"\s*:\s*"([^"]+)"', data[:500])
    if mo:
        run_date = mo.group(1)
    reg = ""
    mr = re.search(r'"regime4"\s*:\s*"([^"]+)"', data[:4000])
    if mr:
        reg = mr.group(1)
    when = datetime.now().strftime("%a %b %-d · %-I:%M %p PT")

    cands = _candidates(data, top, min_score)
    weekday = datetime.now().weekday()  # Mon=0..Sun=6
    stale = weekday >= 5 or (run_date and run_date != datetime.now().strftime("%Y-%m-%d") and weekday >= 5)

    # board-level crowded-factor detection
    setups = [str(_g(r, "setup_family")) for r in cands]
    warn = ""
    if setups:
        top_setup = max(set(setups), key=setups.count)
        cnt = setups.count(top_setup)
        if cnt >= max(3, len(cands) - 1):
            warn = f"\n⚠️ *{cnt}/{len(cands)} share `{top_setup}`* — single-factor board (correlated under stress, not diversified)."

    header = (f"📊 *Swing Analysis* — {when}\n"
              f"Regime *{reg or '—'}* · data run {run_date or '—'}"
              + ("  ·  ⚠️ _markets closed — last-close data, stale_" if stale else "")
              + warn)
    blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": header}}]
    cur_snap = {r.get("ticker"): {
        "score": _num(r.get("score"), 0), "eq": str(_g(r, "entry_quality")),
        "tier": ((_g(r, "conviction", default={}) or {}).get("label")
                 if isinstance(_g(r, "conviction", default={}), dict) else "") or "",
        "price": _num(r.get("price"))} for r in cands if r.get("ticker")}
    diff = _diff_text(prev_state or {}, cur_snap)
    if diff:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": diff}})
    blocks.append({"type": "divider"})
    if not cands:
        blocks.append({"type": "section", "text": {"type": "mrkdwn",
                       "text": "_No equity swing candidates above threshold this run._"}})
    for r in cands:
        aw = _analyst_web(r.get("ticker"))
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": _ticker_block(r, aw)}})
        blocks.append({"type": "divider"})
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn",
                   "text": f"rule-based read · analyst PTs live from web · not advice · <{DASH}|Open dashboard ↗>"}]})
    return blocks, cands


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--min-score", type=float, default=70.0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--scan-first", action="store_true",
                    help="run a fresh scan before analysis (usually redundant — daily/premarket already scan pre-6am; costs EODHD quota)")
    args = ap.parse_args()

    if args.scan_first:
        import subprocess
        try:
            print("scan-first: running swing_trade.py ...", file=sys.stderr)
            subprocess.run([sys.executable, "swing_trade.py"], cwd=str(ROOT), timeout=1800, check=False)
        except Exception as e:
            print(f"scan-first failed (continuing with existing bundle): {e}", file=sys.stderr)

    if not BUNDLE.exists():
        print("bundle missing", file=sys.stderr)
        return 1
    data = BUNDLE.read_text(encoding="utf-8", errors="replace")
    prev_state = _load_state()
    blocks, cands = build_blocks(data, args.top, args.min_score, prev_state)
    payload = {"blocks": blocks, "text": "Swing analysis"}

    if args.dry_run:
        print(json.dumps(payload, indent=2)[:8000])
        return 0
    wh = _webhook()
    if not wh:
        print("SLACK_WEBHOOK_URL not set", file=sys.stderr)
        return 1
    req = urllib.request.Request(wh, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        r = urllib.request.urlopen(req, timeout=10)
        print(f"posted (HTTP {r.status})")
        _save_state(_snapshot(cands))  # persist baseline for next-run diff
        return 0
    except Exception as e:
        print(f"post failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
