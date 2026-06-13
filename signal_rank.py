"""Regime-conditional ranking score (RANK-REBUILD-2026-06-13).

WHY THIS EXISTS
---------------
Forensic audit (docs/signal_screener_audit_2026_06_13) found the composite 5-pillar
`score` is ANTI-correlated with realized return (Pearson IC = -0.10, t=-4.0). Decomposed:

    pillar IC vs return     TRENDING   CHOPPY     <- the inversion is regime-conditional
    cat_score (Catalyst)     +0.242    +0.107     only pillar positive in BOTH
    qg_score  (Quality)      +0.016    +0.094
    sm_score  (Smart Money)  +0.045    +0.007     ~flat
    tech_score(Technicals)   +0.109    -0.057     momentum-beta: works trending, inverts choppy
    rs_score  (RS+Sector)    +0.032    -0.085     momentum-beta: inverts choppy
    bonus_total (Zacks/news) +0.066    -0.143     crowding fade — structurally excluded here

Walk-forward (scripts/signal_walkforward.py): ranking each scan-day's candidates by
this regime-conditional blend and taking the top tercile lifts the picked set from
PF 1.06 (current score) -> PF 1.77, and beats the score's own BOTTOM tercile (1.30).
TEST 1 also showed the predictive pillar ROTATES with regime (cat+qg was NEGATIVE in
the April trending stretch, positive May-June choppy) — hence the weights MUST be
regime-conditional, not a static cat+qg replacement.

MECHANISM (principle 2)
-----------------------
  Catalyst  = event-driven alpha (PEAD/UOA/earnings) — regime-agnostic (Bernard-Thomas)
  Quality   = defensive factor — helps in choppy/down tape
  Technicals/RS = momentum-beta — only carries when momentum carries (trending)
  Bonus     = analyst/news/Zacks crowding — fades; never enters the ranker

DESIGN
------
  * Built from PRE-bonus pillar norms (cat/qg/tech/rs/sm) -> bonus structurally excluded.
  * Regime-conditional weight sets (choppy/risk_off lean catalyst+quality; trending adds
    momentum back).
  * Rescaled to a 0-100 axis so the existing regime buy_thresholds stay meaningful.
  * The composite `score` is NOT discarded — it becomes a >=60 quality GATE
    (enforced in decision_engine), while rank_score does the RANKING/promotion.

All weights live in config so they are tunable + auditable (principle 7). This module is
pure/stateless and default-OFF: nothing changes until config flag `_enabled: true`.
"""
from __future__ import annotations

# Coarse regime family -> ('momentum carries' vs 'mean-reversion / defensive').
_TRENDING = {"risk_on_trending", "bull"}
_CHOPPY   = {"risk_on_choppy", "neutral", "unknown", ""}
_RISK_OFF = {"risk_off_trending", "risk_off", "panic"}

# Validated default weights (per pillar, applied to the 0..pillar_max norm).
# Trending: momentum allowed back in. Choppy/RiskOff: catalyst+quality led, momentum fades.
DEFAULT_WEIGHTS: dict[str, dict[str, float]] = {
    "trending": {"cat": 1.0, "qg": 1.0, "tech": 0.5, "rs": 0.3, "sm": 0.3},
    "choppy":   {"cat": 1.0, "qg": 1.0, "tech": 0.0, "rs": 0.0, "sm": 0.5},
    "risk_off": {"cat": 1.0, "qg": 1.2, "tech": 0.0, "rs": -0.3, "sm": 0.5},
}

# Default pillar maxima (used only if caller doesn't pass live maxes).
DEFAULT_MAX = {"cat": 20.0, "qg": 10.0, "tech": 30.0, "rs": 25.0, "sm": 15.0}


def _family(regime4: str | None) -> str:
    r = (regime4 or "").lower()
    if r in _TRENDING: return "trending"
    if r in _RISK_OFF: return "risk_off"
    return "choppy"


def compute_rank_score(
    pillars: dict,
    regime4: str | None,
    *,
    weights: dict | None = None,
    pillar_max: dict | None = None,
) -> dict:
    """Regime-conditional rank score on a 0-100 axis.

    pillars: dict with keys cat/qg/tech/rs/sm (accepts the *_score or *_score_norm names).
    Returns {rank_score, regime_family, blend, weights_used}.
    Bonus is intentionally NOT an input — it is structurally excluded.
    """
    fam = _family(regime4)
    w = (weights or DEFAULT_WEIGHTS).get(fam, DEFAULT_WEIGHTS["choppy"])
    pmax = pillar_max or DEFAULT_MAX

    def g(*names):
        for n in names:
            v = pillars.get(n)
            if v is not None:
                try: return float(v)
                except (TypeError, ValueError): return 0.0
        return 0.0

    vals = {
        "cat":  g("cat", "cat_score", "cat_score_norm", "catalyst"),
        "qg":   g("qg", "qg_score", "qg_score_norm", "quality", "quality_gate"),
        "tech": g("tech", "tech_score", "tech_score_norm"),
        "rs":   g("rs", "rs_score", "rs_score_norm", "rs_sector"),
        "sm":   g("sm", "sm_score", "sm_score_norm", "smart_money"),
    }

    num = sum(w.get(k, 0.0) * vals[k] for k in vals)
    # Denominator: max achievable for this weight set (positive weights only — negative
    # weights only ever subtract, so they don't raise the ceiling). Keeps 0..100 honest.
    den = sum(max(0.0, w.get(k, 0.0)) * pmax.get(k, DEFAULT_MAX[k]) for k in vals)
    rank = 0.0 if den <= 0 else max(0.0, min(100.0, 100.0 * num / den))

    return {
        "rank_score": round(rank, 1),
        "regime_family": fam,
        "blend": {k: round(vals[k], 1) for k in vals},
        "weights_used": dict(w),
    }
