#!/usr/bin/env python3
"""360 audit — Signal Screener scoring  →  Track Record / The Ledger outcome.

Every row in data/signal_log.json carries BOTH the screener's scoring decomposition
at signal time (composite score, per-pillar scores, catalyst tier, conviction,
entry quality, setup family, regime, stars, R:R) AND the realized forward outcome
(result, actual_pnl_pct, alpha_vs_spy). That is the same store The Ledger renders
(cache/audit_ledger + signal_log -> data_leaders.json nightly), so this audit
reconciles 1:1 with what you see on Track Record -> The Ledger.

The question it answers: *which scoring actually has good profit?* For every scoring
dimension it computes, over RESOLVED trades only, the honest hedge-fund metrics:
  n · win-rate · profit factor · Wilson 95% lower bound · avg P&L · avg alpha vs SPY.

Profit factor (PF) = gross winning % / gross losing %. PF<1 = the bucket loses money.
Wilson LB is the floor of the win-rate's 95% CI — the number to trust at small n.
Buckets with n<30 are flagged; per docs/claude_md_calibration.md the retail floor is
n>=10 preliminary / n>=30 standard. Single-window, in-sample — confirm with
walk_forward before acting (principle 1 + 20).

Usage:
  python3 scripts/audit_signal_to_ledger.py                 # all verdicts, full report
  python3 scripts/audit_signal_to_ledger.py --verdict BUY   # actionable signals only (default lens)
  python3 scripts/audit_signal_to_ledger.py --mode Swing    # one horizon
  python3 scripts/audit_signal_to_ledger.py --json out.json # machine-readable
"""
from __future__ import annotations
import argparse, json, math, os, sys
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
LOG = BASE / "data" / "signal_log.json"
WIN = {"WIN_EXPIRED", "TARGET_HIT"}
LOSS = {"STOPPED", "LOSS_EXPIRED"}


def wilson_lb(w: int, n: int):
    """Wilson 95% lower bound on the win-rate (the small-n honest floor)."""
    if n == 0:
        return None
    p = w / n
    z = 1.96
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return round(100 * (centre - half))


def stats(rows):
    res = [r for r in rows if r.get("result") in WIN or r.get("result") in LOSS]
    n = len(res)
    if not n:
        return {"n": 0, "wr": None, "pf": None, "wilson": None, "avg_pnl": None, "avg_alpha": None}
    w = sum(1 for r in res if r["result"] in WIN)
    pnls = [r["actual_pnl_pct"] for r in res if r.get("actual_pnl_pct") is not None]
    gw = sum(p for p in pnls if p > 0)
    gl = abs(sum(p for p in pnls if p < 0))
    alphas = [r["alpha_vs_spy"] for r in res if r.get("alpha_vs_spy") is not None]
    return {
        "n": n,
        "wr": round(100 * w / n),
        "pf": round(gw / gl, 2) if gl > 0 else None,
        "wilson": wilson_lb(w, n),
        "avg_pnl": round(sum(pnls) / len(pnls), 2) if pnls else None,
        "avg_alpha": round(sum(alphas) / len(alphas), 2) if alphas else None,
    }


def score_band(v):
    if v is None:
        return None
    for e in (60, 70, 80, 90):
        if v < e:
            return f"<{e}"
    return ">=90"


# (title, key function) — each scoring lever the screener exposes on a signal.
DIMENSIONS = [
    ("COMPOSITE SCORE", lambda r: score_band(r.get("score"))),
    ("CATALYST TIER", lambda r: f"T{r['catalyst_tier']}" if r.get("catalyst_tier") is not None else None),
    ("CONVICTION", lambda r: r.get("conviction_label")),
    ("ENTRY QUALITY", lambda r: r.get("entry_quality")),
    ("SETUP FAMILY", lambda r: r.get("setup_family")),
    ("REGIME", lambda r: r.get("regime4")),
    ("STARS", lambda r: f"{r['stars']}*" if r.get("stars") is not None else None),
    ("R:R BAND", lambda r: ("<2" if (r.get("rr") or 0) < 2 else "2-3" if r["rr"] < 3 else ">=3") if r.get("rr") is not None else None),
    ("MODE", lambda r: r.get("mode")),
]


def build(rows):
    out = {}
    for title, keyfn in DIMENSIONS:
        g = defaultdict(list)
        for r in rows:
            k = keyfn(r)
            if k is not None:
                g[str(k)].append(r)
        buckets = [{"bucket": k, **stats(v)} for k, v in g.items()]
        # rank by PF desc (None last) so the profitable buckets float to the top
        buckets.sort(key=lambda b: (b["pf"] if b["pf"] is not None else -9), reverse=True)
        out[title] = buckets
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verdict", default=None, help="filter to one verdict (BUY/WATCH/SHORT). Default: all, plus a BUY-only section.")
    ap.add_argument("--mode", default=None, help="filter to one horizon (Swing/Position/Invest)")
    ap.add_argument("--json", default=None, help="write machine-readable report to this path")
    args = ap.parse_args()

    if not LOG.exists():
        sys.exit(f"missing {LOG}")
    sl = json.loads(LOG.read_text())

    def subset(verdict=None):
        rows = sl
        if verdict:
            rows = [r for r in rows if r.get("verdict") == verdict]
        if args.mode:
            rows = [r for r in rows if r.get("mode") == args.mode]
        return rows

    report = {}
    # Headline: verdict-level reconciliation (does the system's own call rank by profit?)
    by_verdict = []
    vg = defaultdict(list)
    for r in subset():
        vg[r.get("verdict", "?")].append(r)
    for v in ["BUY", "WATCH", "SHORT", "AVOID"]:
        by_verdict.append({"bucket": v, **stats(vg.get(v, []))})
    report["BY VERDICT"] = by_verdict

    # Deep dive — by default on BUY (the actionable signals); override with --verdict.
    lens = args.verdict or "BUY"
    report["_lens"] = lens
    report.update(build(subset(lens)))

    # ---- console render ----
    def line(b):
        flag = "  <n30" if (b["n"] and b["n"] < 30) else ""
        return (f"  {b['bucket']:<20} n={str(b['n']):>4}  WR={str(b['wr'])+'%':>5}"
                f"  PF={str(b['pf']):>5}  WilLB={str(b['wilson'])+'%':>5}"
                f"  pnl={str(b['avg_pnl']):>6}  alpha={str(b['avg_alpha']):>6}{flag}")

    print(f"\n360 AUDIT — Signal Screener scoring -> Ledger outcome   ({LOG.name})")
    print(f"resolved-trade metrics · deep-dive lens = verdict:{lens}"
          + (f" · mode:{args.mode}" if args.mode else "") + "\n")
    print("BY VERDICT  (does the system's own call rank by profit?)")
    for b in report["BY VERDICT"]:
        print(line(b))
    for title, _ in DIMENSIONS:
        print(f"\n{title}  (ranked by PF)")
        for b in report[title]:
            print(line(b))
    print("\nPF<1.0 = bucket loses money · WilLB is the small-n honest floor (retail floor ~35%)")
    print("Single-window/in-sample — confirm with backtest/walk_forward_v2 before acting.\n")

    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2))
        print(f"wrote {args.json}")


if __name__ == "__main__":
    main()
