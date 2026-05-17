"""Pre-bake setup-level statistics for the Technicals sub-tab's §6 + §8 sections.

For each setup_family in cache/picks_history.json, computes:
  · raw win rate (point estimate)
  · Wilson 95% lower bound (what to ACT on)
  · sample size n
  · profit factor (raw + survivorship-haircut)
  · median R-multiple
  · edge-decay slice: trailing 90d / 6mo / 12mo
  · KS drift stat (latest 30d vs full sample)

Also computes per-(setup_family × regime4) Wilson CI so §8 can show
"this setup in THIS regime" vs the cross-regime average.

Output: cache/setup_stats.json + infra/prototype/setup_stats.json
Refresh cadence: run_daily_scan.sh appends this to the morning block
(post-train, pre-inference) so the Technicals tab never reads stale numbers.
"""
from __future__ import annotations
import json
import math
import os
from collections import defaultdict
from datetime import datetime, timezone
import statistics

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PICKS = os.path.join(ROOT, "cache", "picks_history.json")
OUT_CACHE = os.path.join(ROOT, "cache", "setup_stats.json")
OUT_PROTO = os.path.join(ROOT, "infra", "prototype", "setup_stats.json")


def _wilson_ci(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson 95% CI on a binomial proportion. Returns (lb, ub)."""
    if n == 0:
        return (0.0, 0.0)
    p = wins / n
    den = 1 + z * z / n
    centre = p + z * z / (2 * n)
    spread = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, (centre - spread) / den), min(1.0, (centre + spread) / den))


def _profit_factor(trades: list[dict]) -> float:
    gain = sum(max(0.0, t.get("realized_r") or 0) for t in trades)
    loss = -sum(min(0.0, t.get("realized_r") or 0) for t in trades)
    return gain / loss if loss > 0 else (gain if gain > 0 else 0.0)


def _ks_stat(sample_a: list[float], sample_b: list[float]) -> float:
    """Two-sample Kolmogorov-Smirnov stat — empirical-CDF max absolute difference."""
    if not sample_a or not sample_b:
        return 0.0
    combined = sorted(set(sample_a + sample_b))
    cdf_a = lambda x: sum(1 for v in sample_a if v <= x) / len(sample_a)
    cdf_b = lambda x: sum(1 for v in sample_b if v <= x) / len(sample_b)
    return max(abs(cdf_a(x) - cdf_b(x)) for x in combined)


def _parse_date(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        try:
            return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            return None


def _compute_one(trades: list[dict]) -> dict:
    """Wilson CI + PF + median R for ONE slice of trades."""
    n = len(trades)
    if n == 0:
        return {"n": 0, "wr": None, "wilson_lb": None, "wilson_ub": None,
                "pf": None, "pf_haircut": None, "median_r": None}
    wins = sum(1 for t in trades if (t.get("realized_r") or 0) >= 0 or t.get("win") is True)
    lb, ub = _wilson_ci(wins, n)
    pf = _profit_factor(trades)
    pf_haircut = max(0.0, pf - 0.20)  # institutional haircut per CLAUDE.md
    rs = sorted([t.get("realized_r") for t in trades if t.get("realized_r") is not None])
    return {
        "n": n,
        "wr": wins / n if n else None,
        "wilson_lb": lb,
        "wilson_ub": ub,
        "pf": pf,
        "pf_haircut": pf_haircut,
        "median_r": statistics.median(rs) if rs else None,
    }


def _slice_by_days(trades: list[dict], days: int, now: datetime) -> list[dict]:
    cutoff = now.timestamp() - days * 86400
    out = []
    for t in trades:
        ed = _parse_date(t.get("exit_date") or t.get("entry_date"))
        if ed and ed.timestamp() >= cutoff:
            out.append(t)
    return out


def main():
    payload = json.load(open(PICKS))
    trades = payload.get("trades", [])
    print(f"[setup-stats] loaded {len(trades)} trades from picks_history")

    now = datetime.now(timezone.utc)

    # Group by setup_family
    by_setup: dict[str, list[dict]] = defaultdict(list)
    for t in trades:
        sf = (t.get("setup_family") or "").strip() or "unknown"
        if sf == "" or sf == "unknown":
            continue  # skip unclassified
        by_setup[sf].append(t)

    setup_stats: dict[str, dict] = {}
    full_r_sample = [t.get("realized_r") for t in trades if t.get("realized_r") is not None]

    for setup, st in by_setup.items():
        base = _compute_one(st)

        # Edge-decay slices
        slice_90  = _slice_by_days(st,  90, now)
        slice_180 = _slice_by_days(st, 180, now)
        slice_365 = _slice_by_days(st, 365, now)
        decay = {
            "trailing_90d":  _compute_one(slice_90),
            "trailing_6mo":  _compute_one(slice_180),
            "trailing_12mo": _compute_one(slice_365),
        }

        # KS drift — latest 30d vs full sample
        latest_30 = _slice_by_days(st, 30, now)
        latest_r = [t.get("realized_r") for t in latest_30 if t.get("realized_r") is not None]
        full_r_setup = [t.get("realized_r") for t in st if t.get("realized_r") is not None]
        ks = _ks_stat(latest_r, full_r_setup) if len(latest_r) >= 5 else 0.0

        # Per-regime breakdown
        by_regime: dict[str, list[dict]] = defaultdict(list)
        for t in st:
            r = (t.get("regime4") or t.get("regime") or "unknown").strip() or "unknown"
            by_regime[r].append(t)
        per_regime = {r: _compute_one(rt) for r, rt in by_regime.items()}

        setup_stats[setup] = {
            **base,
            "decay": decay,
            "ks_drift_30d": ks,
            "per_regime": per_regime,
        }

    # Sanity: print top setups by sample size
    ranked = sorted(setup_stats.items(), key=lambda kv: -kv[1]["n"])
    print(f"[setup-stats] {len(setup_stats)} setup families · top by n:")
    for sf, s in ranked[:5]:
        wlb = s["wilson_lb"] or 0
        print(f"  {sf:25s}  n={s['n']:3d}  WR={(s['wr'] or 0)*100:.0f}%  Wilson LB={wlb*100:.0f}%  PF={s['pf']:.2f}")

    out = {
        "_meta": {
            "generated_at": now.isoformat(),
            "source": "cache/picks_history.json",
            "n_trades_total": len(trades),
            "n_setup_families": len(setup_stats),
            "wilson_z": 1.96,
            "haircut_pf": 0.20,
            "haircut_wr_survivorship": 0.03,
        },
        "setups": setup_stats,
    }

    os.makedirs(os.path.dirname(OUT_CACHE), exist_ok=True)
    with open(OUT_CACHE, "w") as f:
        json.dump(out, f, indent=2, default=str)
    with open(OUT_PROTO, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"[setup-stats] wrote {OUT_CACHE}")
    print(f"[setup-stats] wrote {OUT_PROTO}")


if __name__ == "__main__":
    main()
