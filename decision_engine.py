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
import math
import statistics
from pathlib import Path

DEFAULT_FUND_ADEQUACY = 0.50  # fund_score/fund_max ratio required to pass gate
DEFAULT_BUY_THRESHOLD = 60    # fallback if regime/threshold lookup fails
EARNINGS_BLOCK_DAYS = 5       # block BUY if earnings within N days (institutional standard)
EARNINGS_CAVEAT_DAYS = 10     # soft caveat for 5-10 day earnings proximity
SETUP_KILL_MIN_WR = 0.35      # setups below 35% WR over min_n closed get killed
SETUP_KILL_MIN_PNL = 0.0      # AND avg_pnl below this threshold
SETUP_KILL_MIN_N = 30         # require >=30 closed signals before any kill decision
SETUP_KILL_MIN_WR_LB = 0.30   # Wilson 95% lower-bound floor — point WR alone is noise at small N
STATIC_KILL_MIN_N = 10        # static_setup_kill_list entries must declare n >= this

# Gates that, when failed, mean "wait for better setup" rather than structural reject
WATCH_WORTHY_FAILURES = {"entry_quality", "decision_state", "multi_timeframe"}


def compute_regime_confidence_modifier(hmm: dict | None) -> float:
    """Tier 1C: scale sizing by HMM regime probability + confidence.

    Strong bull-regime confidence → full size; uncertain/bearish → discount.
    Reads from build_data.py's _compute_hmm_regime_safe() output:
      p_bull, p_neutral, p_bear, confidence (0.0-1.0).

    Returns multiplier in [0.5, 1.0]. Default 1.0 if no HMM data.
    """
    if not hmm or not isinstance(hmm, dict):
        return 1.0
    p_bull = float(hmm.get("p_bull") or 0.5)
    confidence = float(hmm.get("confidence") or 0.5)
    # Strong bull AND confident: full size
    if p_bull >= 0.85 and confidence >= 0.60:
        return 1.0
    # Solid bull: light discount
    if p_bull >= 0.70:
        return 0.90
    # Mixed: meaningful caution
    if p_bull >= 0.50:
        return 0.75
    # Bear-leaning: half size
    return 0.50


REGIME_SIZE_MODIFIER = {
    # 4-regime taxonomy
    "risk_on_trending": 1.00,
    "risk_on_choppy":   0.85,
    "risk_off_trending": 0.70,
    "risk_off_choppy":  0.70,
    "panic":            0.50,
    # 3-regime legacy fallback
    "bull":             1.00,
    "neutral":          0.85,
    "bear":             0.70,
}


def compute_setup_size_multipliers(signal_log_path: str | None = None,
                                     min_n: int = 20,
                                     regime: str | None = None) -> dict:
    """Per-setup position-size multiplier based on real signal_tracker outcomes.

    Returns dict: {setup_name: multiplier_float}. Expectancy-based scale:
        1.5  — avg_pnl >= +4% AND WR >= 60%   (high-edge setups, e.g., 10-Week Pullback)
        1.3  — avg_pnl >= +2%                  (positive expectancy proven, e.g., VCP/Trend Cont.)
        1.0  — avg_pnl >= 0  OR  n < min_n     (default)
        0.7  — avg_pnl <  0 but WR >= kill threshold (loss-prone but not killed)
        0.0  — failed performance floor        (killed)

    Expectancy (avg_pnl) drives the call — a setup with WR<50% but +3% avg_pnl
    has positive expectancy and deserves full size, not a discount.

    Forward-looking only. Open positions retain their original size.
    """
    import json as _json
    from pathlib import Path as _P
    from collections import defaultdict as _dd
    # Phase B.1: route through state_layer when caller doesn't override path
    if signal_log_path is None:
        try:
            from state_layer import load_signal_log
            sigs = load_signal_log()
        except Exception:
            sigs = []
    else:
        try:
            sigs = _json.loads(_P(signal_log_path).read_text())
        except Exception:
            return {}
    by_setup: dict = _dd(list)
    for s in sigs or []:
        if s.get("status") != "CLOSED":
            continue
        pnl = s.get("actual_pnl_pct")
        setup = s.get("strategy")
        if pnl is None or not setup:
            continue
        by_setup[setup].append(float(pnl))
    multipliers: dict = {}
    for setup, pnls in by_setup.items():
        n = len(pnls)
        if n < min_n:
            multipliers[setup] = 1.0
            continue
        wins = sum(1 for p in pnls if p > 0)
        wr = wins / n
        avg = sum(pnls) / n
        if wr < SETUP_KILL_MIN_WR and avg < SETUP_KILL_MIN_PNL:
            multipliers[setup] = 0.0
        elif avg >= 4.0 and wr >= 0.60:
            multipliers[setup] = 1.5
        elif avg >= 2.0:
            multipliers[setup] = 1.3
        elif avg >= 0.0:
            multipliers[setup] = 1.0
        else:
            multipliers[setup] = 0.7  # negative expectancy but not killed → discount
    # #8: regime-conditional sizing — discount across all setups in unfavorable regimes
    if regime:
        regime_mod = REGIME_SIZE_MODIFIER.get(regime.lower(), 1.0)
        if regime_mod != 1.0:
            multipliers = {k: round(v * regime_mod, 2) for k, v in multipliers.items()}
    return multipliers


def compute_setup_score_band_kills(signal_log_path: str | None = None,
                                     min_wr: float = 0.30,
                                     min_pnl: float = 0.0,
                                     min_n: int = 15) -> dict:
    """Stratified kill list: (setup, score_band) combos that historically lose.

    Today's whole-setup kill is too coarse — analyze_signals 2026-05-06 showed
    52wk Breakout@>=80 has WR 23.5%/avg -1.69% while 52wk Breakout@70-79 has
    WR 38.3%/avg +0.80%. Killing the whole setup throws away the working bands.

    Returns: {(setup, score_band): {wr, avg_pnl, n, reason}}.
    Lower n threshold (15 vs 30) since combos are smaller buckets.
    """
    import json as _json
    from pathlib import Path as _P
    from collections import defaultdict as _dd
    # Phase B.1: route through state_layer when caller doesn't override path
    if signal_log_path is None:
        try:
            from state_layer import load_signal_log
            sigs = load_signal_log()
        except Exception:
            sigs = []
    else:
        try:
            sigs = _json.loads(_P(signal_log_path).read_text())
        except Exception:
            return {}
    def _band(score: float) -> str:
        if score >= 80: return ">=80"
        if score >= 70: return "70-79"
        if score >= 60: return "60-69"
        if score >= 50: return "50-59"
        return "<50"
    by_combo: dict = _dd(list)
    for s in sigs or []:
        if s.get("status") != "CLOSED":
            continue
        pnl = s.get("actual_pnl_pct")
        setup = s.get("strategy")
        score = s.get("score")
        if pnl is None or not setup or score is None:
            continue
        by_combo[(setup, _band(float(score)))].append(float(pnl))
    from tracker import wilson_ci as _wilson  # local import to avoid circulars
    kills: dict = {}
    for (setup, band), pnls in by_combo.items():
        n = len(pnls)
        if n < min_n:
            continue
        wins = sum(1 for p in pnls if p > 0)
        wr = wins / n
        avg_pnl = sum(pnls) / n
        wr_lb, _wr_hi = _wilson(wins, n, 0.95)
        # Kill only when both point WR is below floor AND Wilson lower-bound also fails.
        # Prevents 5-trade noise from triggering kills.
        if wr < min_wr and wr_lb < SETUP_KILL_MIN_WR_LB and avg_pnl < min_pnl:
            kills[(setup, band)] = {
                "wr": round(wr * 100, 1),
                "wr_lb": round(wr_lb * 100, 1),
                "avg_pnl": round(avg_pnl, 2),
                "n": n,
                "reason": f"setup×score-band kill: {setup}@{band} WR {wr*100:.1f}% (LB {wr_lb*100:.1f}%) avg {avg_pnl:+.2f}% over {n} closed",
            }
    return kills


def compute_setup_kill_list(signal_log_path: str | None = None,
                             min_wr: float = SETUP_KILL_MIN_WR,
                             min_pnl: float = SETUP_KILL_MIN_PNL,
                             min_n: int = SETUP_KILL_MIN_N) -> dict:
    """Read signal_tracker outcomes; return setups that fail performance floor.

    Returns dict: {setup_name: {'wr': pct, 'avg_pnl': pct, 'n': count, 'reason': str}}.
    Only setups meeting all three thresholds (WR<min_wr AND avg_pnl<min_pnl AND
    n>=min_n) are included. Empty dict if log unavailable or no kills.

    Also merges in any setups listed under config["static_setup_kill_list"] —
    used for setups that don't have ≥min_n closed signals yet but were
    identified as broken via backtest (e.g., VCP Breakout 0% WR over 5 trades
    in the 60d backtest, 2026-05-08).
    """
    import json as _json
    from pathlib import Path as _P
    from collections import defaultdict as _dd
    # Phase B.1: route through state_layer for cache + future Supabase support.
    # Caller can still pass signal_log_path explicitly to override (used by tests).
    if signal_log_path is None:
        try:
            from state_layer import load_signal_log
            sigs = load_signal_log()
        except Exception:
            sigs = []
    else:
        try:
            sigs = _json.loads(_P(signal_log_path).read_text())
        except Exception:
            sigs = []
    by_setup: dict = _dd(list)
    for s in sigs or []:
        if s.get("status") != "CLOSED":
            continue
        pnl = s.get("actual_pnl_pct")
        setup = s.get("strategy")
        if pnl is None or not setup:
            continue
        by_setup[setup].append(float(pnl))
    from tracker import wilson_ci as _wilson  # local import to avoid circulars
    kills: dict = {}
    for setup, pnls in by_setup.items():
        n = len(pnls)
        if n < min_n:
            continue
        wins = sum(1 for p in pnls if p > 0)
        wr = wins / n
        avg_pnl = sum(pnls) / n
        wr_lb, _wr_hi = _wilson(wins, n, 0.95)
        # Wilson lower-bound gate: catches the case where point WR looks bad but
        # the sample is too small to distinguish from a true 35%+ WR.
        if wr < min_wr and wr_lb < SETUP_KILL_MIN_WR_LB and avg_pnl < min_pnl:
            kills[setup] = {
                "wr": round(wr * 100, 1),
                "wr_lb": round(wr_lb * 100, 1),
                "avg_pnl": round(avg_pnl, 2),
                "n": n,
                "reason": f"setup performance floor: WR {wr*100:.1f}% (Wilson LB {wr_lb*100:.1f}%) over {n} closed",
            }
    # Merge in static (manual) kill list from config — gated on declared n + reason.
    # Pre-2026-05-08 entries could be bare strings or dicts with no `n`; those are
    # rejected to prevent the back-door noise-kill that triggered VCP Breakout.
    try:
        cfg_path = _P(__file__).parent / "config" / "config.json"
        if cfg_path.exists():
            cfg = _json.loads(cfg_path.read_text())
            rejected: list = []
            for entry in (cfg.get("static_setup_kill_list") or []):
                if isinstance(entry, str):
                    rejected.append(f"{entry}: bare-string entries no longer accepted (declare n + wr_lb)")
                    continue
                if not isinstance(entry, dict):
                    continue
                name = entry.get("setup")
                if not name or name in kills:
                    continue
                declared_n = int(entry.get("n") or 0)
                declared_wr_lb = entry.get("wr_lb")  # caller-provided Wilson LB (0-1)
                reason = entry.get("reason") or "manually killed"
                # Gate: must declare n>=STATIC_KILL_MIN_N AND either an explicit
                # wr_lb<SETUP_KILL_MIN_WR_LB or be marked override=true (audit trail).
                if declared_n < STATIC_KILL_MIN_N and not entry.get("override"):
                    rejected.append(f"{name}: n={declared_n} < {STATIC_KILL_MIN_N} (set override=true to force)")
                    continue
                if declared_wr_lb is not None:
                    try:
                        if float(declared_wr_lb) >= SETUP_KILL_MIN_WR_LB and not entry.get("override"):
                            rejected.append(f"{name}: declared wr_lb={declared_wr_lb} >= {SETUP_KILL_MIN_WR_LB} (insufficient evidence)")
                            continue
                    except (TypeError, ValueError):
                        pass
                kills[name] = {
                    "wr": entry.get("wr"),
                    "wr_lb": declared_wr_lb,
                    "avg_pnl": entry.get("avg_pnl"),
                    "n": declared_n,
                    "reason": reason,
                    "source": "static",
                }
            if rejected:
                kills["_rejected_static"] = {"reason": "; ".join(rejected)}
    except Exception:
        pass
    return kills


def _normalize_decision_state(ds: Any) -> str | None:
    """decision_state is sometimes a string, sometimes a dict {'state': '...'}."""
    if isinstance(ds, dict):
        return ds.get("state")
    return ds


# ── ROLLING-SHARPE KILL SWITCH (Direction 2, 2026-05-13) ───────────────────
# Capital preservation gate: if the last N closed BUY signals have a negative
# rolling Sharpe (recent losses), block NEW BUYs until edge returns. The
# truncate-left-tail mechanism that smooths aggregate Sharpe per the article's
# "consistent across regimes" bar. Sized at the FULL gate cascade level — not
# a multiplier on individual scores — because the bad-period signal is
# system-wide, not setup-specific.
_ROLLING_SHARPE_CACHE: dict = {"_signal_log_mtime": 0, "_state": None}


def _signal_log_path() -> Path:
    return Path(__file__).resolve().parent / "data" / "signal_log.json"


def compute_rolling_sharpe_kill_state(config: dict | None = None) -> dict:
    """Compute the rolling-Sharpe kill switch state from data/signal_log.json.

    Cached by signal_log.json mtime — recomputes only when the log changes.
    Returns:
      {
        active: bool,           # True if new BUYs should be blocked
        reason: str,            # human-readable explanation
        sharpe: float|None,     # rolling sharpe over last N closed BUYs
        n: int,                 # actual samples used
        avg_pnl: float|None,
        threshold: float,       # config min_sharpe
        lookback_n: int,        # config lookback
        min_sample_n: int,      # config minimum sample required
      }
    """
    cfg = (config or {}).get("rolling_sharpe_kill") or {}
    enabled = bool(cfg.get("_enabled", False))
    threshold = float(cfg.get("min_sharpe", -0.5))
    lookback_n = int(cfg.get("lookback_n", 20))
    min_sample_n = int(cfg.get("min_sample_n", 10))
    out_default = {
        "active": False, "reason": "disabled" if not enabled else "no data",
        "sharpe": None, "n": 0, "avg_pnl": None,
        "threshold": threshold, "lookback_n": lookback_n,
        "min_sample_n": min_sample_n,
    }
    if not enabled:
        return out_default

    p = _signal_log_path()
    if not p.exists():
        return {**out_default, "reason": "signal_log.json missing"}

    try:
        mtime = p.stat().st_mtime
    except OSError:
        return {**out_default, "reason": "signal_log.json stat failed"}

    # Cache hit if log hasn't changed
    if mtime == _ROLLING_SHARPE_CACHE["_signal_log_mtime"] and _ROLLING_SHARPE_CACHE["_state"]:
        return _ROLLING_SHARPE_CACHE["_state"]

    try:
        import json as _json
        signals = _json.loads(p.read_text())
    except Exception:
        return {**out_default, "reason": "signal_log.json parse failed"}
    if not isinstance(signals, list):
        return {**out_default, "reason": "signal_log.json not a list"}

    # Filter to CLOSED BUYs with valid pnl. Sort by exit date (or fall back
    # to entry date), take last N. Skip outliers >100% (CTRA-class).
    closed_buys: list[dict] = []
    for s in signals:
        if not isinstance(s, dict):
            continue
        if s.get("status") != "CLOSED":
            continue
        if (s.get("verdict") or "").upper() != "BUY":
            continue
        pnl = s.get("actual_pnl_pct")
        if pnl is None:
            continue
        try:
            pnl = float(pnl)
        except (TypeError, ValueError):
            continue
        if abs(pnl) > 100:  # outlier defensive
            continue
        closed_buys.append({"pnl": pnl, "date": s.get("date") or ""})
    closed_buys.sort(key=lambda r: r["date"])  # ascending
    recent = closed_buys[-lookback_n:]
    n = len(recent)

    if n < min_sample_n:
        state = {**out_default, "n": n,
                 "reason": f"only {n} closed BUYs (< {min_sample_n} min sample) — no kill"}
        _ROLLING_SHARPE_CACHE.update({"_signal_log_mtime": mtime, "_state": state})
        return state

    pnls = [r["pnl"] for r in recent]
    avg = statistics.mean(pnls)
    std = statistics.stdev(pnls) if len(pnls) >= 2 else 0
    sharpe = (avg / std) if std > 0 else 0.0

    active = sharpe < threshold
    state = {
        "active": active,
        "reason": (
            f"rolling sharpe {sharpe:+.3f} < {threshold:+.2f} on last {n} BUYs "
            f"(avg pnl {avg:+.2f}%); pausing new BUYs"
            if active else
            f"rolling sharpe {sharpe:+.3f} >= {threshold:+.2f} on last {n} BUYs — gate inactive"
        ),
        "sharpe": round(sharpe, 4),
        "n": n,
        "avg_pnl": round(avg, 3),
        "threshold": threshold,
        "lookback_n": lookback_n,
        "min_sample_n": min_sample_n,
    }
    _ROLLING_SHARPE_CACHE.update({"_signal_log_mtime": mtime, "_state": state})
    return state


def _eval_hard_gates(t: dict, regime: str | None = None,
                     entry_quality_relax_regimes: set | None = None) -> tuple[list[dict], list[str]]:
    """Returns (gate_evaluations, failed_gate_names).

    entry_quality_relax_regimes: set of regime4 names where EXTENDED/MISSED
    entries are ALLOWED to pass (become BUY) instead of being blocked. Per
    regime_sharpe_decomp evidence (2026-05-13) — these bands are profitable
    in risk_on_choppy regime specifically (MISSED PF 2.59 n=302, EXTENDED
    PF 1.33 n=335). Default empty (current behavior — block always).
    """
    gates: list[dict] = []
    failures: list[str] = []
    _eq_relax = entry_quality_relax_regimes or set()
    _regime_lower = (regime or "").lower()

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
    # ENTRY-Q-REGIME-RELAX (2026-05-13): regime_sharpe_decomp on n=897 closed
    # trades shows MISSED (n=302, PF 2.59, Sharpe +0.33) and EXTENDED (n=335,
    # PF 1.33, Sharpe +0.10) are BOTH profitable in aggregate — better than
    # PULLBACK (n=72, PF 0.88) which the gate currently prefers. In
    # risk_on_choppy regime specifically, this profitability holds. Relax
    # the block in regimes where evidence supports it. Default behavior
    # unchanged unless config.scoring.entry_quality_regime_relax is set.
    eq = t.get("entry_quality")
    _eq_bad = eq in ("MISSED", "EXTENDED")
    _eq_relaxed_for_regime = _eq_bad and _regime_lower in _eq_relax
    # MOMENTUM-SLEEVE BYPASS (2026-05-13): when ticker classified as Momentum
    # Continuation family, EXTENDED/MISSED is the EXPECTED entry — bypass.
    _is_momentum = (t.get("setup_family") == "Momentum Continuation")
    _is_defensive_eq = (t.get("setup_family") == "Defensive Rotation")
    _is_meanrev_eq = (t.get("setup_family") == "Mean Reversion")
    _is_pead_eq = (t.get("setup_family") == "PEAD")
    _is_insider_eq = (t.get("setup_family") == "Insider Cluster")
    if _is_momentum and _eq_bad:
        passed = True
        reason = f"entry_quality={eq} allowed for Momentum Continuation sleeve (bypass)"
    elif _is_defensive_eq and _eq_bad:
        passed = True
        reason = f"entry_quality={eq} allowed for Defensive Rotation sleeve (sector flow, not pullback) (bypass)"
    elif _is_meanrev_eq and _eq_bad:
        passed = True
        reason = f"entry_quality={eq} allowed for Mean Reversion sleeve (EXTENDED-down IS the trigger) (bypass)"
    elif _is_pead_eq and _eq_bad:
        passed = True
        reason = f"entry_quality={eq} allowed for PEAD sleeve (gap-up entry IS the trigger) (bypass)"
    elif _is_insider_eq and _eq_bad:
        passed = True
        reason = f"entry_quality={eq} allowed for Insider Cluster sleeve (info edge) (bypass)"
    elif _eq_relaxed_for_regime:
        passed = True
        reason = f"entry_quality={eq} allowed in {_regime_lower} (relax per regime_sharpe_decomp 2026-05-13)"
    else:
        passed = not _eq_bad
        reason = "" if passed else f"entry_quality={eq} — wait for pullback to value zone"
    gates.append({
        "name": "entry_quality",
        "passed": passed,
        "reason": reason,
    })
    if not passed:
        failures.append("entry_quality")

    # 4. Decision state (state machine)
    # PEAD bypass (2026-05-14): PEAD setups have already gapped — decision_state=MISSED
    # is the EXPECTED state for catalyst-driven entries. The whole mechanism is buying
    # the post-report move, not pulling back to a primary zone.
    ds = _normalize_decision_state(t.get("decision_state"))
    _is_pead_ds = (t.get("setup_family") == "PEAD")
    _is_insider_ds = (t.get("setup_family") == "Insider Cluster")
    passed = ds not in ("MISSED", "NO_EDGE")
    if _is_pead_ds and not passed:
        passed = True
        ds_reason = f"decision_state={ds} allowed for PEAD sleeve (gap-up IS the entry) (bypass)"
    elif _is_insider_ds and not passed:
        passed = True
        ds_reason = f"decision_state={ds} allowed for Insider Cluster sleeve (info edge) (bypass)"
    else:
        ds_reason = "" if passed else f"decision_state={ds}"
    gates.append({
        "name": "decision_state",
        "passed": passed,
        "reason": ds_reason,
    })
    if not passed:
        failures.append("decision_state")

    # 5. Tail-loss filter — broadened to catch all conviction-engine demotions
    # (2026-05-07: ATEN had conviction.tier=0 / label=WATCH but tail_filter_demoted=None.
    # Original narrow check missed this — engine still allowed BUY despite zero conviction.)
    # CATALYST-SLEEVE BYPASS (2026-05-14): conviction tier is composite-score-band only
    # (60-69 = tier 0/WATCH). Catalyst-driven sleeves (PEAD/Momentum/Defensive/MeanRev)
    # explicitly accept moderate composite scores because their mechanism comes from
    # outside the composite score (catalyst / regime flow / oversold mechanic).
    # Bypass only when the sleeve detector itself fired (audit-verifiable trail).
    conv = t.get("conviction") or {}
    tail_demoted = bool(conv.get("tail_filter_demoted"))
    tier_zero = (conv.get("tier") == 0 and (conv.get("label") or "").upper() in ("WATCH", "AVOID", "WAIT"))
    _sleeve_fam = t.get("setup_family")
    _catalyst_sleeve = _sleeve_fam in ("PEAD", "Momentum Continuation",
                                         "Defensive Rotation", "Mean Reversion",
                                         "Insider Cluster")
    # Only bypass tier_zero (not actual tail_loss demotion — that's a star-rating call)
    if _catalyst_sleeve and tier_zero and not tail_demoted:
        demoted = False
        reason = f"conviction tier=0 bypassed for {_sleeve_fam} sleeve (catalyst-driven)"
    else:
        demoted = tail_demoted or tier_zero
        reason = ""
        if demoted:
            if tier_zero and not tail_demoted:
                reason = f"conviction tier=0 / label={conv.get('label')} — engine demoted"
            else:
                reason = (conv.get("description") or "tail-loss filter demoted")[:140]
    passed = not demoted
    gates.append({"name": "tail_loss_filter", "passed": passed, "reason": reason})
    if not passed:
        failures.append("tail_loss_filter")

    # 6. Earnings proximity (Phase 4.1) — never enter swing pos with earnings <5d.
    # Bundle stores earnings under r.earnings.days_to_earnings; V2 tickers.json
    # surfaces as r.earn_days. Check both so engine works at both layers.
    ed = t.get("earn_days")
    if ed is None:
        ed = (t.get("earnings") or {}).get("days_to_earnings")
    if ed is not None and isinstance(ed, (int, float)) and 0 <= ed < EARNINGS_BLOCK_DAYS:
        gates.append({
            "name": "earnings_proximity",
            "passed": False,
            "reason": f"earnings in {int(ed)} day(s) — institutional standard blocks BUY <{EARNINGS_BLOCK_DAYS}d",
        })
        failures.append("earnings_proximity")
    else:
        gates.append({"name": "earnings_proximity", "passed": True, "reason": ""})

    # 7. Setup performance floor (Phase 3.2 + #7 stratified) — auto-kill chronically
    # losing setups AND specific (setup, score_band) combos.
    setup_kills = t.get("_setup_kill_list") or {}
    band_kills = t.get("_setup_band_kill_list") or {}
    setup_name = t.get("setup_family") or t.get("setup") or t.get("setup_type")
    score = float(t.get("score") or 0)
    if score >= 80: band = ">=80"
    elif score >= 70: band = "70-79"
    elif score >= 60: band = "60-69"
    elif score >= 50: band = "50-59"
    else: band = "<50"
    killed_reason = None
    if setup_name and setup_name in setup_kills:
        info = setup_kills[setup_name]
        killed_reason = f"{setup_name}: {info['reason']}, avg_pnl {info['avg_pnl']:+.2f}%"
    elif setup_name and (setup_name, band) in band_kills:
        info = band_kills[(setup_name, band)]
        killed_reason = info["reason"]
    if killed_reason:
        gates.append({"name": "setup_performance", "passed": False, "reason": killed_reason})
        failures.append("setup_performance")
    else:
        gates.append({"name": "setup_performance", "passed": True, "reason": ""})

    # 8. Fundamental adequacy
    # Three possible field paths used across bundle/V2 layers — check all:
    #   1. r.fund_score / r.fund_max          (V2 tickers.json after build_data)
    #   2. r.fund_total.{score,max}            (some legacy paths)
    #   3. r.fundamentals.{score,max}          (raw bundle from swing_trade scan)
    # Bug fix 2026-05-07: engine was missing path 3, allowing tickers like AMAT
    # to bypass fund gate (fundamentals.score=14, max=30 = 47% < 50% should fail).
    fs = t.get("fund_score")
    fm = t.get("fund_max")
    if (fs is None or fm is None):
        ft = t.get("fund_total") or {}
        fs = fs if fs is not None else ft.get("score")
        fm = fm if fm is not None else ft.get("max")
    if (fs is None or fm is None):
        ftn = t.get("fundamentals") or {}
        fs = fs if fs is not None else ftn.get("score")
        fm = fm if fm is not None else ftn.get("max")
    if fs is not None and fm and fm > 0:
        ratio = fs / fm
        # Conditional bypass (2026-05-11): the score gate already weights qg
        # as one of 5 pillars (max 30% contribution). Re-testing fund_adequacy
        # in isolation double-counts and blocks strong-score / Tier-1 catalyst
        # names where technicals + catalyst more than compensate. Evidence:
        # picks_history n=314 shows qg<2 still wins 55.6% with PF 1.29 when
        # other pillars are strong. Bypass conditions:
        #   1. score >= 75 → already vetted as elite by composite
        #   2. catalyst_tier == 1 → PEAD/UOA/VCP/52wk-breakout — catalyst-driven
        _score = t.get("score") or 0
        _cat_tier = t.get("catalyst_tier")
        _is_mom_family = (t.get("setup_family") == "Momentum Continuation")
        _is_def_family = (t.get("setup_family") == "Defensive Rotation")
        _is_pead_family = (t.get("setup_family") == "PEAD")
        _is_insider_family = (t.get("setup_family") == "Insider Cluster")
        # Bypass conditions are gated by a score floor — pure cat_tier=1
        # without a composite floor would let noise tickers (score=3 with
        # a PEAD tag) slip through. Score 60 = WATCH-eligible composite floor.
        # MOMENTUM-SLEEVE BYPASS (2026-05-13): momentum-classified tickers
        # bypass fund_adequacy entirely — momentum doesn't depend on quality.
        # DEFENSIVE-ROTATION BYPASS (2026-05-14): defensive ETFs don't have
        # classical fundamentals; large-cap defensives are quality by definition.
        _bypass = (_is_mom_family or _is_def_family or _is_pead_family or _is_insider_family
                   or (_score >= 75) or (_cat_tier == 1 and _score >= 60))
        if ratio < DEFAULT_FUND_ADEQUACY and _bypass:
            passed = True
            _bypass_reason = ("Momentum Continuation sleeve" if _is_mom_family
                              else "Defensive Rotation sleeve" if _is_def_family
                              else "PEAD sleeve" if _is_pead_family
                              else "Insider Cluster sleeve" if _is_insider_family
                              else f"score={_score:.0f}, cat_tier={_cat_tier}")
            reason = (f"fundamentals {fs}/{fm} = {ratio*100:.0f}% < {DEFAULT_FUND_ADEQUACY*100:.0f}% — "
                      f"bypassed ({_bypass_reason})")
        else:
            passed = ratio >= DEFAULT_FUND_ADEQUACY
            reason = "" if passed else f"fundamentals {fs}/{fm} = {ratio*100:.0f}% < {DEFAULT_FUND_ADEQUACY*100:.0f}% adequacy"
    else:
        passed = True  # no data → don't block (avoid false negatives on data outages)
        reason = "no fundamentals data — gate skipped"
    gates.append({"name": "fundamental_adequacy", "passed": passed, "reason": reason})
    if not passed:
        failures.append("fundamental_adequacy")

    # 9. Technical alignment — price vs EMA stack (2026-05-07: ATEN passed score
    # threshold 72 but was below ALL 3 EMAs — that's a downtrend, not a BUY setup).
    # Hard fail when price is below all of (21EMA, 50EMA, 200SMA). Caveat handled
    # in _eval_soft_gates when partial breach.
    # Flags live at t.technicals.indicators.above_{20,50}ema/200sma — fall back
    # to top-level / build_data flattening for compatibility.
    _ind = ((t.get("technicals") or {}).get("indicators") or {}) if isinstance(t.get("technicals"), dict) else {}
    above_21 = (t.get("above_21ema") if t.get("above_21ema") is not None
                else _ind.get("above_20ema"))
    above_50 = (t.get("above_50ema") if t.get("above_50ema") is not None
                else _ind.get("above_50ema"))
    above_200 = (t.get("above_200sma") if t.get("above_200sma") is not None
                 else _ind.get("above_200sma"))
    # Only evaluate if at least one MA flag is populated (otherwise data may be missing)
    if any(v is not None for v in (above_21, above_50, above_200)):
        # All False = price below entire EMA stack = structural downtrend
        if above_21 is False and above_50 is False and above_200 is False:
            gates.append({
                "name": "technical_alignment",
                "passed": False,
                "reason": "price below 21EMA, 50EMA, AND 200SMA — structural downtrend, not BUY setup",
            })
            failures.append("technical_alignment")
        else:
            gates.append({"name": "technical_alignment", "passed": True, "reason": ""})
    else:
        gates.append({"name": "technical_alignment", "passed": True, "reason": "no MA data — gate skipped"})

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
    if ed is None:
        ed = (t.get("earnings") or {}).get("days_to_earnings")
    if ed is not None and EARNINGS_BLOCK_DAYS <= ed < EARNINGS_CAVEAT_DAYS:
        caveats.append(f"earnings in {int(ed)} days")

    # Partial EMA breach — soft caveat (full breach is a hard gate above)
    above_21 = t.get("above_21ema")
    above_50 = t.get("above_50ema")
    above_200 = t.get("above_200sma")
    breach_count = sum(1 for v in (above_21, above_50, above_200) if v is False)
    if 0 < breach_count < 3:  # 1 or 2 MAs below — caveat, not block
        breached = [name for name, v in
                    (("21EMA", above_21), ("50EMA", above_50), ("200SMA", above_200))
                    if v is False]
        caveats.append(f"price below {' & '.join(breached)} — incomplete trend confirmation")

    return caveats


def _resolve_buy_threshold(regime: str | None, thresholds: dict | None) -> int:
    if not thresholds:
        return DEFAULT_BUY_THRESHOLD
    key = (regime or "risk_on_choppy").lower()
    return int((thresholds.get(key) or {}).get("buy_min_score") or DEFAULT_BUY_THRESHOLD)


def compute_final_verdict(t: dict, regime: str | None = None,
                          thresholds: dict | None = None,
                          setup_kill_list: dict | None = None,
                          system_status: dict | None = None,
                          setup_band_kill_list: dict | None = None,
                          config: dict | None = None) -> dict:
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
    # Inject kill lists into ticker dict for _eval_hard_gates to use (Phase 3.2 + #7)
    if setup_kill_list or setup_band_kill_list:
        t = {**t,
             "_setup_kill_list": setup_kill_list or {},
             "_setup_band_kill_list": setup_band_kill_list or {}}
    # Bear setup is a parallel path — keep upstream short logic
    bear = (t.get("bear_setup") or {})
    # System-level circuit breakers (drawdown / forced cash / macro blackout)
    # — checked BEFORE bear-setup so SHORT signals also respect them.
    ss = (system_status or {})
    cb = (ss.get("circuit_breaker") or {})
    fc = (ss.get("forced_cash") or {})
    mc = (ss.get("macro_calendar") or {})
    if cb.get("active") or fc.get("active") or mc.get("blackout_today"):
        reason_parts = []
        if cb.get("active"):
            reason_parts.append("Circuit breaker: " + (cb.get("reasons", ["drawdown limit"])[0] if cb.get("reasons") else cb.get("level", "tripped")))
        if fc.get("active"):
            reason_parts.append("Forced cash mode active")
        if mc.get("blackout_today"):
            reason_parts.append("Macro blackout: " + (mc.get("blackout_reason") or "FOMC/CPI"))
        return {
            "verdict": "WAIT",
            "reason": " · ".join(reason_parts),
            "caveats": [],
            "gates_evaluated": [{"name": "system_circuit_breaker", "passed": False, "reason": " · ".join(reason_parts)}],
            "demote_to": "watch_list",
        }
    if t.get("direction") == "short" or bear.get("score", 0) >= 10:
        return {
            "verdict": "AVOID",
            "reason": "bear setup detected",
            "caveats": [],
            "gates_evaluated": [],
            "demote_to": None,
        }

    # A3 (2026-05-09): Regime gate. Per 750d backtest: strategy is bull-only;
    # losses concentrate in risk_off and panic regimes. Refuse new BUY entries
    # in those regimes — leaves existing positions to their exit rules but
    # stops adding to losing exposure. Vinod-style risk discipline.
    _regime_lower = (regime or "").lower()
    _is_defensive = (t.get("setup_family") == "Defensive Rotation")
    _is_pead = (t.get("setup_family") == "PEAD")
    _is_insider = (t.get("setup_family") == "Insider Cluster")
    if _regime_lower in ("panic", "risk_off_trending") and not (_is_defensive or _is_pead or _is_insider):
        return {
            "verdict": "WATCH",
            "reason": f"regime gate: no new longs in {regime} (bull-only strategy)",
            "caveats": [f"regime={regime} blocks new BUYs; existing positions unaffected"],
            "gates_evaluated": [{
                "name": "regime_gate",
                "passed": False,
                "reason": f"regime is {regime} — strategy bull-only per 750d backtest evidence",
                "severity": "high",
            }],
            "demote_to": "watch_list",
        }
    # DEFENSIVE-ROTATION BYPASS (2026-05-14): sleeve is BUILT for these
    # regimes — institutional flight-to-safety flow into low-beta defensives.
    # Audit logged but gate intentionally passes.

    # ROLLING-SHARPE KILL (2026-05-13, Direction 2): capital preservation gate.
    # If recent N closed BUYs show rolling Sharpe < threshold, pause new BUYs.
    # Truncates left-tail bad periods. Block-not-relax — silently waits for
    # rolling Sharpe to recover before resuming.
    _rs_state = compute_rolling_sharpe_kill_state(config) if config else {"active": False}
    if _rs_state.get("active"):
        return {
            "verdict": "WATCH",
            "reason": f"rolling-Sharpe kill: {_rs_state.get('reason')}",
            "caveats": [
                f"recent {_rs_state.get('n')} BUYs Sharpe {_rs_state.get('sharpe'):+.3f} "
                f"(threshold {_rs_state.get('threshold'):+.2f})"
            ],
            "gates_evaluated": [{
                "name": "rolling_sharpe_kill",
                "passed": False,
                "reason": _rs_state.get("reason"),
                "severity": "high",
                "stats": _rs_state,
            }],
            "demote_to": "watch_list",
        }

    # ENTRY-Q-REGIME-RELAX (2026-05-13): read config to determine which
    # regimes allow EXTENDED/MISSED entries (evidence-backed per
    # regime_sharpe_decomp). Default empty = no change to prior behavior.
    # Config lives in regime4_thresholds.entry_quality_regime_relax — a
    # dict of {regime_name: ["EXTENDED", "MISSED", ...]}. Any regime with
    # a non-empty list gets the relax applied.
    _eq_relax = set()
    try:
        if isinstance(thresholds, dict):
            _eq_relax_cfg = thresholds.get("entry_quality_regime_relax") or {}
            if isinstance(_eq_relax_cfg, dict):
                for _reg, _allowed in _eq_relax_cfg.items():
                    if isinstance(_allowed, (list, set, tuple)) and _allowed:
                        _eq_relax.add(_reg.lower())
    except Exception:
        pass
    gates, failures = _eval_hard_gates(t, regime=regime, entry_quality_relax_regimes=_eq_relax)
    caveats = _eval_soft_gates(t)
    # Stamp caveat when entry_quality was relaxed (so user sees WHY a normally-
    # blocked EXTENDED/MISSED entry made BUY — not silent override).
    if _eq_relax and t.get("entry_quality") in ("MISSED", "EXTENDED") and (regime or "").lower() in _eq_relax:
        caveats.append(f"entry_quality={t.get('entry_quality')} relaxed in {regime} per evidence (PF 1.33-2.59 in choppy n>=302)")

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
        # A2 (2026-05-09): signal_filter whitelist gate. Demote to WATCH if
        # the (setup × regime × score_band × entry_quality) combination isn't
        # whitelisted. Off by default (config["signal_filter"]["_enabled"]=false)
        # → fail-open (returns allow=True with reason="filter_disabled").
        try:
            from signal_filter import evaluate as _sf_eval
            sf = _sf_eval(t)
            if not sf.get("allow"):
                return {
                    "verdict": "WATCH",
                    "reason": f"signal_filter demoted: {sf.get('reason')}",
                    "caveats": caveats + [f"signal_filter:{sf.get('reason')}"],
                    "gates_evaluated": gates + [{
                        "name": "signal_filter",
                        "passed": False,
                        "reason": sf.get("reason"),
                        "matched_rule_id": sf.get("matched_rule_id"),
                    }],
                    "demote_to": "watch_list",
                    "signal_filter": sf,
                }
            # allowed — fall through to BUY, attach audit info
            _filter_audit = sf
        except Exception as _sf_e:
            log.debug(f"signal_filter eval failed (allowing through): {_sf_e}") if 'log' in dir() else None
            _filter_audit = None

        return {
            "verdict": "BUY",
            "reason": f"all gates passed; score {score} >= {threshold} ({regime or 'default'})",
            "caveats": caveats,
            "gates_evaluated": gates,
            "demote_to": None,
            "signal_filter": _filter_audit,
        }

    return {
        "verdict": "WATCH",
        "reason": f"all gates passed but score {score} < BUY threshold {threshold}",
        "caveats": caveats,
        "gates_evaluated": gates,
        "demote_to": None,
    }
