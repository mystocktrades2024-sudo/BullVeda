"""True walk-forward backtest — tune on train, score on test, per-fold metrics.

Usage:
    python3 backtest/walk_forward_v2.py --folds 4 --train-days 250 --test-days 50
"""
from dataclasses import dataclass, field
from datetime import date, timedelta
import subprocess
import json
import logging
from pathlib import Path
import math

log = logging.getLogger("wf_v2")
logging.basicConfig(level=logging.INFO)

BASE_DIR = Path(__file__).parent.parent


@dataclass
class FoldResult:
    fold_id: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    tuned_min_score: int
    tuned_min_rs: int
    n_trades: int = 0
    wr: float = 0.0
    pf: float = 0.0
    max_dd: float = 0.0
    sharpe: float = 0.0


def wilson_ci(wins: int, total: int, confidence: float = 0.95) -> tuple[float, float]:
    """95% Wilson confidence interval for win rate."""
    if total == 0:
        return (0.0, 1.0)
    z = 1.96  # 95%
    phat = wins / total
    denom = 1 + z*z/total
    center = (phat + z*z/(2*total)) / denom
    spread = z * math.sqrt((phat*(1-phat) + z*z/(4*total)) / total) / denom
    return (max(0, center - spread), min(1, center + spread))


def tune_on_train(train_start: str, train_end: str) -> dict:
    """Grid search over (min_score, min_rs) on train window. Return best pair.

    Optimized (2026-04-15): coarser grid (3×4=12 vs 5×5=25), parallel execution
    (4 workers), 3600s timeout. Cuts tuning time ~5× vs original.

    TODO (P2 follow-up, 2026-05-08): extend grid to also tune
      config["setup_score_multiplier"] candidates per setup family. Today the
      multipliers (Trend Continuation +8%, etc.) are hand-edited based on
      eyeballing 60d backtest output — exactly the noise-driven tuning the
      Wilson CI gates in decision_engine.py defend against.

      Implementation sketch:
        1. backtest.py needs a new --config-override <json> CLI arg that
           merges into the loaded config before analyze_ticker runs.
        2. tune_on_train() then iterates a multiplier grid per setup family:
             {"Trend Continuation": [1.00, 1.05, 1.10],
              "EMA21 Pullback":     [1.00, 0.95, 0.90], ...}
        3. Per fold: pick best multipliers on train, validate they ALSO
           improve on test (no train→test sign flip allowed), then write
           config["setup_score_multiplier"]["_validations"][setup] with
           {"n": fold_n, "wr_lb": fold_wr_lb, "source": f"wf_fold_{i}"}.
        4. Only multipliers with passing _validations actually take effect
           (analysis.py:8503 enforces this).

      Effort: ~3 hours once 3y OHLCV backfill is done (P1).
    """
    score_grid = [55, 62, 72]
    rs_grid = [55, 65, 75, 85]

    from concurrent.futures import ThreadPoolExecutor, as_completed

    best = {"score": 0, "min_score": 65, "min_rs": 70}
    combos = [(ms, mrs) for ms in score_grid for mrs in rs_grid]
    log.info(f"Grid search: {len(combos)} combos on {train_start}→{train_end}")

    def _eval(ms_mrs):
        ms, mrs = ms_mrs
        try:
            result = run_backtest_subset(
                start=train_start, end=train_end,
                min_score=ms, min_rs=mrs,
            )
            sharpe = result.get("sharpe", 0)
            n = result.get("n_trades", 0)
            objective = sharpe * math.sqrt(max(n, 1))
            return ms, mrs, objective, result
        except Exception as e:
            log.warning(f"Grid point ms={ms},mrs={mrs} failed: {e}")
            return ms, mrs, 0, {}

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_eval, c): c for c in combos}
        done = 0
        for fut in as_completed(futures):
            ms, mrs, obj, res = fut.result()
            done += 1
            log.info(f"  [{done}/{len(combos)}] ms={ms} mrs={mrs} → obj={obj:.2f} "
                     f"(n={res.get('n_trades',0)}, wr={res.get('wr',0):.1%})")
            if obj > best["score"]:
                best = {"score": obj, "min_score": ms, "min_rs": mrs}

    log.info(f"Best on train: min_score={best['min_score']}, min_rs={best['min_rs']} (obj={best['score']:.2f})")
    return best


def run_backtest_subset(start: str, end: str, min_score: int, min_rs: int) -> dict:
    """Invoke backtest.py with date range + thresholds; parse summary."""
    # Use existing backtest.py CLI. Days = (end - start).days
    from datetime import date as _d
    s = _d.fromisoformat(start); e = _d.fromisoformat(end)
    days = (e - s).days
    cmd = [
        "python3", str(BASE_DIR / "backtest.py"),
        "--portfolio",  # 2026-05-08: required to get Sharpe/MaxDD/Total trades aliases
        "--days", str(days),
        "--min-score", str(min_score),
        "--min-rs", str(min_rs),
        "--end-date", end,  # backtest.py must support --end-date flag
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    # Parse summary from stdout. backtest.py prints machine-readable aliases
    # (lowercase "Total trades:" etc.) at lines 1754-1757 specifically for us
    # WHEN --portfolio is passed. Without --portfolio, only the signal-mode
    # summary prints ("Total signals:") and we silently get zeros — that's the
    # bug the audit caught. The fallback below handles signal mode gracefully
    # so a missing flag returns *something* meaningful instead of all zeros.
    result = {"n_trades": 0, "wr": 0, "pf": 0, "max_dd": 0, "sharpe": 0}
    for line in proc.stdout.splitlines():
        # Strip percentage signs and commas before parsing
        def _num(s: str) -> float:
            return float(s.replace(",", "").replace("%", "").strip())
        try:
            if "Total trades:" in line or "Total Trades:" in line:
                result["n_trades"] = int(_num(line.split(":")[-1]))
            elif "Total signals:" in line and result["n_trades"] == 0:
                result["n_trades"] = int(_num(line.split(":")[-1]))
            elif "Win rate:" in line and "raw" not in line:
                result["wr"] = _num(line.split(":")[-1]) / 100
            elif "Win Rate (adj):" in line:
                # "Win Rate (adj):   X.X%  (minus ...)" → take leading number
                v = line.split(":")[-1].split("(")[0]
                result["wr"] = _num(v) / 100
            elif "Profit factor:" in line or "Profit Factor:" in line:
                result["pf"] = _num(line.split(":")[-1])
            elif "Max drawdown:" in line or "Max Drawdown:" in line:
                result["max_dd"] = _num(line.split(":")[-1]) / 100
            elif "Sharpe:" in line:
                result["sharpe"] = _num(line.split(":")[-1])
        except (ValueError, IndexError):
            continue  # skip malformed lines, don't crash whole parse
    return result


def run_walk_forward(folds: int = 3, train_days: int = 120, test_days: int = 30,
                     end_date: str = None) -> list:
    """Run walk-forward with N folds ending at end_date (or today)."""
    from datetime import date as _d
    end = _d.fromisoformat(end_date) if end_date else _d.today()

    results = []
    for i in range(folds):
        # Fold i's test ends at (end - i*test_days)
        test_end = end - timedelta(days=i * test_days)
        test_start = test_end - timedelta(days=test_days)
        train_end = test_start - timedelta(days=1)
        train_start = train_end - timedelta(days=train_days)

        log.info(f"=== Fold {i+1}/{folds} ===")
        log.info(f"Train: {train_start} -> {train_end}  Test: {test_start} -> {test_end}")

        # Tune on train
        try:
            tuned = tune_on_train(train_start.isoformat(), train_end.isoformat())
        except Exception as e:
            log.error(f"Fold {i+1} tune failed: {e} — skipping")
            continue

        # Score on test
        try:
            test_result = run_backtest_subset(
                start=test_start.isoformat(), end=test_end.isoformat(),
                min_score=tuned["min_score"], min_rs=tuned["min_rs"],
            )
        except Exception as e:
            log.error(f"Fold {i+1} test scoring failed: {e} — skipping")
            continue

        fold = FoldResult(
            fold_id=i + 1,
            train_start=train_start.isoformat(),
            train_end=train_end.isoformat(),
            test_start=test_start.isoformat(),
            test_end=test_end.isoformat(),
            tuned_min_score=tuned["min_score"],
            tuned_min_rs=tuned["min_rs"],
            n_trades=test_result["n_trades"],
            wr=test_result["wr"],
            pf=test_result["pf"],
            max_dd=test_result["max_dd"],
            sharpe=test_result["sharpe"],
        )
        results.append(fold)
        log.info(f"Fold {i+1}: N={fold.n_trades} WR={fold.wr:.1%} PF={fold.pf:.2f}")

    return results


def summarize(results: list) -> dict:
    """Aggregate per-fold stats + 95% Wilson CI."""
    total_n = sum(r.n_trades for r in results)
    total_wins = sum(int(r.wr * r.n_trades) for r in results)
    lo, hi = wilson_ci(total_wins, total_n)
    return {
        "n_folds": len(results),
        "total_trades": total_n,
        "aggregate_wr": total_wins / total_n if total_n else 0,
        "wr_95_ci": (round(lo, 4), round(hi, 4)),
        "mean_sharpe": sum(r.sharpe for r in results) / len(results) if results else 0,
        "mean_max_dd": sum(r.max_dd for r in results) / len(results) if results else 0,
        "folds": [
            {"id": r.fold_id, "wr": round(r.wr, 4), "pf": round(r.pf, 2),
             "n": r.n_trades, "sharpe": round(r.sharpe, 2),
             "test_range": f"{r.test_start} to {r.test_end}"}
            for r in results
        ],
    }


def apply_config_from_results(results_path: Path = None, dry_run: bool = False) -> dict:
    """F-2 (2026-05-04): Auto-apply weight shifts from a saved WF run to config.json.

    Reads cache/walk_forward_v2_results.json (or override path), backs up
    config/config.json, and writes the recommended `regime_weight_shifts` block.

    For now WF doesn't compute per-regime optimal weights — it preserves whatever
    `regime_weight_shifts` was active during the run + records WR/Sharpe/MaxDD.
    This function still gives the user a one-command path to replay a previous
    WF-validated config: edit the recommended JSON, then `--apply-config`.

    Args:
      results_path: path to the saved WF results JSON (default: cache/walk_forward_v2_results.json)
      dry_run: if True, print the diff without writing
    Returns:
      {ok, applied, backup_path, recommended, current}
    """
    from datetime import datetime as _dt
    rp = results_path or (BASE_DIR / "cache" / "walk_forward_v2_results.json")
    cp = BASE_DIR / "config" / "config.json"
    if not rp.exists():
        return {"ok": False, "error": f"Results file not found: {rp}"}
    if not cp.exists():
        return {"ok": False, "error": f"Config not found: {cp}"}

    summary = json.loads(rp.read_text())
    config = json.loads(cp.read_text())
    current_shifts = config.get("regime_weight_shifts", {})
    recommended = summary.get("recommended_weight_shifts") or current_shifts
    if not recommended:
        return {"ok": False, "error": "No recommended_weight_shifts in results JSON"}

    # Show diff
    print("\n=== F-2 · Apply WF-validated config ===")
    print(f"Source: {rp}")
    print(f"Target: {cp}")
    print(f"\nAggregate WR over {summary.get('total_trades', 0)} trades: {summary.get('aggregate_wr', 0):.2%}")
    print(f"Mean Sharpe: {summary.get('mean_sharpe', 0):.2f}")
    print(f"\nProposed regime_weight_shifts:")
    for regime, shifts in recommended.items():
        if isinstance(shifts, dict):
            cur = current_shifts.get(regime, {})
            print(f"  {regime}:")
            for pillar, v in shifts.items():
                cv = cur.get(pillar) if isinstance(cur, dict) else None
                marker = "→" if cv != v else "·"
                print(f"    {pillar:6s}: {cv if cv is not None else '—'!s:>4} {marker} {v}")

    if dry_run:
        print("\n--dry-run — no changes written")
        return {"ok": True, "applied": False, "recommended": recommended, "current": current_shifts}

    # Backup + write
    backup_path = cp.with_suffix(f".backup-{_dt.now().strftime('%Y%m%d-%H%M%S')}.json")
    backup_path.write_text(cp.read_text())
    config["regime_weight_shifts"] = recommended
    config.setdefault("regime_weight_shifts", {})["_applied_at"] = _dt.now().isoformat()
    config["regime_weight_shifts"]["_applied_from"] = str(rp)
    cp.write_text(json.dumps(config, indent=2))
    print(f"\n✓ Applied · backup at {backup_path.name}")
    return {"ok": True, "applied": True, "backup_path": str(backup_path),
            "recommended": recommended, "current": current_shifts}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--folds", type=int, default=4)
    parser.add_argument("--train-days", type=int, default=250)
    parser.add_argument("--test-days", type=int, default=50)
    parser.add_argument("--end-date", type=str, default=None)
    parser.add_argument("--apply-config", action="store_true",
                        help="Skip running WF — just apply weights from cache/walk_forward_v2_results.json")
    parser.add_argument("--dry-run", action="store_true",
                        help="With --apply-config: show diff without writing config.json")
    args = parser.parse_args()

    if args.apply_config:
        result = apply_config_from_results(dry_run=args.dry_run)
        if not result["ok"]:
            print(f"✗ {result['error']}")
            raise SystemExit(1)
        raise SystemExit(0)

    results = run_walk_forward(args.folds, args.train_days, args.test_days, args.end_date)
    summary = summarize(results)
    # Preserve current weight shifts so --apply-config can replay them
    try:
        _cfg_path = BASE_DIR / "config" / "config.json"
        if _cfg_path.exists():
            _cfg = json.loads(_cfg_path.read_text())
            summary["recommended_weight_shifts"] = _cfg.get("regime_weight_shifts", {})
    except Exception:
        pass

    out_path = BASE_DIR / "cache" / "walk_forward_v2_results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2)

    print("\n=== WALK-FORWARD V2 RESULTS ===")
    print(f"Folds: {summary['n_folds']}")
    print(f"Total trades: {summary['total_trades']}")
    print(f"Aggregate WR: {summary['aggregate_wr']:.2%} (95% CI: {summary['wr_95_ci'][0]:.1%} - {summary['wr_95_ci'][1]:.1%})")
    print(f"Mean Sharpe: {summary['mean_sharpe']:.2f}")
    print(f"Mean Max DD: {summary['mean_max_dd']:.2%}")
    print(f"\nDetails saved to {out_path}")
    print(f"\nTo apply these weights to live config: python3 backtest/walk_forward_v2.py --apply-config")
    print(f"To preview without writing:           python3 backtest/walk_forward_v2.py --apply-config --dry-run")
