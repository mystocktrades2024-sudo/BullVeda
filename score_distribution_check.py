"""Check if score thresholds are well-calibrated to current score distribution.
Compares bulk scan scores (all_scored) against regime buy/watch thresholds.
Warns if <5% of scored stocks qualify for BUY — means threshold is too high.
"""
from pathlib import Path
import json
import logging

log = logging.getLogger("score_dist")
BASE_DIR = Path(__file__).parent


def check_distribution():
    """Read latest cache/last_bundle.json, compare scores vs thresholds."""
    bundle_path = BASE_DIR / "cache" / "last_bundle.json"
    config_path = BASE_DIR / "config" / "config.json"
    if not bundle_path.exists():
        return {"error": "No last_bundle.json"}

    bundle = json.loads(bundle_path.read_text())
    config = json.loads(config_path.read_text())

    all_scored = bundle.get("all_scored", [])
    if not all_scored:
        return {"error": "No scored tickers in bundle"}

    scores = [float(r.get("score", 0)) for r in all_scored if r.get("score")]
    if not scores:
        return {"error": "No numeric scores"}

    import statistics
    n = len(scores)
    sorted_scores = sorted(scores)
    stats = {
        "n_scored": n,
        "min": round(min(scores), 1),
        "max": round(max(scores), 1),
        "mean": round(statistics.mean(scores), 1),
        "median": round(statistics.median(scores), 1),
        "p25": round(sorted_scores[n // 4], 1),
        "p75": round(sorted_scores[3 * n // 4], 1),
        "p90": round(sorted_scores[9 * n // 10], 1),
    }

    # Get regime thresholds — prefer 4-regime, fallback to legacy
    regime4 = bundle.get("regime", {}).get("regime4", "")
    regime_legacy = bundle.get("regime", {}).get("regime", "neutral")
    r4_thr = config.get("regime4_thresholds", {}).get(regime4, {})
    r3_thr = config.get("regime_thresholds", {}).get(regime_legacy, {})
    buy_min = r4_thr.get("buy_min_score") or r3_thr.get("buy_min_score", 72)
    watch_min = r4_thr.get("watch_min_score") or r3_thr.get("watch_min_score", 60)

    n_buy = sum(1 for s in scores if s >= buy_min)
    n_watch = sum(1 for s in scores if s >= watch_min)

    pct_buy = n_buy / n * 100
    pct_watch = n_watch / n * 100

    # Alert if BUY qualifiers < 2% or > 20% — threshold miscalibration
    warnings = []
    if pct_buy < 2:
        warnings.append(
            f"Only {pct_buy:.1f}% of scored tickers qualify for BUY "
            f"(threshold {buy_min}, p90={stats['p90']}). "
            f"Consider lowering threshold — likely too strict for current distribution."
        )
    elif pct_buy > 20:
        warnings.append(
            f"{pct_buy:.1f}% of scored tickers qualify for BUY — too many. "
            f"Consider raising threshold."
        )

    return {
        "regime": regime,
        "stats": stats,
        "threshold_buy": buy_min,
        "threshold_watch": watch_min,
        "n_above_buy": n_buy,
        "n_above_watch": n_watch,
        "pct_above_buy": round(pct_buy, 2),
        "pct_above_watch": round(pct_watch, 2),
        "warnings": warnings,
        "suggested_buy_threshold": stats["p90"],  # top 10% of distribution
        "suggested_watch_threshold": stats["p75"],  # top 25%
    }


def main():
    logging.basicConfig(level=logging.INFO)
    result = check_distribution()
    print(json.dumps(result, indent=2))
    if result.get("warnings"):
        for w in result["warnings"]:
            log.warning(w)


if __name__ == "__main__":
    main()
