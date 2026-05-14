# Momentum Continuation Sleeve — Strategy Identification

**Status**: DESIGN ONLY — not yet implemented
**Author**: 2026-05-13 strategic planning session
**Evidence base**: `cache/regime_sharpe_decomp_2026-05-13.json` (post-data-hygiene)

---

## Why this strategy exists

### The problem

Clean-data analysis (n=903 trades) reveals our pullback strategy has **zero alpha in trending regime**:

| Regime | n | Sharpe/trade | PF | Verdict |
|---|---|---|---|---|
| risk_on_trending | 266 | **+0.00** | **1.00** | Break-even — no edge |
| risk_on_choppy | 541 | +0.16 | 1.60 | Our alpha cell |
| bear/panic | 0 | — | — | Untested |

**PF 1.00 means we're churning to zero in trending markets** — entering trades that on average match our exit costs. Tuning the existing pullback rules cannot fix this. The strategy mechanism (buy retracement to value) does not work in markets without retracements.

### The mechanism we're missing

Trending markets reward a different mechanic:
- **Buy strength, not retracement** — chase confirmed momentum
- **Tighter stops** — no mean reversion to fall back on
- **Faster targets** — momentum extends further than reverts
- **Bypass entry_quality** — EXTENDED is the natural entry in trending

This is the **CTA momentum** style (Renaissance, AQR, Man AHL run versions of this at scale).

### Today's missed opportunities (proof of concept)

From the Sharpe screen (cache/sharpe_screen.html, 2026-05-13), 5 stocks are currently being silently killed by setup_score_multiplier despite annualized Sharpe ≥ 2.0:

| Ticker | Sharpe | RetAnn | What killed it |
|---|---|---|---|
| ADI | 3.85 | +184% | 52wk Breakout in kill list |
| TXN | 3.03 | +132% | 52wk Breakout in kill list |
| FFIV | 2.44 | +84% | 52wk Breakout in kill list |
| VRT | 2.36 | +156% | 52wk Breakout in kill list |
| TER | 2.28 | +159% | EMA21 Pullback in kill list |

The momentum sleeve would **catch these** because it doesn't depend on the killed setup_types — it triggers on independent momentum criteria.

---

## Design specification

### Trigger conditions (ALL must be true)

| Condition | Rule | Why |
|---|---|---|
| Regime | `risk_on_trending` only | Other regimes use existing strategies |
| Score floor | `score ≥ 70` | Composite quality gate (loose; momentum is the primary signal) |
| Trend strength | `ADX(14) ≥ 25` | Confirms a real trend, not noise |
| Volume confirmation | `RVOL(20) ≥ 1.3` | Institutional flow validation |
| Trend stack | `price > EMA8 > EMA21 > EMA50` | Multi-timeframe uptrend alignment |
| Recent momentum | `5d return ≥ +3%` | Filters out flat extension |
| Price-history Sharpe | `126d Sharpe ≥ 1.5` | Validated edge in price action — no random extensions |
| Daily $ volume | `≥ $20M` | Tighter than core strategy ($10M) — momentum needs liquidity |
| Earnings | `> 7 days away` | Same as core — IV crush risk |

### Bypasses (what this sleeve IGNORES)

| Existing gate | Behavior in this sleeve |
|---|---|
| `entry_quality` (FRESH/PULLBACK/VALID) | **BYPASSED** — EXTENDED is normal |
| `setup_score_multiplier` (52wk Breakout / EMA21 Pullback kills) | **BYPASSED** — different setup family |
| `tail_loss_filter` (stars==3) | KEPT — quality still matters |
| `fundamental_adequacy` | **BYPASSED** with caveat — momentum doesn't care about fundamentals |
| Sector dispersion downgrade | KEPT — narrow-leadership warning still valid |

### Stop discipline (different from core)

| Aspect | Core strategy | Momentum sleeve | Why |
|---|---|---|---|
| Initial stop | 1.25 ATR | **0.75 ATR** | Tighter — no mean reversion expected |
| Trail-stop trigger | +2% MFE | **+1.5% MFE** | Lock gains faster |
| Trail distance | 1.0 ATR | **0.5 ATR** | Tighter trail when active |
| Time stop | 10-15 days | **5 days max** | Don't ride extended trades long |

### Targets (faster cycle)

| Target | Core strategy | Momentum sleeve |
|---|---|---|
| T1 | +5% (≈1.0R) | **+3%** (≈1.5R) — scale 50% out |
| T2 | +10% (≈2.0R) | **+6%** (≈3.0R) — scale 25% more |
| T3 (runner) | +15% (≈3.0R) | **+10%** (≈5.0R) — runner with 0.5 ATR trail |

### Position sizing (chase risk discount)

| Aspect | Core | Momentum sleeve |
|---|---|---|
| Base size | Half-Kelly | **Half-Kelly × 0.5** = Quarter-Kelly |
| Reasoning | Standard | We're chasing, not entering at value — explicit discount |

### Regime gate

ONLY fires when:
- `regime4 == "risk_on_trending"`
- AND no system_circuit_breaker active

In choppy/bear/panic: this sleeve is INACTIVE. Normal pullback strategy operates.

---

## Why this design — through the 5 lenses

### Hedge fund analyst
Standard CTA momentum-following template. Profitable across decades when rules are followed mechanically. Sharpe filter (1.5+) is the key quality gate distinguishing "trend" from "noise."

### Graham-Buffett value
Hates this strategy categorically — no margin of safety, chasing prices. **Acknowledge and skip this lens** for this sleeve. The mandate is momentum capture, not value buying.

### Swing trader
Classic Livermore/Darvas: "Trend is your friend." Tight stops + faster targets compensate for chase risk. **Strongly endorses.**

### Quant earnings
Earnings filter (>7 days) prevents IV crush. Otherwise ignores — momentum is regime-driven, not earnings-driven.

### CFP / portfolio manager
**Concerns**:
- Half size (half-Kelly × 0.5 = quarter-Kelly)
- Tighter stops cap drawdown per trade
- Max 5-day hold caps directional exposure
- Sleeve only fires in trending = correlated with broad market in bull
**Verdict**: acceptable as 25% of portfolio max (1-2 positions concurrent).

---

## Risk factors (5-lens)

| Risk | Severity | Mitigation |
|---|---|---|
| Chase trades have wide left tails (sudden reversals) | High | Tight 0.75 ATR stop + 5-day max hold |
| Whipsaw in failed breakouts | Medium | ADX ≥ 25 + RVOL ≥ 1.3 filter out weak signals |
| Concentration in top sectors during narrow leadership | Medium | Existing sector_dispersion gate still applies |
| Over-fitting to recent bull period | High | Validate with backtest before shipping live |
| Crowded momentum trade (too many funds chasing same names) | Medium | Sharpe ≥ 1.5 filter favors stocks already in motion (less crowded than chasing breakout) |
| IV crush around earnings | Low | Earnings >7d filter |

---

## Validation plan (BEFORE going live)

Per CLAUDE.md principle 7 (no knob-tweaking without evidence):

### Phase 1: Paper-validation (WEEK 1)
1. Implement the trigger logic + emit signals as `setup_family = "Momentum Continuation"` to `signal_log.json`
2. Use `verdict = "WATCH_MOMENTUM"` (not BUY) so signals log but don't trade
3. Run for 7-14 days during a trending or mixed regime period
4. Compute hypothetical PnL on the WATCH_MOMENTUM signals

**Pass criteria**: ≥ 10 signals fire; hypothetical PF ≥ 1.5; max-drawdown < 10%

### Phase 2: Half-size live (WEEK 2-4)
If Phase 1 passes:
- Promote to `verdict = "BUY"` with HALF the designed size (i.e., quarter-Kelly × 0.5 = 1/8 Kelly)
- Run for 21-30 days
- Compare to control (existing strategy in same period)

**Pass criteria**: Sharpe ≥ 0.5 per trade in trending regime; combined system Sharpe higher than baseline

### Phase 3: Full size (WEEK 5+)
If Phase 2 passes:
- Promote to designed size (quarter-Kelly)
- Continue monitoring weekly via regime_sharpe_decomp
- Roll back via `config.momentum_sleeve_enabled = false` if degradation observed

---

## Implementation scope

### Code changes required (estimate: 4-6 hours focused work)

1. `analysis.py:classify_setup_family()` — add momentum detection branch
2. `analysis.py:compute_trade_plan()` — add momentum-specific stops/targets
3. `decision_engine.py` — add momentum sleeve bypass logic for entry_quality + setup kills
4. `config/config.json` — new `momentum_sleeve` block with `_enabled: false` default
5. `scripts/momentum_validate.py` — Phase 1 validation harness

### Effort breakdown

| Phase | Effort |
|---|---|
| MVP implementation | 4-6 hr |
| Phase 1 paper validation | 7-14 days observation |
| Phase 2 half-size live | 21-30 days |
| Phase 3 full size | ongoing |
| Total to "validated production" | 6-8 weeks |

---

## Roll-back plan

Single config flag: `momentum_sleeve_enabled: false` reverts to current behavior. No code rollback needed.

---

## What this sleeve does NOT do

- Does NOT replace the pullback strategy — they coexist
- Does NOT fire in choppy or bear regimes
- Does NOT trade SHORT — only long-side momentum
- Does NOT bypass earnings blackout
- Does NOT bypass macro circuit breaker (CPI/FOMC days)
- Does NOT bypass rolling-Sharpe kill switch

---

## Comparison to alternatives considered

### Alternative A: Tune existing strategy harder
**Verdict**: Won't work. Pullback mechanism CAN'T capture extension. Tuning is rearranging deck chairs.

### Alternative B: Just relax entry_quality globally
**Verdict**: Tried for choppy regime today. Different problem. Bull weakness needs different mechanism, not gate relaxation.

### Alternative C: Multi-asset (TLT, GLD, vol)
**Verdict**: Bigger lift (3-4 weeks). Better as Phase 4 after momentum sleeve proven. Diversifies regime exposure but doesn't directly fix bull weakness.

### Alternative D: Mean-reversion sleeve for choppy
**Verdict**: Worth doing in Phase 2 of Choice C. But our choppy already works (PF 1.60). Bull is the priority.

---

## Decision

**Recommended next step**: implement MVP (Phase 1, paper-only) within 1 week. Validate with 14 days of live observation. Promote based on evidence.

**Do NOT ship live without Phase 1+2 validation** — would violate CLAUDE.md principle 7.
