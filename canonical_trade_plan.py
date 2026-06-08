"""
canonical_trade_plan.py — single source-of-truth trade plan object (K6).

Vinod feedback (2026-05-09): "SMC trade plan is different to tool generated
plan in Overview tab", "Bear case & Severe Case doesn't align with overall
Plan and Thesis", "Trade plan entry, Stop, T1 and T2 has to align with rest
of the numbers in the outlook".

Root cause (per 2026-05-06 audit): "system had 7 independent decision engines
writing to the same ticker JSON with no aggregation. The dashboard's verdict
was whichever engine wrote last." compute_final_verdict fixed the verdict
cascade, but PER-TAB DISPLAY still pulled from inconsistent intermediate
fields.

The fix: ONE canonical dataclass. Every tab binds to fields of this object.
No tab does its own entry/stop/target/sizing computation.

This module is the schema definition + the assembler. The assembler reads
from existing analysis output (analyze_ticker → trade_plan, indicators,
gates, conviction, monte_carlo) and produces a single CanonicalTradePlan.

PROFESSIONAL HEDGE FUND DESIGN PRINCIPLES applied:
  1. Statistical context attached (Wilson CI, n_historical) per setup —
     trader sees "67% WR over 47 historical trades, LB 52%" not just "BUY"
  2. Regime conditioning surfaced (this strategy's WR IN THIS regime, not generic)
  3. Setup attribution by scoring pillar (which factor drove the BUY)
  4. Risk-first ordering — max_loss_pct, drawdown_haircut surface before targets
  5. Mechanism hypothesis (why this setup works) for each setup family
  6. Audit trail (which gates passed/failed, signal_filter decision)
  7. Capacity awareness — beta-adjusted sizing, position_size_pct
  8. Schema versioning so future fields don't break old saved plans
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

# Schema version — bump when adding fields that aren't backward-compatible
SCHEMA_VERSION = 1


@dataclass
class TradeZone:
    """Entry zone — a range, not a single price."""
    low: float | None = None
    mid: float | None = None
    high: float | None = None


@dataclass
class StatisticalContext:
    """Historical performance of this exact setup × regime combination.

    Sourced from data/signal_log.json filtered to matching setup+regime.
    Wilson CI is the LOWER bound — what we can defend at 95% confidence.
    """
    n_historical: int = 0                          # closed signals matching setup+regime
    wr_point: float | None = None                  # win rate (0-1)
    wr_lower_bound: float | None = None            # Wilson 95% LB (0-1)
    wr_upper_bound: float | None = None
    avg_pnl_pct: float | None = None               # avg P&L per trade (%)
    profit_factor: float | None = None
    expectancy_R: float | None = None              # expectancy in R-multiples
    reliability: str = "untrustworthy"              # high / medium / low / untrustworthy


@dataclass
class RegimeContext:
    """Regime the system is in + how this strategy performs in this regime."""
    regime_name: str | None = None                  # risk_on_trending / risk_on_choppy / risk_off_trending / panic
    regime_confidence: float | None = None          # HMM probability 0-1
    setup_wr_in_regime: float | None = None         # this setup's historical WR in this regime
    setup_n_in_regime: int = 0
    max_size_pct: float = 100.0                     # multiplier on Kelly size for this regime
    short_allowed: bool = False


@dataclass
class CatalystContext:
    """Catalysts present at entry time — supporting WHY signal exists now."""
    days_to_earnings: int | None = None
    has_pead: bool = False                          # post-earnings announcement drift
    has_uoa_calls: bool = False                     # unusual options activity (calls)
    has_uoa_puts: bool = False
    insider_cluster_30d: int = 0                    # # insider buys last 30d
    insider_score: float | None = None
    news_sentiment_7d: float | None = None
    analyst_upgrade_14d: bool = False
    catalyst_density: int = 0                       # tier1_signals.count
    catalyst_tier: int | None = None                # 1=premier, 2=mid, 3=marginal


@dataclass
class RiskMetrics:
    """Risk dimension — surfaces BEFORE targets in the canonical view."""
    max_loss_pct: float | None = None               # entry-to-stop %
    max_loss_dollars: float | None = None
    rr_ratio: float | None = None                   # risk:reward
    beta_adjusted_size_pct: float | None = None     # 1/beta multiplier
    drawdown_haircut: float = 1.0                   # 1.0=no haircut, 0.5=50% reduction
    correlation_adj_pct: float | None = None        # adjustment for portfolio correlation
    risk_flags: list[dict] = field(default_factory=list)  # K2 VWAP-below-stop etc.

    # ── SMC-aware stop layer (added 2026-05-26) ──
    # Real-world bug (CORZ): canonical stop landed INSIDE the Bull Order Block
    # zone that the same scan identified as structural support. A normal
    # liquidity sweep of the OB hits the stop before price reverses. The
    # thesis is right; the stop placement defeats it. These fields surface
    # the trap and propose an alternative.
    stop_smc_suggested: float | None = None         # 1% below the nearest active Bull OB low
    stop_smc_source: str | None = None              # human-readable rationale
    stop_smc_distance_pct: float | None = None      # |stop_smc - entry_mid| / entry_mid * 100
    stop_smc_rr: float | None = None                # R:R if SMC stop is used vs target1
    stop_inside_ob: bool = False                    # TRUE if legacy stop sits INSIDE an active Bull OB → trap
    stop_inside_ob_zone: str | None = None          # e.g. "$20.81-$23.00 Bull OB"
    # 2026-05-26 SHIP 1 — trap severity. Confluence-weighted; 158 traps was too noisy.
    # Routes UI rendering: HIGH = full red banner, MED = amber chrome, LOW = collapsed.
    stop_inside_ob_severity: str | None = None      # "LOW" | "MED" | "HIGH" | None
    stop_inside_ob_score: int | None = None         # 0-9, the underlying weighted score
    # 2026-05-26 SHIP 2 — sleeve suppression. Catalyst sleeves (PEAD/ESP/Insider)
    # are catalyst-dominated; structural OB sweep mechanics rarely play out.
    stop_inside_ob_suppressed: bool = False         # True when warning is suppressed
    stop_inside_ob_suppress_reason: str | None = None  # e.g. "catalyst sleeve: PEAD"
    # 2026-05-26 SHIP 4 — stop-depth-in-OB (the sweep mechanic itself).
    # depth_pct = (ob_high - legacy_stop) / (ob_high - ob_low) * 100
    #   0% = at top edge of OB; 100% = at bottom edge.
    # MIDDLE (25-75%) is the deepest sweep risk — that's where institutional
    # limit orders cluster and where stop-hunt sweeps target.
    stop_depth_in_ob_pct: float | None = None       # 0-100 (or None if no trap)
    stop_depth_zone: str | None = None              # TOP / UPPER / MIDDLE / LOWER / BOTTOM


@dataclass
class GateResults:
    """Audit trail — every gate evaluated and its outcome."""
    passed: list[str] = field(default_factory=list)
    failed: list[dict] = field(default_factory=list)  # [{name, reason, severity}]
    soft_caveats: list[str] = field(default_factory=list)
    signal_filter: dict | None = None               # A2 filter decision dict


@dataclass
class SetupAttribution:
    """Which scoring pillars drove the verdict — explainable AI for trades."""
    setup_type: str | None = None                   # Pocket Pivot / VCP Breakout / etc.
    setup_family: str | None = None                 # Impulse Catalyst / Breakout Expansion / etc.
    mechanism_hypothesis: str | None = None         # WHY this setup has edge (1 sentence)
    pillar_scores: dict = field(default_factory=dict)  # {technicals: 28, catalyst: 14, ...}
    score_normalized: int | None = None             # 0-100
    elliott_wave: dict | None = None                # K5 EW classification (if applicable)


@dataclass
class CanonicalTradePlan:
    """Single source-of-truth trade plan. Every dashboard tab reads from this.

    Attribute access: plan.entry.mid, plan.risk.rr_ratio, plan.stats.wr_lower_bound.
    Dict access for legacy callers: plan.to_dict()["entry"]["mid"].
    """
    schema_version: int = SCHEMA_VERSION
    ticker: str = ""
    direction: str = "long"
    verdict: str = "WATCH"                          # BUY / WATCH / AVOID
    conviction_tier: str | None = None              # T1 / T2 / T3 / WATCH

    entry: TradeZone = field(default_factory=TradeZone)
    stop: float | None = None
    target1: float | None = None
    target2: float | None = None
    target3: float | None = None   # bull-stretch (structural engine, Phase 2 cutover)
    hold_period_days: int | None = None
    position_size_pct: float | None = None
    shares: int | None = None

    risk: RiskMetrics = field(default_factory=RiskMetrics)
    stats: StatisticalContext = field(default_factory=StatisticalContext)
    regime: RegimeContext = field(default_factory=RegimeContext)
    catalysts: CatalystContext = field(default_factory=CatalystContext)
    setup: SetupAttribution = field(default_factory=SetupAttribution)
    gates: GateResults = field(default_factory=GateResults)

    # Provenance
    decided_at: str | None = None                   # ISO timestamp
    config_snapshot_hash: str | None = None         # sha1 of config at decision time
    git_commit: str | None = None

    def to_dict(self) -> dict:
        """Legacy-compatible dict export. Tabs that haven't been refactored
        can still read this format."""
        return asdict(self)


# ─────────────────────────────────────────────────────────────────────────
# Mechanism hypotheses — why each setup family has an edge.
# Used for the "WHY this setup" line in the canonical plan view.
# Per professional research-note convention: every signal must have a thesis.
# ─────────────────────────────────────────────────────────────────────────
MECHANISM_HYPOTHESES = {
    "Impulse Catalyst": (
        "Post-earnings announcement drift (PEAD) and unusual options activity "
        "front-run analyst revisions; institutional buy programs spread over 5-8 days."
    ),
    "Breakout Expansion": (
        "Volume contraction (VCP) preceding a breakout reflects supply absorption; "
        "the breakout above resistance triggers stop-runs and momentum-fund buying."
    ),
    "Trend Continuation": (
        "Pullbacks to EMA21/50 in established uptrends are buy points where "
        "institutional buyers re-add. Rally resumes within 1-3 days when buying "
        "absorbs the pullback."
    ),
    "Special Situation": (
        "Insider cluster buys, short squeezes, and float rotations are non-technical "
        "catalysts that reprice the stock outside its normal volatility regime."
    ),
}


def _wilson_ci(wins: int, n: int, conf: float = 0.95) -> tuple[float, float]:
    """Wilson score interval for win rate. Returns (lo, hi) as decimals."""
    import math
    if n == 0:
        return (0.0, 1.0)
    z = 1.96 if conf == 0.95 else 2.576
    phat = wins / n
    denom = 1 + z * z / n
    center = (phat + z * z / (2 * n)) / denom
    spread = z * math.sqrt((phat * (1 - phat) + z * z / (4 * n)) / n) / denom
    return (max(0.0, center - spread), min(1.0, center + spread))


def _reliability(n: int, ci_width: float) -> str:
    if n >= 100 and ci_width < 0.12:
        return "high"
    if n >= 50 and ci_width < 0.20:
        return "medium"
    if n >= 30:
        return "low"
    return "untrustworthy"


def _historical_setup_stats(setup_type: str | None, regime: str | None) -> tuple[StatisticalContext, RegimeContext]:
    """Pull historical performance for this setup × regime from signal_log."""
    stats = StatisticalContext()
    regime_ctx = RegimeContext(regime_name=regime)
    if not setup_type:
        return stats, regime_ctx
    try:
        # Lazy import to avoid circulars
        try:
            from state_layer import load_signal_log
            entries = load_signal_log()
        except Exception:
            import json as _json
            from pathlib import Path as _P
            p = _P(__file__).parent / "data" / "signal_log.json"
            entries = _json.loads(p.read_text()) if p.exists() else []

        # Setup-only stats (regardless of regime)
        setup_pnls = []
        regime_pnls = []
        for s in (entries or []):
            if s.get("status") != "CLOSED":
                continue
            if s.get("strategy") != setup_type:
                continue
            pnl = s.get("actual_pnl_pct")
            if pnl is None:
                continue
            setup_pnls.append(float(pnl))
            s_regime = (s.get("raw_json") or {}).get("regime") or s.get("regime")
            if regime and s_regime == regime:
                regime_pnls.append(float(pnl))

        if setup_pnls:
            n = len(setup_pnls)
            wins = sum(1 for p in setup_pnls if p > 0)
            wr = wins / n
            lo, hi = _wilson_ci(wins, n)
            avg_pnl = sum(setup_pnls) / n
            pos = [p for p in setup_pnls if p > 0]
            neg = [p for p in setup_pnls if p < 0]
            pf = (sum(pos) / abs(sum(neg))) if neg else (float("inf") if pos else 0)
            # R-multiple expectancy assumes avg_loss = -1R, avg_win in R
            # Approximated: expectancy = wr * avg_win - (1-wr) * avg_loss
            avg_win = sum(pos) / len(pos) if pos else 0
            avg_loss = abs(sum(neg) / len(neg)) if neg else 1
            expectancy_R = (wr * (avg_win / max(avg_loss, 0.01))) - ((1 - wr) * 1.0)
            stats = StatisticalContext(
                n_historical=n,
                wr_point=round(wr, 3),
                wr_lower_bound=round(lo, 3),
                wr_upper_bound=round(hi, 3),
                avg_pnl_pct=round(avg_pnl, 2),
                profit_factor=round(pf, 2) if pf != float("inf") else 999.0,
                expectancy_R=round(expectancy_R, 2),
                reliability=_reliability(n, hi - lo),
            )

        if regime_pnls:
            n_r = len(regime_pnls)
            wins_r = sum(1 for p in regime_pnls if p > 0)
            regime_ctx.setup_wr_in_regime = round(wins_r / n_r, 3)
            regime_ctx.setup_n_in_regime = n_r
    except Exception:
        pass

    return stats, regime_ctx


def compute_smc_stop_fields(
    order_blocks: list[dict] | None,
    direction: str,
    entry_mid: float | None,
    legacy_stop: float | None,
    target1: float | None,
    spot: float | None = None,
    fractal_low: float | None = None,
    sleeve: str | None = None,
) -> dict:
    """Compute SMC-aware stop suggestion + trap detector.

    Real-world bug detector: when the canonical stop sits INSIDE an active
    Bull Order Block, a normal liquidity sweep of the OB will trigger the
    stop before price reverses (CORZ 2026-05-26 — stop $21.65 vs Bull OB
    $20.81-$23.00).

    Returns a dict with:
      stop_smc_suggested        — proposed stop (1% below nearest Bull OB low)
      stop_smc_source           — human-readable rationale
      stop_smc_distance_pct     — abs(suggested - entry_mid) / entry_mid * 100
      stop_smc_rr               — R:R using SMC stop vs target1
      stop_inside_ob            — TRUE if legacy stop sits INSIDE an active Bull OB
      stop_inside_ob_zone       — e.g. "$20.81-$23.00 Bull OB"

    Direction support: "long" (BUY) and "short" (SHORT). SHORT mirrors BUY —
    looks for Bear Order Blocks ABOVE spot, places stop 1% above the relevant
    Bear OB high, and detects "stop inside Bear OB" as a buy-side liquidity
    sweep trap (F6 — 2026-05-26).

    Active = status in {'fresh', 'tested-held', 'mitigated'} — institutions
    consider mitigated OBs (status='mitigated') as STILL TRADEABLE so long as
    structure hasn't been broken. The OB has been "tagged" once; the second
    sweep is where the supply trades.

    NB: SwingTrade ships two OB sources:
      - `t.smc.order_blocks`     — current production source; type/high/low
      - `t.smc_data.order_blocks` — newer schema; kind/high/low/status
    We accept BOTH shapes.
    """
    out = {
        "stop_smc_suggested": None,
        "stop_smc_source": None,
        "stop_smc_distance_pct": None,
        "stop_smc_rr": None,
        "stop_inside_ob": False,
        "stop_inside_ob_zone": None,
        "stop_inside_ob_severity": None,
        "stop_inside_ob_score": None,
        "stop_inside_ob_suppressed": False,
        "stop_inside_ob_suppress_reason": None,
        "stop_depth_in_ob_pct": None,
        "stop_depth_zone": None,
    }

    direction_norm = (direction or "long").lower()
    if not order_blocks or direction_norm not in ("long", "short"):
        return out
    is_short = direction_norm == "short"

    ref_price = float(spot or entry_mid or 0)
    if ref_price <= 0:
        return out

    # ── normalize OB schema across both data sources ──
    # For LONG: collect Bull OBs BELOW spot (structural support).
    # For SHORT: collect Bear OBs ABOVE spot (structural resistance).
    INVALID_STATUS = {"broken", "invalidated", "violated"}
    direction_token = "bear" if is_short else "bull"
    ob_label = "Bear" if is_short else "Bull"
    # 2026-05-26 SHIP 1 — retain richer per-OB dict so we can compute severity.
    relevant_obs: list[tuple[float, float]] = []   # (low, high)
    relevant_obs_rich: list[dict] = []             # original OB dicts (status, confluence, strength, …)
    for ob in order_blocks:
        if not isinstance(ob, dict):
            continue
        kind_raw = (ob.get("type") or ob.get("kind") or "").lower()
        if direction_token not in kind_raw:
            continue
        status_raw = (ob.get("status") or "").lower()
        if status_raw in INVALID_STATUS:
            continue
        lo = ob.get("low")
        hi = ob.get("high")
        if lo is None or hi is None:
            continue
        try:
            lo_f = float(lo)
            hi_f = float(hi)
        except (TypeError, ValueError):
            continue
        # LONG: Bull OB whose low sits BELOW ref (support beneath spot).
        # SHORT: Bear OB whose high sits ABOVE ref (resistance above spot).
        if is_short:
            if hi_f > ref_price:
                relevant_obs.append((lo_f, hi_f))
                relevant_obs_rich.append(ob)
        else:
            if lo_f < ref_price:
                relevant_obs.append((lo_f, hi_f))
                relevant_obs_rich.append(ob)

    if not relevant_obs:
        # Fallback: 2% above/below fractal level if we have it (still structural)
        if fractal_low and float(fractal_low) > 0:
            fl = float(fractal_low)
            if is_short:
                # SHORT fallback: place 2% above fractal_low (which acts as a
                # proxy resistance handle when no Bear OB exists). Caller passes
                # whatever fractal anchor is most relevant — for SHORT this is
                # typically a recent swing-high or fractal-high.
                out["stop_smc_suggested"] = round(fl * 1.02, 2)
                out["stop_smc_source"] = f"2% above fractal ${fl:.2f} (no Bear OB found)"
            else:
                out["stop_smc_suggested"] = round(fl * 0.98, 2)
                out["stop_smc_source"] = f"2% below fractal_low ${fl:.2f} (no Bull OB found)"
            if entry_mid:
                out["stop_smc_distance_pct"] = round(abs(out["stop_smc_suggested"] - entry_mid) / entry_mid * 100, 2)
            if entry_mid and target1:
                if is_short:
                    risk = out["stop_smc_suggested"] - entry_mid
                    reward = entry_mid - target1
                else:
                    risk = entry_mid - out["stop_smc_suggested"]
                    reward = target1 - entry_mid
                if risk > 0 and reward > 0:
                    out["stop_smc_rr"] = round(reward / risk, 2)
        return out

    # ── 1. SMC stop placement ──
    # LONG: Place stop 1% BELOW deepest trap OB (or nearest OB) so liquidity
    #       sweep can complete without exiting position.
    # SHORT: Mirror — place stop 1% ABOVE highest trap OB (or nearest Bear OB)
    #        so the buy-side liquidity sweep above spot can complete.
    #
    # We DON'T sweep clear of EVERY historical OB (some tickers emit dozens
    # going back months — pulls stop absurdly far). Either:
    #
    #   A. If legacy stop is INSIDE one or more OBs → that's the trap.
    #   B. Otherwise → use NEAREST OB to spot as routine structural reference.
    if is_short:
        # SHORT: sort ascending — nearest resistance is LOWEST-high Bear OB above spot
        relevant_obs.sort(key=lambda x: x[1])
        nearest_low, nearest_high = relevant_obs[0]
    else:
        # LONG: sort descending — nearest support is HIGHEST-low Bull OB below spot
        relevant_obs.sort(key=lambda x: x[0], reverse=True)
        nearest_low, nearest_high = relevant_obs[0]

    trap_obs: list[tuple[float, float]] = []
    if legacy_stop and float(legacy_stop) > 0:
        ls = float(legacy_stop)
        trap_obs = [(l, h) for (l, h) in relevant_obs if l <= ls <= h]

    if trap_obs:
        if is_short:
            # SHORT trap: clear the HIGHEST trap OB high
            trap_low = min(t[0] for t in trap_obs)
            trap_high = max(t[1] for t in trap_obs)
            smc_stop = round(trap_high * 1.01, 2)
            out["stop_smc_suggested"] = smc_stop
            out["stop_smc_source"] = (
                f"1% above {ob_label} OB trap zone ${trap_low:.2f}-${trap_high:.2f} "
                f"(legacy stop ${legacy_stop:.2f} sits INSIDE this OB)"
            )
        else:
            # LONG trap: clear the DEEPEST trap OB low
            trap_low = min(t[0] for t in trap_obs)
            trap_high = max(t[1] for t in trap_obs)
            smc_stop = round(trap_low * 0.99, 2)
            out["stop_smc_suggested"] = smc_stop
            out["stop_smc_source"] = (
                f"1% below {ob_label} OB trap zone ${trap_low:.2f}-${trap_high:.2f} "
                f"(legacy stop ${legacy_stop:.2f} sits INSIDE this OB)"
            )
    else:
        if is_short:
            smc_stop = round(nearest_high * 1.01, 2)
            out["stop_smc_suggested"] = smc_stop
            out["stop_smc_source"] = (
                f"1% above nearest {ob_label} OB high ${nearest_high:.2f} "
                f"(OB zone ${nearest_low:.2f}-${nearest_high:.2f})"
            )
        else:
            smc_stop = round(nearest_low * 0.99, 2)
            out["stop_smc_suggested"] = smc_stop
            out["stop_smc_source"] = (
                f"1% below nearest {ob_label} OB low ${nearest_low:.2f} "
                f"(OB zone ${nearest_low:.2f}-${nearest_high:.2f})"
            )

    if entry_mid:
        out["stop_smc_distance_pct"] = round(abs(smc_stop - entry_mid) / entry_mid * 100, 2)
        if target1:
            if is_short:
                risk = smc_stop - entry_mid
                reward = entry_mid - target1
            else:
                risk = entry_mid - smc_stop
                reward = target1 - entry_mid
            if risk > 0 and reward > 0:
                out["stop_smc_rr"] = round(reward / risk, 2)

    # ── 2. trap detector: legacy stop INSIDE any active OB zone ──
    if legacy_stop and float(legacy_stop) > 0:
        ls = float(legacy_stop)
        # Trap = legacy_stop sits between min(any.low) and max(any.high)
        # across all active OBs on the relevant side of spot.
        ob_min_low = min(b[0] for b in relevant_obs)
        ob_max_high = max(b[1] for b in relevant_obs)
        if ob_min_low < ls < ob_max_high:
            # find the specific OB that contains it for the zone label —
            # pull the FULL dict so we can read confluence/strength/status.
            containing_obs = [
                ob for ob in relevant_obs_rich
                if float(ob.get("low") or 0) <= ls <= float(ob.get("high") or 0)
            ]
            if containing_obs:
                # LONG: pick the DEEPEST (lowest low) — defines the sweep path.
                # SHORT: pick the HIGHEST (highest high) — defines the upside sweep.
                if is_short:
                    containing = max(containing_obs, key=lambda ob: float(ob.get("high") or 0))
                else:
                    containing = min(containing_obs, key=lambda ob: float(ob.get("low") or 0))
                c_low = float(containing.get("low") or 0)
                c_high = float(containing.get("high") or 0)
                out["stop_inside_ob"] = True
                out["stop_inside_ob_zone"] = f"${c_low:.2f}-${c_high:.2f} {ob_label} OB"

                # ── SHIP 1 · trap severity scoring (0–6) ──
                # Confluence weight (newer schema has confluence_score 0–5;
                # legacy schema uses strength_score whose distribution is very
                # different — empirically across 158 active traps the legacy
                # distribution is: p25=0.6, median=1.0, p75=2.4, max=34.
                # Calibrated thresholds: ≥2.0 → +2 (top quartile), ≥1.0 → +1.
                score = 0
                conf = containing.get("confluence_score")
                if conf is None:
                    strength = containing.get("strength_score") or 0
                    try:
                        strength_f = float(strength)
                    except (TypeError, ValueError):
                        strength_f = 0.0
                    if strength_f >= 2.0:
                        score += 2
                    elif strength_f >= 1.0:
                        score += 1
                else:
                    try:
                        conf_f = float(conf)
                    except (TypeError, ValueError):
                        conf_f = 0.0
                    if conf_f >= 3:
                        score += 2
                    elif conf_f >= 1:
                        score += 1

                # Status weight — fresh OBs sweep harder than touched ones.
                # 'tested' and 'tested-held' both indicate the OB has been
                # tagged once but still holds — treat as +1 (per spec).
                # 'partial-mit' is an intermediate state — also +1.
                status_norm = (containing.get("status") or "").lower()
                if status_norm == "fresh":
                    score += 2
                elif status_norm in ("tested-held", "tested", "partial-mit"):
                    score += 1
                # mitigated / fully-mit → 0 (already worked, sweep less urgent)

                # Proximity weight — close OBs are imminent risk.
                mid_ob = (c_low + c_high) / 2.0
                distance_pct = abs(mid_ob - ref_price) / ref_price * 100 if ref_price > 0 else 999
                if distance_pct < 3:
                    score += 2
                elif distance_pct < 7:
                    score += 1

                # ── SHIP 4 · STOP-DEPTH-IN-OB — the actual sweep mechanic ──
                # depth_pct = (ob_high - legacy_stop) / (ob_high - ob_low) * 100
                #   0% = stop at top edge of OB (still inside, but a small wick
                #        takes it out — least sweep-target risk)
                # 100% = stop at bottom edge (also "exit edge"; institutions
                #        already have to push deeper than the OB to fill)
                # The MIDDLE is where institutional limit orders cluster and
                # where stop-hunt sweeps target. CORZ at 62% depth = textbook.
                ob_span = c_high - c_low
                depth_pct = None
                depth_zone = None
                depth_weight = 0
                if ob_span > 0:
                    depth_pct = (c_high - ls) / ob_span * 100
                    # Direction-symmetric: for SHORT (Bear OB), the "deep sweep"
                    # target is also the MIDDLE of the OB. Flip the meaning of
                    # TOP/BOTTOM so UI reads consistently — for shorts, the
                    # "top edge" is the OB high (where stop hunt push starts).
                    if is_short:
                        depth_pct = (ls - c_low) / ob_span * 100
                    # Categorize for UI chips
                    if depth_pct < 15:
                        depth_zone = "TOP"
                    elif depth_pct < 25:
                        depth_zone = "UPPER"
                    elif depth_pct <= 75:
                        depth_zone = "MIDDLE"
                    elif depth_pct <= 85:
                        depth_zone = "LOWER"
                    else:
                        depth_zone = "BOTTOM"
                    # Weight: middle = deepest sweep risk
                    if 25 < depth_pct < 75:
                        depth_weight = 3
                    elif 15 <= depth_pct <= 25 or 75 <= depth_pct <= 85:
                        depth_weight = 2
                    else:
                        depth_weight = 1
                    score += depth_weight
                out["stop_depth_in_ob_pct"] = round(depth_pct, 2) if depth_pct is not None else None
                out["stop_depth_zone"] = depth_zone

                # Severity bands — recalibrated for new max score of 9:
                #   confluence  0-2
                #   status      0-2
                #   proximity   0-2
                #   depth       1-3 (always contributes when inside OB)
                # MED FLOOR: any stop_inside_ob=true MUST surface as at least MED.
                # The trap is the trap — collapsing it into a <details> means
                # the user misses it. LOW is reserved for the no-trap case.
                if score >= 6:
                    severity = "HIGH"
                else:
                    severity = "MED"   # NEW FLOOR — never LOW for an actual trap
                out["stop_inside_ob_score"] = int(score)
                out["stop_inside_ob_severity"] = severity

                # ── SHIP 2 · sleeve-conditional warning suppression ──
                # Catalyst-driven sleeves are catalyst-dominated; structural
                # OB sweep mechanics rarely play out within the short hold window.
                # Suppress the alarm (preserve data) for these sleeves.
                CATALYST_SLEEVES = {"pead", "esp_play", "insider_cluster"}
                CATALYST_FAMILY_TOKENS = ("pead", "esp play", "esp_play",
                                          "insider cluster", "insider_cluster")
                sleeve_norm = (sleeve or "").strip().lower()
                matched_sleeve = None
                if sleeve_norm:
                    if sleeve_norm in CATALYST_SLEEVES:
                        matched_sleeve = sleeve_norm
                    else:
                        for tok in CATALYST_FAMILY_TOKENS:
                            if tok in sleeve_norm:
                                matched_sleeve = tok
                                break
                if matched_sleeve:
                    pretty = (matched_sleeve
                              .replace("_", " ")
                              .replace("esp play", "ESP Play")
                              .replace("pead", "PEAD")
                              .replace("insider cluster", "Insider Cluster"))
                    out["stop_inside_ob_suppressed"] = True
                    out["stop_inside_ob_suppress_reason"] = f"catalyst sleeve: {pretty}"

    return out


def from_analysis_result(result: dict, regime_thresholds: dict | None = None,
                          git_commit: str | None = None) -> CanonicalTradePlan:
    """Assemble a CanonicalTradePlan from analyze_ticker() output.

    `result` is the dict returned by analysis.analyze_ticker() — has
    trade_plan, indicators, gates, conviction, monte_carlo, decision, etc.
    """
    from datetime import datetime as _dt
    plan = CanonicalTradePlan()

    plan.ticker = result.get("ticker", "")
    plan.direction = result.get("direction", "long")

    # Decision wiring
    decision = result.get("decision") or {}
    plan.verdict = decision.get("verdict") or result.get("verdict") or "WATCH"
    conv = result.get("conviction") or {}
    plan.conviction_tier = conv.get("label") or conv.get("tier")

    # Trade plan core
    tp = result.get("trade_plan") or {}
    _e_low = tp.get("entry_low")
    _e_high = tp.get("entry_high")
    _e_mid = tp.get("entry_mid") or tp.get("entry")
    if _e_mid is None and _e_low is not None and _e_high is not None:
        try:
            _e_mid = (float(_e_low) + float(_e_high)) / 2.0
        except (TypeError, ValueError):
            _e_mid = None
    plan.entry = TradeZone(low=_e_low, mid=_e_mid, high=_e_high)
    plan.stop = tp.get("stop")
    plan.target1 = tp.get("target1")
    plan.target2 = tp.get("target2")
    plan.target3 = tp.get("target3")   # bull-stretch (structural cutover) — None on ATR fallback
    plan.hold_period_days = tp.get("hold_days") or (tp.get("exit_params") or {}).get("time_stop_days")

    # Risk metrics — surfaced first per hedge-fund convention
    entry_mid = plan.entry.mid or 0
    if entry_mid and plan.stop:
        plan.risk.max_loss_pct = round((entry_mid - plan.stop) / entry_mid * 100, 2)
    plan.risk.rr_ratio = tp.get("rr_ratio")
    plan.risk.beta_adjusted_size_pct = tp.get("beta_adj")
    plan.risk.risk_flags = tp.get("risk_flags") or []
    # Drawdown haircut from kelly_size if present
    ksz = result.get("kelly_size") or {}
    plan.risk.drawdown_haircut = ksz.get("drawdown_mult", 1.0)

    # ── SMC-aware stop layer (2026-05-26) ──
    # Pull OBs from either source (`smc.order_blocks` is production today;
    # `smc_data.order_blocks` is the newer schema). Compute the SMC stop
    # suggestion + trap detector. Does NOT overwrite plan.stop (legacy);
    # surfaces as parallel fields so the UI can show the comparison.
    _smc = result.get("smc") or {}
    _smc_data = result.get("smc_data") or {}
    _obs = _smc.get("order_blocks") or _smc_data.get("order_blocks") or []
    # ── SHIP 2 · resolve sleeve for suppression check ──
    # Priority: explicit catalyst-sleeve audit `fired` flag > setup_family token.
    _sleeve_hint = None
    if (result.get("pead_audit") or {}).get("fired"):
        _sleeve_hint = "pead"
    elif (result.get("esp_play_audit") or {}).get("fired"):
        _sleeve_hint = "esp_play"
    elif (result.get("insider_cluster_audit") or {}).get("fired"):
        _sleeve_hint = "insider_cluster"
    else:
        _sleeve_hint = (result.get("setup_family")
                        or (result.get("trade_plan") or {}).get("setup_family"))
    _smc_fields = compute_smc_stop_fields(
        order_blocks=_obs,
        direction=plan.direction,
        entry_mid=plan.entry.mid,
        legacy_stop=plan.stop,
        target1=plan.target1,
        spot=result.get("price"),
        fractal_low=result.get("fractal_low"),
        sleeve=_sleeve_hint,
    )
    plan.risk.stop_smc_suggested = _smc_fields["stop_smc_suggested"]
    plan.risk.stop_smc_source = _smc_fields["stop_smc_source"]
    plan.risk.stop_smc_distance_pct = _smc_fields["stop_smc_distance_pct"]
    plan.risk.stop_smc_rr = _smc_fields["stop_smc_rr"]
    plan.risk.stop_inside_ob = _smc_fields["stop_inside_ob"]
    plan.risk.stop_inside_ob_zone = _smc_fields["stop_inside_ob_zone"]
    plan.risk.stop_inside_ob_severity = _smc_fields.get("stop_inside_ob_severity")
    plan.risk.stop_inside_ob_score = _smc_fields.get("stop_inside_ob_score")
    plan.risk.stop_inside_ob_suppressed = _smc_fields.get("stop_inside_ob_suppressed", False)
    plan.risk.stop_inside_ob_suppress_reason = _smc_fields.get("stop_inside_ob_suppress_reason")
    # SHIP 4 — depth fields
    plan.risk.stop_depth_in_ob_pct = _smc_fields.get("stop_depth_in_ob_pct")
    plan.risk.stop_depth_zone = _smc_fields.get("stop_depth_zone")

    # Setup attribution
    plan.setup.setup_type = tp.get("setup_type") or result.get("setup_type")
    plan.setup.setup_family = result.get("setup_family")
    plan.setup.mechanism_hypothesis = MECHANISM_HYPOTHESES.get(plan.setup.setup_family or "")
    plan.setup.score_normalized = result.get("score")
    plan.setup.pillar_scores = (result.get("score_breakdown") or {})
    plan.setup.elliott_wave = tp.get("elliott_wave")

    # Statistical context — historical performance of this setup × regime
    regime_name = result.get("regime") or result.get("regime_name") or result.get("regime_label")
    stats, regime_ctx = _historical_setup_stats(plan.setup.setup_type, regime_name)
    plan.stats = stats
    plan.regime = regime_ctx

    # Regime threshold info
    if regime_thresholds and regime_name:
        rt = regime_thresholds.get(regime_name) or {}
        plan.regime.max_size_pct = rt.get("max_size_pct", 100)
        plan.regime.short_allowed = bool(rt.get("short_allow_override", False))
    plan.regime.regime_confidence = (result.get("regime_meta") or {}).get("confidence")

    # Catalysts
    tier1 = result.get("tier1_signals") or {}
    options = result.get("options_iv") or {}
    insider = result.get("insider") or {}
    news = result.get("news") or {}
    plan.catalysts.days_to_earnings = result.get("earn_days") or result.get("days_to_earnings")
    plan.catalysts.has_pead = bool(tier1.get("pead"))
    plan.catalysts.has_uoa_calls = (options.get("uoa_calls") or 0) > 0
    plan.catalysts.has_uoa_puts = (options.get("uoa_puts") or 0) > 0
    plan.catalysts.insider_cluster_30d = insider.get("cluster_30d") or insider.get("buys_30d") or 0
    plan.catalysts.insider_score = insider.get("score") or insider.get("insider_score")
    plan.catalysts.news_sentiment_7d = news.get("sentiment_score") or news.get("composite_score")
    plan.catalysts.catalyst_density = tier1.get("count") or 0
    plan.catalysts.catalyst_tier = result.get("catalyst_tier")

    # Gate audit trail
    gates_passed = []
    gates_failed = []
    for g in (decision.get("gates_evaluated") or []):
        if isinstance(g, dict):
            if g.get("passed"):
                gates_passed.append(g.get("name", "unknown"))
            else:
                gates_failed.append({
                    "name": g.get("name"),
                    "reason": g.get("reason"),
                    "severity": g.get("severity", "high"),
                })
    plan.gates.passed = gates_passed
    plan.gates.failed = gates_failed
    plan.gates.soft_caveats = decision.get("caveats") or []
    plan.gates.signal_filter = decision.get("signal_filter")

    # Provenance
    plan.decided_at = _dt.now().isoformat()
    plan.git_commit = git_commit

    return plan


def attach_to_result(result: dict, regime_thresholds: dict | None = None,
                      git_commit: str | None = None) -> dict:
    """Mutate the analyze_ticker result dict to include canonical_trade_plan.

    All UI tabs read result["canonical_trade_plan"] (the asdict version)
    instead of pulling from random intermediate fields.
    """
    plan = from_analysis_result(result, regime_thresholds=regime_thresholds,
                                 git_commit=git_commit)
    result["canonical_trade_plan"] = plan.to_dict()
    return result


if __name__ == "__main__":
    # Smoke test: build an empty plan
    p = CanonicalTradePlan(ticker="TEST")
    import json as _json
    print(_json.dumps(p.to_dict(), indent=2, default=str))
