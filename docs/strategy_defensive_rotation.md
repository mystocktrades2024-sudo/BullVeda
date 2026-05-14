# Strategy — Defensive Rotation Sleeve

**Status**: DESIGNED 2026-05-14, Phase 1 paper validation pending
**Closes**: bear regime gap in Choice C roster (no longs in risk_off/panic = no income)
**Spec author**: SwingTrade quant team (CLAUDE.md mindset)

---

## One-sentence mechanism

When growth equities de-rate (SPY < 50EMA + breadth deteriorating),
institutional capital rotates into defensive sectors (utilities,
consumer staples, healthcare) with low beta and stable cash flows —
producing 5-15% outperformance vs SPY over 10-30 day holds.

This is the **flight-to-safety bid**. Not theory — Federal Reserve flow-of-funds data, ICI fund flows, and decades of CRSP returns all show defensive sectors outperform during SPY drawdowns ≥ 5%.

## Why now

| Roster slot | Mechanism | Status |
|---|---|---|
| Pullback to Value | Buy retracement to support | LIVE (choppy regime) |
| Momentum Continuation | Buy strength + ADX + Sharpe ≥1.5 | ACTIVATED 2026-05-14 (trending) |
| **Defensive Rotation** | **Buy defensives during SPY < 50EMA** | **THIS DOC (bear)** |
| Mean Reversion | Buy oversold (RSI < 30) | Designed only (choppy alt) |
| PEAD / Catalyst | Buy post-earnings beat + revisions | Designed only (all regimes) |

The article's bar (Sharpe ≥ 1.5 across all 3 regimes) is **mathematically impossible** without a bear sleeve. We currently go to cash in risk_off — that's defensive, but generates 0 Sharpe contribution.

---

## Eligible universe (curated whitelist)

Sleeve only fires on these tickers. Rationale: defensive thesis is about SECTOR exposure, not stock-picking within sectors.

### Tier 1 — sector ETFs (preferred, lower-friction)
| Ticker | Sector | Beta | Notes |
|---|---|---|---|
| **XLU** | Utilities | ~0.45 | Pure defensive — rates-sensitive but lowest beta |
| **XLP** | Consumer Staples | ~0.60 | Daily-purchase products, inelastic demand |
| **XLV** | Healthcare | ~0.75 | Largest defensive ETF, broad exposure |
| **IEF** | 7-10y Treasury | ~−0.20 | Negative-beta flight asset |
| **TLT** | 20+y Treasury | ~−0.50 | Stronger flight-to-quality bid, more rates-sensitive |
| **GLD** | Gold | ~0.10 | Real-asset flight, dollar-correlation matters |

### Tier 2 — individual defensives (optional, larger account adds diversification)
| Ticker | Sector | Notes |
|---|---|---|
| **JNJ, PG, KO, PEP, WMT, COST** | Staples | Mega-cap dividend payers |
| **DUK, SO, NEE, AEP, EXC** | Utilities | Regulated utility moats |
| **MRK, ABBV, LLY, UNH, PFE** | Healthcare | Pharma + healthcare services |
| **VZ, T** | Telecom | Yield-heavy, less growth-correlated |

Curated to ~25 names. Avoids opening the door to "buy anything that's down."

---

## Triggers (all must be true)

| Gate | Condition | Why |
|---|---|---|
| **Universe** | Ticker in whitelist above | Sleeve thesis is sector-based |
| **Regime** | In `risk_off_trending` OR `panic` OR (`risk_on_choppy` AND SPY below 50EMA) | When defensive flow is institutionally active |
| **SPY 50EMA break** | SPY < SPY-EMA50 | Confirms growth de-rate; no flight without it |
| **RS vs SPY (21d)** | Ticker outperforming SPY by ≥ 0% | Don't fight the trend — defensive must be working NOW |
| **Beta** | < 1.0 (informational, not gating) | Defensive characteristic check |
| **Volatility** | ATR/price < 4% | Defensives shouldn't be choppy on entry |

No earnings filter — defensive ETFs don't have earnings; Tier-2 individuals are large-cap and the 7-day earnings rule already applies.

---

## Trade plan (defensive-specific)

| Field | Value | vs core swing |
|---|---|---|
| **Stop** | 1.0 ATR (close-based) | tighter than core 1.25 ATR — defensives don't whip |
| **Stop type** | **HARD: SPY reclaims 50EMA** | regime-exit; thesis broken |
| **Target 1** | +3% | modest — defensives don't moonshot |
| **Target 2** | +6% | |
| **Target 3** | trail at 0.5 ATR after +1.5% activation | |
| **Hold** | 10-30 trading days max | sector rotation timescale, not swing |
| **R:R** | minimum 2.0 (lower than core 3.0) | mechanism is steady, not asymmetric |

## Sizing

- **Base**: half-Kelly per sleeve
- **Per-regime size cap**:
  - `risk_on_choppy` (warm-up regime): 15% portfolio max
  - `risk_off_trending`: 35% portfolio max
  - `panic`: 50% portfolio max (defense is the play)
- Stacks with Sharpe-tilt (item #5) and core kelly stack

Mean expected: 5-15% of portfolio per signal at $5K, scales linearly.

---

## Bypasses applied

| Gate | Status | Why |
|---|---|---|
| `regime_gate` (no-longs-in-risk-off) | **BYPASS** | The whole point — sleeve is built FOR risk_off |
| `entry_quality` | **BYPASS** | Defensive doesn't care about FRESH/PULLBACK — sector flow is the signal |
| `fund_adequacy` | **BYPASS** | ETFs lack classical fundamentals |
| `tail_loss_filter` (stars=3) | **NOT bypassed** | Quality star rating still applies |
| `system_circuit_breaker` | **NOT bypassed** | Macro blackout days still halt entries |
| `rolling_sharpe_kill` | **NOT bypassed** | System safety net always active |

---

## Validation plan

### Phase 1 — paper-shadow (WEEK 1-2)
- `_enabled: false` to start (no signal emission)
- Once enabled, signals tag `setup_family = "Defensive Rotation"` with `WATCH_DEFENSIVE` verdict
- Need a regime where sleeve can fire — wait for `risk_off_trending` or panic episode
- Pass criteria: ≥3 signals fire in any qualifying 14d window, hypothetical max DD < 5%

### Phase 2 — half-size live (after Phase 1 passes)
- Promote to real BUY at quarter-Kelly × 0.5 (half-size)
- Observe 21-30d during applicable regime
- Pass: Sharpe per trade ≥ 0.3, combined system Sharpe higher than baseline-without-defensive

### Phase 3 — full-size (after Phase 2 passes)
- Per-config sizing (half-Kelly × regime cap)

### Kill criteria
- Rolling-Sharpe < -0.5 on n=10 fired signals
- Defensive sleeve PF < 0.8 over rolling 30d window
- Max DD breach 8% on any single signal

---

## Mechanism hypothesis (Principle 2 enforcement)

```python
MECHANISM_HYPOTHESES["Defensive Rotation"] = (
    "When SPY < 50EMA + breadth deteriorating, institutional capital "
    "rotates from growth into low-beta defensive sectors (utilities, "
    "staples, healthcare). Beta-rebalancing flow produces 5-15% "
    "outperformance over 10-30d holds. Mechanism is sector-rotation, "
    "not stock-picking."
)
```

## Risks

| Risk | Mitigation |
|---|---|
| False-positive regime read | 2-bar confirmation already in regime classifier; SPY 50EMA must hold closed-below |
| Rate shock devastates utilities | XLU specifically — accept residual risk, regime-exit kicks in on broader risk-off reversal |
| Crowded trade signal | Monitor defensive ETF AUM flows — fade size if XLU AUM up >30% MoM |
| Defensive AAII outperformance fades | Phase 2 paper validation catches this before live capital |

## What this sleeve does NOT do

- Does **NOT** short — purely long defensive exposure
- Does **NOT** trade individual high-beta stocks pretending to be defensive
- Does **NOT** trade options or VIX products (separate sleeve if/when designed)
- Does **NOT** stay levered into a defensive trade across regime change

## Reference documents

| Doc | Purpose |
|---|---|
| docs/choice_c_decision.md | Sleeve roadmap |
| docs/strategy_momentum_continuation.md | Sibling sleeve (template) |
| config/config.json :: defensive_rotation_sleeve | Live config |
| analysis.py :: _detect_defensive_rotation | Detector |

---

## Open items

| ID | Item | Status |
|---|---|---|
| DEFROT-1 | Design doc (this file) | DONE 2026-05-14 |
| DEFROT-2 | Config block | DONE 2026-05-14 |
| DEFROT-3 | Detector function | DONE 2026-05-14 |
| DEFROT-4 | Wire into analyze_ticker | DONE 2026-05-14 |
| DEFROT-5 | Decision engine bypasses | DONE 2026-05-14 |
| DEFROT-6 | Universe coverage (ETFs in scan) | DONE 2026-05-14 |
| DEFROT-7 | Smoke test + commit | DONE 2026-05-14 |
| DEFROT-8 | Phase 1 paper validation | PENDING — needs qualifying regime |
| DEFROT-9 | Phase 2 half-size live | PENDING |
| DEFROT-10 | Phase 3 full-size | PENDING |
