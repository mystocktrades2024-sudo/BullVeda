# Strategy — Pre-FOMC Drift Overlay

**Status**: SHIPPED 2026-05-14 (Phase 1 paper validation pending)
**Type**: **OVERLAY**, not a sleeve — modifies sizing of existing BUYs
**Mechanism reference**: Lucca-Moench 2015 NY Fed Staff Report

---

## One-sentence mechanism

In the 24 hours BEFORE each scheduled FOMC announcement, the S&P 500
drifts upward — historically accounting for **~80% of pre-2008 equity
premium** over the FOMC cycle. The effect persists post-2008 but at
reduced magnitude (~50%).

This is the **most documented calendar anomaly in macro literature**.
Lucca-Moench published in Journal of Finance 2015, replicated in
multiple subsequent studies. Mechanism: pre-announcement positioning by
informed traders + reduced uncertainty leading to lower risk premium
demand on the day before.

## Why it's an OVERLAY, not a sleeve

Pre-FOMC drift isn't a stock-specific signal — it's a **time-window
multiplier** that increases the expected value of LONG SPY-correlated
positions in the 24h pre-FOMC. It applies to ALL existing BUY signals:
- Pullback to Value
- Momentum Continuation
- PEAD
- Mean Reversion
- Insider Cluster
- ESP Play

Implementation: a sizing multiplier that fires on the trading day
BEFORE any FOMC date. Multiplies all BUY-direction sizing by 1.25-1.5×
(configurable). Doesn't generate new signals, doesn't change setup
classification.

---

## Trigger (single condition)

| Condition | Detail |
|---|---|
| Today is `T-1` to FOMC date | i.e., today is the trading day immediately before a scheduled FOMC announcement |
| Position direction = LONG | Shorts don't get the drift bonus (asymmetric mechanism) |
| `prefomc_drift_overlay._enabled = True` | Config flag |

Other conditions:
- ONLY scheduled FOMC dates (not emergency / unscheduled — different mechanism)
- ONLY applies to NEW entries (existing positions not resized mid-stream)

---

## Action when fired

For every BUY (direction=long) on the FOMC-eve trading day:

```python
sizing_multiplier *= prefomc_drift_overlay.size_boost_mult  # default 1.25
```

This is on top of all other size multipliers (kelly, regime, Sharpe-tilt).

### Conservative sizing constraints

- Boost is CAPPED at the regime's `max_size_pct`
- If portfolio already at max gross exposure, boost is suppressed
- Slack message logs the FOMC-eve event when overlay fires

---

## Pre-FOMC ramp confidence (informational)

The overlay surfaces a `prefomc_drift_status` field on the bundle:

```json
{
  "active": true,
  "fomc_date": "2026-06-17",
  "trading_days_until": 0,
  "size_boost_mult": 1.25,
  "applied_to_n_buys": 4,
  "mechanism_note": "Lucca-Moench 2015 — pre-FOMC drift accounts for ~80% of pre-2008 equity premium"
}
```

Dashboard banner can show "PRE-FOMC DRIFT ACTIVE — BUY sizing 1.25×"
to alert the user.

---

## What this overlay does NOT do

- Does **NOT** create new signals (it's a multiplier on existing ones)
- Does **NOT** apply to short positions
- Does **NOT** override system_circuit_breaker / rolling_sharpe_kill safety nets
- Does **NOT** apply on emergency / unscheduled FOMC events (different microstructure)
- Does **NOT** apply on FOMC day-of (event itself blocked by macro_blackout)

---

## Validation plan

### Phase 1 — paper observation (paper-validation across next 2-3 FOMC events)
- Pass: BUY count on FOMC-eve consistently elevated, boost multiplier reflected in trade plans
- Verify: dashboard banner appears when overlay active

### Phase 2 — half-impact live
- Start with `size_boost_mult: 1.15` (half of designed boost) for 2 cycles
- Pass: positive expectancy vs non-FOMC-eve baseline

### Phase 3 — full-impact
- Promote to `size_boost_mult: 1.25` per design

---

## Risks

| Risk | Mitigation |
|---|---|
| Effect erosion post-2008 (well-documented, less alpha now) | Phase 2/3 validation catches if mechanism is dead |
| Hawkish/dovish surprise crashes the drift | Macro blackout still blocks day-of entries |
| FOMC date moves / emergency cuts | Only scheduled FOMC dates in calendar |
| Crowded trade (every fund knows about Lucca-Moench) | Effect may be priced in; smaller magnitude expected |

## Mechanism hypothesis

```python
MECHANISM_HYPOTHESES["Pre-FOMC Drift"] = (
    "Lucca-Moench 2015: SPY drifts up 24h before scheduled FOMC announcements; "
    "accounted for ~80% of pre-2008 equity premium, ~50% post-2008. Mechanism: "
    "pre-announcement informed-trader positioning + risk premium decay. "
    "Overlay (not sleeve) — multiplies sizing of existing BUY signals."
)
```
