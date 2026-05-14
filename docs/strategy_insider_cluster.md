# Strategy — Insider Cluster Sleeve

**Status**: SHIPPED 2026-05-14 (Phase 1 paper validation pending)
**Closes**: information-edge gap (catalyst sleeve focused on insider asymmetry)
**Mechanism reference**: Bettis-Coles-Lemmon 2000, Cohen-Malloy-Pomorski 2012

---

## One-sentence mechanism

When 3+ company insiders (CEO/CFO/Director) make open-market purchases
totaling $200K+ within 30 days, they have material non-public information
that the market hasn't priced — stocks drift up 8-15% over the next
30-60 days as the information becomes public.

This is **the cleanest information asymmetry signal available**. Insiders
have a fiduciary duty NOT to trade on material info, but the SEC Form 4
disclosure pattern (timing + size + multi-insider clustering) reveals
they bought ahead of something material 60-65% of the time
(Bettis-Coles-Lemmon 2000, n=10,000+).

## Why now

We have insider data flowing through tier1_signals.insider_cluster already:
- Detection running
- Narrative populated ("22 insider buys in 30d (5+ = strong cluster)")
- Points contribution: +7 to composite score

But it's INFORMATIONAL ONLY (`apply_to_score: false` by default). Promoting
to a setup_family makes it a tradeable mechanism with its own sizing/stops/hold.

---

## Triggers (all must be true)

| Gate | Condition | Why |
|---|---|---|
| **Tier1 detected** | `tier1_signals.insider_cluster.detected == True` | Reuses existing 10-condition detector |
| **Cluster strength** | ≥ 3 buys (or 2 with CEO/CFO involvement) | Bettis-Coles-Lemmon n>=3 floor |
| **Min score** | ≥ 40 | Filter pure junk; catalyst dominates |
| **Liquidity** | $5M+ daily $ vol | Tighter than other sleeves; insider names often mid-cap |
| **Price > EMA50** | Yes | Don't catch falling knife (managers might buy into trend break) |

Notably absent: **regime gate.** Insider edge is regime-independent like PEAD.

---

## Trade plan (insider-specific)

| Field | Value | vs core swing |
|---|---|---|
| **Stop** | 1.0 ATR OR below EMA50 (whichever tighter) | EMA50 is the insider thesis line |
| **Target 1** | +5% | first profit-take |
| **Target 2** | +10% | drift target |
| **Target 3** | +15% | runner (academic literature avg) |
| **Trail** | +3% activate, 0.5 ATR | aggressive trail (insider info value decays fast) |
| **Hold** | 30-60d max | drift window per literature |
| **R:R** | minimum 2.0 | lower than core — mechanism is win-rate driven |

## Sizing

- **Base**: half-Kelly per sleeve
- **Regime cap**: 35% portfolio max (regime-agnostic but conservative)
- **Stacks with Sharpe-tilt** + core Kelly stack

---

## Bypasses applied

Same pattern as PEAD — catalyst-driven sleeves get the catalyst-sleeve bypass set:

| Gate | Bypass |
|---|---|
| `regime_gate` (no longs in risk_off/panic) | YES — insider edge is regime-independent |
| `entry_quality` | YES — insider buying often coincides with price weakness |
| `fund_adequacy` | YES — insider info > formal fundamental data |
| `decision_state` (MISSED) | YES — insider buying can land at any price level |
| `tail_loss_filter` (tier=0) | YES — score band doesn't capture catalyst mechanism |

NOT bypassed: `tail_loss_filter` (stars=3 quality), `rolling_sharpe_kill`,
`system_circuit_breaker` (macro/CB), `setup_score_multiplier` kills (won't apply
because setup_family is overridden to "Insider Cluster", not a killed setup).

---

## Validation plan

### Phase 1 — paper-shadow
- `_enabled: false` initially (just shipped, but enabled here for first observation)
- Pass criteria: ≥ 5 signals in 14d, hypothetical PF ≥ 1.4, WR ≥ 55%

### Phase 2 — half-size live

### Phase 3 — full-size

---

## Mechanism hypothesis

```python
MECHANISM_HYPOTHESES["Insider Cluster"] = (
    "Information asymmetry: when 3+ insiders make open-market purchases "
    "totaling $200K+ within 30d, they hold material non-public information. "
    "Stock drifts 8-15% over 30-60d as information becomes public. "
    "Bettis-Coles-Lemmon 2000, Cohen-Malloy-Pomorski 2012. "
    "Mechanism is regime-independent — fires in all regimes."
)
```
