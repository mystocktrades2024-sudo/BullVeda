#!/usr/bin/env python3
"""P1 spike: Hidden Markov Model regime classifier vs current Gaussian classifier.

Fits hmmlearn.GaussianHMM(n_components=3) on SPY 10y returns + 21d realized vol.
Compares regime labels (timestamps) vs current Gaussian soft classifier.

Validation gate (per Research Lab P1):
  - HMM regime-flip prediction accuracy must exceed Gaussian baseline by >5pp
    on 30+ historical regime flips
  - Bootstrap CI on improvement must clear 0

Output: cache/hmm_spike_<date>.json + console comparison
"""
from __future__ import annotations
import json
import sys
from datetime import date
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import importlib.util
_spec = importlib.util.spec_from_file_location("backtest_mod", ROOT / "backtest.py")
_bt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bt)
_regime_as_of = _bt._regime_as_of
from data_fetcher import fetch_ohlcv_with_failover

try:
    from hmmlearn.hmm import GaussianHMM
except ImportError:
    print("hmmlearn not installed — pip install hmmlearn")
    sys.exit(1)


def build_features(spy_df: pd.DataFrame) -> pd.DataFrame:
    """Per-day features for regime classification: log-return, 21d realized vol."""
    df = spy_df.copy()
    df["log_ret"] = np.log(df["Close"] / df["Close"].shift(1))
    df["rv_21d"] = df["log_ret"].rolling(21).std() * np.sqrt(252)  # annualized
    df = df.dropna()
    return df[["log_ret", "rv_21d"]]


def label_regime_by_mean(model: GaussianHMM, X: pd.DataFrame) -> dict:
    """Map HMM state ids → human labels (bull/neutral/bear) by mean log-return."""
    means = model.means_[:, 0]  # mean of log_ret per state
    sorted_ids = np.argsort(means)[::-1]  # highest mean first → bull
    labels = ["?"] * len(means)
    if len(means) == 3:
        labels[sorted_ids[0]] = "bull"
        labels[sorted_ids[1]] = "neutral"
        labels[sorted_ids[2]] = "bear"
    return labels


def main():
    print("Fetching SPY 10y daily OHLCV...")
    spy, _ = fetch_ohlcv_with_failover("SPY", days=2520)  # ~10y
    if spy is None or len(spy) < 1000:
        print("SPY data too short — abort")
        return 1
    print(f"  loaded {len(spy)} bars: {spy.index[0].date()} → {spy.index[-1].date()}")

    feats = build_features(spy)
    print(f"  features: {len(feats)} rows × {feats.shape[1]} cols")

    # Fit HMM
    print()
    print("Fitting GaussianHMM(n_components=3)...")
    X = feats.values
    model = GaussianHMM(n_components=3, covariance_type="full", n_iter=200, random_state=42)
    model.fit(X)
    labels = label_regime_by_mean(model, feats)
    print(f"  state labels: {labels}")
    print(f"  state means (log_ret, rv_21d):")
    for i, lbl in enumerate(labels):
        m = model.means_[i]
        print(f"    state {i} ({lbl}): mean_ret={m[0]:+.5f}/day  mean_rv21={m[1]:.3f}")
    print(f"  transition matrix:")
    for i, row in enumerate(model.transmat_):
        print(f"    from {labels[i]:<8}: " + "  ".join(f"{labels[j]:>8}={p:.3f}" for j, p in enumerate(row)))

    # Predict states timeline
    states = model.predict(X)
    state_labels = [labels[s] for s in states]
    hmm_df = pd.DataFrame({"date": feats.index, "hmm_state": state_labels})

    # Compute current Gaussian classifier labels (3-regime backtest baseline) for comparison
    print()
    print("Computing current Gaussian-classifier labels for comparison (sample 50 dates)...")
    sample_dates = feats.index[200:][::max(1, len(feats) // 50)]  # 50 evenly-spaced samples
    rows = []
    for d in sample_dates:
        gauss = _regime_as_of(spy, d)
        hmm_state = state_labels[list(feats.index).index(d)]
        rows.append({
            "date": d.strftime("%Y-%m-%d"),
            "hmm": hmm_state,
            "gaussian_3reg": gauss["regime"],
            "above_50ema": gauss.get("above_50ema"),
            "spy_price": gauss.get("spy_price"),
        })
    cmp = pd.DataFrame(rows)
    print(cmp.to_string(index=False, max_rows=20))
    print(f"  ... ({len(cmp)} comparison points total)")

    # Agreement matrix
    print()
    print("HMM vs Gaussian agreement (50 sample dates):")
    agree = ((cmp["hmm"] == cmp["gaussian_3reg"])).sum()
    print(f"  Direct label match: {agree}/{len(cmp)} = {agree/len(cmp)*100:.1f}%")
    # Cross-tabulation
    ct = pd.crosstab(cmp["hmm"], cmp["gaussian_3reg"])
    print(f"\n  HMM (rows) vs Gaussian (cols):")
    print(ct.to_string())

    # Save
    out = {
        "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "spy_range": [str(spy.index[0].date()), str(spy.index[-1].date())],
        "n_bars": len(spy),
        "n_features": len(feats),
        "state_labels": labels,
        "state_means_logret": [float(model.means_[i, 0]) for i in range(3)],
        "state_means_rv21": [float(model.means_[i, 1]) for i in range(3)],
        "transition_matrix": model.transmat_.tolist(),
        "sample_dates": rows,
        "agreement_pct": round(agree / len(cmp) * 100, 1),
    }
    out_path = ROOT / "cache" / f"hmm_spike_{date.today()}.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved: {out_path}")
    print()
    print("VALIDATION GATE STATUS (per Research Lab P1):")
    print(f"  Agreement with current Gaussian: {agree/len(cmp)*100:.1f}%")
    print(f"  ⚠️ Spike only — does NOT yet measure regime-flip prediction accuracy.")
    print(f"  Next step: backtest each model on regime-flip events, compute accuracy diff.")


if __name__ == "__main__":
    main()
