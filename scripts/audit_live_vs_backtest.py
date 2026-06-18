#!/usr/bin/env python3
"""
audit_live_vs_backtest.py — the signal audit: LIVE realized edge vs BASELINE.
=============================================================================
Puts each setup family's REAL forward-realized outcome (from the live audit
ledger — out-of-sample, no look-ahead, real frictions) next to the BASELINE
expectation (setup_stats.json: WR/PF with survivorship + PF haircuts already
applied). The gap is the audit:

  • live PF ≥ baseline (haircut)  → CONFIRMED — the edge survives into reality
  • live PF < baseline materially  → ERODING  — overfit / decayed edge, investigate
  • n < 30                         → THIN     — insufficient evidence (principle 1)

Baseline source is pluggable: today it's setup_stats.json (the tracker's haircut
belief). When a fresh walk-forward backtest is run (scripts/walk_forward_v2), drop
its per-setup PF into baseline.json under the same family keys and it becomes the
"backtest" column — no code change.

Live PF/WR are computed from `realized_r` (the ledger's canonical realized R).
Wilson 95% lower bound is shown on the live WR so point estimates don't mislead.

Usage:
    python3 scripts/audit_live_vs_backtest.py              # print table
    python3 scripts/audit_live_vs_backtest.py --json       # machine-readable
    python3 scripts/audit_live_vs_backtest.py --by-regime  # split by regime4
"""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "cache" / "audit_ledger.json"
SETUP_STATS = ROOT / "cache" / "setup_stats.json"
BASELINE_OVERRIDE = ROOT / "cache" / "backtest_baseline.json"  # optional WF backtest drop-in
OUT_JSON = ROOT / "cache" / "audit_live_vs_backtest.json"

WILSON_Z = 1.96
MIN_N = 30          # principle 1 — below this, evidence is preliminary
EROSION_PF_GAP = 0.15  # live PF this far below baseline → flag erosion


def wilson_lb(wins: int, n: int, z: float = WILSON_Z) -> float:
    if n == 0:
        return 0.0
    p = wins / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)
    return max(0.0, (centre - margin) / denom)


def _pf(rs: list[float]) -> float | None:
    gains = sum(r for r in rs if r > 0)
    losses = -sum(r for r in rs if r < 0)
    if losses == 0:
        return None  # undefined (no losing trades) — JSON-safe; these are tiny-n
    return round(gains / losses, 3)


def _stats(rs: list[float]) -> dict:
    n = len(rs)
    wins = sum(1 for r in rs if r > 0)
    return {
        "n": n,
        "wr": round(wins / n, 4) if n else None,
        "wilson_lb": round(wilson_lb(wins, n), 4) if n else None,
        "pf": _pf(rs),
        "avg_r": round(sum(rs) / n, 3) if n else None,
        "sum_r": round(sum(rs), 1) if n else None,
    }


def load_live(by_regime: bool = False) -> dict:
    recs = json.loads(LEDGER.read_text())["records"]
    groups: dict = defaultdict(list)
    for r in recs:
        rr = r.get("realized_r")
        fam = r.get("setup_family")
        if rr is None or not fam:
            continue
        key = (fam, r.get("regime4") or "?") if by_regime else fam
        groups[key].append(float(rr))
    return {k: _stats(v) for k, v in groups.items()}


def load_baseline() -> dict:
    """Per-family baseline expectation. WF backtest override wins if present."""
    base = {}
    if SETUP_STATS.exists():
        s = json.loads(SETUP_STATS.read_text()).get("setups", {})
        for fam, d in s.items():
            base[fam] = {
                "n": d.get("n"),
                "wr": d.get("wr"),
                "pf": d.get("pf"),
                "pf_haircut": d.get("pf_haircut"),
                "source": "setup_stats(haircut)",
            }
    if BASELINE_OVERRIDE.exists():
        try:
            for fam, d in json.loads(BASELINE_OVERRIDE.read_text()).items():
                base[fam] = {**d, "source": "walk_forward"}
        except Exception:
            pass
    return base


def verdict(live: dict, base: dict | None) -> str:
    if not live or live.get("n", 0) < MIN_N:
        return "THIN"
    lpf = live.get("pf")
    if lpf is None:
        return "THIN"
    if not base:
        return "NO-BASE"
    raw = base.get("pf")               # the actual expected edge
    hair = base.get("pf_haircut")      # conservative floor (survivorship+frictions)
    if raw is None and hair is None:
        return "NO-BASE"
    # CONFIRMED only if live clears the RAW expectation; SOFT within the haircut
    # band (real but light); ERODING below even the conservative floor.
    if raw is not None and lpf >= raw:
        return "CONFIRMED"
    if hair is not None and lpf >= hair:
        return "SOFT"
    return "ERODING"


def build(by_regime: bool = False) -> dict:
    live = load_live(by_regime)
    base = load_baseline()
    rows = []
    for key in sorted(live.keys(), key=lambda k: -(live[k].get("n") or 0)):
        fam = key[0] if by_regime else key
        L = live[key]
        B = base.get(fam)
        rows.append({
            "setup": (f"{key[0]} · {key[1]}" if by_regime else key),
            "family": fam,
            "live": L,
            "baseline": B,
            "pf_gap": (round(L["pf"] - (B.get("pf_haircut") or B.get("pf")), 3)
                       if (B and L.get("pf") not in (None, float("inf"))
                           and (B.get("pf_haircut") or B.get("pf")) is not None) else None),
            "verdict": verdict(L, B),
        })
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "min_n": MIN_N, "wilson_z": WILSON_Z,
        "baseline_note": "baseline = setup_stats haircut expectation unless walk_forward override present",
        "rows": rows,
    }


def _fmt_pf(v):
    if v is None:
        return "—"
    return "∞" if v == float("inf") else f"{v:.2f}"


def print_table(data: dict):
    rows = data["rows"]
    h = f"{'SETUP':<34} {'n':>5} {'WR':>6} {'WilsLB':>7} {'livePF':>7} | {'baseWR':>6} {'basePF*':>7} | {'gap':>6}  VERDICT"
    print(h); print("-" * len(h))
    for r in rows:
        L, B = r["live"], r["baseline"]
        bwr = f"{B['wr']*100:.0f}%" if (B and B.get("wr") is not None) else "—"
        bpf = _fmt_pf(B.get("pf_haircut") if B else None)
        gap = f"{r['pf_gap']:+.2f}" if r["pf_gap"] is not None else "—"
        print(f"{r['setup']:<34} {L['n']:>5} {(L['wr'] or 0)*100:>5.0f}% "
              f"{(L['wilson_lb'] or 0)*100:>6.0f}% {_fmt_pf(L.get('pf')):>7} | "
              f"{bwr:>6} {bpf:>7} | {gap:>6}  {r['verdict']}")
    print()
    counts = defaultdict(int)
    for r in rows:
        counts[r["verdict"]] += 1
    print("verdicts: " + " · ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    print("* basePF = survivorship+PF-haircut expectation (setup_stats). "
          "CONFIRMED = live edge ≥ baseline; ERODING = live materially below.")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="audit_live_vs_backtest.py")
    ap.add_argument("--json", action="store_true", help="emit JSON only")
    ap.add_argument("--by-regime", action="store_true", help="split by regime4")
    args = ap.parse_args(argv)
    data = build(by_regime=args.by_regime)
    OUT_JSON.write_text(json.dumps(data, default=str, indent=1))
    if args.json:
        print(json.dumps(data, default=str, indent=1))
    else:
        print_table(data)
        print(f"\nwrote {OUT_JSON}")


if __name__ == "__main__":
    main()
