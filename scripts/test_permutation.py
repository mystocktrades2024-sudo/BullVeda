#!/usr/bin/env python3
"""test_permutation.py — is the BUY edge REAL, or a coin flip? (principle 1, 4)

A Monte-Carlo permutation / significance test on the realized forward returns of
actual BUY signals. Point estimates lie (principle 1); this asks whether the BUY
selection carries edge that a random draw from the same surfaced universe would
NOT reproduce.

METHOD
------
1. Pool = every CLOSED trade the scanner surfaced (BUY + WATCH + SHORT ...), each
   with a realized directional return `pct_chg` (already signed for direction, so
   a positive value = the trade worked regardless of long/short).
2. Observed statistic = the chosen stat (mean return / win-rate / profit-factor)
   over the BUY-labelled subset.
3. NULL: randomly re-assign the BUY label to n_buy trades drawn from the full pool
   (label shuffle), recompute the stat. Repeat N=1000+ times to build the null
   distribution. This is the test the task specifies: "randomly reassign which
   trades were BUY vs the universe".
4. p-value (one-sided, right tail) = P(null_stat >= observed_stat). Also report the
   percentile of the observed value within the null distribution.
5. SECONDARY "vs coin-flip zero" check: a sign-flip permutation on the BUY returns
   themselves (H0: mean return = 0). Randomly flip the sign of each BUY return and
   recompute the mean; two-sided p tests whether the BUY mean is distinguishable
   from a zero-mean coin flip. This is reported alongside the label-shuffle test.

Per-setup-family: the label-shuffle test is repeated WITHIN each family's pool
(BUY-labelled family trades vs the whole family pool), answering "within this
setup, do BUY-labelled trades beat the family baseline?".

Honesty: any bucket with n_buy < 30 is FLAGGED and its verdict is withheld
(principle 1 — refuse to act on n<30 evidence).

READ-ONLY. No network. No config / scoring mutation. Local cache only.

Usage:
  python3 scripts/test_permutation.py
  python3 scripts/test_permutation.py --stat mean --n-perm 5000
  python3 scripts/test_permutation.py --stat pf --label-verdict BUY --min-n 30
"""
from __future__ import annotations

import argparse
import json
import math
import random
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
HIST = BASE / "cache" / "picks_history.json"
SIGLOG = BASE / "data" / "signal_log.json"
OUT = BASE / "cache" / "test_permutation_result.json"

N30 = 30  # sample-size admissibility floor (principle 1)


# ----------------------------------------------------------------------------- stats
def stat_mean(returns: list[float]) -> float:
    return sum(returns) / len(returns) if returns else 0.0


def stat_wr(returns: list[float]) -> float:
    if not returns:
        return 0.0
    return sum(1 for r in returns if r > 0) / len(returns)


def stat_pf(returns: list[float]) -> float:
    gains = sum(r for r in returns if r > 0)
    losses = sum(-r for r in returns if r < 0)
    if losses <= 0:
        return float("inf") if gains > 0 else 0.0
    return gains / losses


STATS = {"mean": stat_mean, "wr": stat_wr, "pf": stat_pf}
STAT_LABEL = {"mean": "mean return (%)", "wr": "win rate", "pf": "profit factor"}


# ----------------------------------------------------------------------------- data
def load_trades(source: str) -> list[dict]:
    """Return list of closed trades with fields: pct_chg, verdict, setup_family."""
    rows: list[dict] = []
    if source in ("picks", "both"):
        d = json.loads(HIST.read_text())
        for t in d.get("trades", []):
            pc = t.get("pct_chg")
            if pc is None or (isinstance(pc, float) and math.isnan(pc)):
                continue
            rows.append({
                "pct_chg": float(pc),
                "verdict": (t.get("verdict") or "").strip().upper(),
                "setup_family": (t.get("setup_family") or "").strip() or "(unlabelled)",
                "regime4": (t.get("regime4") or "").strip() or "unknown",
                "_src": "picks",
            })
    if source in ("signal", "both") and SIGLOG.exists():
        try:
            sd = json.loads(SIGLOG.read_text())
            recs = sd if isinstance(sd, list) else sd.get("signals", sd.get("entries", []))
            for t in recs:
                if not isinstance(t, dict):
                    continue
                pc = t.get("pct_chg", t.get("pnl_pct", t.get("realized_pct")))
                # only CLOSED trades have a realized return
                if pc is None or (isinstance(pc, float) and math.isnan(pc)):
                    continue
                try:
                    pc = float(pc)
                except (TypeError, ValueError):
                    continue
                if math.isnan(pc):
                    continue
                rows.append({
                    "pct_chg": float(pc),
                    "verdict": (t.get("verdict") or t.get("decision") or "").strip().upper(),
                    "setup_family": (t.get("setup_family") or "").strip() or "(unlabelled)",
                    "regime4": (t.get("regime4") or "").strip() or "unknown",
                    "_src": "signal",
                })
        except Exception:
            pass
    return rows


# ----------------------------------------------------------------------------- test
def label_shuffle_test(pool: list[float], n_label: int, observed: float,
                       stat_fn, n_perm: int, rng: random.Random) -> dict:
    """Shuffle which n_label trades carry the label; build null of the stat."""
    null = []
    m = len(pool)
    for _ in range(n_perm):
        idx = rng.sample(range(m), n_label)
        sub = [pool[i] for i in idx]
        null.append(stat_fn(sub))
    null_sorted = sorted(v for v in null if v != float("inf"))
    n_null = len(null_sorted)
    # right-tail percentile / p-value
    ge = sum(1 for v in null if v >= observed)
    p_right = (ge + 1) / (n_perm + 1)
    pct = 100.0 * sum(1 for v in null if v < observed) / n_perm
    mean_null = sum(v for v in null_sorted) / n_null if n_null else 0.0
    return {
        "null_mean": round(mean_null, 4),
        "null_p05": round(null_sorted[int(0.05 * n_null)], 4) if n_null else None,
        "null_p50": round(null_sorted[int(0.50 * n_null)], 4) if n_null else None,
        "null_p95": round(null_sorted[int(0.95 * n_null)], 4) if n_null else None,
        "observed_percentile": round(pct, 1),
        "p_value": round(p_right, 4),
    }


def sign_flip_test(returns: list[float], n_perm: int, rng: random.Random) -> dict:
    """Two-sided sign-flip permutation: H0 mean return = 0 (coin flip)."""
    obs = stat_mean(returns)
    null = []
    for _ in range(n_perm):
        s = sum(r if rng.random() < 0.5 else -r for r in returns)
        null.append(s / len(returns))
    ge = sum(1 for v in null if abs(v) >= abs(obs))
    p_two = (ge + 1) / (n_perm + 1)
    return {"observed_mean": round(obs, 4), "p_value_vs_zero": round(p_two, 4)}


def verdict_for(p: float, n: int) -> str:
    if n < N30:
        return f"INSUFFICIENT (n={n} < {N30}) — verdict withheld"
    if p < 0.01:
        return "SIGNIFICANT edge (p<0.01) — very unlikely random"
    if p < 0.05:
        return "SIGNIFICANT edge (p<0.05)"
    if p < 0.10:
        return "WEAK / marginal (0.05<=p<0.10) — treat as unproven"
    return "NOT significant — indistinguishable from random"


def run(source: str, stat_key: str, label_verdict: str, n_perm: int,
        min_n: int, seed: int) -> dict:
    rng = random.Random(seed)
    stat_fn = STATS[stat_key]
    trades = load_trades(source)
    pool_ret = [t["pct_chg"] for t in trades]
    labelled = [t["pct_chg"] for t in trades if t["verdict"] == label_verdict]

    result = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "source": source, "statistic": stat_key, "label_verdict": label_verdict,
        "n_perm": n_perm, "seed": seed,
        "pool_size": len(pool_ret), "labelled_n": len(labelled),
    }

    # ---- global
    obs = stat_fn(labelled)
    ls = label_shuffle_test(pool_ret, len(labelled), obs, stat_fn, n_perm, rng)
    sf = sign_flip_test(labelled, n_perm, rng) if labelled else {}
    result["global"] = {
        "n": len(labelled),
        "observed": round(obs, 4),
        "wr": round(stat_wr(labelled), 4),
        "pf": round(stat_pf(labelled), 4),
        "mean_return": round(stat_mean(labelled), 4),
        "label_shuffle": ls,
        "sign_flip_vs_zero": sf,
        "verdict": verdict_for(ls["p_value"], len(labelled)),
    }

    # ---- per setup family
    by_fam_pool: dict[str, list[float]] = defaultdict(list)
    by_fam_lbl: dict[str, list[float]] = defaultdict(list)
    for t in trades:
        by_fam_pool[t["setup_family"]].append(t["pct_chg"])
        if t["verdict"] == label_verdict:
            by_fam_lbl[t["setup_family"]].append(t["pct_chg"])

    fams = []
    for fam, poolf in sorted(by_fam_pool.items()):
        lblf = by_fam_lbl.get(fam, [])
        n = len(lblf)
        if n == 0:
            continue
        obsf = stat_fn(lblf)
        # need a pool larger than the label set for a meaningful shuffle
        if len(poolf) > n and n >= 2:
            lsf = label_shuffle_test(poolf, n, obsf, stat_fn, n_perm, rng)
        else:
            lsf = {"p_value": None, "observed_percentile": None,
                   "note": "pool == label set (no non-label baseline to shuffle against)"}
        pval = lsf.get("p_value")
        fams.append({
            "setup_family": fam, "n": n, "pool_n": len(poolf),
            "observed": round(obsf, 4),
            "wr": round(stat_wr(lblf), 4),
            "pf": round(stat_pf(lblf), 4),
            "mean_return": round(stat_mean(lblf), 4),
            "p_value": pval,
            "observed_percentile": lsf.get("observed_percentile"),
            "admissible": n >= min_n,
            "verdict": verdict_for(pval, n) if pval is not None else
                       (f"INSUFFICIENT (n={n} < {N30})" if n < N30 else lsf.get("note", "n/a")),
        })
    fams.sort(key=lambda x: (x["p_value"] is None, x["p_value"] if x["p_value"] is not None else 9))
    result["by_setup_family"] = fams
    return result


# ----------------------------------------------------------------------------- render
def fmt(v, stat_key):
    if v is None:
        return "  -  "
    if stat_key == "mean":
        return f"{v:+.2f}%"
    if stat_key == "wr":
        return f"{v*100:.1f}%"
    return f"{v:.2f}"


def print_report(r: dict, stat_key: str):
    g = r["global"]
    W = 78
    print("=" * W)
    print(f"  PERMUTATION SIGNIFICANCE TEST  —  stat: {STAT_LABEL[stat_key]}")
    print(f"  source={r['source']}  label={r['label_verdict']}  "
          f"N_perm={r['n_perm']}  seed={r['seed']}")
    print("=" * W)
    print(f"  Surfaced pool: {r['pool_size']} closed trades   "
          f"{r['label_verdict']}-labelled: {r['labelled_n']}")
    print("-" * W)
    print("  GLOBAL")
    print(f"    observed {STAT_LABEL[stat_key]:<20} {fmt(g['observed'], stat_key)}")
    print(f"    (context: WR {g['wr']*100:.1f}%  PF {g['pf']:.2f}  "
          f"mean {g['mean_return']:+.2f}%  n={g['n']})")
    ls = g["label_shuffle"]
    print(f"    null median / p95        {fmt(ls['null_p50'], stat_key)} / "
          f"{fmt(ls['null_p95'], stat_key)}")
    print(f"    observed percentile      {ls['observed_percentile']}th of null")
    print(f"    label-shuffle p-value    {ls['p_value']}")
    if g["sign_flip_vs_zero"]:
        print(f"    sign-flip p (vs zero)    {g['sign_flip_vs_zero']['p_value_vs_zero']}"
              f"  (coin-flip test on BUY returns)")
    print(f"    >>> VERDICT: {g['verdict']}")
    print("-" * W)
    print("  BY SETUP FAMILY  (label-shuffle within each family pool)")
    print(f"    {'family':<26}{'n':>5}{'stat':>9}{'WR':>7}{'PF':>6}{'p':>8}  verdict")
    for f in r["by_setup_family"]:
        flag = "" if f["admissible"] else "  ⚠n<30"
        pv = f["p_value"]
        pvs = f"{pv:.3f}" if isinstance(pv, (int, float)) else " -  "
        short = f["verdict"].split(" —")[0].split(" (")[0]
        print(f"    {f['setup_family'][:25]:<26}{f['n']:>5}"
              f"{fmt(f['observed'], stat_key):>9}{f['wr']*100:>6.0f}%"
              f"{f['pf']:>6.2f}{pvs:>8}  {short}{flag}")
    print("=" * W)
    n30 = [f for f in r["by_setup_family"] if not f["admissible"]]
    if n30:
        print(f"  ⚠  {len(n30)} family bucket(s) below n<30 — verdict withheld "
              f"(principle 1).")
    print(f"  JSON: {OUT}")
    print("=" * W)


def main():
    ap = argparse.ArgumentParser(description="Permutation / Monte-Carlo significance test on BUY edge (read-only).")
    ap.add_argument("--source", choices=["picks", "signal", "both"], default="picks",
                    help="trade source (default picks_history.json)")
    ap.add_argument("--stat", choices=list(STATS), default="mean",
                    help="test statistic (default mean return)")
    ap.add_argument("--label-verdict", default="BUY",
                    help="which verdict is the 'signal' label (default BUY)")
    ap.add_argument("--n-perm", type=int, default=2000, help="permutations (default 2000)")
    ap.add_argument("--min-n", type=int, default=N30, help="admissibility floor (default 30)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--json-only", action="store_true")
    args = ap.parse_args()

    r = run(args.source, args.stat, args.label_verdict.upper(),
            args.n_perm, args.min_n, args.seed)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(r, indent=2))
    if not args.json_only:
        print_report(r, args.stat)


if __name__ == "__main__":
    main()
