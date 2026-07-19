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
    Two modes (config: rolling_sharpe_kill.mode):
      - "aggregate" (default): one rolling Sharpe across ALL closed BUYs.
        Returns {active, sharpe, n, ...} same as before.
      - "per_sleeve":        one rolling Sharpe per setup_family. Returns the
        aggregate fields PLUS sleeve_states={sleeve: {active, sharpe, n, ...}}.
        Aggregate `active` is the OR across sleeves (so any failing sleeve
        flips the global flag), but per-sleeve gate-application is done by
        the caller at the gate site.
    """
    cfg = (config or {}).get("rolling_sharpe_kill") or {}
    enabled = bool(cfg.get("_enabled", False))
    threshold = float(cfg.get("min_sharpe", -0.5))
    lookback_n = int(cfg.get("lookback_n", 20))
    min_sample_n = int(cfg.get("min_sample_n", 10))
    mode = str(cfg.get("mode") or "aggregate").lower()
    reset_at = cfg.get("reset_at") or ""  # ISO date — exclude signals before this date
    out_default = {
        "active": False, "reason": "disabled" if not enabled else "no data",
        "sharpe": None, "n": 0, "avg_pnl": None,
        "threshold": threshold, "lookback_n": lookback_n,
        "min_sample_n": min_sample_n,
        "mode": mode, "sleeve_states": {},
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

    # Cache hit if log hasn't changed AND mode hasn't changed
    cache_key = (mtime, mode)
    if cache_key == _ROLLING_SHARPE_CACHE.get("_cache_key") and _ROLLING_SHARPE_CACHE.get("_state"):
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
    #
    # 2026-05-18 · TWO CRITICAL FIXES:
    #   (a) DEDUPE by (ticker, entry_price, pnl) — the resolver was re-logging
    #       the same closed trade once per day, so a single -4.16% loss could
    #       be counted 7 times in the rolling-20 window.
    #   (b) FILTER OUT WATCH-conviction signals — verdict='BUY' was being set
    #       on paper signals whose conviction_label was actually 'WATCH'
    #       (never sized, never traded). These were inflating the loss count
    #       with hypothetical paper outcomes that were never real trades.
    closed_buys: list[dict] = []
    seen_keys: set[tuple] = set()
    n_dropped_dupe = 0
    n_dropped_watch = 0
    n_dropped_pre_reset = 0
    for s in signals:
        if not isinstance(s, dict):
            continue
        if s.get("status") != "CLOSED":
            continue
        if (s.get("verdict") or "").upper() != "BUY":
            continue
        # 2026-05-19 — reset_at filter: exclude signals dated before reset_at.
        # Used after a system-logic finalization so the kill counts only trades
        # made with the current set of gates/overlays — past trades from earlier
        # logic shouldn't gate the new logic.
        if reset_at:
            sig_date = str(s.get("date") or "")[:10]
            if sig_date and sig_date < reset_at:
                n_dropped_pre_reset += 1
                continue
        # (b) · skip WATCH-conviction signals — these weren't real trades
        conviction = (s.get("conviction_label") or "").upper()
        if conviction == "WATCH":
            n_dropped_watch += 1
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
        # (a) · dedupe by (ticker, entry_price, rounded-pnl). Same physical
        # trade gets one entry, not one per day-it-was-in-the-log.
        dedupe_key = (
            s.get("ticker"),
            round(float(s.get("entry_price") or 0), 4),
            round(float(pnl), 2),
            s.get("exit_reason") or "",
        )
        if dedupe_key in seen_keys:
            n_dropped_dupe += 1
            continue
        seen_keys.add(dedupe_key)
        sleeve = (s.get("setup_family") or s.get("setup_type") or s.get("strategy")
                  or "Unknown")
        closed_buys.append({"pnl": pnl, "date": s.get("date") or "", "sleeve": sleeve})
    closed_buys.sort(key=lambda r: r["date"])
    if n_dropped_dupe or n_dropped_watch or n_dropped_pre_reset:
        try:
            log.info(f"[rolling_sharpe_kill] filtered signal_log: dropped {n_dropped_dupe} dupes, {n_dropped_watch} WATCH-conviction, {n_dropped_pre_reset} pre-reset (<{reset_at}); kept {len(closed_buys)} real BUYs")
        except Exception:
            pass

    def _stat(samples: list[dict]) -> dict:
        """Compute Sharpe/avg/active over a list of {pnl, date} samples."""
        n = len(samples)
        if n < min_sample_n:
            return {"active": False, "sharpe": None, "n": n, "avg_pnl": None,
                    "reason": f"only {n} closed BUYs (< {min_sample_n} min sample) — no kill"}
        pnls = [r["pnl"] for r in samples]
        avg = statistics.mean(pnls)
        std = statistics.stdev(pnls) if len(pnls) >= 2 else 0
        sharpe = (avg / std) if std > 0 else 0.0
        active = sharpe < threshold
        return {
            "active": active, "sharpe": round(sharpe, 4), "n": n,
            "avg_pnl": round(avg, 3),
            "reason": (
                f"rolling sharpe {sharpe:+.3f} < {threshold:+.2f} on last {n} BUYs "
                f"(avg pnl {avg:+.2f}%); pausing new BUYs"
                if active else
                f"rolling sharpe {sharpe:+.3f} >= {threshold:+.2f} on last {n} BUYs — gate inactive"
            ),
        }

    # Aggregate stat — always computed (used by aggregate-mode caller and as
    # display fallback for per-sleeve mode).
    agg = _stat(closed_buys[-lookback_n:])

    # Per-sleeve stats — only relevant when mode=per_sleeve, but cheap to compute.
    sleeve_states: dict[str, dict] = {}
    if mode == "per_sleeve":
        from collections import defaultdict
        by_sleeve = defaultdict(list)
        for r in closed_buys:
            by_sleeve[r["sleeve"]].append(r)
        for sleeve, samples in by_sleeve.items():
            sleeve_states[sleeve] = _stat(samples[-lookback_n:])

    # Aggregate `active`: in per_sleeve mode, only fire when EVERY sleeve with
    # enough samples is below floor — guards against premature global kill when
    # only one sleeve is bleeding. Per-sleeve gating at the call site handles
    # selective kills.
    if mode == "per_sleeve":
        active_sleeves = [s for s in sleeve_states.values()
                          if s.get("active") and s.get("n", 0) >= min_sample_n]
        ready_sleeves = [s for s in sleeve_states.values()
                         if s.get("n", 0) >= min_sample_n]
        active_all = bool(ready_sleeves) and len(active_sleeves) == len(ready_sleeves)
    else:
        active_all = agg.get("active", False)

    state = {
        **agg,
        "active": active_all,
        "threshold": threshold,
        "lookback_n": lookback_n,
        "min_sample_n": min_sample_n,
        "mode": mode,
        "sleeve_states": sleeve_states,
    }
    _ROLLING_SHARPE_CACHE.update({"_cache_key": cache_key, "_state": state,
                                  "_signal_log_mtime": mtime})  # legacy key kept
    return state


_PEAD_GATE_CACHE = {"v": None}
def _pead_extended_gate_on() -> bool:
    """True if config.pead_extended_entry_gate._enabled — when on, PEAD/Impulse Catalyst
    EXTENDED/MISSED entries do NOT bypass the entry_quality gate (they fall to WATCH).
    Default ON (shipped 2026-05-31 from pick_forensics evidence). Cached after first read."""
    if _PEAD_GATE_CACHE["v"] is not None:
        return _PEAD_GATE_CACHE["v"]
    val = True  # default ON
    try:
        from pathlib import Path as _P
        import json as _json
        cfg = _json.loads((_P(__file__).parent / "config" / "config.json").read_text())
        blk = cfg.get("pead_extended_entry_gate")
        if isinstance(blk, dict) and "_enabled" in blk:
            val = bool(blk["_enabled"])
    except Exception:
        val = True
    _PEAD_GATE_CACHE["v"] = val
    return val


def _eval_hard_gates(t: dict, regime: str | None = None,
                     entry_quality_relax_regimes: set | None = None,
                     sector_blocklist: list | None = None,
                     sector_bypass_sleeves: set | None = None) -> tuple[list[dict], list[str]]:
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

    # 0. Sector blocklist gate (2026-05-19)
    # Evidence: Energy PF=0.52/n=128, Basic Materials PF=0.59/n=50,
    # Consumer Cyclical PF=0.25/n=34, Communication Services PF=0.63/n=28.
    # Defensive Rotation sleeve bypasses (it intentionally trades sector ETFs in panic).
    _blocked_sectors = sector_blocklist or []
    _sb_bypass = sector_bypass_sleeves or set()
    _ticker_sector = t.get("sector") or ""
    _is_sector_bypass = t.get("setup_family") in _sb_bypass
    if _blocked_sectors and _ticker_sector and not _is_sector_bypass:
        _sector_blocked = any(_ticker_sector.lower() == s.lower() for s in _blocked_sectors)
        if _sector_blocked:
            gates.append({
                "name": "sector_block",
                "passed": False,
                "reason": f"sector '{_ticker_sector}' in blocklist (PF<0.65 backtest 986 trades — 2026-05-19)",
            })
            failures.append("sector_block")
        else:
            gates.append({"name": "sector_block", "passed": True, "reason": ""})
    # (no gate appended if blocklist not configured — keeps gate list clean for older configs)

    # 0.5. Halt gate (2026-05-19)
    # Schwab securityStatus surfaced via translate_quote_to_stock_info. We block
    # BUY on Halted / News Pending / Deleted — "Closed" (after-hours) is NOT a halt
    # and passes through. Hard block — no sleeve bypasses; safety-of-execution
    # invariant. The decision becomes WATCH with reason chip "halted_<status>".
    _sec_status = t.get("security_status") or t.get("info", {}).get("security_status") or "Normal"
    _is_halted  = bool(t.get("is_halted") or t.get("info", {}).get("is_halted"))
    if _is_halted or (_sec_status and str(_sec_status).lower() not in ("normal", "closed", "")):
        gates.append({
            "name": "halt_gate",
            "passed": False,
            "reason": f"security_status={_sec_status} — halted/news-pending tickers cannot enter BUY",
        })
        failures.append("halt_gate")
    else:
        gates.append({"name": "halt_gate", "passed": True, "reason": ""})

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
    # FRESH added 2026-05-19: backtest 986 trades shows FRESH WR=36.8%, avg=-2.69% (worst band).
    # Buying exactly at support = buying into distribution from weak holders. Block it.
    # Catalyst sleeves (PEAD/Momentum/Insider/etc.) bypass this gate entirely below.
    _eq_bad = eq in ("MISSED", "EXTENDED", "FRESH")
    # MISSED/EXTENDED relaxation: only applies to MISSED/EXTENDED, not FRESH.
    _eq_relaxed_for_regime = eq in ("MISSED", "EXTENDED") and _regime_lower in _eq_relax
    # MOMENTUM-SLEEVE BYPASS (2026-05-13): when ticker classified as Momentum
    # Continuation family, EXTENDED/MISSED is the EXPECTED entry — bypass.
    _is_momentum = (t.get("setup_family") == "Momentum Continuation")
    _is_defensive_eq = (t.get("setup_family") == "Defensive Rotation")
    _is_meanrev_eq = (t.get("setup_family") == "Mean Reversion")
    _is_pead_eq = (t.get("setup_family") == "PEAD")
    _is_insider_eq = (t.get("setup_family") == "Insider Cluster")
    _is_esp_eq = (t.get("setup_family") == "ESP Play")
    if _is_momentum and _eq_bad:
        passed = True
        reason = f"entry_quality={eq} allowed for Momentum Continuation sleeve (bypass)"
    elif _is_defensive_eq and _eq_bad:
        passed = True
        reason = f"entry_quality={eq} allowed for Defensive Rotation sleeve (sector flow, not pullback) (bypass)"
    elif _is_meanrev_eq and _eq_bad:
        passed = True
        reason = f"entry_quality={eq} allowed for Mean Reversion sleeve (EXTENDED-down IS the trigger) (bypass)"
    elif _is_pead_eq and _eq_bad and _pead_extended_gate_on() and eq in ("MISSED", "EXTENDED"):
        # PEAD-EXTENDED-GATE (2026-05-31, pick_forensics): PEAD/Impulse Catalyst alpha is the
        # INITIAL gap (Bernard-Thomas drift decays fast). Chasing it EXTENDED/MISSED bled —
        # recent n=20 = 25% WR, -2.6% avg. So a PEAD that is already EXTENDED/MISSED does NOT
        # bypass; it falls to WATCH. A FRESH PEAD gap (the real edge) still passes (eq not bad).
        passed = False
        reason = f"entry_quality={eq} — PEAD already extended, gap edge spent (pead_extended_entry_gate)"
    elif _is_pead_eq and _eq_bad:
        passed = True
        reason = f"entry_quality={eq} allowed for PEAD sleeve (gap-up entry IS the trigger) (bypass)"
    elif _is_insider_eq and _eq_bad:
        passed = True
        reason = f"entry_quality={eq} allowed for Insider Cluster sleeve (info edge) (bypass)"
    elif _is_esp_eq and _eq_bad:
        passed = True
        reason = f"entry_quality={eq} allowed for ESP Play sleeve (pre-earnings drift) (bypass)"
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
    # GATING-SYMMETRY FIX (2026-05-19): entry_quality gate has risk_on_choppy regime
    # relaxation (per regime_sharpe_decomp 2026-05-13: MISSED n=302 PF 2.59, EXTENDED
    # n=335 PF 1.33 in choppy) but decision_state gate was missing it. Both gates test
    # essentially the same condition (price above value re-entry zone). HPE 2026-05-19
    # would have BUY'd (score 85, 8/9 gates pass) except decision_state=MISSED blocked it
    # despite the regime evidence. Mirror the relaxation here using the same config key.
    ds = _normalize_decision_state(t.get("decision_state"))
    _is_pead_ds = (t.get("setup_family") == "PEAD")
    _is_insider_ds = (t.get("setup_family") == "Insider Cluster")
    _ds_relaxed_for_regime = (ds == "MISSED") and (_regime_lower in _eq_relax)
    passed = ds not in ("MISSED", "NO_EDGE")
    if _is_pead_ds and not passed:
        passed = True
        ds_reason = f"decision_state={ds} allowed for PEAD sleeve (gap-up IS the entry) (bypass)"
    elif _is_insider_ds and not passed:
        passed = True
        ds_reason = f"decision_state={ds} allowed for Insider Cluster sleeve (info edge) (bypass)"
    elif (t.get("setup_family") == "ESP Play") and not passed:
        passed = True
        ds_reason = f"decision_state={ds} allowed for ESP Play sleeve (catalyst) (bypass)"
    elif _ds_relaxed_for_regime:
        passed = True
        ds_reason = f"decision_state={ds} allowed in {_regime_lower} (mirrors entry_quality regime relax per 2026-05-13 evidence)"
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
    # (60-69 = tier 0/WATCH). Catalyst-driven sleeves accept moderate composite scores
    # because mechanism comes from outside the score (catalyst / regime flow / oversold).
    #
    # AUDIT BATCH 3 TIGHTENING (2026-05-15): loss-streak investigation showed 75% of
    # recent losing BUYs came from WATCH/AVOID conviction tiers — bypass was too loose.
    # Restrictions added:
    #   1. Never bypass tier=-1 (AVOID label = composite score < 60) — hard floor
    #   2. tier=0 (WATCH) bypass requires score >= 60 floor
    #   3. tail_filter_demoted (real star-rating demotion) NEVER bypassed
    conv = t.get("conviction") or {}
    tail_demoted = bool(conv.get("tail_filter_demoted"))
    tier_val = conv.get("tier")
    label_up = (conv.get("label") or "").upper()
    tier_zero = (tier_val == 0 and label_up in ("WATCH", "AVOID", "WAIT"))
    tier_avoid = (tier_val == -1) or (label_up == "AVOID")
    _sleeve_fam = t.get("setup_family")
    _catalyst_sleeve = _sleeve_fam in ("PEAD", "Momentum Continuation",
                                         "Defensive Rotation", "Mean Reversion",
                                         "Insider Cluster", "ESP Play")
    # Score floor for bypass (Audit Batch 3): require composite score >= 60
    _score_for_bypass = t.get("score") or 0
    _bypass_score_ok = _score_for_bypass >= 60

    if _catalyst_sleeve and tier_zero and _bypass_score_ok and not tail_demoted and not tier_avoid:
        demoted = False
        reason = f"conviction tier=0 bypassed for {_sleeve_fam} sleeve (catalyst + score>={_score_for_bypass:.0f}>=60)"
    elif _catalyst_sleeve and tier_avoid:
        # Explicitly block — AVOID is hard floor, no bypass
        demoted = True
        reason = f"conviction tier=AVOID NOT bypassed for {_sleeve_fam} (Audit Batch 3 hard floor — composite score < 60)"
    elif _catalyst_sleeve and tier_zero and not _bypass_score_ok:
        # Bypass intended but score floor failed
        demoted = True
        reason = f"conviction tier=0 bypass DENIED for {_sleeve_fam} — score {_score_for_bypass:.0f} < 60 floor"
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
        # 2026-05-23: static_setup_kill_list entries may omit avg_pnl (None).
        # Only include the avg_pnl tail when numeric, else use reason as-is.
        # Prior bug: f"avg_pnl {None:+.2f}" crashed entire decision engine.
        _avg = info.get("avg_pnl")
        _avg_tail = f", avg_pnl {_avg:+.2f}%" if isinstance(_avg, (int, float)) else ""
        killed_reason = f"{setup_name}: {info['reason']}{_avg_tail}"
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
        _is_esp_family = (t.get("setup_family") == "ESP Play")
        # Bypass conditions are gated by a score floor — pure cat_tier=1
        # without a composite floor would let noise tickers (score=3 with
        # a PEAD tag) slip through. Score 60 = WATCH-eligible composite floor.
        # MOMENTUM-SLEEVE BYPASS (2026-05-13): momentum-classified tickers
        # bypass fund_adequacy entirely — momentum doesn't depend on quality.
        # DEFENSIVE-ROTATION BYPASS (2026-05-14): defensive ETFs don't have
        # classical fundamentals; large-cap defensives are quality by definition.
        _bypass = (_is_mom_family or _is_def_family or _is_pead_family or _is_insider_family or _is_esp_family
                   or (_score >= 75) or (_cat_tier == 1 and _score >= 60))
        if ratio < DEFAULT_FUND_ADEQUACY and _bypass:
            passed = True
            _bypass_reason = ("Momentum Continuation sleeve" if _is_mom_family
                              else "Defensive Rotation sleeve" if _is_def_family
                              else "PEAD sleeve" if _is_pead_family
                              else "Insider Cluster sleeve" if _is_insider_family
                              else "ESP Play sleeve" if _is_esp_family
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


def derive_bias_action(verdict, reason: str = "", bear_type: str = "",
                       direction: str = "long", score: float = 0.0) -> dict:
    """Decompose an overloaded verdict into three ORTHOGONAL axes.

    The single verdict enum (BUY/WATCH/AVOID/SHORT) conflates DIRECTION and
    ACTION, so a strong uptrend that's merely too-extended-to-chase (AVOID by
    the entry-quality gate) was rendered "Bearish · short it". These axes keep
    direction and action independent so the UI can say "bullish, but wait":

      bias         : bullish / neutral / bearish   (directional read)
      action       : buy / wait / avoid / short    (what to do)
      reason_class : extended / gate_value / gate_liquidity / bear_setup /
                     kill / regime / system / clear / other   (why the action)

    Pure function — no I/O. Used by compute_final_verdict (wrapper below) AND
    analysis.compute_decisions_by_mode so per-ticker and per-mode agree.
    """
    v = (verdict or "").upper()
    r = (reason or "").lower()
    is_short = (direction or "").lower() == "short" or v in ("SHORT", "SELL") or bool(bear_type)

    # reason_class — WHY the action fired (priority order; first match wins)
    if is_short or "bear setup" in r:
        rc = "bear_setup"
    elif "circuit breaker" in r or "forced cash" in r or "blackout" in r:
        rc = "system"
    elif "regime gate" in r or "no new longs" in r:
        rc = "regime"
    elif ("extended" in r or "entry_quality" in r or "value zone" in r
          or "decision_state" in r or "missed" in r or "pullback" in r):
        rc = "extended"          # timing only — the long thesis is intact
    elif "kill" in r or "cooldown" in r or "sharpe" in r:
        rc = "kill"
    elif "fund" in r or "quality gate" in r or "margin" in r or "adequacy" in r:
        rc = "gate_value"
    elif "liquidity" in r or "drawdown" in r or "price" in r:
        rc = "gate_liquidity"
    elif v == "BUY":
        rc = "clear"
    else:
        rc = "other"

    # bias — directional read. A short/bear is bearish; otherwise the composite
    # score (0-100, 50 = midpoint) decides bullish vs neutral. An AVOID/WATCH
    # long is NOT bearish — that was the whole bug.
    if is_short:
        bias = "bearish"
    elif (score or 0) >= 50:
        bias = "bullish"
    else:
        bias = "neutral"

    # action — what to do. Wait-worthy reasons (extended/regime) keep the long
    # thesis but block the entry here; hard rejects are avoid.
    if is_short:
        action = "short"
    elif v == "BUY":
        action = "buy"
    elif rc in ("extended", "regime") or v == "WATCH":
        action = "wait"
    else:
        action = "avoid"

    return {"bias": bias, "action": action, "reason_class": rc}


def compute_final_verdict(t: dict, regime: str | None = None,
                          thresholds: dict | None = None,
                          setup_kill_list: dict | None = None,
                          system_status: dict | None = None,
                          setup_band_kill_list: dict | None = None,
                          config: dict | None = None) -> dict:
    """Wrapper: run the verdict cascade, then attach the orthogonal
    bias × action × reason_class axes (additive — `verdict` is unchanged for
    back-compat with filters / buckets / signal_log)."""
    res = _compute_final_verdict_impl(
        t, regime=regime, thresholds=thresholds, setup_kill_list=setup_kill_list,
        system_status=system_status, setup_band_kill_list=setup_band_kill_list, config=config)
    try:
        _t = t if isinstance(t, dict) else {}
        _bs = _t.get("bear_setup") if isinstance(_t.get("bear_setup"), dict) else {}
        ba = derive_bias_action(
            verdict=res.get("verdict"), reason=res.get("reason", ""),
            bear_type=(_bs or {}).get("bear_type", ""),
            direction=_t.get("direction", "long"),
            score=_t.get("score", 0) or 0)
        res["bias"], res["action"], res["reason_class"] = ba["bias"], ba["action"], ba["reason_class"]
    except Exception:
        res.setdefault("bias", "neutral"); res.setdefault("action", "wait"); res.setdefault("reason_class", "other")
    return res


def _compute_final_verdict_impl(t: dict, regime: str | None = None,
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

    # AUDIT BATCH 3 (2026-05-15): Same-ticker repeat-entry cooldown.
    # Loss-streak diagnostic: ALB had 3 stop-outs in 5 days (-12%, -10%, -10%),
    # CAVA 2 stops, DUK 2 stops, NEE 2 stops. After a stop-out, the same ticker
    # was re-bought immediately — chasing losses per CLAUDE.md principle 8
    # ("no chasing breakouts; either had a limit order placed or wait for retest").
    # Block re-entry for `cooldown_days` after most recent stop-out on same ticker.
    _ticker = t.get("ticker")
    _cooldown_cfg = (config or {}).get("scoring", {}).get("repeat_entry_cooldown") or {}
    # PORTFOLIO-DECOUPLE (2026-06-07): the cooldown reads the owner's signal_log
    # stop-outs — account-specific, must not gate the universal signal layer.
    # The master flag overrides the cooldown's own _enabled. See config _note.
    _portfolio_blind = bool((config or {}).get("signal_layer_portfolio_blind", {}).get("_enabled", False))
    _cooldown_enabled = bool(_cooldown_cfg.get("_enabled", True)) and not _portfolio_blind
    _cooldown_days = int(_cooldown_cfg.get("cooldown_days_after_stop", 5))
    if _cooldown_enabled and _ticker:
        try:
            import json as _json
            from pathlib import Path as _P
            from datetime import datetime as _dt, timedelta as _td
            _sl_path = _P(__file__).resolve().parent / "data" / "signal_log.json"
            if _sl_path.exists():
                _sl = _json.loads(_sl_path.read_text())
                _now = _dt.now()
                # Find most recent CLOSED stop-out on this ticker
                _recent_stops = [
                    s for s in _sl
                    if isinstance(s, dict)
                    and s.get("ticker") == _ticker
                    and s.get("exit_reason") == "stop_hit"
                    and s.get("status") == "CLOSED"
                    and s.get("date")
                ]
                if _recent_stops:
                    # Get latest by date
                    _latest = max(_recent_stops, key=lambda x: x.get("date", ""))
                    try:
                        _exit_date = _dt.fromisoformat(_latest["date"][:10])
                        _days_since = (_now - _exit_date).days
                        if _days_since < _cooldown_days:
                            return {
                                "verdict": "WATCH",
                                "reason": f"repeat-entry cooldown: {_ticker} stopped out {_days_since}d ago (need {_cooldown_days}d) — last loss {_latest.get('actual_pnl_pct', '?')}%",
                                "caveats": [
                                    f"CLAUDE.md principle 8: no chasing; wait for retest mechanism",
                                    f"Re-entry eligible after {(_exit_date + _td(days=_cooldown_days)).date().isoformat()}",
                                ],
                                "gates_evaluated": [{
                                    "name": "repeat_entry_cooldown",
                                    "passed": False,
                                    "reason": f"{_ticker} stop-out {_days_since}d ago, cooldown {_cooldown_days}d",
                                }],
                                "demote_to": "watch_list",
                            }
                    except Exception:
                        pass
        except Exception:
            pass  # never break verdict-pipeline due to cooldown check

    # A3 (2026-05-09): Regime gate. Per 750d backtest: strategy is bull-only;
    # losses concentrate in risk_off and panic regimes. Refuse new BUY entries
    # in those regimes — leaves existing positions to their exit rules but
    # stops adding to losing exposure. Vinod-style risk discipline.
    _regime_lower = (regime or "").lower()
    _is_defensive = (t.get("setup_family") == "Defensive Rotation")
    _is_pead = (t.get("setup_family") == "PEAD")
    _is_insider = (t.get("setup_family") == "Insider Cluster")
    _is_esp = (t.get("setup_family") == "ESP Play")
    if _regime_lower in ("panic", "risk_off_trending") and not (_is_defensive or _is_pead or _is_insider or _is_esp):
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
    # Modes:
    #   aggregate (default): one rolling Sharpe across ALL closed BUYs.
    #   per_sleeve:          rolling Sharpe per setup_family; demote only when
    #                        candidate's sleeve is below floor (principle 16 —
    #                        per-sub-strategy attribution).
    # Catalyst-sleeve bypass: when catalyst_sleeve_bypass=true, PEAD / Insider
    # Cluster / Defensive Rotation / Momentum Continuation / Mean Reversion /
    # ESP Play bypass the gate entirely — parity with existing bypasses in
    # _eval_hard_gates (mechanism per principle 14 — catalyst alpha is
    # independent of pullback-mechanic Sharpe).
    # MOMENTUM-CONDITION GATE (2026-05-18) — flag-gated. Demotes Trend Continuation +
    # Breakout Expansion BUYs to WATCH when QQQ-SPY 21d momentum spread is negative.
    # Mechanism: P2 factor attribution found TC mom_β +0.74, BE mom_β +0.78 — both
    # statistically significant momentum exposure with ZERO alpha. When momentum factor
    # drawdowns, these setups lose by construction. Audit: cache/factor_attribution_2026-05-18.json
    # rule_mode (MOMGATE-REDERIVE 2026-07-13) selects the demotion rule. DEFAULT
    # "current" => live behavior UNCHANGED. Other modes are PROPOSALS pending paper
    # validation (500-user signal-enable bar): OOS harness in
    # scratchpad/oos_momgate_candidates.py -> cache/oos_momgate_candidates_result.json.
    #   current            : demote spread < min_spread_pct (0.0)              [LIVE]
    #   regime_conditional : same, but gate OFF in risk_on_choppy
    #   toxic_zone         : demote ONLY spread < toxic_threshold_pct (-1.0)   [RECOMMENDED]
    #   disabled           : never demote (A/B parity with _enabled=false)
    _mom_gate_cfg = (config or {}).get("momentum_condition_gate") or {}
    if _mom_gate_cfg.get("_enabled", False):
        _affected = set(_mom_gate_cfg.get("affected_setups", ["Trend Continuation", "Breakout Expansion"]))
        _t_setup = t.get("setup_family") or ""
        if _t_setup in _affected:
            _mom_spread = t.get("_runtime_qqq_spy_momentum_21d")  # injected by build_data
            _rule_mode = str(_mom_gate_cfg.get("rule_mode") or "current").lower()
            _min_spread = _mom_gate_cfg.get("min_spread_pct", 0.0)
            _toxic_thr = _mom_gate_cfg.get("toxic_threshold_pct", -1.0)
            # Resolve the effective demotion threshold + whether the gate applies.
            _gate_applies = True
            _thr = _min_spread
            _reason_zone = f"< {_min_spread:+.2f}%"
            if _rule_mode == "disabled":
                _gate_applies = False
            elif _rule_mode == "regime_conditional":
                # Gate off in choppy (OOS: choppy >0-zone PF 2.63 is best; disabling hurts)
                if str(regime or "") == "risk_on_choppy":
                    _gate_applies = False
            elif _rule_mode == "toxic_zone":
                # Demote only the genuinely-toxic deep-negative zone (OOS PF ~1.02);
                # leave [-1%,0) admitted (restores OOS-best [-1,-0.5%) zone PF 1.56).
                _thr = _toxic_thr
                _reason_zone = f"< {_toxic_thr:+.2f}% (toxic zone)"
            if (_gate_applies and _mom_spread is not None
                    and _mom_spread < _thr):
                return {
                    "verdict": "WATCH",
                    "reason": f"momentum_condition_gate[{_rule_mode}]: {_t_setup} demoted — QQQ-SPY 21d spread {_mom_spread:+.2f}% {_reason_zone}",
                    "caveats": [f"setup is pure-momentum factor play (P2 evidence); paused during momentum drawdown"],
                    "gates_evaluated": [{
                        "name": "momentum_condition_gate",
                        "passed": False,
                        "reason": f"QQQ-SPY 21d spread {_mom_spread:+.2f}% {_reason_zone}",
                        "severity": "medium",
                        "stats": {"setup": _t_setup, "mom_spread_pct": _mom_spread,
                                  "rule_mode": _rule_mode, "threshold_pct": _thr},
                    }],
                    "demote_to": "watch_list",
                }

    _rs_state = compute_rolling_sharpe_kill_state(config) if config else {"active": False}
    _rs_cfg = (config or {}).get("rolling_sharpe_kill") or {}
    _rs_mode = str(_rs_cfg.get("mode") or "aggregate").lower()
    _rs_catalyst_bypass = bool(_rs_cfg.get("catalyst_sleeve_bypass", False))
    _CATALYST_SLEEVES = {"PEAD", "Insider Cluster", "Defensive Rotation",
                         "Momentum Continuation", "Mean Reversion", "ESP Play"}
    _t_sleeve = t.get("setup_family") or ""
    _is_catalyst_sleeve = _t_sleeve in _CATALYST_SLEEVES

    # Determine if THIS candidate is killed.
    _kill_fired = False
    _kill_reason = _rs_state.get("reason", "")
    if _rs_state.get("active") or (_rs_mode == "per_sleeve" and _rs_state.get("sleeve_states")):
        if _rs_catalyst_bypass and _is_catalyst_sleeve:
            # Bypass — record on gate audit but don't demote.
            _kill_fired = False
            _kill_reason = (f"rolling-Sharpe kill bypassed for {_t_sleeve} sleeve "
                            f"(catalyst alpha independent of pullback-mechanic Sharpe)")
        elif _rs_mode == "per_sleeve":
            # Per-sleeve: kill only when THIS candidate's sleeve is below floor.
            _sleeve_state = (_rs_state.get("sleeve_states") or {}).get(_t_sleeve)
            if _sleeve_state and _sleeve_state.get("active"):
                _kill_fired = True
                _kill_reason = (f"rolling-Sharpe kill (per-sleeve, {_t_sleeve}): "
                                f"{_sleeve_state.get('reason')}")
        else:
            # Aggregate mode — original behavior.
            if _rs_state.get("active"):
                _kill_fired = True
                _kill_reason = f"rolling-Sharpe kill: {_rs_state.get('reason')}"

    if _kill_fired:
        _stats_for_audit = _rs_state
        if _rs_mode == "per_sleeve":
            _stats_for_audit = {**_rs_state,
                                "applied_sleeve": _t_sleeve,
                                "applied_sleeve_state": (_rs_state.get("sleeve_states") or {}).get(_t_sleeve)}
        return {
            "verdict": "WATCH",
            "reason": _kill_reason,
            "caveats": [
                f"recent {_rs_state.get('n')} BUYs Sharpe {_rs_state.get('sharpe'):+.3f} "
                f"(threshold {_rs_state.get('threshold'):+.2f}) mode={_rs_mode}"
                if _rs_state.get("sharpe") is not None else
                f"mode={_rs_mode}"
            ],
            "gates_evaluated": [{
                "name": "rolling_sharpe_kill",
                "passed": False,
                "reason": _kill_reason,
                "severity": "high",
                "stats": _stats_for_audit,
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
    # Build sector blocklist from config for gate injection
    _sb_cfg = (config or {}).get("sector_blocklist") or {}
    _sector_blocked_list = _sb_cfg.get("blocked") or []
    _sector_bypass_set = set(_sb_cfg.get("bypass_sleeves") or [])

    gates, failures = _eval_hard_gates(
        t, regime=regime,
        entry_quality_relax_regimes=_eq_relax,
        sector_blocklist=_sector_blocked_list,
        sector_bypass_sleeves=_sector_bypass_set,
    )
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

    # BUY-FLOOR-72-2026-06-14: optional absolute composite quality floor (default
    # OFF). When enabled, a name scoring below `floor` is demoted BUY->WATCH
    # regardless of the regime threshold OR the ranker — the sub-70 composite band
    # loses money (audit_signal_to_ledger). Composite-only: catalyst sleeves bypass
    # this code path via _eval_hard_gates and never reach here. Scoring untouched;
    # byte-identical when _enabled=false (floor=0 → the `>= _score_floor` is a no-op).
    _bsf = (config or {}).get("buy_score_floor", {}) or {}
    # `regimes` is an allowlist (empty/missing => all). Choppy/risk-off only by
    # default — trending is excluded because the sub-70 evidence is choppy-window.
    # `fallback_only`: apply ONLY when the ranker is OFF — the ranker separates the
    # 65-72 band finer than a blunt floor (keep PF 1.03 / demote 0.57), so it owns
    # the call while ON; the floor stays armed as a legacy safety net.
    _bsf_regs = _bsf.get("regimes")
    _ranker_on = bool(((config or {}).get("regime_conditional_ranker") or {}).get("_enabled"))
    _bsf_on = (
        bool(_bsf.get("_enabled"))
        and (not _bsf_regs or (regime or "").lower() in [str(x).lower() for x in _bsf_regs])
        and (not _bsf.get("fallback_only") or not _ranker_on)
    )
    _score_floor = int(_bsf.get("floor", 0)) if _bsf_on else 0

    # RANK-REBUILD-2026-06-13: regime-conditional ranker. When enabled, the
    # composite `score` is DEMOTED from ranker to a >=gate_floor quality GATE,
    # and promotion is decided by rank_score (built from pre-bonus pillar norms,
    # IC-positive + monotone where composite is anti-correlated). DEFAULT OFF →
    # legacy `score >= threshold` path is byte-identical when _enabled=false.
    _rcr = (config or {}).get("regime_conditional_ranker", {}) or {}
    _promote = (score >= threshold) and (score >= _score_floor)
    _rank_thr = None  # exposed to reason strings below
    if _rcr.get("_enabled"):
        _gate_floor = _rcr.get("gate_floor", 60)
        _sb = t.get("scoring_breakdown") or {}
        _rank = _sb.get("rank_score")
        if _rank is None:
            _rank = t.get("rank_score", score)  # fail-safe to composite
        # rank_buy_threshold: scalar OR {trending,choppy,risk_off} keyed by rank_regime_family
        _rbt = _rcr.get("rank_buy_threshold", 50)
        if isinstance(_rbt, dict):
            _fam = _sb.get("rank_regime_family", "choppy")
            _rank_thr = _rbt.get(_fam, _rbt.get("choppy", 50))
        else:
            _rank_thr = _rbt
        _promote = (score >= _gate_floor) and (float(_rank) >= float(_rank_thr)) and (score >= _score_floor)

    if _promote:
        # CHOPPY-BREAKOUT-DEMOTE-2026-06-16: Breakout-Expansion BUYs lose in
        # NON-TRENDING tape — breakouts need trend follow-through and revert in
        # range/correction. Validated on owner track record 2026-05-18..06-16
        # (all risk_on_choppy): breakout BUYs = 46% of book, hit 38%, PF 0.49;
        # demoting them to WATCH lifts the realized book -0.26%/PF0.91 ->
        # +1.05%/PF1.51 (picks_history managed outcomes). Triangulated across the
        # picks_history robustness battery + 06-11 BUY<WATCH audit + 06-08 history
        # audit + the CSV D5 join. REGIME-LOCKED (config.regimes) so trending
        # breakouts are UNTOUCHED; demote-to-WATCH (not kill) preserves agency.
        # Reversible: config["choppy_breakout_demote"]["_enabled"] = false.
        _cbd = (config or {}).get("choppy_breakout_demote", {}) or {}
        if _cbd.get("_enabled"):
            _cbd_regs = [str(x).lower() for x in (_cbd.get("regimes") or ["risk_on_choppy"])]
            _cbd_fams = _cbd.get("families") or ["Breakout"]
            _sf_name = str(t.get("setup_family") or "")
            if (regime or "").lower() in _cbd_regs and any(_fam in _sf_name for _fam in _cbd_fams):
                return {
                    "verdict": "WATCH",
                    "reason": (f"choppy_breakout_demote: '{_sf_name}' demoted to WATCH in "
                               f"{regime or 'non-trending'} — breakouts revert in non-trending "
                               f"tape (validated PF 0.49 / 38% hit on owner track record)"),
                    "caveats": caveats + [f"choppy_breakout_demote:{_sf_name}@{regime}"],
                    "gates_evaluated": gates + [{
                        "name": "choppy_breakout_demote",
                        "passed": False,
                        "reason": f"{_sf_name} in {regime}",
                    }],
                    "demote_to": "watch_list",
                }

        # TC CATALYST-CONFLUENCE GATE (2026-07-13, edge-erosion diagnostic).
        # Trend Continuation was 62% of all BUY volume in Jun–Jul (n=1,393)
        # at −0.68%/wk in choppy tape, and the 2026-05-19 factor attribution
        # showed TC carries ZERO alpha (pure momentum beta +0.74). Pure-
        # technical TC (catalyst_tier 3 = analyst headlines / social / none)
        # is exactly principle 14's "pure technicals without catalyst" case.
        # Require catalyst_tier <= 2 for a TC BUY in the configured regimes;
        # otherwise demote to WATCH (not kill — preserves agency + trending
        # regimes untouched by default). Reversible:
        # config["tc_catalyst_confluence_gate"]["_enabled"] = false.
        _tcg = (config or {}).get("tc_catalyst_confluence_gate", {}) or {}
        if _tcg.get("_enabled"):
            _tcg_regs = [str(x).lower() for x in (_tcg.get("regimes") or ["risk_on_choppy", "neutral"])]
            _tcg_max_tier = int(_tcg.get("max_catalyst_tier", 2))
            _sf_name2 = str(t.get("setup_family") or "")
            _cat_tier2 = t.get("catalyst_tier")
            _cat_ok = isinstance(_cat_tier2, (int, float)) and _cat_tier2 <= _tcg_max_tier
            if ((regime or "").lower() in _tcg_regs
                    and "Trend Continuation" in _sf_name2 and not _cat_ok):
                return {
                    "verdict": "WATCH",
                    "reason": (f"tc_catalyst_confluence: Trend Continuation without a "
                               f"tier-{_tcg_max_tier} catalyst (tier={_cat_tier2}) demoted to WATCH "
                               f"in {regime or 'choppy'} — pure-technical TC has zero alpha "
                               f"(factor attribution 2026-05-19; live Jun-Jul n=1393 −0.68%/wk)"),
                    "caveats": caveats + [f"tc_catalyst_confluence:tier{_cat_tier2}@{regime}"],
                    "gates_evaluated": gates + [{
                        "name": "tc_catalyst_confluence",
                        "passed": False,
                        "reason": f"Trend Continuation catalyst_tier={_cat_tier2} > {_tcg_max_tier} in {regime}",
                    }],
                    "demote_to": "watch_list",
                }

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

        if _rcr.get("_enabled"):
            _sb2 = t.get("scoring_breakdown") or {}
            _rk = _sb2.get("rank_score", t.get("rank_score"))
            _buy_reason = (f"all gates passed; rank_score {_rk} >= {_rank_thr} "
                           f"[{_sb2.get('rank_regime_family','?')}] AND score {score} >= gate "
                           f"{_rcr.get('gate_floor', 60)} ({regime or 'default'})")
        else:
            _buy_reason = f"all gates passed; score {score} >= {threshold} ({regime or 'default'})"
        return {
            "verdict": "BUY",
            "reason": _buy_reason,
            "caveats": caveats,
            "gates_evaluated": gates,
            "demote_to": None,
            "signal_filter": _filter_audit,
        }

    if _score_floor and score < _score_floor:
        # BUY-FLOOR-72: the absolute composite floor is the binding demotion reason
        # (it vetoes regardless of regime threshold or ranker). Surface it explicitly.
        _watch_reason = f"all gates passed but score {score} < BUY score floor {_score_floor} (buy_score_floor)"
    elif _rcr.get("_enabled"):
        _sb3 = t.get("scoring_breakdown") or {}
        _rk = _sb3.get("rank_score", t.get("rank_score"))
        if (score or 0) < _rcr.get("gate_floor", 60):
            _watch_reason = f"all gates passed but score {score} < quality gate {_rcr.get('gate_floor', 60)}"
        else:
            _watch_reason = (f"all gates passed but rank_score {_rk} < rank BUY threshold "
                             f"{_rank_thr} [{_sb3.get('rank_regime_family','?')}]")
    else:
        _watch_reason = f"all gates passed but score {score} < BUY threshold {threshold}"
    return {
        "verdict": "WATCH",
        "reason": _watch_reason,
        "caveats": caveats,
        "gates_evaluated": gates,
        "demote_to": None,
    }
