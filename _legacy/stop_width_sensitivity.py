"""
Stop-width sensitivity sweep — backtests alternative stop multipliers
against the recorded signal_log and reports WR / R / PF / Basel zone for each.

Methodology:
  - Each closed trade has: entry, stop, mae_pct, mfe_pct, actual_pnl_pct
  - actual_pnl_pct represents the NATURAL day-10 outcome (signals were tracked,
    not executed — so stops weren't triggered in the recording)
  - For each candidate stop multiplier m:
      new_stop_dist_pct = original_stop_dist_pct * m
      if mae_pct deeper than new_stop_dist → simulated stop hit; loss = -new_stop_dist
      else → trade runs to natural outcome (actual_pnl_pct)
  - R is computed against the NEW stop distance (consistent denomination)

Output: table of (multiplier, WR%, avg_R, PF, expectancy, Basel zone, exception rate).
"""
from __future__ import annotations
import json
import statistics
from pathlib import Path

LOG_PATH = Path(__file__).parent / "data" / "signal_log.json"


def simulate(trades: list[dict], multiplier: float) -> dict:
    """Re-simulate outcomes with stop_distance × multiplier."""
    pnls = []      # realized PnL %
    r_mults = []   # R-multiples vs new stop distance
    n_stopped = 0
    n_target_hits = 0
    for t in trades:
        e = t.get("entry_price") or 0
        st = t.get("stop") or 0
        t1 = t.get("target1") or 0
        if not e or not st:
            continue
        orig_stop_dist = abs(e - st) / e * 100
        new_stop_dist = orig_stop_dist * multiplier
        mae = abs(t.get("mae_pct") or 0)
        mfe = t.get("mfe_pct") or 0
        actual = t.get("actual_pnl_pct")
        if actual is None:
            continue
        # T1 distance
        t1_dist = (t1 - e) / e * 100 if t.get("direction", "long") == "long" else (e - t1) / e * 100

        if mae > new_stop_dist:
            # Stop hit at new wider/tighter level
            pnl = -new_stop_dist
            n_stopped += 1
        elif mfe >= t1_dist > 0:
            # T1 was reached — assume we sell half at T1, rest exits at actual
            # (conservative: weight 50/50)
            pnl = 0.5 * t1_dist + 0.5 * actual
            n_target_hits += 1
        else:
            # Ran to natural day-10 outcome
            pnl = actual
        pnls.append(pnl)
        r_mults.append(pnl / new_stop_dist if new_stop_dist > 0 else 0)
    return _summarize(pnls, r_mults, n_stopped, n_target_hits)


def _summarize(pnls, r_mults, n_stopped, n_target_hits) -> dict:
    n = len(pnls)
    if n == 0:
        return {"n": 0}
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    sum_wins = sum(wins)
    sum_losses_abs = abs(sum(losses)) if losses else 0
    pf = sum_wins / sum_losses_abs if sum_losses_abs > 0 else float("inf")
    # Basel exception = trade hit ≤ -1R
    exceptions = sum(1 for r in r_mults if r <= -1.0)
    exception_rate = exceptions / n * 100
    # Basel zone (250-trade thresholds, scaled to our n)
    expected_5pct = n * 0.05
    if exceptions <= expected_5pct + 0.5:
        zone = "GREEN"
    elif exceptions <= expected_5pct * 2:
        zone = "YELLOW"
    else:
        zone = "RED"
    return {
        "n": n,
        "win_rate": round(len(wins) / n * 100, 1),
        "avg_pnl_pct": round(statistics.mean(pnls), 2),
        "avg_r": round(statistics.mean(r_mults), 2),
        "pf": round(pf, 2) if pf != float("inf") else "∞",
        "expectancy_r": round(statistics.mean(r_mults), 2),
        "n_stopped": n_stopped,
        "n_target_hits": n_target_hits,
        "exceptions": exceptions,
        "exception_rate_pct": round(exception_rate, 2),
        "basel_zone": zone,
    }


def main():
    log = json.loads(LOG_PATH.read_text())
    closed = [s for s in log if s.get("status") == "CLOSED"]
    print(f"Loaded {len(closed)} closed trades from signal_log.json\n")

    # Baseline (1.0× — current)
    multipliers = [0.75, 1.00, 1.25, 1.50, 1.75, 2.00, 2.25, 2.50]
    results = {}
    print(f"{'MULT':>6} {'N':>4} {'WIN%':>6} {'AVG R':>7} {'PF':>6} {'STOPPED':>8} {'EXCEPT':>7} {'EX_RATE':>8} {'ZONE':>8}")
    print("─" * 70)
    for m in multipliers:
        r = simulate(closed, m)
        results[m] = r
        zone_glyph = {"GREEN": "● GREEN", "YELLOW": "◐ YELLOW", "RED": "○ RED"}.get(r["basel_zone"], r["basel_zone"])
        pf_str = str(r["pf"])
        print(f"{m:>6.2f} {r['n']:>4} {r['win_rate']:>6.1f} {r['avg_r']:>7.2f} {pf_str:>6} {r['n_stopped']:>8} {r['exceptions']:>7} {r['exception_rate_pct']:>8.2f} {zone_glyph:>8}")

    # Best by expectancy (avg R)
    best_r = max(results.items(), key=lambda kv: kv[1]["avg_r"])
    print(f"\nBest by avg-R: {best_r[0]:.2f}× → {best_r[1]['avg_r']} R/trade · WR {best_r[1]['win_rate']}% · PF {best_r[1]['pf']} · Basel {best_r[1]['basel_zone']}")

    # First multiplier that hits GREEN zone
    green = [m for m, r in results.items() if r["basel_zone"] == "GREEN"]
    if green:
        m = min(green)
        r = results[m]
        print(f"First GREEN: {m:.2f}× → {r['avg_r']} R/trade · WR {r['win_rate']}% · PF {r['pf']}")
    else:
        # First YELLOW
        yellow = [m for m, r in results.items() if r["basel_zone"] == "YELLOW"]
        if yellow:
            m = min(yellow)
            r = results[m]
            print(f"First YELLOW (no GREEN exists): {m:.2f}× → {r['avg_r']} R/trade · WR {r['win_rate']}% · PF {r['pf']}")
        else:
            print("No multiplier in tested range achieves YELLOW or GREEN zone.")

    # Save report for downstream use
    out = Path(__file__).parent / "cache" / "stop_sensitivity.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nSaved → {out}")


if __name__ == "__main__":
    main()
