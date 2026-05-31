#!/usr/bin/env python3
"""ml_accuracy_report.py — one-command ML model accuracy check.

Combines the three accuracy lenses into one readable report:
  1. HOLDOUT      — walk-forward holdout metrics from the last train
                    (cache/ml/calibration_report.json): direction acc, hit-net AUC,
                    Brier, magnitude pinball, calibration reliability table.
  2. CHAMPION     — what's actually live + when promoted (cache/ml/champion_metrics.json).
  3. REALIZED     — out-of-sample on LIVE trades via the close-loop labeler
                    (cache/ml/close_loop_report.json): predicted vs actual hit-rate.
                    This is the truest accuracy — real outcomes, no train data.

Read-only. No network, no EODHD. Run anytime:  python3 scripts/ml_accuracy_report.py
"""
from __future__ import annotations
import json
import os
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
ML = BASE / "cache" / "ml"


def _load(name):
    p = ML / name
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception as e:
        return {"_error": str(e)}


def _num(x, nd=4):
    try:
        return round(float(x), nd)
    except (TypeError, ValueError):
        return "—"


def _grade_auc(a):
    try:
        a = float(a)
    except (TypeError, ValueError):
        return ""
    return "excellent" if a >= 0.75 else "good" if a >= 0.65 else "weak" if a >= 0.55 else "≈coin-flip"


def _grade_dir(a):
    try:
        a = float(a)
    except (TypeError, ValueError):
        return ""
    # 3-class baseline = 0.333
    return "strong" if a >= 0.50 else "ok" if a >= 0.42 else "≈random(0.33)"


def main():
    print("=" * 64)
    print("  ML MODEL ACCURACY REPORT")
    print("=" * 64)

    # ── 1. HOLDOUT (walk-forward) ─────────────────────────────────
    cr = _load("calibration_report.json")
    print("\n[1] HOLDOUT — walk-forward (last train)")
    if not cr or cr.get("_error"):
        print("    no calibration_report.json", cr.get("_error") if cr else "")
    else:
        print(f"    trained : {cr.get('trained_at')}")
        print(f"    samples : {cr.get('n_total')}  range {cr.get('date_range')}  feats {cr.get('feature_count')}")
        print(f"    split   : {cr.get('split')}  health {cr.get('calibration_health')}  preliminary {cr.get('preliminary')}")
        # direction can be a float or {accuracy:...}
        dv = cr.get("direction")
        dacc = dv if isinstance(dv, (int, float)) else (dv or {}).get("accuracy")
        print(f"    direction acc : {_num(dacc)}   [{_grade_dir(dacc)}]   (3-class, random=0.333)")
        hn = cr.get("hit_net") or {}
        auc = hn.get("p_t1_first_auc") or hn.get("auc")
        print(f"    hit-net AUC   : {_num(auc)}   [{_grade_auc(auc)}]   (T1-before-stop; the actionable head)")
        print(f"    hit-net Brier : {_num(hn.get('brier'))}   (lower=better; 0.25=useless)")
        mg = cr.get("magnitude") or {}
        print(f"    magnitude q50 pinball : {_num(mg.get('q50_pinball'))}  (lower=better)")
        tf = cr.get("top_features")
        if tf:
            print(f"    top features  : {', '.join(str(x) for x in tf[:8])}")
        cal = (cr.get("hit_net") or {}).get("calibration") or cr.get("calibration")
        if isinstance(cal, list) and cal:
            print("    reliability (pred → realized, n):")
            for b in cal[:10]:
                if isinstance(b, dict):
                    print(f"      {b.get('lo','?')}-{b.get('hi','?')}: pred {_num(b.get('pred'),3)} → real {_num(b.get('realized'),3)} (n={b.get('n')})")

    # ── 2. CHAMPION (what's live) ─────────────────────────────────
    cm = _load("champion_metrics.json")
    print("\n[2] CHAMPION — live model (promoted)")
    if not cm or cm.get("_error"):
        print("    no champion_metrics.json")
    else:
        print(f"    updated : {cm.get('updated_at')}")
        for mode, v in (cm.get("modes") or {}).items():
            if isinstance(v, dict):
                print(f"    {mode:9s}: dir_acc {_num(v.get('direction_accuracy'),3)} [{_grade_dir(v.get('direction_accuracy'))}] · "
                      f"hit_auc {_num(v.get('hit_net_auc'),3)} [{_grade_auc(v.get('hit_net_auc'))}] · "
                      f"brier {_num(v.get('brier'),3)} · n {v.get('n_total')} · promoted {str(v.get('promoted_at'))[:10]}")

    # ── 3. REALIZED (out-of-sample on live trades) ────────────────
    cl = _load("close_loop_report.json")
    print("\n[3] REALIZED — live trade outcomes (close-loop, truest accuracy)")
    if not cl or cl.get("_error"):
        print("    no close_loop_report.json yet — accumulates as ml-close-loop (daily 19:00) labels")
        print("    realized outcomes. The truest test; needs live picks to mature (n>=30 for signal).")
    else:
        n = cl.get("n") or cl.get("n_labeled") or cl.get("n_total")
        print(f"    labeled trades : {n}")
        for k in ("predicted_hit_rate", "realized_hit_rate", "direction_hit_rate", "edge", "auc"):
            if k in cl:
                print(f"    {k}: {_num(cl[k])}")
        if n and isinstance(n, (int, float)) and n < 30:
            print(f"    ⚠ n={n} < 30 — too few for a reliable read (Wilson LB wide). Keep accumulating.")

    print("\n" + "=" * 64)
    print("  How to read: hit-net AUC is the money metric (actionable T1/stop).")
    print("  Direction is 3-class (hard; random=0.33). REALIZED (sec 3) is the")
    print("  honest out-of-sample test once n>=30 live trades accumulate.")
    print("=" * 64)


if __name__ == "__main__":
    main()
