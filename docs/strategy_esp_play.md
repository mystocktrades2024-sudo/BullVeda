# Strategy — Earnings ESP Play Sleeve

**Status**: SHIPPED 2026-05-14 (Phase 1 paper validation pending)
**Closes**: P0 roadmap item — Zacks ESP data already flowing, no detector built
**Mechanism reference**: Zacks Investment Research — "Earnings ESP Filter"

---

## One-sentence mechanism

When Zacks Earnings ESP > 0 (most recent estimate above consensus) AND
Zacks Rank ≤ 3 AND earnings imminent (4-14 days), the stock has a
**~70% probability of beating earnings**. Enter 4-14d pre-earnings, exit
1d before report (pre-earnings drift only — no binary risk).

Documented by Zacks for 25+ years across 100,000+ earnings reports.

## Why now

This is a P0 roadmap item — data already arrives via Zacks per-ticker
enrichment, signal already detected (`r["esp_play"]`), but NO tradeable
sleeve exists. Just packaging it.

---

## Triggers (all must be true)

| Gate | Condition | Why |
|---|---|---|
| **Zacks ESP** | > 0 (most recent estimate above consensus) | Zacks' core filter — strong recent-estimate skew |
| **Zacks Rank** | ≤ 3 (Strong Buy / Buy / Hold) | Filter analyst-rated decliners |
| **Days to earnings** | 4-14 (NOT in 0-3 blackout) | Pre-earnings drift window; exits before binary risk |
| **Min score** | ≥ 50 | Composite quality floor |
| **Liquidity** | $10M+ daily $ vol | Tight stops require liquidity |

Notably absent: **regime gate.** ESP is regime-independent (catalyst).

## Two modes (config-flagged)

### Mode A: Pre-earnings drift only (DEFAULT — safer)
- Enter 4-14d before report
- **Exit 1d BEFORE report** (avoid binary risk)
- Capture pre-earnings drift (~3-5%)
- Hold: 3-13d max

### Mode B: Ride-through earnings (RISKIER — only if explicitly enabled)
- Enter 4-14d before report
- Hold through the print
- Capture full ESP edge (~70% beat = ~5-10% expected move)
- Hold: 5-21d max
- Requires `ride_through_earnings: true` in config (default false)

---

## Trade plan

| Field | Mode A | Mode B |
|---|---|---|
| **Stop** | 1.0 ATR | 1.0 ATR |
| **Hard exit** | Day before earnings (auto-exit) | Below entry × 0.95 post-report |
| **Target 1** | +3% | +5% |
| **Target 2** | +5% | +10% |
| **Target 3** | — | +15% |
| **Trail** | +2% activate, 0.5 ATR | +5% activate, 0.5 ATR |
| **Hold** | 3-13d (auto-exit pre-earnings) | 5-21d (drift + post-earnings) |
| **R:R** | 2.0 min | 2.5 min |

## Sizing

- **Mode A**: half-Kelly × 30% regime cap (lower — pre-earnings only)
- **Mode B**: quarter-Kelly × 25% regime cap (lower — binary risk)
- Default Mode A — safer for $5K paper account

---

## Bypasses applied (catalyst-sleeve pattern)

| Gate | Bypass |
|---|---|
| `regime_gate` (no longs in risk_off/panic) | YES — ESP regime-independent |
| `entry_quality` | YES — pre-earnings drift any entry |
| `fund_adequacy` | YES — ESP > fundamentals for short window |
| `decision_state` | YES — any decision_state |
| `tail_loss_filter` (tier=0) | YES — score band doesn't capture catalyst |
| `earnings_blackout` | **PARTIAL** — sleeve REQUIRES earn_days 4-14 (not in 0-3 hard block); blackout still blocks 0-3d |

NOT bypassed: tail_loss_filter (stars=3), rolling_sharpe_kill,
system_circuit_breaker (macro/CB).

---

## Validation plan

### Phase 1 — paper-shadow (next 14d)
- Mode A (default safer mode)
- Pass criteria: ≥ 8 signals in 14d, hypothetical PF ≥ 1.3, WR ≥ 60% (high bar — Zacks claims ~70%)

### Phase 2 — half-size live

### Phase 3 — full-size OR test Mode B

---

## Mechanism hypothesis

```python
MECHANISM_HYPOTHESES["ESP Play"] = (
    "Earnings ESP > 0 + Rank <= 3 = ~70% beat probability per Zacks data "
    "(25+ years, 100,000+ reports). Pre-earnings drift captures positive "
    "directional bias before the print. Mode A exits day-before to avoid "
    "binary risk; Mode B rides through for full edge."
)
```
