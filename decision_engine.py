"""
decision_engine.py — Single source of truth for ticker verdicts.

Per 2026-05-06 architecture review (AVT case study): the system had 7
independent decision engines (composite-score, gate, conviction, entry_quality,
decision_state, audit_trail, multi-timeframe) writing to the same ticker JSON
with no aggregation. The dashboard's verdict was whichever engine wrote last.

This module replaces that with a single cascade. Every ticker's final verdict
is the output of compute_final_verdict(). No tab/screen recomputes verdicts.

Hard gates (any failure → verdict cannot be BUY):
  1. liquidity_price        — gate.passed (price, liquidity, drawdown)
  2. multi_timeframe        — medium_term_gate_status
  3. entry_quality          — entry_quality not in {MISSED, EXTENDED}
  4. decision_state         — decision_state not in {MISSED, NO_EDGE}
  5. tail_loss_filter       — conviction.tail_filter_demoted == False
  6. fundamental_adequacy   — fund_score/fund_max >= 0.50

Soft gates (BUY allowed; emit caveat in caveats list):
  - analyst_upside < 0
  - tier1_signals.total_points == 0
  - zacks_rank_rationale.growth == "F"
  - earn_days < 5  (earnings catalyst risk)
"""
from __future__ import annotations
from typing import Any

DEFAULT_FUND_ADEQUACY = 0.50  # fund_score/fund_max ratio required to pass gate
DEFAULT_BUY_THRESHOLD = 60    # fallback if regime/threshold lookup fails

# Gates that, when failed, mean "wait for better setup" rather than structural reject
WATCH_WORTHY_FAILURES = {"entry_quality", "decision_state", "multi_timeframe"}


def _normalize_decision_state(ds: Any) -> str | None:
    """decision_state is sometimes a string, sometimes a dict {'state': '...'}."""
    if isinstance(ds, dict):
        return ds.get("state")
    return ds


def _eval_hard_gates(t: dict) -> tuple[list[dict], list[str]]:
    """Returns (gate_evaluations, failed_gate_names)."""
    gates: list[dict] = []
    failures: list[str] = []

    # 1. Liquidity / price / drawdown gate (preserved upstream gate)
    g = t.get("gate") or {}
    passed = bool(g.get("passed"))
    gates.append({
        "name": "liquidity_price",
        "passed": passed,
        "reason": "" if passed else "; ".join(g.get("reasons") or [])[:140],
    })
    if not passed:
        failures.append("liquidity_price")

    # 2. Multi-timeframe gate (medium_term_gate_status)
    mt = t.get("medium_term_gate_status")
    passed = mt in (None, "", "passed", "PASSED")
    reason = ""
    if not passed:
        reasons = t.get("medium_term_gate_reasons") or []
        reason = "; ".join(reasons)[:140]
    gates.append({"name": "multi_timeframe", "passed": passed, "reason": reason})
    if not passed:
        failures.append("multi_timeframe")

    # 3. Entry quality (must not be MISSED or EXTENDED)
    eq = t.get("entry_quality")
    passed = eq not in ("MISSED", "EXTENDED")
    gates.append({
        "name": "entry_quality",
        "passed": passed,
        "reason": "" if passed else f"entry_quality={eq} — wait for pullback to value zone",
    })
    if not passed:
        failures.append("entry_quality")

    # 4. Decision state (state machine)
    ds = _normalize_decision_state(t.get("decision_state"))
    passed = ds not in ("MISSED", "NO_EDGE")
    gates.append({
        "name": "decision_state",
        "passed": passed,
        "reason": "" if passed else f"decision_state={ds}",
    })
    if not passed:
        failures.append("decision_state")

    # 5. Tail-loss filter (conviction.tail_filter_demoted)
    conv = t.get("conviction") or {}
    demoted = bool(conv.get("tail_filter_demoted"))
    passed = not demoted
    reason = ""
    if demoted:
        reason = (conv.get("description") or "tail-loss filter demoted")[:140]
    gates.append({"name": "tail_loss_filter", "passed": passed, "reason": reason})
    if not passed:
        failures.append("tail_loss_filter")

    # 6. Fundamental adequacy
    fs = t.get("fund_score")
    fm = t.get("fund_max")
    # Some tickers store these inside fund_total
    if (fs is None or fm is None):
        ft = t.get("fund_total") or {}
        fs = fs if fs is not None else ft.get("score")
        fm = fm if fm is not None else ft.get("max")
    if fs is not None and fm and fm > 0:
        ratio = fs / fm
        passed = ratio >= DEFAULT_FUND_ADEQUACY
        reason = "" if passed else f"fundamentals {fs}/{fm} = {ratio*100:.0f}% < {DEFAULT_FUND_ADEQUACY*100:.0f}% adequacy"
    else:
        passed = True  # no data → don't block (avoid false negatives on data outages)
        reason = "no fundamentals data — gate skipped"
    gates.append({"name": "fundamental_adequacy", "passed": passed, "reason": reason})
    if not passed:
        failures.append("fundamental_adequacy")

    return gates, failures


def _eval_soft_gates(t: dict) -> list[str]:
    """Soft gates produce caveats but don't block BUY."""
    caveats: list[str] = []

    au = t.get("analyst_upside")
    if au is not None and au < 0:
        caveats.append(f"price above analyst target ({au:+.1f}%)")

    t1 = t.get("tier1_signals") or {}
    if t1.get("total_points", 0) == 0:
        caveats.append("no tier-1 high-conviction signals")

    zr = t.get("zacks_rank_rationale") or {}
    if zr.get("growth") == "F":
        caveats.append("Zacks growth grade: F")

    ed = t.get("earn_days")
    if ed is not None and 0 < ed < 5:
        caveats.append(f"earnings in {ed} days")

    return caveats


def _resolve_buy_threshold(regime: str | None, thresholds: dict | None) -> int:
    if not thresholds:
        return DEFAULT_BUY_THRESHOLD
    key = (regime or "risk_on_choppy").lower()
    return int((thresholds.get(key) or {}).get("buy_min_score") or DEFAULT_BUY_THRESHOLD)


def compute_final_verdict(t: dict, regime: str | None = None,
                          thresholds: dict | None = None) -> dict:
    """
    Single source of truth for ticker verdict. Aggregates all decision-engine
    outputs into one verdict + reason + caveats + audit-grade gate trail.

    Args:
        t: ticker dict from the bundle (or tickers.json) — must contain raw
           signal fields (gate, entry_quality, decision_state, conviction,
           fund_score, fund_max, score, ...).
        regime: optional regime4 label (for threshold lookup)
        thresholds: optional regime4_thresholds dict from config

    Returns:
        dict with keys:
            verdict        : 'BUY' | 'WATCH' | 'WAIT' | 'AVOID'
            reason         : top-line rationale (str)
            caveats        : list of soft-gate notes (list[str])
            gates_evaluated: list of {name, passed, reason} (list[dict])
            demote_to      : 'watch_list' | None (routing hint for caller)
    """
    if not isinstance(t, dict):
        return {"verdict": "WAIT", "reason": "no ticker data", "caveats": [],
                "gates_evaluated": [], "demote_to": None}
    # Bear setup is a parallel path — keep upstream short logic
    bear = (t.get("bear_setup") or {})
    if t.get("direction") == "short" or bear.get("score", 0) >= 10:
        return {
            "verdict": "AVOID",
            "reason": "bear setup detected",
            "caveats": [],
            "gates_evaluated": [],
            "demote_to": None,
        }

    gates, failures = _eval_hard_gates(t)
    caveats = _eval_soft_gates(t)

    if failures:
        primary = next((g for g in gates if g["name"] in failures), None)
        reason = (primary or {}).get("reason") or f"hard gate failed: {failures[0]}"
        verdict = "WATCH" if any(f in WATCH_WORTHY_FAILURES for f in failures) else "WAIT"
        return {
            "verdict": verdict,
            "reason": reason,
            "caveats": caveats,
            "gates_evaluated": gates,
            "demote_to": "watch_list",
        }

    # All hard gates passed — apply ranking threshold
    score = t.get("score") or 0
    threshold = _resolve_buy_threshold(regime, thresholds)

    if score >= threshold:
        return {
            "verdict": "BUY",
            "reason": f"all gates passed; score {score} >= {threshold} ({regime or 'default'})",
            "caveats": caveats,
            "gates_evaluated": gates,
            "demote_to": None,
        }

    return {
        "verdict": "WATCH",
        "reason": f"all gates passed but score {score} < BUY threshold {threshold}",
        "caveats": caveats,
        "gates_evaluated": gates,
        "demote_to": None,
    }
