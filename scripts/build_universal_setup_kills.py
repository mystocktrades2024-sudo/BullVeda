#!/usr/bin/env python3
"""Build the UNIVERSAL per-setup_type multiplier/kill list for the portfolio-blind
signal layer (2026-06-07).

WHY: the signal layer must be identical for every user (500+ user product). The
legacy `setup_score_multiplier` was derived from the OWNER's signal_log (n=550,
includes WATCH-biased entries) — one account shaping everyone's signals. This
script derives the same edge filter from the SYSTEM's pick track record
(cache/picks_history.json — the canonical tracker feed, the picks the system
publishes to ALL users), at setup_type granularity, with Wilson-LB + PF rigor and
the retail-context calibration from docs/claude_md_calibration.md.

SOURCE CAVEAT: picks_history is the system's *forward* pick record (this
deployment's realized outcomes), not a point-in-time historical backtest. It is
universal (same picks for every user) but carries forward-curve / survivorship
caveats. A true backtest.py-derived list is the eventual upgrade (its --smoke
path is currently slow/regressed — tracked separately). Re-run this monthly
(principle 11, edge erosion).

Rule (retail-calibrated):
  n < 10            -> 1.0  (no verdict, keep active)
  10 <= n < 30      -> 0.5  (preliminary, half size)
  n >= 30:
     PF_hc < 1.00 and avg < 0   -> 0.0  (KILL — genuinely unprofitable)
     PF_hc < 1.10               -> 0.7  (discount)
     PF_hc >= 1.40 and WLB>=.45 -> 1.3  (boost)
     else                       -> 1.0  (keep)
  where PF_hc = PF - 0.10 (retail haircut), WLB = Wilson 95% lower bound.

Writes config["universal_setup_multiplier"] = {setup: mult, ..., _validations:
{setup: {n, wr, wr_lb, pf, pf_haircut, avg_pnl_pct, note, source}}}.

Usage: python3 scripts/build_universal_setup_kills.py [--dry-run]
"""
from __future__ import annotations
import json, math, sys
from pathlib import Path
from collections import defaultdict

BASE = Path(__file__).resolve().parent.parent
PICKS = BASE / "cache" / "picks_history.json"
CONFIG = BASE / "config" / "config.json"

Z = 1.96
PF_HAIRCUT = 0.10
N_PRELIM = 10
N_STD = 30
PF_KILL = 1.00
PF_DISCOUNT = 1.10
PF_BOOST = 1.40
WLB_BOOST = 0.45


def wilson_lb(wins: int, n: int, z: float = Z) -> float:
    if n == 0:
        return 0.0
    p = wins / n
    return (p + z * z / (2 * n) - z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)) / (1 + z * z / n)


def compute() -> dict:
    rows = (json.loads(PICKS.read_text()).get("trades")) or []
    by: dict[str, list[float]] = defaultdict(list)
    dropped = 0
    for r in rows:
        st = (r.get("setup_type") or "").strip()
        if not st:
            continue
        if (r.get("direction") or "long").lower() == "short":
            continue
        try:
            pnl = float(r.get("pct_chg"))
        except (TypeError, ValueError):
            dropped += 1
            continue
        if not math.isfinite(pnl):
            dropped += 1
            continue
        by[st].append(pnl)

    mults: dict = {}
    validations: dict = {}
    for st, pnls in sorted(by.items(), key=lambda x: -len(x[1])):
        n = len(pnls)
        wins = sum(1 for p in pnls if p > 0)
        wr = wins / n
        lb = wilson_lb(wins, n)
        gp = sum(p for p in pnls if p > 0)
        gl = abs(sum(p for p in pnls if p < 0))
        pf = (gp / gl) if gl > 0 else (9.99 if gp > 0 else 0.0)
        pf_hc = pf - PF_HAIRCUT
        avg = sum(pnls) / n

        if n < N_PRELIM:
            mult, basis = 1.0, f"n={n}<{N_PRELIM} — no verdict, kept active"
        elif n < N_STD:
            mult, basis = 0.5, f"preliminary (10<=n<30) — half size pending more data"
        elif pf_hc < PF_KILL and avg < 0:
            mult, basis = 0.0, f"KILL — PF {pf:.2f} (hc {pf_hc:.2f}) <1.0 and avg {avg:+.2f}% <0 on n={n}"
        elif pf_hc < PF_DISCOUNT:
            mult, basis = 0.7, f"discount — PF_hc {pf_hc:.2f} <1.10 on n={n}"
        elif pf_hc >= PF_BOOST and lb >= WLB_BOOST:
            mult, basis = 1.3, f"boost — PF_hc {pf_hc:.2f}>=1.40, WilsonLB {lb*100:.1f}%>=45% on n={n}"
        else:
            mult, basis = 1.0, f"keep — PF_hc {pf_hc:.2f} on n={n}"

        # Only non-1.0 entries need to live in the multiplier map; 1.0 is the default.
        if mult != 1.0:
            mults[st] = mult
        validations[st] = {
            "n": n, "wr": round(wr, 3), "wr_lb": round(lb, 3),
            "pf": round(pf, 2), "pf_haircut": round(pf_hc, 2),
            "avg_pnl_pct": round(avg, 2),
            "note": basis,
            "source": "picks_history.json (system pick track record, universal)",
        }
    mults["_validations"] = validations
    mults["_meta"] = {
        "generated_by": "scripts/build_universal_setup_kills.py",
        "source": "cache/picks_history.json",
        "n_trades": sum(len(v) for v in by.values()),
        "n_setups": len(by),
        "dropped_nonfinite": dropped,
        "rule": "retail-calibrated; n>=30 firm, PF haircut 0.10, Wilson z=1.96",
        "caveat": "forward pick-record (not point-in-time backtest); universal across users; re-run monthly",
    }
    mults["_note"] = ("UNIVERSAL setup multiplier — consumed by analysis.py ONLY when "
                      "signal_layer_portfolio_blind._enabled=true (replaces the account-derived "
                      "setup_score_multiplier). Regenerate: python3 scripts/build_universal_setup_kills.py")
    return mults


def main():
    dry = "--dry-run" in sys.argv
    block = compute()
    # Pretty print summary
    print(f"Universal setup multipliers (source: {block['_meta']['source']}, "
          f"n_trades={block['_meta']['n_trades']}):")
    for st, v in block["_validations"].items():
        m = block.get(st, 1.0)
        print(f"  {st:30} mult={m:<4} | {v['note']}")
    if dry:
        print("\n--dry-run: config not written.")
        return
    cfg = json.loads(CONFIG.read_text())
    cfg["universal_setup_multiplier"] = block
    # ensure_ascii=False preserves the hand-maintained UTF-8 (em-dashes etc.) in
    # the _note fields — default True would escape them all and churn the whole diff.
    CONFIG.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))
    print(f"\nWrote config['universal_setup_multiplier'] -> {CONFIG}")


if __name__ == "__main__":
    main()
