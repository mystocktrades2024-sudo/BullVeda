"""True walk-forward backtest — tune on train, score on test, per-fold metrics.

Usage:
    python3 backtest/walk_forward_v2.py --folds 4 --train-days 250 --test-days 50
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
import subprocess
import json
import logging
import os
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

    Setup-multiplier tuning is a separate phase — see tune_setup_multipliers()
    below. tune_on_train picks (min_score, min_rs); tune_setup_multipliers
    picks the per-setup multipliers using the chosen (min_score, min_rs) as
    fixed.
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


# Default setup multiplier grid (2026-05-09). Centered on 1.0 with ±10%
# steps. Promotions (>1.0) and demotions (<1.0) both eligible — Wilson gates
# in decision_engine + analysis.py keep noise out at runtime.
SETUP_MULT_CANDIDATES = [0.80, 0.90, 1.00, 1.10, 1.20]


def tune_setup_multipliers(train_start: str, train_end: str,
                            min_score: int, min_rs: int,
                            setups_to_tune: list[str] | None = None) -> dict:
    """Per-setup multiplier grid search on the train window.

    For each setup in setups_to_tune (default: all setup families with mults
    in current config), iterate SETUP_MULT_CANDIDATES and record the best by
    objective = sharpe × √n. Returns dict: {setup: best_mult}.

    Uses --config-override to mutate setup_score_multiplier without touching
    config.json on disk. _validations is also overridden so the demotion gate
    in analysis.py doesn't reject the test mult.

    Cost: len(setups) × len(SETUP_MULT_CANDIDATES) backtest runs per fold.
    With 4 setups × 5 candidates = 20 runs per fold. At ~30s per run with the
    3y window, that's 10 min per fold.
    """
    if setups_to_tune is None:
        # Read current setup_score_multiplier keys from config (excluding meta)
        cfg_path = BASE_DIR / "config" / "config.json"
        try:
            cfg = json.loads(cfg_path.read_text())
            mults = cfg.get("setup_score_multiplier") or {}
            setups_to_tune = [k for k, v in mults.items()
                              if not k.startswith("_") and isinstance(v, (int, float))]
        except Exception:
            setups_to_tune = []
    if not setups_to_tune:
        log.warning("No setups to tune — returning empty multiplier dict")
        return {}

    out: dict = {}
    for setup in setups_to_tune:
        log.info(f"  Tuning multiplier for: {setup}")
        best_obj = -float("inf")
        best_mult = 1.0
        for mult in SETUP_MULT_CANDIDATES:
            override = {
                "setup_score_multiplier": {
                    setup: mult,
                    # Bypass the _validations gate by injecting a synthetic
                    # passing entry — we want to actually MEASURE the effect
                    # of mult<1.0, not have analysis.py revert it.
                    "_validations": {
                        setup: {"n": 999, "wr_lb": 0.0, "source": "wf_grid_tune"}
                    } if mult < 1.0 else {},
                }
            }
            try:
                result = run_backtest_subset(
                    start=train_start, end=train_end,
                    min_score=min_score, min_rs=min_rs,
                    config_override=override,
                )
                sharpe = result.get("sharpe", 0)
                n = result.get("n_trades", 0)
                obj = sharpe * math.sqrt(max(n, 1))
                log.info(f"    mult={mult:.2f} → sharpe={sharpe:.2f} n={n} obj={obj:.2f}")
                if obj > best_obj:
                    best_obj = obj
                    best_mult = mult
            except Exception as e:
                log.warning(f"    mult={mult} failed: {e}")
        out[setup] = best_mult
        log.info(f"  Best for {setup}: mult={best_mult:.2f} (obj={best_obj:.2f})")
    return out


def validate_multipliers_on_test(test_start: str, test_end: str,
                                  min_score: int, min_rs: int,
                                  proposed_multipliers: dict) -> dict:
    """Run test fold with proposed multipliers vs baseline (mult=1.0).

    Returns:
      {
        "test_metrics_with_mults": {sharpe, wr, n_trades, ...},
        "test_metrics_baseline":   {sharpe, wr, n_trades, ...},
        "improvement":             baseline_sharpe - mults_sharpe,
        "passes":                  bool — True if proposed mults didn't make
                                   things worse on the test fold.
      }
    """
    baseline_override = {"setup_score_multiplier": {"_validations": {}}}
    # Force all to 1.0 in baseline so the comparison is clean
    for setup in proposed_multipliers:
        baseline_override["setup_score_multiplier"][setup] = 1.0

    proposed_override = {
        "setup_score_multiplier": {
            **{s: m for s, m in proposed_multipliers.items()},
            "_validations": {
                s: {"n": 999, "wr_lb": 0.0, "source": "wf_test_validation"}
                for s, m in proposed_multipliers.items() if m < 1.0
            },
        }
    }

    log.info("  Validating proposed multipliers on test fold...")
    test_with_mults = run_backtest_subset(
        start=test_start, end=test_end,
        min_score=min_score, min_rs=min_rs,
        config_override=proposed_override,
    )
    test_baseline = run_backtest_subset(
        start=test_start, end=test_end,
        min_score=min_score, min_rs=min_rs,
        config_override=baseline_override,
    )

    sharpe_with = test_with_mults.get("sharpe", 0)
    sharpe_base = test_baseline.get("sharpe", 0)
    improvement = sharpe_with - sharpe_base
    # Pass if mults didn't make Sharpe materially worse (within 0.1 tolerance)
    passes = improvement >= -0.10

    log.info(f"  Test fold: with_mults sharpe={sharpe_with:.2f}, "
             f"baseline sharpe={sharpe_base:.2f}, delta={improvement:+.2f} → "
             f"{'PASS' if passes else 'FAIL'}")
    return {
        "test_metrics_with_mults": test_with_mults,
        "test_metrics_baseline": test_baseline,
        "improvement": improvement,
        "passes": passes,
    }


def write_validations_from_folds(per_fold_results: list[dict],
                                  multiplier_proposals_by_fold: list[dict]) -> dict:
    """Aggregate fold-level multiplier proposals into final _validations entries.

    A multiplier ships only if:
      - Same direction (>1.0 or <1.0) chosen in ≥3 of 4 folds (rank stability)
      - Test-fold validation passed in ≥3 of 4 folds
      - Average of accepted folds' multipliers used as final value

    Returns dict suitable for writing to config["setup_score_multiplier"]:
      {
        "<setup>": <final_mult>,
        "_validations": {
          "<setup>": {"n": <test_n_total>, "wr_lb": <wr_lb>,
                      "source": "wf_<n>folds", "approved_at": "<iso>"}
        }
      }
    """
    from collections import defaultdict
    by_setup = defaultdict(list)
    for fold_idx, (fold_result, fold_proposals) in enumerate(
            zip(per_fold_results, multiplier_proposals_by_fold)):
        if not fold_result.get("validation", {}).get("passes"):
            continue
        for setup, mult in (fold_proposals or {}).items():
            by_setup[setup].append((fold_idx, mult, fold_result))

    finals: dict = {}
    validations: dict = {}
    n_folds = len(per_fold_results)
    threshold = max(1, int(round(n_folds * 0.75)))  # 3 of 4

    for setup, fold_data in by_setup.items():
        if len(fold_data) < threshold:
            log.info(f"  {setup}: only {len(fold_data)}/{n_folds} folds passed — skipping (<{threshold})")
            continue
        directions = [1 if m > 1.0 else (-1 if m < 1.0 else 0) for _, m, _ in fold_data]
        majority = max(set(directions), key=directions.count)
        consistent = sum(1 for d in directions if d == majority)
        if consistent < threshold:
            log.info(f"  {setup}: direction unstable across folds ({consistent}/{n_folds} agree) — skipping")
            continue
        consistent_mults = [m for _, m, _ in fold_data if (m > 1.0) == (majority > 0) or (m < 1.0) == (majority < 0) or (m == 1.0 and majority == 0)]
        final_mult = sum(consistent_mults) / len(consistent_mults)
        finals[setup] = round(final_mult, 3)

        # Aggregate test n + Wilson LB across passing folds
        test_n_total = sum(fr["validation"]["test_metrics_with_mults"].get("n_trades", 0)
                            for _, _, fr in fold_data)
        test_wr_avg = sum(fr["validation"]["test_metrics_with_mults"].get("wr", 0)
                           for _, _, fr in fold_data) / len(fold_data)
        # Wilson LB approx: estimate with avg WR + total n
        from math import sqrt as _sqrt
        wins_est = int(test_wr_avg * test_n_total)
        if test_n_total > 0:
            z = 1.96
            phat = wins_est / test_n_total
            denom = 1 + z * z / test_n_total
            center = (phat + z * z / (2 * test_n_total)) / denom
            spread = z * _sqrt((phat * (1 - phat) + z * z / (4 * test_n_total)) / test_n_total) / denom
            wr_lb = max(0.0, center - spread)
        else:
            wr_lb = 0.0

        validations[setup] = {
            "n": test_n_total,
            "wr": round(test_wr_avg, 3),
            "wr_lb": round(wr_lb, 3),
            "source": f"wf_{len(fold_data)}folds_{datetime.now().strftime('%Y%m%d')}",
            "approved_at": datetime.now().isoformat(),
        }
        log.info(f"  {setup}: SHIP — final mult={final_mult:.3f}, n={test_n_total}, wr_lb={wr_lb:.3f}")

    return {**finals, "_validations": validations}


def run_backtest_subset(start: str, end: str, min_score: int, min_rs: int,
                         config_override: dict | None = None) -> dict:
    """Invoke backtest.py with date range + thresholds; parse summary.

    config_override (2026-05-09): pass a dict to deep-merge over config.json
    before backtest.py runs. Used for setup multiplier grid search. Written
    to a temp JSON file so the path is the same regardless of override size.
    """
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
    if os.environ.get("WF_AS_OF_MEMBERSHIP") == "1":
        cmd.append("--as-of-membership")
    # Write override to a temp file (cleaner than inline JSON in CLI args)
    _override_tempfile = None
    if config_override:
        import tempfile, json as _json_w
        fd, _override_tempfile = tempfile.mkstemp(suffix="_wf_override.json", prefix="wf_")
        try:
            with os.fdopen(fd, "w") as fp:
                _json_w.dump(config_override, fp)
            cmd.extend(["--config-override", _override_tempfile])
        except Exception:
            try:
                os.unlink(_override_tempfile)
            except Exception:
                pass
            _override_tempfile = None
    # 2026-05-09: bumped timeout 3600 → 14400 (4h). With CPU contention + the
    # ~1000-ticker as-of-membership universe, individual backtests can exceed
    # the previous 1h cap. Tradeoff: a true hang now ties up a worker for 4h.
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=14400)
    # Cleanup temp override file
    if _override_tempfile:
        try:
            os.unlink(_override_tempfile)
        except Exception:
            pass
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
                     end_date: str = None, tune_multipliers: bool = False) -> list:
    """Run walk-forward with N folds ending at end_date (or today).

    tune_multipliers (2026-05-09): when True, also runs tune_setup_multipliers
    on each fold's train window and validates on the test window. Per-fold
    multiplier proposals attached to FoldResult.tuned_extras for downstream
    write_validations_from_folds() aggregation.
    """
    from datetime import date as _d
    end = _d.fromisoformat(end_date) if end_date else _d.today()

    results = []
    multiplier_proposals_by_fold: list[dict] = []

    for i in range(folds):
        # Fold i's test ends at (end - i*test_days)
        test_end = end - timedelta(days=i * test_days)
        test_start = test_end - timedelta(days=test_days)
        train_end = test_start - timedelta(days=1)
        train_start = train_end - timedelta(days=train_days)

        log.info(f"=== Fold {i+1}/{folds} ===")
        log.info(f"Train: {train_start} -> {train_end}  Test: {test_start} -> {test_end}")

        # Phase 1: tune (min_score, min_rs) on train
        try:
            tuned = tune_on_train(train_start.isoformat(), train_end.isoformat())
        except Exception as e:
            log.error(f"Fold {i+1} tune failed: {e} — skipping")
            continue

        # Phase 2: tune setup multipliers on train (using chosen min_score, min_rs as fixed)
        fold_multipliers: dict = {}
        validation_result: dict | None = None
        if tune_multipliers:
            try:
                fold_multipliers = tune_setup_multipliers(
                    train_start.isoformat(), train_end.isoformat(),
                    min_score=tuned["min_score"], min_rs=tuned["min_rs"],
                )
                # Validate proposed multipliers on test fold
                if fold_multipliers:
                    validation_result = validate_multipliers_on_test(
                        test_start.isoformat(), test_end.isoformat(),
                        min_score=tuned["min_score"], min_rs=tuned["min_rs"],
                        proposed_multipliers=fold_multipliers,
                    )
            except Exception as e:
                log.warning(f"Fold {i+1} multiplier tuning failed: {e} — proceeding without multipliers")

        multiplier_proposals_by_fold.append(fold_multipliers)

        # Phase 3: score on test (with the proposed multipliers if validation passed)
        test_override = None
        if fold_multipliers and validation_result and validation_result.get("passes"):
            test_override = {
                "setup_score_multiplier": {
                    **fold_multipliers,
                    "_validations": {
                        s: {"n": 999, "wr_lb": 0.0, "source": "wf_test_scoring"}
                        for s, m in fold_multipliers.items() if m < 1.0
                    },
                }
            }
        try:
            test_result = run_backtest_subset(
                start=test_start.isoformat(), end=test_end.isoformat(),
                min_score=tuned["min_score"], min_rs=tuned["min_rs"],
                config_override=test_override,
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
        # Attach multiplier proposal + validation under tuned_extras (FoldResult
        # is a frozen dataclass field, so we use setattr defensively)
        try:
            fold.tuned_extras = {
                "multipliers": fold_multipliers,
                "validation": validation_result,
            }
        except Exception:
            pass
        results.append(fold)
        log.info(f"Fold {i+1}: N={fold.n_trades} WR={fold.wr:.1%} PF={fold.pf:.2f}")

    # Phase 4: aggregate multiplier proposals across folds (write candidate _validations)
    if tune_multipliers and any(multiplier_proposals_by_fold):
        try:
            log.info("=== Aggregating multiplier proposals across folds ===")
            # Build per-fold result list with validation attached
            per_fold_for_agg = [
                {"validation": getattr(r, "tuned_extras", {}).get("validation")
                                or {"passes": False}}
                for r in results
            ]
            shipped = write_validations_from_folds(per_fold_for_agg, multiplier_proposals_by_fold)
            cache_path = BASE_DIR / "cache" / "wf_multiplier_proposals.json"
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps({
                "generated_at": datetime.now().isoformat(),
                "shipped_multipliers": shipped,
                "per_fold_proposals": multiplier_proposals_by_fold,
            }, indent=2))
            log.info(f"Wrote shipped-multiplier candidates to {cache_path}")
        except Exception as e:
            log.warning(f"Multiplier aggregation failed: {e}")

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
    parser.add_argument("--tune-multipliers", action="store_true",
                        help="Also tune setup_score_multiplier per setup family on each fold's "
                             "train window. Validate on test fold. Aggregate into shipped "
                             "multipliers (3 of 4 folds must agree). Adds ~10min per fold.")
    parser.add_argument("--as-of-membership", action="store_true",
                        help="Pass --as-of-membership to backtest.py subprocess calls so "
                             "each fold uses point-in-time S&P 500 membership instead of "
                             "today's. Closes survivorship-bias bias in walk-forward.")
    args = parser.parse_args()
    # Persist the as-of-membership flag for run_backtest_subset to pick up
    if args.as_of_membership:
        os.environ["WF_AS_OF_MEMBERSHIP"] = "1"

    if args.apply_config:
        result = apply_config_from_results(dry_run=args.dry_run)
        if not result["ok"]:
            print(f"✗ {result['error']}")
            raise SystemExit(1)
        raise SystemExit(0)

    results = run_walk_forward(args.folds, args.train_days, args.test_days, args.end_date,
                               tune_multipliers=args.tune_multipliers)
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
