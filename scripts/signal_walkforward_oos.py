#!/usr/bin/env python3
"""Genuine OUT-OF-SAMPLE walk-forward A/B: rank-verdict vs composite-verdict.

WHY THIS EXISTS
---------------
scripts/signal_walkforward.py is mislabeled — its TEST 2/3 pool ALL scan-days
together and evaluate on the same 2026-04..06 window the DEFAULT_WEIGHTS were
chosen from. That is in-sample. The 500-user enable bar
(feedback_signal_enable_bar_500users) requires OUT-OF-SAMPLE walk-forward,
n>=30 per fold, holding across regimes, with haircuts, before any live promotion.

This harness:
  * Recomputes rank_score per historical trade through the REAL production
    formula (signal_rank.compute_rank_score) using the live config weights.
  * Splits time into expanding-window folds; the rank BUY-threshold is fit ONLY
    on each fold's TRAIN slice, then frozen and evaluated on the held-out TEST
    slice (genuinely unseen).
  * Reports, per fold and per regime, the two arms:
        ARM-COMPOSITE : names the live composite verdict BUYs  (score >= buy_thr)
        ARM-RANK      : names the ranker BUYs (score>=gate_floor AND rank>=rank_thr)
    on WR / PF / n / avg%, raw and after a retail haircut.
  * Flags threshold drift across folds (overfit tell).

Read-only. No config writes, no trades.
"""
from __future__ import annotations
import json, sys, math
from collections import defaultdict, Counter

sys.path.insert(0, ".")
from signal_rank import compute_rank_score, DEFAULT_MAX, _family  # production formula

CFG = json.load(open("config/config.json"))
RCR = CFG.get("regime_conditional_ranker", {}) or {}
GATE_FLOOR = RCR.get("gate_floor", 60)
RANK_BUY_THR = RCR.get("rank_buy_threshold", 50)   # {trending,choppy,risk_off} or scalar
WEIGHTS = RCR.get("weights")  # None -> signal_rank.DEFAULT_WEIGHTS

# Composite BUY thresholds per regime (the live "score >= threshold" gate the
# ranker is being A/B'd against). Pulled from regime4_thresholds if present.
REG_THR = {}
_r4 = CFG.get("regime4_thresholds", {}) or {}
for _k, _v in (_r4.get("regimes", _r4) or {}).items():
    if isinstance(_v, dict) and "buy_min_score" in _v:
        REG_THR[_k] = _v["buy_min_score"]
DEFAULT_BUY_THR = CFG.get("buy_min_score", 72)

# Retail haircut (docs/claude_md_calibration.md): friction on each leg + PF haircut.
FRICTION_PCT = 0.15   # round-trip slippage/fees floor, subtracted from each trade's pct_chg
PF_HAIRCUT = 0.10     # retail PF haircut applied to reported PF


def num(x):
    try:
        f = float(x)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def load_trades():
    T = json.load(open("cache/picks_history.json")).get("trades", [])
    R = []
    for t in T:
        y = num(t.get("pct_chg"))
        if y is None or not t.get("run_date"):
            continue
        pillars = {
            "cat_score": num(t.get("cat_score")) or 0.0,
            "qg_score": num(t.get("qg_score")) or 0.0,
            "tech_score": num(t.get("tech_score")) or 0.0,
            "rs_score": num(t.get("rs_score")) or 0.0,
            "sm_score": num(t.get("sm_score")) or 0.0,
        }
        reg = t.get("regime4") or "risk_on_choppy"
        rk = compute_rank_score(pillars, reg, weights=WEIGHTS, pillar_max=DEFAULT_MAX)
        R.append({
            "date": t["run_date"],
            "regime": reg,
            "fam": _family(reg),
            "score": num(t.get("score")),
            "rank": rk["rank_score"],
            "ret": y,
            "ret_net": y - FRICTION_PCT,        # haircut on the outcome
            "verdict": (t.get("verdict") or t.get("decision") or "").upper(),
        })
    return [r for r in R if r["score"] is not None]


def pf(rows, key="ret"):
    g = sum(r[key] for r in rows if r[key] > 0)
    l = sum(-r[key] for r in rows if r[key] < 0)
    return (g / l) if l > 0 else (9.99 if g > 0 else 0.0)


def wr(rows, key="ret"):
    return (sum(1 for r in rows if r[key] > 0) / len(rows) * 100) if rows else 0.0


def composite_buys(rows):
    """ARM-COMPOSITE: live score>=regime buy threshold."""
    out = []
    for r in rows:
        thr = REG_THR.get(r["regime"], DEFAULT_BUY_THR)
        if r["score"] >= thr:
            out.append(r)
    return out


def rank_buys(rows, rank_thr_by_fam):
    """ARM-RANK: score>=gate_floor AND rank>=fitted per-family threshold."""
    out = []
    for r in rows:
        thr = rank_thr_by_fam.get(r["fam"], rank_thr_by_fam.get("choppy", 50))
        if r["score"] >= GATE_FLOOR and r["rank"] >= thr:
            out.append(r)
    return out


def fit_rank_threshold(train_rows):
    """Fit the rank BUY-threshold per regime-family on TRAIN only.

    Rule (mechanism-light, no PF-maximizing overfit): for each family, pick the
    LOWEST rank cutoff among a coarse grid whose train PF clears 1.20 AND keeps
    >=40% of the gate-passing volume. Falls back to the config threshold if no
    cutoff qualifies (so we never invent edge that isn't in train).
    """
    fitted = {}
    grid = [30, 34, 36, 40, 44, 48, 50, 55, 60]
    for fam in ("trending", "choppy", "risk_off"):
        pool = [r for r in train_rows if r["fam"] == fam and r["score"] >= GATE_FLOOR]
        cfg_thr = (RANK_BUY_THR.get(fam, 50) if isinstance(RANK_BUY_THR, dict) else RANK_BUY_THR)
        if len(pool) < 20:
            fitted[fam] = cfg_thr
            continue
        best = None
        for cut in grid:
            sub = [r for r in pool if r["rank"] >= cut]
            if len(sub) < max(10, 0.40 * len(pool)):
                continue
            p = pf(sub)
            if p >= 1.20:
                best = cut  # lowest qualifying cutoff keeps the most volume
                break
        fitted[fam] = best if best is not None else cfg_thr
    return fitted


def summarize(rows, label):
    if not rows:
        return f"  {label:22s}  n=  0   --"
    p_raw, p_net = pf(rows, "ret"), pf(rows, "ret_net")
    p_hc = max(0.0, p_net - PF_HAIRCUT)
    avg = sum(r["ret"] for r in rows) / len(rows)
    return (f"  {label:22s}  n={len(rows):4d}  WR={wr(rows):5.1f}%  "
            f"PF={p_raw:4.2f}  PFnet={p_net:4.2f}  PFhaircut={p_hc:4.2f}  avg={avg:+5.2f}%")


def run():
    R = load_trades()
    R.sort(key=lambda r: r["date"])
    days = sorted({r["date"] for r in R})
    print(f"OOS WALK-FORWARD A/B — rank-verdict vs composite-verdict")
    print(f"loaded {len(R)} resolved trades across {len(days)} scan-days "
          f"({days[0]} -> {days[-1]})")
    print(f"regime mix: {dict(Counter(r['fam'] for r in R))}")
    print(f"config: gate_floor={GATE_FLOOR}  rank_buy_thr={RANK_BUY_THR}  "
          f"friction={FRICTION_PCT}%  pf_haircut={PF_HAIRCUT}\n")

    # Expanding-window folds: train = everything before the test slice.
    # 3 test slices across the 2-month span (each ~2-3 weeks held out).
    n = len(days)
    cuts = [int(n * 0.45), int(n * 0.65), int(n * 0.82), n]
    folds = []
    prev = cuts[0]
    for c in cuts[1:]:
        folds.append((days[:prev], days[prev:c]))
        prev = c

    fitted_history = []
    agg_comp, agg_rank = [], []
    for i, (train_days, test_days) in enumerate(folds, 1):
        train = [r for r in R if r["date"] in set(train_days)]
        test = [r for r in R if r["date"] in set(test_days)]
        fit = fit_rank_threshold(train)
        fitted_history.append(fit)
        print(f"=== FOLD {i}: train {train_days[0]}..{train_days[-1]} "
              f"(n={len(train)})  |  TEST {test_days[0]}..{test_days[-1]} (n={len(test)}) ===")
        print(f"  fitted rank threshold (on train): {fit}")
        comp = composite_buys(test)
        rank = rank_buys(test, fit)
        agg_comp += comp
        agg_rank += rank
        print(summarize(comp, "ARM-COMPOSITE (test)"))
        print(summarize(rank, "ARM-RANK (test)"))
        # per-regime split on the test slice
        for fam in ("choppy", "trending"):
            ct = [r for r in comp if r["fam"] == fam]
            rt = [r for r in rank if r["fam"] == fam]
            if ct or rt:
                print(f"    [{fam}]")
                print("    " + summarize(ct, "composite").strip())
                print("    " + summarize(rt, "rank").strip())
        print()

    print("=== AGGREGATE across all held-out test folds ===")
    print(summarize(agg_comp, "ARM-COMPOSITE (OOS)"))
    print(summarize(agg_rank, "ARM-RANK (OOS)"))
    print()
    # threshold drift across folds (overfit tell)
    print("=== threshold stability across folds (drift = overfit tell) ===")
    for fam in ("choppy", "trending", "risk_off"):
        seq = [f.get(fam) for f in fitted_history]
        print(f"  {fam:9s}: {seq}")
    print("\nINTERPRETATION GUIDE:")
    print("  * ARM-RANK PFhaircut must clear ~1.20 OOS AND beat ARM-COMPOSITE at")
    print("    comparable n, in EACH regime that has n>=30 — else it's not validated.")
    print("  * If the fitted threshold jumps fold-to-fold, the edge is overfit.")
    print("  * Trending n is thin here — treat any trending verdict as preliminary.")


if __name__ == "__main__":
    run()
