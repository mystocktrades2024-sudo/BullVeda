#!/usr/bin/env python3
"""
build_backtest_baseline.py — derive the audit's backtest baseline from the latest
portfolio backtest output, write cache/backtest_baseline.json.

The audit (scripts/audit_live_vs_backtest.py) reads cache/backtest_baseline.json as
the authoritative per-setup backtest column (live PF is compared against it). This
script computes per-setup PF/WR + survivorship/PF haircut from the trade-level
records of the most recent comprehensive backtest (prefers the widest window).

Source preference (most trades / widest window first):
  cache/portfolio_backtest_252d*.json  →  cache/portfolio_backtest_*.json (latest)

  python3 scripts/build_backtest_baseline.py
  python3 scripts/build_backtest_baseline.py --file cache/portfolio_backtest_252d_....json
"""
from __future__ import annotations

import argparse
import glob
import json
import os
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "cache" / "backtest_baseline.json"
PF_HAIRCUT = 0.20  # survivorship + friction haircut (CLAUDE.md principle 6/19)


def _pick_source(explicit: str | None) -> str | None:
    if explicit:
        return explicit if os.path.exists(explicit) else None
    # prefer the widest window (252d), else the most recent of any portfolio backtest
    for pat in ("cache/portfolio_backtest_252d*.json", "cache/portfolio_backtest_*.json"):
        fs = sorted(glob.glob(str(ROOT / pat)), key=os.path.getmtime, reverse=True)
        fs = [f for f in fs if "_5d_" not in f]  # skip tiny smoke runs
        if fs:
            return fs[0]
    return None


def build(explicit: str | None = None) -> dict:
    src = _pick_source(explicit)
    if not src:
        raise SystemExit("no portfolio_backtest_*.json found to build a baseline from")
    d = json.loads(Path(src).read_text())
    trades = d.get("trades") or []
    if not trades:
        raise SystemExit(f"{src} has no trade-level records")

    g = defaultdict(list)
    for t in trades:
        s = t.get("setup_type") or t.get("setup_family")
        if s and t.get("pnl_pct") is not None:
            g[s].append(float(t["pnl_pct"]))

    base = {}
    for setup, rs in g.items():
        n = len(rs)
        wins = sum(1 for r in rs if r > 0)
        gains = sum(r for r in rs if r > 0)
        losses = -sum(r for r in rs if r < 0)
        pf = round(gains / losses, 3) if losses > 0 else None
        base[setup] = {
            "n": n,
            "wr": round(wins / n, 4) if n else None,
            "pf": pf,
            "pf_haircut": (round(pf - PF_HAIRCUT, 3) if pf is not None else None),
            "source": "walk_forward" if "wf" in src.lower() else "backtest_single_window",
            "from_file": os.path.basename(src),
        }
    OUT.write_text(json.dumps(base, indent=1))
    return {"src": os.path.basename(src), "setups": len(base), "trades": len(trades)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=None, help="explicit backtest json to use")
    a = ap.parse_args()
    r = build(a.file)
    print(f"✓ wrote {OUT.name} from {r['src']} · {r['setups']} setups · {r['trades']} trades")
