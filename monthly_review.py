"""
monthly_review.py — Decision-engine sanity review, intended for monthly cadence.

Re-runs analyze_signals against current signal_log, compares kill list and
size multipliers vs last review, and prints actionable recommendations:
  - "Setup X passed kill threshold for first time → consider re-enabling"
  - "Setup Y crossed below kill threshold → currently active in kill list"
  - "Multiplier for Z changed: 1.0× → 1.3× (now in 'proven' band)"

Maintains state in cache/monthly_review_state.json so subsequent runs detect
*changes* not just current state.

Usage:
    python3 monthly_review.py             # console + writes change log
    python3 monthly_review.py --reset     # snapshot current state, no diffing
    python3 monthly_review.py --json      # machine-readable output

Recommended cadence: 1st of every month, OR ~4 weeks after a major rule change
(e.g., the 2026-06-03 review was scheduled to validate today's tightenings
once the 425 open positions close).
"""
from __future__ import annotations
import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent
STATE_PATH = ROOT / "cache" / "monthly_review_state.json"


def _capture() -> dict:
    """Snapshot current kill list + multipliers + signal stats."""
    sys.path.insert(0, str(ROOT))
    from decision_engine import (compute_setup_kill_list, compute_setup_size_multipliers,
                                  compute_setup_score_band_kills)
    from analyze_signals import analyze
    return {
        "as_of":         str(date.today()),
        "kill_list":     compute_setup_kill_list(),
        "band_kills":    {f"{s}@{b}": v for (s,b), v in compute_setup_score_band_kills().items()},
        "multipliers":   compute_setup_size_multipliers(),
        "signal_stats":  analyze(),
    }


def _diff(prior: dict, now: dict) -> list[str]:
    """Recommendation lines based on snapshot diff."""
    recs: list[str] = []

    # Kill list changes
    p_kills = set((prior.get("kill_list") or {}).keys())
    n_kills = set((now.get("kill_list") or {}).keys())
    new_kills = n_kills - p_kills
    revived = p_kills - n_kills
    for k in new_kills:
        info = now["kill_list"][k]
        recs.append(f"🔴 NEW KILL: {k} crossed below performance floor "
                    f"(WR {info['wr']}%, avg {info['avg_pnl']:+.2f}%, n={info['n']})")
    for k in revived:
        recs.append(f"🟢 REVIVED: {k} was killed last review but no longer meets kill criteria — "
                    f"consider re-enabling")

    # Stratified band kills
    p_bk = set((prior.get("band_kills") or {}).keys())
    n_bk = set((now.get("band_kills") or {}).keys())
    for k in n_bk - p_bk:
        recs.append(f"🟠 NEW STRATIFIED KILL: {k}")
    for k in p_bk - n_bk:
        recs.append(f"🟢 STRATIFIED KILL CLEARED: {k}")

    # Multiplier changes (>=0.2 jump or band change)
    p_m = prior.get("multipliers") or {}
    n_m = now.get("multipliers") or {}
    for setup, n_v in n_m.items():
        p_v = p_m.get(setup, 1.0)
        if abs(n_v - p_v) >= 0.2:
            arrow = "↑" if n_v > p_v else "↓"
            recs.append(f"⚙️  SIZING: {setup} {p_v}× → {n_v}× {arrow}")

    # Sample size growth
    p_s = (prior.get("signal_stats") or {}).get("overall") or {}
    n_s = (now.get("signal_stats") or {}).get("overall") or {}
    p_n = p_s.get("total_closed", 0)
    n_n = n_s.get("total_closed", 0)
    if n_n > p_n:
        recs.append(f"📊 sample grew: {p_n} → {n_n} closed signals "
                    f"(WR {p_s.get('win_rate_pct', 0)}% → {n_s.get('win_rate_pct', 0)}%, "
                    f"avg {p_s.get('avg_pnl_pct', 0):+.2f}% → {n_s.get('avg_pnl_pct', 0):+.2f}%)")

    return recs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="snapshot current state, skip diffing")
    ap.add_argument("--json", action="store_true", help="JSON output to stdout")
    args = ap.parse_args()

    now = _capture()

    if args.reset or not STATE_PATH.exists():
        STATE_PATH.write_text(json.dumps(now, indent=2, default=str))
        if args.json:
            print(json.dumps({"action": "snapshot", "as_of": now["as_of"]}))
        else:
            print(f"✓ Snapshot taken: {STATE_PATH}")
            print(f"  Kill list: {list(now['kill_list'].keys())}")
            print(f"  Stratified: {list(now['band_kills'].keys())}")
        return

    prior = json.loads(STATE_PATH.read_text())
    recs = _diff(prior, now)

    out = {
        "review_date":  now["as_of"],
        "prior_review": prior.get("as_of"),
        "recommendations": recs,
        "current": {
            "kill_list":   list(now["kill_list"].keys()),
            "band_kills":  list(now["band_kills"].keys()),
            "n_closed":    (now["signal_stats"].get("overall") or {}).get("total_closed"),
            "win_rate":    (now["signal_stats"].get("overall") or {}).get("win_rate_pct"),
            "avg_pnl":     (now["signal_stats"].get("overall") or {}).get("avg_pnl_pct"),
        },
    }
    log_path = ROOT / "cache" / f"monthly_review_{now['as_of']}.json"
    log_path.write_text(json.dumps(out, indent=2, default=str))

    if args.json:
        print(json.dumps(out, indent=2, default=str))
        return

    print(f"=== MONTHLY REVIEW — {now['as_of']} (vs {prior.get('as_of')}) ===")
    print(f"Closed signals: {prior.get('signal_stats',{}).get('overall',{}).get('total_closed')} → "
          f"{now['signal_stats']['overall']['total_closed']}")
    print()
    if recs:
        print("Recommendations:")
        for r in recs:
            print(f"  {r}")
    else:
        print("No notable changes since last review — current rules remain calibrated.")
    print(f"\nFull log: {log_path}")
    print(f"To advance baseline: python3 monthly_review.py --reset")


if __name__ == "__main__":
    main()
