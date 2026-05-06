"""
Elite Picks — multi-factor critic engine.

Produces Top-5 picks for each (mode × stage) combination:
    Swing × {BUY, WATCH, SHORT}
    Position × {BUY, WATCH, SHORT}
    Invest × {BUY, WATCH, SHORT}

The picker is INTENTIONALLY a critic — not just "highest score wins". Each
candidate is scored on a 0-100 Elite Conviction Score combining 8 weighted
factors, with hard gates that disqualify outright.

Philosophy: a high raw score that fails the multi-factor check is NOT elite.
A score-78 that aligns with regime + has clean entry + Spring detector firing
+ MC P(target) > 70% beats a score-92 that's overbought + extended entry +
weak sector + mismatched regime.

Factor weights (out of 100):
  20 · Score-band hit rate (historical WR for this score band)
  25 · Forward edge      (MC P(target first) − P(stop first))
  10 · HMM regime align  (P(bull/bear) matches direction)
   5 · Cross-asset       (risk-on for BUY, risk-off for SHORT)
  10 · Tier-1 stack      (validated detectors firing — Spring etc.)
  10 · Sector ranking    (60th+ percentile in sector)
  10 · Conviction tier   (T1=10 / T2=7 / T3=4)
  10 · Entry quality     (FRESH=10 / PULLBACK=8 / VALID=5 / EXTENDED=0)

Hard gates (immediate disqualification):
  - R:R coherence flag set (data inconsistent)
  - Earnings within 3 days
  - Stop ≥ entry (broken plan)
  - Score < 50
  - Tail-loss filter demoted (for BUY only)

Mode-specific multipliers boost the most relevant factors per horizon.
"""
from __future__ import annotations
from typing import Optional


def _safe(v, default=0.0):
    try: return float(v) if v is not None else default
    except (TypeError, ValueError): return default


def _score_band(score: float) -> str:
    if score >= 90: return "90-100"
    if score >= 80: return "80-89"
    if score >= 70: return "70-79"
    if score >= 60: return "60-69"
    return "<60"


def _hard_gate_fail(r: dict, stage: str, accuracy_summary: dict) -> Optional[str]:
    """Return reason string if hard-gate failed, None if passed."""
    score = _safe(r.get("score"))
    if score < 50:
        return f"score {score:.0f} < 50 minimum"

    tp = r.get("trade_plan") or {}
    stop = _safe(tp.get("stop") or r.get("stop"))
    e_lo = _safe(tp.get("entry_low") or r.get("entry_lo"))
    e_hi = _safe(tp.get("entry_high") or r.get("entry_hi") or e_lo)
    e_mid = (e_lo + e_hi) / 2 if e_lo and e_hi else (e_lo or e_hi or 0)

    if stage in ("BUY",) and e_mid > 0 and stop > 0 and stop >= e_mid:
        return f"stop ${stop:.2f} >= entry ${e_mid:.2f} (broken plan)"
    if stage in ("SHORT",) and e_mid > 0 and stop > 0 and stop <= e_mid:
        return f"stop ${stop:.2f} <= entry ${e_mid:.2f} (broken short plan)"

    earn_days = r.get("earn_days")
    if isinstance(earn_days, (int, float)) and earn_days >= 0 and earn_days <= 3:
        return f"earnings in {int(earn_days)}d (binary risk)"

    # R:R coherence flag (set by build_data._rr_is_inconsistent)
    if r.get("rr_inconsistent") or r.get("_rr_inconsistent"):
        return "R:R math inconsistent (T1/entry/stop disagree)"

    conv = r.get("conviction") or {}
    if stage == "BUY" and conv.get("tail_filter_demoted"):
        return "tail-loss filter demoted (score<60 OR stars<4)"

    return None


def _factor_score_band(r: dict, accuracy: dict) -> tuple[float, str]:
    """20 pts: scale band's WR from accuracy framework."""
    score = _safe(r.get("score"))
    band = _score_band(score)
    band_data = (accuracy.get("by_score_band") or {}).get(band, {})
    wr = band_data.get("win_rate")
    if wr is None:
        return 10.0, f"band {band} (no historical data)"
    pts = round(wr / 100 * 20, 1)
    return pts, f"band {band} historical WR {wr:.0f}% → {pts:.1f}/20"


def _factor_forward_edge(r: dict, stage: str) -> tuple[float, str]:
    """25 pts: MC P(target first) - P(stop first), or fallback to MC P(profit)."""
    mc = r.get("monte_carlo") or {}
    if mc.get("p_hit_target_first") is not None and mc.get("p_hit_stop_first") is not None:
        edge = float(mc["p_hit_target_first"]) - float(mc["p_hit_stop_first"])
        # +50% edge = full 25 pts; -50% = 0
        pts = max(0.0, min(25.0, (edge + 50) / 100 * 25))
        return round(pts, 1), f"MC P(T1 first) {mc['p_hit_target_first']:.0f}% − P(stop first) {mc['p_hit_stop_first']:.0f}% = +{edge:+.0f}% edge → {pts:.1f}/25"
    if mc.get("p_profit") is not None:
        # Fallback: 60% P(profit) = 12 pts (half), 80% = 18, 100% = 25
        pts = max(0.0, min(25.0, (float(mc["p_profit"]) - 50) / 50 * 25))
        return round(pts, 1), f"MC P(profit) {mc['p_profit']:.0f}% → {pts:.1f}/25"
    return 8.0, "MC unavailable — neutral default"


def _factor_hmm_regime(r: dict, hmm: dict, stage: str) -> tuple[float, str]:
    """10 pts: HMM regime probability matches stage direction."""
    if not hmm or hmm.get("error"):
        return 5.0, "HMM unavailable"
    p_bull = _safe(hmm.get("p_bull"))
    p_bear = _safe(hmm.get("p_bear"))
    if stage == "BUY":
        pts = round(p_bull * 10, 1)
        return pts, f"P(bull) {p_bull*100:.0f}% → {pts:.1f}/10"
    if stage == "SHORT":
        pts = round(p_bear * 10, 1)
        return pts, f"P(bear) {p_bear*100:.0f}% → {pts:.1f}/10"
    # WATCH: neutral regime favored
    p_neu = _safe(hmm.get("p_neutral"))
    pts = round((p_neu * 5 + max(p_bull, p_bear) * 5), 1)
    return pts, f"P(neutral) {p_neu*100:.0f}% + max-side {max(p_bull,p_bear)*100:.0f}% → {pts:.1f}/10"


def _factor_cross_asset(macro: dict, stage: str) -> tuple[float, str]:
    """5 pts: cross-asset risk-on/off matches stage."""
    if not macro:
        return 2.5, "macro unavailable"
    sig = (macro.get("risk_signal") or "neutral").lower()
    if stage == "BUY":
        if sig == "risk_on":   return 5.0, "risk-on (DXY weak + HYG firm)"
        if sig == "risk_off":  return 0.0, "risk-off — DON'T fight tape"
        return 3.0, "neutral cross-asset"
    if stage == "SHORT":
        if sig == "risk_off":  return 5.0, "risk-off (defensive bid)"
        if sig == "risk_on":   return 0.5, "risk-on — bad timing for shorts"
        return 3.0, "neutral cross-asset"
    return 3.0, f"cross-asset {sig}"


def _factor_tier1_stack(r: dict) -> tuple[float, str]:
    """10 pts: sum of validated tier-1 detector points (capped)."""
    t1 = r.get("tier1_signals") or {}
    sigs = t1.get("signals") or {}
    # Detectors with proven edge get full weight (validated in tier1_backfill.py)
    proven = ["failed_breakdown_spring"]
    pts = 0.0
    fired = []
    for det_name, det in sigs.items():
        if not isinstance(det, dict): continue
        if not det.get("detected"): continue
        det_pts = _safe(det.get("points"))
        weight = 1.0 if det_name in proven else 0.5
        pts += det_pts * weight
        fired.append(f"{det_name.replace('_', ' ')} +{det_pts*weight:.1f}")
    pts_capped = round(min(10.0, pts), 1)
    if fired:
        return pts_capped, f"{', '.join(fired)} → {pts_capped:.1f}/10"
    return 2.0, "no tier-1 signals firing"


def _factor_sector_rank(r: dict) -> tuple[float, str]:
    """10 pts: sector_pct_rank — relative strength within sector."""
    pct = r.get("sector_pct_rank")
    if pct is None:
        return 5.0, "sector rank unavailable"
    pct_f = _safe(pct)
    pts = round(min(10.0, pct_f / 100 * 10), 1)
    return pts, f"sector pct rank {pct_f:.0f}% → {pts:.1f}/10"


def _factor_conviction_tier(r: dict) -> tuple[float, str]:
    """10 pts: T1=10, T2=7, T3=4."""
    conv = r.get("conviction") or {}
    label = (conv.get("label") or r.get("conviction_label") or "").upper()
    pts_map = {"T1": 10.0, "T2": 7.0, "T3": 4.0, "WATCH": 0.0}
    pts = pts_map.get(label, 2.0)
    return pts, f"conviction {label or '?'} → {pts:.1f}/10"


def _factor_entry_quality(r: dict) -> tuple[float, str]:
    """10 pts: FRESH=10 / PULLBACK=8 / VALID=5 / EXTENDED=0."""
    eq = (r.get("entry_quality") or "").upper()
    pts_map = {"FRESH": 10.0, "PULLBACK": 8.0, "VALID": 5.0, "EXTENDED": 0.0, "MISSED": 0.0}
    pts = pts_map.get(eq, 3.0)
    return pts, f"entry {eq or '?'} → {pts:.1f}/10"


def _mode_multipliers(mode: str) -> dict:
    """Per-horizon factor weight bonuses."""
    if mode == "Swing":
        return {"forward_edge": 1.2, "entry_quality": 1.2}
    if mode == "Position":
        return {"conviction_tier": 1.2, "sector_rank": 1.2}
    if mode == "Invest":
        return {"score_band": 1.2, "conviction_tier": 1.1}
    return {}


def _stage_filter(r: dict, stage: str, raw_score: float) -> bool:
    """Stage-specific filter: must pass before composite scoring."""
    score = raw_score
    if stage == "BUY":
        return score >= 60
    if stage == "SHORT":
        # Require score ≤ 50 OR explicit short verdict
        return score <= 50 or (r.get("verdict") or "").upper() in ("SHORT", "SELL")
    if stage == "WATCH":
        # Score in 55-75 range — close to BUY but not there yet
        return 55 <= score <= 75
    return False


def score_candidate(r: dict, mode: str, stage: str,
                     accuracy: dict, hmm: dict, macro: dict) -> Optional[dict]:
    """
    Score a single candidate. Returns None if hard-gated, else a dict with:
      score: 0-100 composite Elite Conviction Score
      breakdown: per-factor pts + reason
      why_confident: top 3 factors' reasons
      watch_out: bottom 2 factors' reasons (or hard-gate-near-misses)
      verdict_line: 1-line conclusion
    """
    raw = _safe(r.get("score"))
    if not _stage_filter(r, stage, raw):
        return None

    gate_fail = _hard_gate_fail(r, stage, accuracy)
    if gate_fail is not None:
        return None

    factors = {
        "score_band":       _factor_score_band(r, accuracy),
        "forward_edge":     _factor_forward_edge(r, stage),
        "hmm_regime":       _factor_hmm_regime(r, hmm, stage),
        "cross_asset":      _factor_cross_asset(macro, stage),
        "tier1_stack":      _factor_tier1_stack(r),
        "sector_rank":      _factor_sector_rank(r),
        "conviction_tier":  _factor_conviction_tier(r),
        "entry_quality":    _factor_entry_quality(r),
    }
    mults = _mode_multipliers(mode)
    breakdown = {}
    total = 0.0
    for name, (pts, reason) in factors.items():
        m = mults.get(name, 1.0)
        adj_pts = round(pts * m, 1)
        breakdown[name] = {"pts": pts, "adj_pts": adj_pts, "weight": m, "reason": reason}
        total += adj_pts
    # Cap at 100 (a 1.2× multiplier can push above 100 in rare cases)
    total = round(min(100.0, total), 1)

    # Sort factors by adjusted points
    sorted_factors = sorted(breakdown.items(), key=lambda kv: -kv[1]["adj_pts"])
    why = [v["reason"] for _, v in sorted_factors[:3]]
    watch = [v["reason"] for _, v in sorted_factors[-2:] if v["adj_pts"] < 5]

    # Verdict line
    if total >= 80:
        verdict_line = f"ELITE — {stage} signal with {total:.0f}/100 conviction. Take with full size."
    elif total >= 65:
        verdict_line = f"HIGH-QUALITY — {stage} signal at {total:.0f}/100. Solid setup, manage size to 60-80% of normal."
    elif total >= 50:
        verdict_line = f"MARGINAL — {stage} signal at {total:.0f}/100. Watch but don't lead with this."
    else:
        verdict_line = f"WEAK — {stage} signal at {total:.0f}/100. Better opportunities exist."

    return {
        "ticker":      r.get("ticker"),
        "name":        r.get("name") or r.get("ticker"),
        "sector":      r.get("sector"),
        "score_raw":   raw,
        "elite_score": total,
        "stage":       stage,
        "mode":        mode,
        "breakdown":   breakdown,
        "why_confident": why,
        "watch_out":   watch,
        "verdict_line": verdict_line,
        "snapshot":    {
            "price":    r.get("price"),
            "entry":    [r.get("entry_lo") or (r.get("trade_plan") or {}).get("entry_low"),
                         r.get("entry_hi") or (r.get("trade_plan") or {}).get("entry_high")],
            "stop":     r.get("stop") or (r.get("trade_plan") or {}).get("stop"),
            "target1":  r.get("t1") or (r.get("trade_plan") or {}).get("target1"),
            "target2":  r.get("t2") or (r.get("trade_plan") or {}).get("target2"),
            "rr":       r.get("rr") or (r.get("trade_plan") or {}).get("rr_ratio"),
            "p_target": (r.get("monte_carlo") or {}).get("p_hit_target_first"),
            "p_stop":   (r.get("monte_carlo") or {}).get("p_hit_stop_first"),
            "p_profit": (r.get("monte_carlo") or {}).get("p_profit"),
            "fwd_sharpe":(r.get("monte_carlo") or {}).get("fwd_sharpe"),
            "var_95":   (r.get("forward_dist") or {}).get("var_95_pct"),
            "cvar":     (r.get("forward_dist") or {}).get("cvar_975_pct"),
            "rs_rank":  r.get("rs_rank"),
            "stars":    r.get("star_rating") or r.get("stars"),
            "setup":    r.get("setup_family") or r.get("setup"),
            "earn_days":r.get("earn_days"),
        },
    }


def compute_elite_picks(short_term: list, medium_term: list, long_term: list,
                          accuracy: dict, hmm: dict, macro: dict,
                          top_n: int = 5) -> dict:
    """
    For each (mode × stage), score all candidates and return top-N by elite_score.

    Args:
      short_term, medium_term, long_term: raw row lists (with rich fields)
      accuracy: from accuracy_framework (has by_score_band)
      hmm: bundle hmm_regime block
      macro: bundle macro_signals block
      top_n: how many to return per cell (default 5)

    Returns:
      {
        Swing: { BUY: [...], WATCH: [...], SHORT: [...] },
        Position: { ... },
        Invest: { ... },
        meta: { computed_at, top_n, n_candidates_evaluated }
      }
    """
    import datetime as _dt
    out = {
        "Swing":    {"BUY": [], "WATCH": [], "SHORT": []},
        "Position": {"BUY": [], "WATCH": [], "SHORT": []},
        "Invest":   {"BUY": [], "WATCH": [], "SHORT": []},
        "meta": {
            "computed_at": _dt.datetime.now().isoformat(),
            "top_n": top_n,
        },
    }
    n_eval = 0
    n_qualified = 0

    for mode_label, mode_rows in [("Swing", short_term),
                                    ("Position", medium_term),
                                    ("Invest", long_term)]:
        for stage in ("BUY", "WATCH", "SHORT"):
            scored = []
            for r in (mode_rows or []):
                n_eval += 1
                pick = score_candidate(r, mode_label, stage, accuracy, hmm, macro)
                if pick is not None:
                    scored.append(pick)
                    n_qualified += 1
            scored.sort(key=lambda p: -p["elite_score"])
            out[mode_label][stage] = scored[:top_n]

    out["meta"]["n_candidates_evaluated"] = n_eval
    out["meta"]["n_passing_hard_gates"] = n_qualified
    return out


if __name__ == "__main__":
    # Smoke test on current bundle
    import json
    from pathlib import Path

    base = Path(__file__).parent
    data = json.loads((base / "infra/prototype/data.json").read_text())
    tickers = json.loads((base / "infra/prototype/tickers.json").read_text())

    # Build per-mode rows by joining ticker payload with data lists
    def _enrich(rows):
        out = []
        for r in rows:
            tk = r.get("ticker")
            rich = tickers.get(tk, {}) if tk else {}
            merged = {**r, **rich}
            out.append(merged)
        return out

    st = _enrich(data.get("short_term", []))
    mt = _enrich(data.get("medium_term", []))
    lt = _enrich(data.get("long_term", []))

    elite = compute_elite_picks(
        short_term=st, medium_term=mt, long_term=lt,
        accuracy=data.get("accuracy", {}),
        hmm=data.get("hmm_regime", {}),
        macro=data.get("macro_signals", {}),
    )
    print(f"\nMeta: {elite['meta']}\n")
    for mode in ("Swing", "Position", "Invest"):
        for stage in ("BUY", "WATCH", "SHORT"):
            picks = elite[mode][stage]
            print(f"=== {mode} · {stage} · {len(picks)} picks ===")
            for p in picks:
                snap = p['snapshot']
                print(f"  {p['ticker']:6} {p['elite_score']:5.1f}  {p['verdict_line'][:80]}")
            print()
