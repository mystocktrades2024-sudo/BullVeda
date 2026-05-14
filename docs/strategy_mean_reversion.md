# Strategy — Mean Reversion Sleeve

**Status**: DESIGNED 2026-05-14, Phase 1 paper validation pending
**Closes**: choppy-regime diversifier gap (Pullback to Value is currently the only choppy strategy)
**Spec author**: SwingTrade quant team (CLAUDE.md mindset)

---

## One-sentence mechanism

In a choppy market with long-term uptrend intact (price > EMA200),
temporarily oversold conditions (RSI < 30) reflect emotional selling
rather than fundamental damage — prices revert to short-term mean
over 3-5 trading days.

This is **statistical arbitrage on emotional selling**. Not theory — academic literature on short-term reversal (Jegadeesh 1990, Lehmann 1990, Conrad-Kaul 1989) shows persistent profitability of buying oversold stocks in non-trending markets. Mechanism: liquidity providers earn premium for absorbing forced sellers.

## Why now

Today's regime is **risk_on_choppy + SPY > 50EMA**. Pullback to Value is currently the only choppy-regime sleeve we have. Diversifying within choppy reduces single-mechanism risk — if Pullback's edge erodes, Mean Reversion still produces.

| Sleeve | Choppy regime fit |
|---|---|
| Pullback to Value | Buy retracement to EMA/support — assumes uptrend resumes |
| **Mean Reversion** | **Buy oversold spike-down — assumes mean reversion to short-term average** |
| Defensive Rotation | Only fires when SPY breaks 50EMA (different regime) |
| Momentum Continuation | Choppy is wrong regime (waits for trending) |

Pullback and Mean Reversion are mechanism-orthogonal. Both can fire on the same day; they target different ticker subsets (Pullback = pulling back to support; Mean Reversion = oversold spike-down).

---

## Triggers (all must be true)

| Gate | Condition | Why |
|---|---|---|
| **Regime** | `risk_on_choppy` OR `bull` | Mean reversion mechanism fails in strong trends OR panic |
| **RSI(14)** | < 30 | Classical oversold; signals statistical short-term reversal odds |
| **Price > EMA200** | True | Long-term uptrend intact — no falling-knife |
| **Recent low within 5d** | True | Fresh oversold, not stale (decayed signal) |
| **Volume** | RVOL ≥ 1.0 | Selling-exhaustion check — high vol on the low = capitulation |
| **Daily $ vol** | ≥ $10M | Liquidity floor for tight-stop exits |
| **Earnings buffer** | ≥ 7d | Don't catch falling knife into earnings |
| **Min score** | ≥ 50 | Composite quality floor |

Beta does NOT gate — both high-beta and low-beta names bounce. The mechanism is statistical, not factor-driven.

---

## Trade plan (mean-reversion-specific)

| Field | Value | vs core swing |
|---|---|---|
| **Stop** | 1.0 ATR (close-based) | tight — bounce setups fail fast, no reason to be patient |
| **Target 1** | +3% | first profit-take |
| **Target 2** | +5% | upper bounce target |
| **Target 3** | — | no T3 — bounces don't run |
| **Trail** | activate +1.5%, 0.5 ATR distance | aggressive trail (lock in bounce gains) |
| **Hold** | 3-5 trading days max | time-stop on no bounce |
| **R:R** | minimum 1.5 | lower than core — mechanism is win-rate driven not magnitude |

**Time stop is critical.** If the bounce doesn't materialize in 3-5d, the thesis is broken. Holding longer = letting a losing trade fester.

## Sizing

- **Base**: half-Kelly per sleeve
- **Regime cap**: 25% portfolio max (choppy regime → moderate confidence)
- **Stacks with Sharpe-tilt** (item #5) and core Kelly stack

Setup has higher base win rate (~60-65%) than core but lower magnitude — sizing reflects that.

---

## Bypasses applied

| Gate | Status | Why |
|---|---|---|
| `entry_quality` | **BYPASS (when EXTENDED-DOWN)** | We WANT extended-down — that's the trigger. Otherwise this gate kills every mean-reversion entry. |
| `fund_adequacy` | **NOT bypassed** | Quality matters — junk stocks bounce less reliably. |
| `regime_gate` | **NOT bypassed** | Sleeve already excludes risk_off/panic via own regime filter. |
| `tail_loss_filter` | **NOT bypassed** | Star rating quality check still applies. |
| `system_circuit_breaker` | **NOT bypassed** | Macro blackout halts entries. |
| `rolling_sharpe_kill` | **NOT bypassed** | Safety net always wins. |

---

## Validation plan

### Phase 1 — paper-shadow (WEEK 1-2)
- `_enabled: false` to start
- Once flipped: signals tag `setup_family = "Mean Reversion"` with WATCH_MEANREV verdict
- Pass criteria: ≥ 8 signals in any 14d window, hypothetical PF ≥ 1.3, win rate ≥ 55%

### Phase 2 — half-size live (after Phase 1 passes)
- Promote to real BUY at quarter-Kelly × 0.5 (half-size)
- Observe 21-30d
- Pass: Sharpe per trade ≥ 0.25, time-stop discipline maintained

### Phase 3 — full-size (after Phase 2 passes)
- Per-config sizing (half-Kelly × regime cap)

### Kill criteria
- Rolling-Sharpe < -0.5 on n=15 fired signals
- WR < 50% on n=15 (mechanism breaks below coinflip)
- Avg loss > 1.5× avg win (size discipline broken)

---

## Mechanism hypothesis (Principle 2)

```python
MECHANISM_HYPOTHESES["Mean Reversion"] = (
    "In choppy regime with long-term uptrend intact (price > EMA200), "
    "RSI < 30 reflects emotional / forced selling, not fundamental "
    "damage. Liquidity providers earn premium absorbing flow; prices "
    "revert to short-term mean over 3-5d. Mechanism is statistical "
    "(Jegadeesh 1990, Lehmann 1990); fails in strong trends and panic."
)
```

## Risks

| Risk | Mitigation |
|---|---|
| Falling-knife (no real bounce) | EMA200 floor + time-stop 3-5d |
| Earnings catalyst causes oversold | 7d earnings buffer |
| Capitulation continues (regime shift) | regime gate (no fires in risk_off / panic) |
| Mean reversion erosion | Phase 1/2 validation + edge-erosion radar (item #4) |
| Crowded trade | Watch RVOL — if every retail screen shows the same RSI<30 list, fade size |

## What this sleeve does NOT do

- Does **NOT** short overbought (separate strategy if ever built)
- Does **NOT** average down — single entry, single stop, single time-stop
- Does **NOT** hold > 5 days regardless of P&L
- Does **NOT** fire on sub-$10M ADV names (liquidity matters for tight stops)

## Reference documents

| Doc | Purpose |
|---|---|
| docs/choice_c_decision.md | Sleeve roadmap |
| docs/strategy_momentum_continuation.md | Sibling sleeve template |
| docs/strategy_defensive_rotation.md | Sibling sleeve template |
| config/config.json :: mean_reversion_sleeve | Live config |
| analysis.py :: _detect_mean_reversion | Detector |

---

## Open items

| ID | Item | Status |
|---|---|---|
| MEANREV-1 | Design doc (this file) | DONE 2026-05-14 |
| MEANREV-2 | Config block | DONE 2026-05-14 |
| MEANREV-3 | Detector function | DONE 2026-05-14 |
| MEANREV-4 | Wire into analyze_ticker | DONE 2026-05-14 |
| MEANREV-5 | Decision engine bypass (entry_quality) | DONE 2026-05-14 |
| MEANREV-6 | Smoke test + commit | DONE 2026-05-14 |
| MEANREV-7 | Phase 1 paper validation | PENDING — enable in choppy regime |
| MEANREV-8 | Phase 2 half-size live | PENDING |
| MEANREV-9 | Phase 3 full-size | PENDING |
