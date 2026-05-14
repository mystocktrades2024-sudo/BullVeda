# Strategy — PEAD (Post-Earnings Announcement Drift) Sleeve

**Status**: DESIGNED 2026-05-14, Phase 1 paper validation pending
**Closes**: catalyst-driven gap in Choice C — fires in ALL regimes (catalyst trumps regime)
**Spec author**: SwingTrade quant team (CLAUDE.md mindset)

---

## One-sentence mechanism

Stocks that beat earnings AND get positive analyst revisions exhibit
60-day price drift in the direction of the surprise, because the market
under-reacts to earnings information initially — analysts revise
estimates slowly over weeks, creating a persistent bid.

This is the **most-documented anomaly in academic finance**. Bernard-Thomas (1989), Ball-Brown (1968), Foster-Olsen-Shevlin (1984), Chordia-Shivakumar (2006). Mechanism is well-understood: institutional analyst networks revise on a 4-8 week cycle, and the drift period correlates with revision velocity.

## Why now

| Sleeve | Mechanism | Fires when |
|---|---|---|
| Pullback to Value | Buy retracement | choppy |
| Momentum Continuation | Buy strength | trending |
| Defensive Rotation | Buy defensives | risk_off / panic |
| Mean Reversion | Buy oversold | choppy |
| **PEAD** | **Buy post-earnings beat + revisions** | **all regimes** |

PEAD is catalyst-driven; regime conditions matter less. It's the **all-weather sleeve** in the roster. Per CLAUDE.md principle 14 (catalyst-driven priority): catalyst-based mechanisms produce more alpha than pure technical, because the information edge is real.

---

## Triggers (all must be true)

| Gate | Condition | Why |
|---|---|---|
| **Days since earnings** | 1-3 trading days post-report | Fresh PEAD — drift just started |
| **EPS surprise** | ≥ +5% beat | Material upside surprise |
| **Revenue surprise** | ≥ +2% beat | Both lines beat (avoid one-line beats) |
| **Price reaction** | Gap up ≥ +3% on report day | Market acknowledges beat |
| **Analyst revisions** | ≥ 2 upward revisions OR consensus PT raised | Confirmation institutions are catching up |
| **Min score** | ≥ 55 | Composite quality floor (lower than other sleeves — catalyst dominates) |
| **Liquidity** | $10M+ daily $ vol | Tight stops require liquidity |

Notably absent: **regime gate.** PEAD fires in all regimes including risk_off (with reduced size). Catalyst alpha is regime-independent.

---

## Trade plan (PEAD-specific)

| Field | Value | vs core swing |
|---|---|---|
| **Stop** | 1.0 ATR | tight — catalyst integrity test |
| **Hard exit** | Below post-report gap level | Catalyst broken = thesis broken |
| **Target 1** | +5% | first profit-take |
| **Target 2** | +10% | drift target — academic literature: avg 5-15% over 60d |
| **Target 3** | trail at 0.5 ATR after +5% activation | let runners drift |
| **Hold** | 10-30 trading days max | drift window per literature |
| **R:R** | minimum 2.5 | catalyst-driven setups have higher win rate than core |

## Sizing

- **Base**: full Kelly (highest evidence base of any sleeve)
- **Regime cap**:
  - `risk_on_trending` / `bull`: 100%
  - `risk_on_choppy`: 75%
  - `risk_off_trending`: 50%
  - `panic`: 25% (still fires — catalyst alpha persists)
- Stacks with Sharpe-tilt (item #5)

PEAD gets the largest sizing in the roster because the academic edge is strongest.

---

## Bypasses applied

| Gate | Status | Why |
|---|---|---|
| `regime_gate` (no-longs-in-risk-off) | **BYPASS** | Catalyst alpha is regime-independent (well-documented) |
| `entry_quality` | **BYPASS** | Gap-up entries ARE the trigger — EXTENDED is correct |
| `earnings_blackout` | **BYPASS (post-report only)** | Sleeve fires DURING the catalyst, not into it |
| `fund_adequacy` | **NOT bypassed** | Quality still matters even with catalyst |
| `tail_loss_filter` | **NOT bypassed** | Star rating discipline |
| `system_circuit_breaker` | **NOT bypassed** | Macro blackout halts entries |
| `rolling_sharpe_kill` | **NOT bypassed** | System safety net |

---

## Validation plan

### Phase 1 — paper-shadow (WEEK 1-3)
- `_enabled: false` to start
- Signals tag `setup_family = "PEAD"`, verdict `WATCH_PEAD`
- Wait for earnings season for signal density
- Pass criteria: ≥ 10 signals in 21d window, hypothetical PF ≥ 1.5, WR ≥ 55%

### Phase 2 — half-size live
- Promote to BUY at half-Kelly × 0.5
- Pass: Sharpe per trade ≥ 0.35

### Phase 3 — full-size

### Kill criteria
- Rolling-Sharpe < -0.5 on n=20
- Drift period appears compressed (avg hold < 5d successful exits)

---

## Mechanism hypothesis (Principle 2)

```python
MECHANISM_HYPOTHESES["PEAD"] = (
    "Post-earnings announcement drift — markets under-react to "
    "earnings surprises (Bernard-Thomas 1989, Ball-Brown 1968). "
    "Beat + positive revisions produce 5-15% drift over 60d. "
    "Mechanism: institutional analysts revise on 4-8 week cycle; "
    "drift correlates with revision velocity. Catalyst alpha is "
    "regime-independent — fires in all regimes with reduced size in panic."
)
```

## Risks

| Risk | Mitigation |
|---|---|
| Gap-fill before drift (catalyst rejected) | Hard stop below post-report gap level |
| Analyst revisions stall | Time-stop at 30 trading days |
| Pre-announcement positioning unwinds post-report | Day 1-3 filter — only fire on fresh PEAD, not stale |
| Sector-wide earnings shock | Don't size larger than sector cap (existing limit applies) |

## Reference documents

| Doc | Purpose |
|---|---|
| docs/choice_c_decision.md | Sleeve roadmap |
| config/config.json :: pead_sleeve | Live config |
| analysis.py :: _detect_pead | Detector |

---

## Open items

| ID | Item | Status |
|---|---|---|
| PEAD-1 | Design doc (this file) | DONE 2026-05-14 |
| PEAD-2 | Config block | DONE 2026-05-14 |
| PEAD-3 | Detector function | DONE 2026-05-14 |
| PEAD-4 | Wire into analyze_ticker | DONE 2026-05-14 |
| PEAD-5 | Decision engine bypasses | DONE 2026-05-14 |
| PEAD-6 | Smoke test + commit | DONE 2026-05-14 |
| PEAD-7 | Phase 1 paper validation | PENDING — needs earnings season density |
