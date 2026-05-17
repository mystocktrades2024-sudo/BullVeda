"""Load picks_history.trades + signal_log + decision_log into a feature matrix
for the 3-headed ML Edge model (direction · magnitude · hit-net).

Single source of truth for what counts as a training row and which features
land in X. Inference (`ml.predict`) re-uses `FeatureSpec` to vectorize new
candidates the same way."""
from __future__ import annotations
import json
import os
from dataclasses import dataclass, field
from typing import Iterable
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@dataclass
class FeatureSpec:
    numeric: list[str] = field(default_factory=lambda: [
        "score", "tech_score", "cat_score", "rs_score", "sm_score", "qg_score",
        "rr_ratio", "raw_total", "bonus_total", "wr_multiplier",
        "market_vix", "market_breadth", "market_spy_1m", "market_dist_days",
        "catalyst_tier",
    ])
    categorical: list[str] = field(default_factory=lambda: [
        "regime4", "setup_family", "entry_quality", "conviction_tier", "direction",
    ])
    category_values: dict[str, list[str]] = field(default_factory=lambda: {
        "regime4":   ["risk_on_trending", "risk_on_choppy", "risk_off_trending", "panic", "unknown"],
        "setup_family": ["Impulse Catalyst", "Breakout Expansion", "Trend Continuation",
                         "Special Situation", "Mean Reversion", "Defensive Rotation", "unknown"],
        "entry_quality": ["FRESH", "PULLBACK", "VALID", "EXTENDED", "MISSED", "unknown"],
        "conviction_tier": ["T1", "T2", "T3", "WATCH", "unknown"],
        "direction":  ["long", "short", "neutral", "unknown"],
    })

    @property
    def all_columns(self) -> list[str]:
        cols = list(self.numeric)
        for c in self.categorical:
            for v in self.category_values[c]:
                cols.append(f"{c}__{v}")
        return cols


def _safe_float(x, default=0.0):
    try:
        if x is None or x == "":
            return default
        return float(x)
    except (TypeError, ValueError):
        return default


def _normalize_row(row: dict, spec: FeatureSpec) -> dict:
    out = {}
    for c in spec.numeric:
        out[c] = _safe_float(row.get(c))
    for c in spec.categorical:
        raw_val = row.get(c)
        val = str(raw_val) if raw_val not in (None, "") else "unknown"
        if val not in spec.category_values[c]:
            val = "unknown"
        for v in spec.category_values[c]:
            out[f"{c}__{v}"] = 1.0 if v == val else 0.0
    return out


def vectorize(rows: Iterable[dict], spec: FeatureSpec | None = None) -> tuple[pd.DataFrame, FeatureSpec]:
    spec = spec or FeatureSpec()
    rows = list(rows)
    if not rows:
        return pd.DataFrame(columns=spec.all_columns), spec
    norm = [_normalize_row(r, spec) for r in rows]
    return pd.DataFrame(norm, columns=spec.all_columns), spec


def _label_direction(pct_chg: float, threshold: float = 2.0) -> int:
    """3-class label: 0=down>=threshold, 1=chop, 2=up>=threshold."""
    if pct_chg >= threshold:
        return 2
    if pct_chg <= -threshold:
        return 0
    return 1


def _label_hit_net(t: dict) -> int | None:
    """P(T1 before stop) proxy. Uses realized_r when present; else win flag.

    Returns None if neither signal is decisive (excluded from training)."""
    rr = t.get("realized_r")
    if rr is not None and rr != "":
        try:
            rr = float(rr)
            if rr >= 1.0:
                return 1
            if rr <= -1.0:
                return 0
            return None
        except (TypeError, ValueError):
            pass
    win = t.get("win")
    if win is True:
        return 1
    if win is False:
        return 0
    return None


def load_training_frame() -> tuple[pd.DataFrame, dict, FeatureSpec]:
    """Return (X, ys, spec) where ys has keys 'dir', 'mag', 'hit', plus 'date' index.

    Source: cache/picks_history.json -> trades (n~832, 84%+ pillar coverage).
    Signal_log labels would expand n but lack pillar features — skipped for v1."""
    path = os.path.join(ROOT, "cache", "picks_history.json")
    with open(path) as f:
        ph = json.load(f)
    raw_trades = ph.get("trades", [])

    rows, labels_dir, labels_mag, labels_hit, dates = [], [], [], [], []
    for t in raw_trades:
        pct = t.get("pct_chg")
        if pct in (None, ""):
            continue
        try:
            pct = float(pct)
        except (TypeError, ValueError):
            continue
        if t.get("score") in (None, "") or _safe_float(t.get("score")) <= 0:
            continue  # need at least the composite score as a feature

        hit = _label_hit_net(t)
        rows.append(t)
        labels_dir.append(_label_direction(pct))
        labels_mag.append(pct)
        labels_hit.append(hit if hit is not None else -1)  # -1 sentinel; filtered downstream
        dates.append(t.get("entry_date") or t.get("run_date") or "1970-01-01")

    X, spec = vectorize(rows)
    X = X.reset_index(drop=True)
    ys = {
        "dir":  pd.Series(labels_dir, name="dir"),
        "mag":  pd.Series(labels_mag, name="mag"),
        "hit":  pd.Series(labels_hit, name="hit"),
        "date": pd.Series(pd.to_datetime(dates, errors="coerce"), name="date"),
    }
    return X, ys, spec


def load_for_inference(rows: list[dict], spec: FeatureSpec | None = None) -> pd.DataFrame:
    """Vectorize the same way for live inference — uses the same FeatureSpec."""
    X, _ = vectorize(rows, spec=spec)
    return X
