#!/usr/bin/env python3
"""pick_forensics.py — "why did my BUY lose / why did AVOID win" post-mortem.

Answers the owner's Q5: for closed picks, WHERE do calls go wrong?
Reads cache/picks_history.json -> trades[] (1200+ closed trades, each carrying the
DECISION context (verdict, score, setup_family, regime4, entry_quality, catalyst_tier,
5 pillar scores) AND the OUTCOME (win, pnl_pct, mfe/mae, realized_r)). No join needed —
the tracker already stamps both on every closed trade.

Three lenses:
  1. VERDICT TRUTH    — did BUY actually win? did WATCH/AVOID outcomes justify skipping?
                        (the core "I said bullish, why -ve?" check + the inverse)
  2. WHERE IT BREAKS  — win-rate / avg-pnl / profit-factor by setup_family x regime4 x
                        entry_quality x score-band — ranked worst-first (the kill candidates)
  3. WORST CALLS      — the individual BUY/bullish picks that lost most (with mfe/mae so you
                        see if it ran your way first then reversed, or never worked)

Wilson lower-bound on every win-rate so small-n cells aren't over-trusted (principle 1).
Read-only. Usage:
  python3 scripts/pick_forensics.py                # full report
  python3 scripts/pick_forensics.py --verdict BUY  # focus one verdict
  python3 scripts/pick_forensics.py --min-n 10     # only cells with n>=10
  python3 scripts/pick_forensics.py --html out.html
"""
from __future__ import annotations
import argparse
import json
import math
import os
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
HIST = BASE / "cache" / "picks_history.json"


def _wilson_lb(wins, n, z=1.96):
    if n == 0:
        return 0.0
    p = wins / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)
    return max(0.0, (c - m) / d)


def _pf(trades):
    g = sum(t["pnl_pct"] for t in trades if t.get("pnl_pct", 0) > 0)
    l = -sum(t["pnl_pct"] for t in trades if t.get("pnl_pct", 0) < 0)
    return (g / l) if l > 0 else (float("inf") if g > 0 else 0.0)


def _stats(trades):
    n = len(trades)
    if n == 0:
        return None
    wins = sum(1 for t in trades if t.get("win"))
    avg = sum(t.get("pnl_pct", 0) for t in trades) / n
    return {
        "n": n, "wins": wins, "wr": wins / n, "wilson_lb": _wilson_lb(wins, n),
        "avg_pnl": avg, "pf": _pf(trades),
        "avg_mfe": sum(t.get("mfe_pct", 0) or 0 for t in trades) / n,
        "avg_mae": sum(t.get("mae_pct", 0) or 0 for t in trades) / n,
    }


def load_trades():
    if not HIST.exists():
        return []
    try:
        d = json.loads(HIST.read_text())
        return d.get("trades", []) if isinstance(d, dict) else []
    except Exception:
        return []


def score_band(s):
    try:
        s = float(s)
    except (TypeError, ValueError):
        return "?"
    return "90+" if s >= 90 else "80-89" if s >= 80 else "70-79" if s >= 70 else "60-69" if s >= 60 else "<60"


def run(verdict_filter=None, min_n=5):
    trades = load_trades()
    if not trades:
        return {"error": "no trades in picks_history.json"}
    if verdict_filter:
        trades = [t for t in trades if str(t.get("verdict", "")).upper() == verdict_filter.upper()]

    out = {"n_total": len(trades)}

    # ── 1. VERDICT TRUTH ──────────────────────────────────────────
    by_verdict = defaultdict(list)
    for t in trades:
        by_verdict[str(t.get("verdict", "?")).upper()].append(t)
    out["verdict_truth"] = {}
    for v, ts in sorted(by_verdict.items(), key=lambda x: -len(x[1])):
        st = _stats(ts)
        # the "wrong-way" counts: BUY/bullish that LOST; AVOID/SHORT that the long would've WON
        if v in ("BUY",):
            st["went_wrong"] = sum(1 for t in ts if not t.get("win"))
            st["wrong_pct"] = st["went_wrong"] / st["n"] if st["n"] else 0
        if v in ("AVOID", "SHORT", "WATCH"):
            st["would_have_won"] = sum(1 for t in ts if (t.get("pnl_pct", 0) or 0) > 0)
        out["verdict_truth"][v] = st

    # ── 2. WHERE IT BREAKS — multi-dim cells, ranked worst-first ──
    def cells(keyfn, label):
        groups = defaultdict(list)
        for t in trades:
            groups[keyfn(t)].append(t)
        rows = []
        for k, ts in groups.items():
            st = _stats(ts)
            if st and st["n"] >= min_n:
                rows.append({"key": k, **st})
        rows.sort(key=lambda r: (r["wilson_lb"], r["avg_pnl"]))  # worst first
        return {"dim": label, "rows": rows}

    out["by_setup"] = cells(lambda t: t.get("setup_family", "?"), "setup_family")
    out["by_regime"] = cells(lambda t: t.get("regime4", t.get("regime", "?")), "regime4")
    out["by_entry_quality"] = cells(lambda t: t.get("entry_quality", "?"), "entry_quality")
    out["by_score_band"] = cells(lambda t: score_band(t.get("score")), "score_band")
    out["by_setup_x_regime"] = cells(
        lambda t: f"{t.get('setup_family','?')} / {t.get('regime4', t.get('regime','?'))}",
        "setup_family x regime4")

    # ── 3. WORST CALLS — biggest BUY/bullish losers ──────────────
    longs = [t for t in trades if str(t.get("verdict", "")).upper() in ("BUY", "WATCH")
             and t.get("direction", "long") == "long"]
    losers = sorted([t for t in longs if (t.get("pnl_pct", 0) or 0) < 0],
                    key=lambda t: t.get("pnl_pct", 0))[:15]
    out["worst_calls"] = [{
        "ticker": t.get("ticker"), "date": t.get("entry_date"), "verdict": t.get("verdict"),
        "score": t.get("score"), "setup": t.get("setup_family"), "regime": t.get("regime4", t.get("regime")),
        "entry_q": t.get("entry_quality"), "pnl_pct": round(t.get("pnl_pct", 0), 2),
        "mfe_pct": round(t.get("mfe_pct", 0) or 0, 2), "mae_pct": round(t.get("mae_pct", 0) or 0, 2),
        "hold_days": t.get("hold_days"),
        # diagnosis: did it run our way first (mfe>3) then reverse, or never work?
        "diagnosis": ("ran +%.1f%% then reversed" % (t.get("mfe_pct", 0) or 0)) if (t.get("mfe_pct", 0) or 0) > 3
                     else "never worked (immediate adverse)",
    } for t in losers]

    return out


def _fmt(st):
    if not st:
        return "—"
    inf = "inf" if st["pf"] == float("inf") else f"{st['pf']:.2f}"
    return (f"n={st['n']:>4} wr={st['wr']*100:>5.1f}% wlb={st['wilson_lb']*100:>5.1f}% "
            f"avg={st['avg_pnl']:>+6.2f}% pf={inf:>5} mfe={st['avg_mfe']:>+5.1f} mae={st['avg_mae']:>+5.1f}")


def print_report(r):
    if r.get("error"):
        print("ERROR:", r["error"]); return
    print("=" * 92)
    print(f"  PICK FORENSICS — {r['n_total']} closed trades   (why BUY loses / where calls break)")
    print("=" * 92)
    print("\n[1] VERDICT TRUTH — did the call match the outcome?")
    for v, st in r["verdict_truth"].items():
        extra = ""
        if "wrong_pct" in st:
            extra = f"   ⚠ {st['went_wrong']} BUYs LOST ({st['wrong_pct']*100:.0f}%)"
        if "would_have_won" in st:
            extra = f"   ({st['would_have_won']} would've won as a long)"
        print(f"  {v:7s} {_fmt(st)}{extra}")
    for title, key in [("[2a] WORST SETUP FAMILIES", "by_setup"),
                       ("[2b] WORST REGIMES", "by_regime"),
                       ("[2c] WORST ENTRY QUALITY", "by_entry_quality"),
                       ("[2d] WORST SCORE BANDS", "by_score_band"),
                       ("[2e] WORST SETUP × REGIME (kill candidates)", "by_setup_x_regime")]:
        print(f"\n{title}  (worst-first, Wilson-LB ranked)")
        for row in r[key]["rows"][:8]:
            print(f"  {str(row['key'])[:34]:34s} {_fmt(row)}")
    print("\n[3] WORST 15 BUY/bullish CALLS (the 'I said buy, why -ve' list)")
    print(f"  {'TICKER':7s} {'DATE':10s} {'SCORE':>5s} {'PNL%':>7s} {'MFE':>6s} {'MAE':>6s}  SETUP/REGIME · diagnosis")
    for w in r["worst_calls"]:
        print(f"  {str(w['ticker']):7s} {str(w['date']):10s} {str(w['score']):>5s} "
              f"{w['pnl_pct']:>+7.2f} {w['mfe_pct']:>+6.1f} {w['mae_pct']:>+6.1f}  "
              f"{str(w['setup'])[:18]}/{str(w['regime'])[:10]} · {w['diagnosis']}")
    print("\n" + "=" * 92)
    print("  READ: wlb=Wilson lower-bound (small-n honest WR). 'ran +X% then reversed' = exit/")
    print("  target/trail problem; 'never worked' = entry/signal problem. setup×regime cells with")
    print("  low wlb + negative avg are kill-list candidates (verify n>=30 before acting).")
    print("=" * 92)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--verdict", default=None)
    ap.add_argument("--min-n", type=int, default=5)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    rep = run(verdict_filter=args.verdict, min_n=args.min_n)
    if args.json:
        print(json.dumps(rep, indent=2, default=str))
    else:
        print_report(rep)
