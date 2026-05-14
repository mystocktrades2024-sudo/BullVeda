# Choice C — Full Strategy Roster Decision

**Date**: 2026-05-13
**Status**: APPROVED in principle, sequenced over 4 weeks
**Evidence**: post-data-hygiene `cache/regime_sharpe_decomp_2026-05-13.json` (n=903 trades)

---

## What Choice C is

Build a multi-strategy portfolio system instead of relying on a single
strategy across all regimes. Each sub-strategy is tuned for its
strongest regime; a regime classifier routes signals to the appropriate
sleeve.

Three options were on the table:
- **Choice A** — single strategy, accept partial-cycle behavior
- **Choice B** — add ONE additional sleeve (lightest expansion)
- **Choice C** — full strategy roster (4-strategy system)

This document explains why Choice C is the right path.

---

## The clean-data evidence

Post-data-hygiene (alpha_vs_spy / exit_reason / regime4 backfilled),
the per-regime Sharpe decomposition shows:

| Regime | n | WR | Sharpe/trade | PF | Verdict |
|---|---|---|---|---|---|
| risk_on_trending | 266 | 48.5% | **+0.00** | **1.00** | Break-even — zero alpha |
| risk_on_choppy | 541 | 58.2% | +0.16 | 1.60 | Working — our alpha cell |
| risk_off / panic | 0 | — | — | — | Untested — never traded |

**Key finding**: trending regime is genuinely break-even. The pullback
strategy has no edge there. Tuning won't fix it; the mechanism is wrong.

---

## Why Choice C, not B

Choice B (one momentum sleeve) addresses ONLY the bull weakness. It does
not address:
- Bear regime (no defensive strategy)
- Choppy alpha decay risk (no diversification within choppy)
- Catalyst-driven moves (no PEAD sleeve)

Choice C builds the full system over time, with each sleeve validated
before the next is built. **Same total time, more comprehensive end state.**

The article's "Sharpe ≥ 1.5 across all 3 regimes" bar requires positive
expectancy in bull AND bear. Choice B reaches the bull half. Choice C
reaches both.

---

## The 4-strategy roster

| Strategy | Best regime | Mechanism | Status |
|---|---|---|---|
| **Pullback to Value (CORE)** | Choppy | Buy retracement to EMA/support; 3:1 R:R | LIVE — Sharpe +0.16 in choppy |
| **Momentum Continuation** | Trending | Buy strength + ADX≥25 + volume; tighter stops | DESIGNED (docs/strategy_momentum_continuation.md) |
| **Mean Reversion** | Choppy alt | Buy oversold (RSI<30); short-hold (3-5d) | NOT YET DESIGNED |
| **Catalyst-Driven (PEAD)** | All regimes | Buy post-earnings positive surprise + revisions | NOT YET DESIGNED |

Note: SHORT-side as a fifth strategy is deferred — small account ($5K
paper), high implementation complexity, low priority until other 4 are validated.

---

## Sequenced 4-week build plan

### Week 1 — Momentum Continuation MVP (paper validation)

**Goal**: implement the trigger logic + emit to signal_log as a SHADOW
signal (no real trade routing).

**Code**:
- `analysis.py:classify_setup_family()` — add momentum branch
- `analysis.py:compute_trade_plan()` — momentum-specific stops/targets
- `decision_engine.py` — bypass logic for entry_quality + setup kills when family=Momentum Continuation
- `config/config.json` — `momentum_sleeve` block, default `_enabled: false`

**Validation**: 7-14 days of WATCH_MOMENTUM signals logged. Hypothetical PnL
computed. Pass criteria: ≥ 10 signals fire, hypothetical PF ≥ 1.5.

**Go/No-go gate**: pass criteria → proceed to Week 2. Fail → debug or abandon
sleeve.

### Week 2 — Momentum half-size live

**Goal**: route Momentum signals as real BUYs at HALF the designed size
(quarter-Kelly × 0.5).

**Pass criteria after 21-30 days**: Sharpe per trade in trending ≥ 0.5;
combined system Sharpe higher than baseline.

**Go/No-go gate**: pass → full size in Week 3. Fail → roll back, return to
single-strategy.

### Week 3 — Momentum full size + Mean Reversion design

**Goal A**: promote Momentum to designed quarter-Kelly size.
**Goal B**: design the Mean Reversion sleeve doc (parallel to docs/strategy_momentum_continuation.md).

Mean Reversion design considerations:
- Trigger: RSI(14) < 30 + within 5d of intraday low + price > EMA200
- Bypass: entry_quality (we WANT EXTENDED-down)
- Stop: 1.0 ATR (tight on bounce setup)
- Target: +3-5% (bounce, not trend follow)
- Hold: 3-5 days max
- Regime: choppy primarily, also non-panic bear
- Size: half-Kelly (high confidence in regime fit)

### Week 4 — Mean Reversion MVP + PEAD design

**Goal A**: Mean Reversion paper-validation (same 7-14 day shadow).
**Goal B**: PEAD/catalyst sleeve design doc.

PEAD considerations:
- Trigger: post-earnings beat + analyst revisions positive + price > EMA21 within 3d of earnings
- Bypass: many — catalyst dominates
- Stop: 1.0 ATR
- Target: +5-10% (catalyst extension)
- Hold: 5-15 days
- Regime: all (catalyst doesn't care)
- Size: full Kelly (high evidence base in academic literature)

### Week 5+ — PEAD MVP + ongoing validation

Continue weekly regime_sharpe_decomp monitoring. Add or remove sleeves
based on rolling evidence.

---

## Kill switches at each stage

If at ANY week the rolling-Sharpe kill fires (Sharpe < -0.5 on n=20):
- HALT all sleeve promotion
- Run loss_streak_investigation.py (per docs/runbook_loss_streak.md)
- Diagnose, then decide whether to continue or roll back

If choppy regime PF drops below 1.0 in any week:
- HALT — our alpha cell is degrading
- Investigate edge erosion before adding new strategies

---

## What changes after Choice C is complete

| Aspect | Today | Post-Choice-C |
|---|---|---|
| Strategies in production | 1 (pullback) | 4 (pullback + momentum + mean-reversion + PEAD) |
| Trending regime alpha | None | Momentum sleeve carries it |
| Choppy regime alpha | Pullback only | Pullback + mean-reversion (diversified) |
| Bear regime | Cash only | PEAD still fires; possible defensive rotation |
| Catalyst capture | Modest (tier-1 boost in score) | PEAD-led capture for earnings/M&A |
| System complexity | 1 trigger logic | 4 trigger logic + regime router |
| Validation surface | Per-strategy Wilson LB | Per-(strategy × regime) Wilson LB |
| Article's bar (≥1.5 Sharpe across regimes) | Not met | Designed to meet |

---

## Risks of Choice C

| Risk | Probability | Mitigation |
|---|---|---|
| Strategies double-fire (one ticker tagged by multiple sleeves) | Medium | Mutually exclusive triggers; conflict-resolution rule in classify |
| Total exposure exceeds risk budget | Low | Per-sleeve sizing caps; portfolio-level max-positions |
| Validation fatigue (too many sleeves to monitor) | Medium | weekly_diagnostics.sh aggregates; Slack alerts on regression |
| Choice C timeline slips (life intervenes) | High | Weekly go/no-go gates allow pause without breaking system |
| Bear sleeve never gets tested (regimes don't cooperate) | High | Accept residual gap; document as known limitation |

---

## What I'd skip even within Choice C

- **SHORT-side strategy** — too complex for $5K paper account, low priority
- **Multi-asset (TLT/GLD)** — different mandate, defer
- **Pairs trading** — different infrastructure (long/short within sector), defer
- **Crypto sleeve** — already have crypto_screener.py separately, keep that lane

---

## Reference documents

| Doc | Purpose |
|---|---|
| `docs/strategy_momentum_continuation.md` | Momentum sleeve design (Week 1-3) |
| `docs/runbook_loss_streak.md` | When to investigate regression |
| `scripts/weekly_diagnostics.sh` | Sunday auto-run of diagnostics |
| `scripts/regime_sharpe_decomp.py` | Per-regime stats anytime |
| `cache/regime_sharpe_decomp_2026-05-13.json` | The clean-data baseline |

---

## Decision

**APPROVED**: pursue Choice C in 4-week sequenced build with weekly go/no-go gates.

**FIRST ACTION**: Week 1 implementation of momentum sleeve (paper validation).

**SUSPEND TRIGGER**: rolling-Sharpe kill firing OR choppy regime PF < 1.0.

**REVIEW CADENCE**: weekly via weekly_diagnostics.sh.
