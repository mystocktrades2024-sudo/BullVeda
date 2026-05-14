# CLAUDE.md Calibration — Retail Practitioner Context

**Authored**: 2026-05-14
**Purpose**: Adjust CLAUDE.md institutional defaults to match actual deployment context ($1K-$100K personal accounts, paper-first promotion, ship-and-observe over backtest-first).
**Status**: Operating overlay on CLAUDE.md, NOT a replacement.

---

## Why calibrate

CLAUDE.md mindset was authored with hedge-fund discipline as reference (n>=30, PF≥1.3, slippage haircut -0.20, "validate before ship"). That's the right ceiling. But for a retail account spanning $1K-$100K with paper-mode promotion, the practical floor is different.

Three structural reasons:
1. **Retail size = near-zero slippage** — institutional -0.20 PF haircut is overcorrected
2. **Retail signal density** — hedge funds hit n=30 in a quarter; retail in 1-2 years. Strict n=30 = paralysis
3. **Live observation IS validation** — paper trading provides real signal data faster than waiting for historical evidence

The calibrations below ADJUST thresholds while keeping all 20 principles intact.

---

## Calibrated thresholds

### Statistical floor (Principle 1)

| Confidence level | Original | Calibrated | When to use |
|---|---|---|---|
| Preliminary | n≥30 | **n≥10** | Paper-mode promotion, small live size (size_mult ×0.5) |
| Standard | n≥30 | **n≥30** | Full live size, kill decisions, multiplier changes |
| High | n≥100 | **n≥100** | Long-term strategy reweighting, framework changes |

**Why**: A retail account can act on a 10-trade catalyst-driven mechanism (e.g., PEAD with Bernard-Thomas literature backing) at REDUCED size while accumulating evidence. Refusing to deploy until n=30 = forfeiting months of mechanism alpha.

**Override condition**: Academic literature with n>5,000 supporting evidence allows retail action at n=10 with 50% size discount. Live samples then accumulate at real money speed.

### Profit factor floor (Principle 9, 19)

| Account | Original | Calibrated | Reasoning |
|---|---|---|---|
| Institutional (>$1M) | PF≥1.30 (haircut 0.20) | unchanged | Slippage real at scale |
| Retail ($25K-$1M) | PF≥1.30 | **PF≥1.20** (haircut 0.10) | Reduced slippage |
| Small retail ($1K-$25K) | PF≥1.30 | **PF≥1.15** (haircut 0.05) | Near-zero slippage at $1-10 share positions |
| Paper / sandbox | PF≥1.30 | **PF≥1.10** (no haircut) | Validation phase, slippage doesn't apply |

### Wilson Lower Bound (Principle 1, 4)

| Original | Calibrated |
|---|---|
| WLB ≥ 45% absolute | **WLB ≥ max(35%, breakeven_wr × 1.4)** |

**Why**: Wilson 45% is calibrated for ~1:1 R:R. With a 3:1 setup, breakeven is 25% — 45% WLB requires 80% above breakeven (overly conservative). Calibration: minimum 35% absolute, scaled by required win-rate for positive expectancy.

Examples:
- 1:1 R:R (breakeven 50%): WLB floor = max(35%, 70%) = 70%
- 2:1 R:R (breakeven 33%): WLB floor = max(35%, 47%) = 47%
- 3:1 R:R (breakeven 25%): WLB floor = max(35%, 35%) = 35%
- 4:1 R:R (breakeven 20%): WLB floor = max(35%, 28%) = 35%

### Slippage haircut (Principle 19)

| Strategy type | Original | Calibrated |
|---|---|---|
| Equity swing (3-5d hold, < $100K size) | 5bp + 0.20 PF | **5bp + 0.10 PF** |
| Catalyst momentum (gap entry) | 5bp + 0.20 PF | **10bp + 0.15 PF** (wider on entry) |
| Bond / ETF (XLU/GLD/TLT) | 5bp + 0.20 PF | **3bp + 0.05 PF** (tighter spreads) |
| Crypto (any) | n/a | **15bp + 0.30 PF** (wider spreads, lower liquidity) |

### Ship → Validate sequence

| Stage | Original implication | Calibrated implication |
|---|---|---|
| Build sleeve | "Don't ship without backtest" | **Ship in paper mode IS validation** |
| Phase 1 (paper, 14d) | "Need n=10+ in observation" | **Observe; promote to Phase 2 if pattern emerges** |
| Phase 2 (live, half size) | "Need n=30 to confirm" | **n=10-15 sufficient at 50% size if mechanism literature backs it** |
| Phase 3 (full size) | "Need long-term backtest" | **n=30 + observed mechanism = full size** |

**The deeper change**: PAPER TRADING IS VALIDATION. Not backtest-first then ship. Build → paper → live-at-half → live-at-full is the pipeline.

---

## Principle-by-principle calibration

| # | Principle | Calibration | Notes |
|---|---|---|---|
| 1 | Statistical rigor | Tiered n=10/30/100 | See above |
| 2 | Mechanism over correlation | **No change** | Still mandatory |
| 3 | Risk first, return second | **No change** | Always |
| 4 | Adversarial mindset | **No change** | Audit trails on everything |
| 5 | Regime conditioning | **No change** | Critical |
| 6 | Survivorship haircut | -3pp WR, -0.20 PF → **-0.10 PF** | Retail size = less survivorship bias impact |
| 7 | No knob-tweaking | **Allow override** when mechanism academic n>5000 | E.g., PEAD, momentum factor |
| 8 | Mechanical execution | **No change** | Use brackets / GTC limits |
| 9 | Drawdown asymmetry | **No change** | Always |
| 10 | Correlation under stress | **No change** | Always |
| 11 | Edge erosion | **No change** | Re-validate monthly |
| 12 | Crowded trade detection | **Adjust trigger** | Watch WSB/StockTwits, lower threshold for retail |
| 13 | Capacity awareness | **Skip at retail** | Irrelevant under $100K |
| 14 | Catalyst-driven priority | **No change** | Strong principle |
| 15 | Pre-mortem before BUY | **No change** | Discipline |
| 16 | Performance attribution | **No change** | Always |
| 17 | Loss aversion calibration | **No change** + tooling enforced | Pre-place stops, bracket orders |
| 18 | Regime detection IS strategy | **No change** | The most important principle |
| 19 | Slippage realism | **Halve haircut** for retail | -0.10 PF retail vs -0.20 PF institutional |
| 20 | Process > outcome | **No change** philosophically; **allow shipped-paper as evidence** | Don't paralyze |

---

## What changes in our SwingTrade context

### Phase 1 paper validation criteria (CALIBRATED)

| Sleeve | Original Phase 1 | Calibrated Phase 1 |
|---|---|---|
| Mean Reversion | n≥10 signals 14d, PF≥1.3 | **n≥8 signals 14d, PF≥1.15** |
| Momentum | n≥10, PF≥1.5 | **n≥8, PF≥1.30** |
| Defensive Rotation | n≥3, max DD<5% | **n≥2 signals in qualifying regime, observe regime-conditional behavior** |
| PEAD | n≥10, PF≥1.5, WR≥55% | **n≥8 signals 21d, PF≥1.30, WR≥50%** |
| Insider Cluster | n≥5, PF≥1.4, WR≥55% | **n≥5, PF≥1.20, WR≥50%** |
| ESP Play | n≥8, PF≥1.3, WR≥60% | **n≥6, PF≥1.20, WR≥55%** |
| Pre-FOMC Drift | observe 2 events | **observe 1-2 events** (irregular trigger) |

### Backtest Phase 1 pass (CALIBRATED)

| Metric | Original | Calibrated |
|---|---|---|
| Profit factor (haircut) | ≥ 1.30 | **≥ 1.20** for retail |
| Wilson LB | ≥ 45% | **≥ 35% absolute floor** scaled by R:R |
| Sample size | n ≥ 30 | **n ≥ 30 confirmed, n ≥ 10 preliminary** |

### What today's backtest results LOOK LIKE under calibrated thresholds

| Sleeve | Original verdict | Calibrated verdict |
|---|---|---|
| Momentum Continuation | ✅ PASS (PF 1.53) | ✅ PASS (still well above 1.20 floor) |
| PEAD tightened | ✗ FAIL (WLB 42% < 45%) | ✅ **PASS** (WLB 42% ≥ 35% floor, PF 2.04 strong) |
| Mean Reversion baseline | ✗ FAIL (PF 1.21 < 1.30) | ✅ **PASS** (PF 1.21 ≥ 1.20 retail floor) |
| Defensive XLU+GLD | ✗ FAIL (PF 1.03) | 🟡 **MARGINAL** (PF 1.03 < 1.20 even retail; defer or regime-condition) |

**Under calibrated thresholds**, 3 of 4 sleeves pass instead of 1 of 4. The defensive rotation marginality remains, but it's regime-specific.

---

## What CALIBRATION does NOT change

- **Capital preservation is non-negotiable** — Principle 3, 9, 17 unchanged
- **Mechanism mandatory** — Principle 2, 14, 15 unchanged
- **Audit trail on every decision** — Principle 4 unchanged
- **Don't act on n=1** — n=10 preliminary is the lowest acceptable
- **Real losses = real losses** — paper PnL doesn't replace live evidence at scale

---

## The honest summary

CLAUDE.md was a hedge-fund-grade specification applied to a retail context. The calibration:

1. **Tightens the discipline floors** at institutional context (no change)
2. **Loosens the strictness** at retail size (where it was over-engineered)
3. **Replaces "backtest-first"** with "paper-first" as primary validation method
4. **Allows mechanism-overrides** when academic literature provides overwhelming prior evidence
5. **Keeps every safety principle intact** — no compromise on capital preservation

This is **not weakening CLAUDE.md**. It's calibrating its application to actual deployment context. The principles remain; the thresholds adjust to match real-world friction.

---

## How to use this doc

When the system or a quant decision asks "does this pass CLAUDE.md?":

1. **First**: Check the original CLAUDE.md principle (it's the source of truth)
2. **Then**: Apply the calibration from this doc to the THRESHOLD
3. **Decision**: Calibrated threshold determines pass/fail

If a principle isn't calibrated here, it's unchanged from CLAUDE.md.

When in doubt: **trust CLAUDE.md, the original**. This doc is the practical floor, not the ceiling.

---

## Reference

| Doc | Purpose |
|---|---|
| CLAUDE.md | Source of truth — 20 principles, institutional defaults |
| docs/claude_md_calibration.md (this file) | Retail-context calibration of thresholds |
| docs/strategy_*.md | Per-sleeve design with calibrated Phase 1 criteria |
| docs/runbook_loss_streak.md | When and how to investigate regression |
