"""Build cache/ml/stress_buckets.json from historical_backfill samples.

For each (mode, stress_scenario) compute the conditional mean q50 shift
observed in historical samples that match the scenario. This replaces the
heuristic stress overlay in the AI Prediction tab with real data.

Stress scenarios use rs_vs_spy_63d as the relative-stress proxy (since VIX
isn't a feature). Logic:
  - 'base'      → all samples
  - 'spy_down'  → samples where rs_vs_spy_63d ≤ −0.05 (SPY weak, sell-off mode)
  - 'vix'       → samples where rvol_20 ≥ 1.5 AND atr_pct ≥ 0.04 (elevated vol)

Output:
    {
      "swing":    {"base": {"q10":..,"q50":..,"q90":..}, "spy_down": {...}, "vix": {...}},
      "position": {...},
      "invest":   {...},
      "_meta":    {n_samples, generated_at}
    }

Run once after each `ml.historical_backfill` regenerate. Cheap (~5s).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

BACKFILL = ROOT / "cache" / "ml" / "historical_backfill.json"
OUT = ROOT / "cache" / "ml" / "stress_buckets.json"


def _quantiles(values, qs=(0.10, 0.25, 0.50, 0.75, 0.90)):
    if not values:
        return None
    vs = sorted(values)
    n = len(vs)
    out = {}
    for q in qs:
        idx = int(q * (n - 1))
        out[f"q{int(q * 100)}"] = round(vs[idx], 4)
    return out


def main():
    if not BACKFILL.exists():
        print(f"[stress] no backfill at {BACKFILL}; abort")
        return
    print(f"[stress] reading {BACKFILL}…")
    data = json.loads(BACKFILL.read_text())
    rows = data.get("rows") or []
    print(f"[stress] {len(rows):,} rows")

    out = {"_meta": {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_total":      len(rows),
    }}
    targets = [("swing", "y_5d"), ("position", "y_21d"), ("invest", "y_126d")]

    for mode, ycol in targets:
        base_returns = [r[ycol] for r in rows if r.get(ycol) is not None]
        spy_down_returns = [
            r[ycol] for r in rows
            if r.get(ycol) is not None and (r.get("rs_vs_spy_63d") or 0) <= -0.05
        ]
        vix_returns = [
            r[ycol] for r in rows
            if r.get(ycol) is not None
            and (r.get("rvol_20") or 0) >= 1.5
            and (r.get("atr_pct") or 0) >= 0.04
        ]
        out[mode] = {
            "base":     _quantiles(base_returns),
            "spy_down": _quantiles(spy_down_returns),
            "vix":      _quantiles(vix_returns),
            "n": {
                "base":     len(base_returns),
                "spy_down": len(spy_down_returns),
                "vix":      len(vix_returns),
            },
        }
        print(f"[stress] {mode}: base={len(base_returns)}, spy_down={len(spy_down_returns)}, vix={len(vix_returns)}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2))
    print(f"[stress] wrote {OUT}")


if __name__ == "__main__":
    main()
