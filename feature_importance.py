"""Feature importance analysis for SwingTrade scoring pillars.

Runs three analyses against historical closed trades:

    1. Spearman correlation of total-score vs forward-return (legacy).
    2. OLS multi-pillar regression: pct_chg = sum(beta_i * pillar_i) + eps.
       Emits per-pillar coefficients, R-squared, and a suggested weight vector.
       (Audit ranking flaw #16.)
    3. Pairwise Spearman correlation matrix between pillar scores.
       Flags any pair with |rho| >= 0.7 as redundant. (Audit ranking flaw #17.)

Also produces a score distribution histogram (Flaw #18).

Usage:
    python3 feature_importance.py
    python3 feature_importance.py --hold-days 10
    python3 feature_importance.py --output cache/feature_importance.json

Addresses:
    Flaw #16 -- Per-pillar feature importance via OLS regression
    Flaw #17 -- Pillar-pair redundancy via Spearman correlation matrix
    Flaw #18 -- Score distribution histogram

Note: pillar breakdown was added to the trade record schema alongside this
analysis. Existing trades closed before the schema change won't have the
per-pillar fields; the regression/correlation routines only consume trades
where every required field is non-null and return a clear error message
otherwise.
"""
import json
import logging
import argparse
import statistics
from pathlib import Path

log = logging.getLogger("feature_importance")
BASE_DIR = Path(__file__).parent

PILLAR_KEYS = ["tech_score", "cat_score", "rs_score", "sm_score", "qg_score"]
PILLAR_SHORT = ["tech", "cat", "rs", "sm", "qg"]


def load_historical_trades():
    """Load closed trades from picks_history.json (scoring + outcome data)."""
    path = BASE_DIR / "cache" / "picks_history.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    trades = data.get("trades", [])
    return trades


def compute_simple_correlation(trades: list, hold_days: int = 5) -> dict:
    """Compute Spearman correlation of score vs pct_chg per trade.
    Since we don't have pillar breakdown in saved trades, use total score as proxy.
    """
    if not trades:
        return {"error": "No closed trades available"}

    valid = [t for t in trades if t.get("pct_chg") is not None and t.get("score") is not None]
    if len(valid) < 20:
        return {
            "error": f"Too few trades ({len(valid)}) -- need >=20 for meaningful correlation",
            "n_trades": len(valid),
        }

    scores = [float(t["score"]) for t in valid]
    returns = [float(t["pct_chg"]) for t in valid]

    # Spearman rank correlation
    def rank(arr):
        paired = sorted(enumerate(arr), key=lambda x: x[1])
        ranks = [0] * len(arr)
        for rnk, (orig_idx, _) in enumerate(paired):
            ranks[orig_idx] = rnk
        return ranks

    score_ranks = rank(scores)
    return_ranks = rank(returns)

    n = len(valid)
    mean_sr = statistics.mean(score_ranks)
    mean_rr = statistics.mean(return_ranks)
    cov = sum((score_ranks[i] - mean_sr) * (return_ranks[i] - mean_rr) for i in range(n))
    var_s = sum((r - mean_sr) ** 2 for r in score_ranks)
    var_r = sum((r - mean_rr) ** 2 for r in return_ranks)
    rho = cov / ((var_s * var_r) ** 0.5) if (var_s * var_r) > 0 else 0

    r_squared = rho ** 2

    # Split by score buckets -- WR per bucket
    buckets = {"<50": [], "50-60": [], "60-70": [], "70-80": [], "80+": []}
    for s, r in zip(scores, returns):
        if s < 50:
            buckets["<50"].append(r)
        elif s < 60:
            buckets["50-60"].append(r)
        elif s < 70:
            buckets["60-70"].append(r)
        elif s < 80:
            buckets["70-80"].append(r)
        else:
            buckets["80+"].append(r)

    bucket_stats = {}
    for label, bucket in buckets.items():
        if bucket:
            wr = sum(1 for r in bucket if r > 0) / len(bucket)
            avg = statistics.mean(bucket)
            bucket_stats[label] = {
                "n": len(bucket),
                "wr": round(wr, 3),
                "avg_return": round(avg, 3),
            }
        else:
            bucket_stats[label] = {"n": 0, "wr": None, "avg_return": None}

    return {
        "n_trades": len(valid),
        "spearman_rho": round(rho, 3),
        "r_squared": round(r_squared, 3),
        "interpretation": (
            "STRONG predictive" if r_squared > 0.2
            else "MODERATE predictive" if r_squared > 0.1
            else "WEAK predictive" if r_squared > 0.05
            else "NO predictive power -- score is noise"
        ),
        "by_score_bucket": bucket_stats,
        "hold_days": hold_days,
    }


def multi_pillar_regression(trades: list) -> dict:
    """OLS regression: pct_chg = beta_tech*tech_score + beta_cat*cat_score + ... + eps

    Returns coefficients (pillar importance) + R-squared.
    Requires trades to have per-pillar breakdown (added post-audit-16 fix).
    """
    valid = [
        t for t in trades
        if all(t.get(k) is not None for k in PILLAR_KEYS + ["pct_chg"])
    ]

    if len(valid) < 10:
        return {"error": f"Need 10+ trades with breakdown; have {len(valid)}"}

    try:
        import numpy as np
    except ImportError:
        return {"error": "numpy required for regression"}

    X = np.array([[float(t[k]) for k in PILLAR_KEYS] for t in valid])
    y = np.array([float(t["pct_chg"]) for t in valid])

    # Add intercept column
    X_with_intercept = np.column_stack([np.ones(len(X)), X])

    try:
        coefs, _residuals, _rank, _sv = np.linalg.lstsq(X_with_intercept, y, rcond=None)
        intercept = float(coefs[0])
        betas = {name: float(coefs[i + 1]) for i, name in enumerate(PILLAR_SHORT)}

        # R-squared (overall model fit)
        y_pred = X_with_intercept @ coefs
        ss_res = float(np.sum((y - y_pred) ** 2))
        ss_tot = float(np.sum((y - y.mean()) ** 2))
        r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0

        # Normalized importance (|beta| * std(X_col))
        stds = X.std(axis=0)
        importance = {
            name: abs(betas[name]) * float(stds[i])
            for i, name in enumerate(PILLAR_SHORT)
        }
        total_imp = sum(importance.values())
        importance_pct = {
            k: round(v / total_imp * 100, 1) if total_imp > 0 else 0.0
            for k, v in importance.items()
        }

        top_pillar = (
            max(importance_pct, key=importance_pct.get)
            if total_imp > 0 else "n/a"
        )

        return {
            "n_trades": len(valid),
            "intercept": round(intercept, 3),
            "coefficients": {k: round(v, 4) for k, v in betas.items()},
            "r_squared": round(r_squared, 3),
            "importance_pct": importance_pct,
            "interpretation": (
                f"R-squared={r_squared:.3f} -- pillar weights should shift toward {top_pillar}"
            ),
            "suggested_weights": {k: round(v, 1) for k, v in importance_pct.items()},
        }
    except Exception as e:
        return {"error": f"Regression failed: {e}"}


def pillar_correlation_matrix(trades: list) -> dict:
    """Pairwise Spearman correlation between pillar scores.
    Values > 0.7 indicate redundant pillars."""
    valid = [
        t for t in trades
        if all(t.get(k) is not None for k in PILLAR_KEYS)
    ]
    if len(valid) < 10:
        return {"error": f"Need 10+ trades; have {len(valid)}"}

    def spearman(a, b):
        # Rank arrays (ties broken by index — acceptable for low-tie pillar scores)
        def rank_arr(arr):
            order = sorted(range(len(arr)), key=lambda i: arr[i])
            ranks = [0] * len(arr)
            for r, idx in enumerate(order):
                ranks[idx] = r
            return ranks

        ra = rank_arr(a)
        rb = rank_arr(b)
        n = len(a)
        mean_a = sum(ra) / n
        mean_b = sum(rb) / n
        cov = sum((ra[i] - mean_a) * (rb[i] - mean_b) for i in range(n))
        var_a = sum((r - mean_a) ** 2 for r in ra)
        var_b = sum((r - mean_b) ** 2 for r in rb)
        return cov / ((var_a * var_b) ** 0.5) if (var_a * var_b) > 0 else 0.0

    matrix = {}
    redundant_pairs = []
    for i, p1 in enumerate(PILLAR_KEYS):
        matrix[p1] = {}
        for j, p2 in enumerate(PILLAR_KEYS):
            vals1 = [float(t[p1]) for t in valid]
            vals2 = [float(t[p2]) for t in valid]
            rho = spearman(vals1, vals2)
            matrix[p1][p2] = round(rho, 3)
            if i < j and abs(rho) >= 0.7:
                redundant_pairs.append({"pair": f"{p1} <-> {p2}", "rho": round(rho, 3)})

    return {
        "n_trades": len(valid),
        "matrix": matrix,
        "redundant_pairs": redundant_pairs,
        "interpretation": (
            f"{len(redundant_pairs)} redundant pair(s) found"
            if redundant_pairs
            else "All pillars are uncorrelated -- good"
        ),
    }


def score_distribution(trades: list) -> dict:
    """Histogram of score values across all trades (Flaw #18)."""
    if not trades:
        return {}
    scores = [float(t["score"]) for t in trades if t.get("score") is not None]
    if not scores:
        return {"total": 0, "histogram": {}}
    bins = {f"{i}-{i+5}": 0 for i in range(0, 100, 5)}
    for s in scores:
        bin_start = int(s // 5) * 5
        if bin_start >= 100:
            bin_start = 95
        bin_key = f"{bin_start}-{bin_start+5}"
        if bin_key in bins:
            bins[bin_key] += 1
    return {
        "total": len(scores),
        "mean": round(sum(scores) / len(scores), 1),
        "median": round(sorted(scores)[len(scores) // 2], 1),
        "min": round(min(scores), 1),
        "max": round(max(scores), 1),
        "histogram": bins,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hold-days", type=int, default=5)
    parser.add_argument("--output", type=str, default=None)
    args = parser.parse_args()

    trades = load_historical_trades()
    log.info(f"Loaded {len(trades)} historical trades")

    correlation = compute_simple_correlation(trades, args.hold_days)
    regression = multi_pillar_regression(trades)
    pillar_corr = pillar_correlation_matrix(trades)
    distribution = score_distribution(trades)

    result = {
        "correlation": correlation,
        "pillar_regression": regression,
        "pillar_correlation": pillar_corr,
        "distribution": distribution,
    }

    print(json.dumps(result, indent=2))

    out_path = args.output or str(BASE_DIR / "cache" / "feature_importance.json")
    Path(out_path).write_text(json.dumps(result, indent=2))
    log.info(f"Saved to {out_path}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    main()
