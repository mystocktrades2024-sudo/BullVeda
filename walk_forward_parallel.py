#!/usr/bin/env python3
"""AI-12: Parallel walk-forward backtest runner.

Runs N independent backtest.py processes concurrently with different
parameter combinations (days windows, score/rs thresholds, or position
sizes), then aggregates the results into a comparison matrix.

Each fold is a separate subprocess → uses multiple CPU cores and produces
a per-fold result file under cache/walk_forward/. Output summary JSON at
cache/walk_forward/summary.json.

Usage:
  # Default: 3 folds (1yr / 2yr / 3yr lookback)
  python3 walk_forward_parallel.py

  # Custom matrix via JSON config
  python3 walk_forward_parallel.py --matrix '[{"days":252,"tag":"1yr"},{"days":504,"tag":"2yr"}]'

  # Sensitivity sweep (AI-19): vary buy_min_score
  python3 walk_forward_parallel.py --sensitivity score --values 60,65,70,75

  # Parallelism cap
  python3 walk_forward_parallel.py --max-workers 2
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).parent
_OUT_DIR = _ROOT / "cache" / "walk_forward"
_OUT_DIR.mkdir(parents=True, exist_ok=True)


def _run_one_fold(spec: dict) -> dict:
    """Execute one backtest subprocess and capture its result."""
    tag = spec.get("tag", f"fold_{id(spec) & 0xffff:x}")
    log_file = _OUT_DIR / f"{tag}.log"
    result_file = _OUT_DIR / f"{tag}.json"

    cmd = [
        sys.executable, str(_ROOT / "backtest.py"),
        "--portfolio",
        "--days", str(spec.get("days", 252)),
        "--hold", str(spec.get("hold", 7)),
        "--min-score", str(spec.get("min_score", 55)),
        "--min-rs", str(spec.get("min_rs", 65)),
        "--top-n", str(spec.get("top_n", 5)),
        "--equity", str(spec.get("equity", 5000)),
        "--positions", str(spec.get("positions", 5)),
        "--size-pct", str(spec.get("size_pct", 0.25)),
    ]

    start = time.time()
    with log_file.open("w") as lf:
        proc = subprocess.run(cmd, cwd=str(_ROOT), stdout=lf, stderr=subprocess.STDOUT)
    elapsed = time.time() - start

    # Parse last backtest summary from cache/backtest_results.json (backtest.py writes it)
    summary = {"tag": tag, "spec": spec, "exit_code": proc.returncode,
               "elapsed_sec": round(elapsed, 1), "log": str(log_file)}

    # Pull any machine-readable result backtest.py may have written
    try:
        bt_results = _ROOT / "cache" / "backtest_results.json"
        if bt_results.exists():
            summary["results"] = json.loads(bt_results.read_text())
    except Exception:
        pass

    # Extract key metrics by grepping the log
    try:
        text = log_file.read_text()
        import re
        for pat, key in [
            (r"Win rate:\s*([\d.]+)%", "win_rate"),
            (r"Profit factor:\s*([\d.]+)", "profit_factor"),
            (r"Total return:\s*([+-]?[\d.]+)%", "total_return_pct"),
            (r"Max drawdown:\s*([+-]?[\d.]+)%", "max_drawdown_pct"),
            (r"Total trades:\s*(\d+)", "total_trades"),
        ]:
            m = re.search(pat, text)
            if m:
                summary[key] = float(m.group(1)) if "." in m.group(1) or "-" in m.group(1) else int(m.group(1))
    except Exception:
        pass

    result_file.write_text(json.dumps(summary, indent=2, default=str))
    return summary


def build_default_matrix() -> list[dict]:
    """3-fold walk-forward: 1-year / 2-year / 3-year trailing windows."""
    return [
        {"tag": "1yr_trailing", "days": 252, "hold": 7, "min_score": 55, "min_rs": 65},
        {"tag": "2yr_trailing", "days": 504, "hold": 7, "min_score": 55, "min_rs": 65},
        {"tag": "3yr_trailing", "days": 756, "hold": 7, "min_score": 55, "min_rs": 65},
    ]


def build_sensitivity_matrix(param: str, values: list[float]) -> list[dict]:
    """Generate a matrix varying one parameter for AI-19 sensitivity grid."""
    base = {"days": 252, "hold": 7, "min_score": 55, "min_rs": 65}
    matrix = []
    for v in values:
        spec = dict(base)
        if param == "score":
            spec["min_score"] = int(v)
            spec["tag"] = f"score_{int(v)}"
        elif param == "rs":
            spec["min_rs"] = int(v)
            spec["tag"] = f"rs_{int(v)}"
        elif param == "hold":
            spec["hold"] = int(v)
            spec["tag"] = f"hold_{int(v)}"
        elif param == "size":
            spec["size_pct"] = float(v)
            spec["tag"] = f"size_{int(v*100)}pct"
        else:
            raise ValueError(f"unknown sensitivity param: {param}")
        matrix.append(spec)
    return matrix


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--matrix", help="JSON list of fold specs. Overrides default.")
    ap.add_argument("--sensitivity", choices=["score", "rs", "hold", "size"],
                    help="Sweep a single parameter (AI-19).")
    ap.add_argument("--values", help="Comma-separated values for --sensitivity")
    ap.add_argument("--max-workers", type=int, default=3,
                    help="Parallel subprocess cap (default 3)")
    args = ap.parse_args()

    # Build matrix
    if args.matrix:
        matrix = json.loads(args.matrix)
    elif args.sensitivity and args.values:
        vals = [float(v) for v in args.values.split(",")]
        matrix = build_sensitivity_matrix(args.sensitivity, vals)
    else:
        matrix = build_default_matrix()

    print(f"=== Parallel walk-forward — {len(matrix)} folds, max {args.max_workers} workers ===")
    for i, spec in enumerate(matrix):
        print(f"  fold {i+1}: {spec.get('tag', '?')} — "
              f"days={spec.get('days', '?')} hold={spec.get('hold', '?')} "
              f"score>={spec.get('min_score', '?')} rs>={spec.get('min_rs', '?')}")
    print()

    started = datetime.now()
    results = []

    # Fork N parallel subprocesses via ProcessPoolExecutor
    with ProcessPoolExecutor(max_workers=args.max_workers) as pool:
        futs = {pool.submit(_run_one_fold, spec): spec for spec in matrix}
        for fut in as_completed(futs):
            spec = futs[fut]
            try:
                r = fut.result()
                results.append(r)
                print(f"  ✓ {r['tag']} — "
                      f"WR {r.get('win_rate', '?')}% · "
                      f"PF {r.get('profit_factor', '?')} · "
                      f"Return {r.get('total_return_pct', '?')}% · "
                      f"N {r.get('total_trades', '?')} · "
                      f"{r['elapsed_sec']}s")
            except Exception as e:
                print(f"  ✗ {spec.get('tag', '?')} failed: {e}")

    elapsed_total = (datetime.now() - started).total_seconds()
    print(f"\nAll folds complete in {elapsed_total:.0f}s (would be ~{elapsed_total*len(matrix):.0f}s sequential)")

    # Aggregate summary
    summary = {
        "generated": started.isoformat(),
        "elapsed_sec": round(elapsed_total, 1),
        "parallelism_saved_sec": round(elapsed_total * (len(matrix) - 1), 1),
        "n_folds": len(results),
        "results": sorted(results, key=lambda r: r.get("tag", "")),
        "aggregated": _aggregate(results),
    }
    (_OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(f"\nSummary: {_OUT_DIR}/summary.json")

    # Print aggregate table
    agg = summary["aggregated"]
    if agg:
        print()
        print(f"Aggregate across {len(results)} folds:")
        print(f"  WR:      mean {agg['wr_mean']:.1f}% · min {agg['wr_min']:.1f}% · max {agg['wr_max']:.1f}%")
        print(f"  PF:      mean {agg['pf_mean']:.2f}")
        print(f"  Return:  mean {agg['return_mean']:.1f}% · min {agg['return_min']:.1f}%")
        # Flag folds below 60% WR per AI-12 spec
        weak = [r["tag"] for r in results if isinstance(r.get("win_rate"), (int, float)) and r["win_rate"] < 60]
        if weak:
            print(f"  ⚠️  Folds below 60% WR: {', '.join(weak)}")

    return 0


def _aggregate(results: list[dict]) -> dict | None:
    wrs = [r["win_rate"] for r in results if isinstance(r.get("win_rate"), (int, float))]
    pfs = [r["profit_factor"] for r in results if isinstance(r.get("profit_factor"), (int, float))]
    rets = [r["total_return_pct"] for r in results if isinstance(r.get("total_return_pct"), (int, float))]
    if not wrs:
        return None
    return {
        "wr_mean":   round(sum(wrs) / len(wrs), 1),
        "wr_min":    round(min(wrs), 1),
        "wr_max":    round(max(wrs), 1),
        "pf_mean":   round(sum(pfs) / len(pfs), 2) if pfs else 0,
        "return_mean": round(sum(rets) / len(rets), 1) if rets else 0,
        "return_min":  round(min(rets), 1) if rets else 0,
    }


if __name__ == "__main__":
    sys.exit(main())
