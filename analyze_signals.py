"""
analyze_signals.py — Auto-generate signal_tracker performance analysis.

Replaces the ad-hoc shell-Python slicing we did 2026-05-06 with a single
script that produces a deterministic JSON + console summary on demand.

Run after each scan (or on a schedule) to refresh per-setup, per-regime,
per-result performance breakdown that the dashboard can consume.

Usage:
    python3 analyze_signals.py            # console + write json
    python3 analyze_signals.py --quiet    # json only, no console
    python3 analyze_signals.py --json     # json to stdout

Output: cache/signal_analysis_YYYY-MM-DD.json
"""
from __future__ import annotations
import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).parent
SIGNAL_LOG = ROOT / "data" / "signal_log.json"
OUT_DIR = ROOT / "cache"


def _slice(items: list, key_fn) -> dict:
    """Group a list of signals by a key, return per-group {n, win_rate, avg}."""
    g: dict = defaultdict(list)
    for s in items:
        try:
            g[key_fn(s)].append(s.get("actual_pnl_pct"))
        except Exception:
            pass
    out: dict = {}
    for k, pnls in g.items():
        pnls = [p for p in pnls if p is not None]
        if not pnls:
            continue
        n = len(pnls)
        wins = sum(1 for p in pnls if p > 0)
        out[str(k)] = {
            "n": n,
            "wins": wins,
            "losses": n - wins,
            "win_rate_pct": round(wins / n * 100, 1),
            "avg_pnl_pct": round(sum(pnls) / n, 2),
        }
    return out


def _score_band(s: dict) -> str:
    sc = float(s.get("score") or 0)
    if sc >= 80: return ">=80"
    if sc >= 70: return "70-79"
    if sc >= 60: return "60-69"
    if sc >= 50: return "50-59"
    return "<50"


def _rr_band(s: dict) -> str:
    rr = float(s.get("rr") or 0)
    if rr >= 5: return ">=5"
    if rr >= 4: return "4-5"
    if rr >= 3: return "3-4"
    return "<3"


def analyze() -> dict:
    if not SIGNAL_LOG.exists():
        return {"error": "signal_log.json not found"}
    sigs = json.loads(SIGNAL_LOG.read_text())
    closed = [s for s in sigs if s.get("status") == "CLOSED" and s.get("actual_pnl_pct") is not None]
    opens = [s for s in sigs if s.get("status") != "CLOSED"]
    n = len(closed)
    if n == 0:
        return {"error": "no closed signals to analyze"}

    pnls = [s["actual_pnl_pct"] for s in closed]
    wins = sum(1 for p in pnls if p > 0)
    overall = {
        "as_of": str(date.today()),
        "total_closed": n,
        "total_open": len(opens),
        "win_rate_pct": round(wins / n * 100, 1),
        "avg_pnl_pct": round(sum(pnls) / n, 2),
        "best_pct": round(max(pnls), 2),
        "worst_pct": round(min(pnls), 2),
        "date_range": {
            "first": min(s.get("date", "") for s in closed),
            "last":  max(s.get("date", "") for s in closed),
        },
    }

    # Result distribution
    result_dist = {}
    for label, pnls_g in defaultdict(list, {**{r: [s["actual_pnl_pct"] for s in closed if s.get("result") == r] for r in {s.get("result") for s in closed}}}).items():
        if pnls_g:
            result_dist[label] = {"n": len(pnls_g), "avg_pnl_pct": round(sum(pnls_g)/len(pnls_g), 2)}

    return {
        "overall":       overall,
        "by_setup":      _slice(closed, lambda s: s.get("strategy") or "(none)"),
        "by_score_band": _slice(closed, _score_band),
        "by_rr_band":    _slice(closed, _rr_band),
        "by_result":     result_dist,
        "by_direction":  _slice(closed, lambda s: s.get("direction") or "long"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true", help="suppress console output")
    ap.add_argument("--json", action="store_true", help="dump full JSON to stdout")
    args = ap.parse_args()

    a = analyze()
    if "error" in a:
        print(f"Error: {a['error']}", file=sys.stderr)
        sys.exit(1)

    out_path = OUT_DIR / f"signal_analysis_{date.today().isoformat()}.json"
    out_path.write_text(json.dumps(a, indent=2, default=str))

    if args.json:
        print(json.dumps(a, indent=2, default=str))
        return

    if not args.quiet:
        ov = a["overall"]
        print(f"=== SIGNAL TRACKER ANALYSIS — {ov['as_of']} ===")
        print(f"Total: {ov['total_closed']} closed, {ov['total_open']} open  ·  "
              f"WR={ov['win_rate_pct']}%  avg={ov['avg_pnl_pct']:+.2f}%  "
              f"best={ov['best_pct']:+.2f}%  worst={ov['worst_pct']:+.2f}%")
        print(f"Range: {ov['date_range']['first']} → {ov['date_range']['last']}")

        def show(title, slc, sortby):
            print(f"\n--- {title} ---")
            rows = sorted(slc.items(), key=lambda x: -x[1][sortby])
            for k, v in rows:
                print(f"  {k:25s}  n={v['n']:4d}  WR={v['win_rate_pct']:5.1f}%  avg={v['avg_pnl_pct']:+.2f}%")
        show("By setup",       a["by_setup"],      "n")
        show("By score band",  a["by_score_band"], "n")
        show("By R:R band",    a["by_rr_band"],    "n")
        print(f"\n--- By result ---")
        for k, v in sorted(a["by_result"].items(), key=lambda x: -x[1]["n"]):
            print(f"  {k:20s}  n={v['n']:4d}  avg={v['avg_pnl_pct']:+.2f}%")
        print(f"\nWritten: {out_path}")


if __name__ == "__main__":
    main()
