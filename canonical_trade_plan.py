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
    plan.entry = TradeZone(
        low=tp.get("entry_low"),
        mid=tp.get("entry_mid") or tp.get("entry"),
        high=tp.get("entry_high"),
    )
    plan.stop = tp.get("stop")
    plan.target1 = tp.get("target1")
    plan.target2 = tp.get("target2")
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
