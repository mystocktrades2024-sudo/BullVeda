# Runbook — Loss Streak Investigation

**Use when**: rolling-Sharpe kill fires OR you observe 5+ consecutive losing closed BUYs OR weekly diagnostics flag regression.

**Tool**: `scripts/loss_streak_investigation.py`

**Pre-requisite**: data hygiene complete (alpha_vs_spy, exit_reason, regime4 populated). Verified via `signal_tracker.update_outcomes()` — runs automatically on every scan.

---

## Step 1 — Run the script

```bash
cd "/Volumes/MyMacDisk/Claude Skills/SwingTrade"
python3 scripts/loss_streak_investigation.py
```

Output goes to stdout AND `cache/loss_streak_investigation_<DATE>.json`.

---

## Step 2 — Read the AGGREGATE COMPARISON block

```
metric              recent20      baseline     delta
n                         20            81
wr                       0.10          0.22    -0.12
avg_pnl                 -3.46         -2.11    -1.35
sharpe_per_trade        -0.45         -0.24    -0.21
max_loss               -19.79        -24.48    +4.69
```

**Decision tree:**
- `recent20 sharpe ≥ baseline`: false alarm. Continue normal operations.
- `recent20 sharpe < baseline by < 0.10`: noise. Continue but monitor.
- `recent20 sharpe < baseline by ≥ 0.10`: **real regression — proceed to Step 3**.

---

## Step 3 — Read the DISTRIBUTION SKEW block

Look for over-representation of any dimension by ≥ 15pp vs baseline:

```
By regime4:
  risk_on_trending     55.0%    21.0%    +34.0pp ⚠️ over-rep
  risk_on_choppy        0.0%    11.1%    -11.1pp
```

This tells you WHERE the losses are concentrated.

**Decision tree by which dimension is over-represented:**

### regime4 over-rep
| Concentration | Likely cause | Action |
|---|---|---|
| risk_on_trending | Bull regime weakness (PF 1.00 known issue) | Don't act — known limitation. Push forward on momentum sleeve (docs/strategy_momentum_continuation.md). |
| risk_on_choppy | Edge erosion in our alpha cell | URGENT — re-run regime_sharpe_decomp. If choppy PF dropped vs prior, escalate. |
| risk_off_* | Should never happen — regime gate blocks longs | Investigate why regime gate didn't fire. |

### setup over-rep
| Concentration | Likely cause | Action |
|---|---|---|
| Trend Continuation | Setup family decay | Re-validate Wilson LB on last 30 trades. Demote multiplier if WLB < 0.30. |
| Breakout Expansion | If in trending regime — already addressed by FAMILY-KILL (commit aa5d8f27c). Verify gate fired. |
| 10-Week Pullback | Currently boosted 1.5×. Re-validate; demote to 1.0× if WLB < 0.30 on n ≥ 30. |
| Other | Stratify further by score band. |

### entry_quality over-rep
| Concentration | Likely cause | Action |
|---|---|---|
| MISSED in trending | Aggregate "MISSED is profitable" finding may not hold in trending regime | Run regime × entry_quality stratification |
| FRESH | Small-sample noise — n=20 always has wide bands | Likely false alarm |
| EXTENDED in trending | Today's deferred ENTRY-Q-AB experiment relevant | Investigate mechanism |

### exit_reason over-rep
| Concentration | Likely cause | Action |
|---|---|---|
| stop_hit | Stops too tight OR market environment | Check ALPHA vs SPY block — if market down, environment. If alpha negative, stops issue. |
| time_stop_loss | Trades not maturing — wrong holding period | Consider holding period extension for current regime |
| time_stop_win | Stops not triggered — likely OK |
| ema21_no_move_2d | Specific to EMA21 Pullback — already killed | Verify kill is firing |

---

## Step 4 — Read the ALPHA vs SPY block

```
recent-20 avg alpha vs SPY: -1.50%
recent-20 avg SPY return:    +0.30%
recent-20 avg pnl:           -3.46%
```

**Decision tree:**
- `SPY ret negative AND alpha ~ 0`: market down — losses are environment, NOT strategy. **Don't act on strategy.**
- `SPY ret positive AND pnl negative`: strategy underperformance. **Strategy issue — drill into regime + setup.**
- `SPY ret ~ 0 AND alpha negative`: strategy underperformance in flat market. **Worst signal — strategy is broken right now.**

---

## Step 5 — Read INDIVIDUAL TRADES block

Look at the worst 3-5 losses:
- Same ticker repeating? (e.g., CAVA appearing twice — may be over-allocated to one name)
- Same setup? (already covered by Step 3)
- Same regime? (already covered)
- Cluster by date? (single bad day = market event, not strategy)

If a single day produces multiple large losses, check macro_calendar.json for events that day. Could indicate macro blackout rule needs widening.

---

## Step 6 — Decide action

### Always do:
- Save the JSON snapshot for trend tracking
- Document findings in commit message if shipping a change

### Conditional:
| Trigger | Action |
|---|---|
| Single-regime over-rep + matches known limitation | No action (don't tune on noise) |
| Setup-family WLB drops below 0.30 on n ≥ 30 | Demote setup_score_multiplier per evidence |
| Choppy regime degrades | Consider rolling-Sharpe kill threshold tightening |
| Recent stop_hit pattern + alpha ~ 0 | Consider stop_atr_multiple loosening (1.25 → 1.5) |
| Alpha consistently negative vs flat SPY | Strategy degradation — escalate to Choice C (full roster) discussion |

### Never do:
- Tune setup multipliers on n < 30 (CLAUDE.md principle 1)
- Override rolling-Sharpe kill if it fires (CLAUDE.md principle 17)
- Roll back gates because of one bad week

---

## Related tools

| Tool | Purpose |
|---|---|
| `scripts/regime_sharpe_decomp.py` | Per-regime × per-setup stats — the strategic view |
| `scripts/loss_streak_investigation.py` | Recent 20 vs baseline — the tactical view |
| `scripts/sharpe_screener.py` | Per-stock Sharpe — for ticker-level analysis |
| `scripts/killed_setup_stratification.py` | Within killed setups, find profitable sub-segments |
| `scripts/weekly_diagnostics.sh` | Sunday auto-run of all of the above + Slack alert |
| `scripts/backfill_signal_log_regime.py` | One-time regime backfill from scan logs |

---

## Quick-reference: when to NOT investigate

- Single losing trade — noise. n=1 is meaningless.
- 2-3 losses in a row — still noise. Flat distributions have streaks.
- Macro blackout day (CPI, FOMC) — system blocks BUYs anyway. Not a strategy event.
- During a fresh deploy — wait 30 days for sample to accumulate before diagnosing.

---

## Last updated

2026-05-13 — created after data hygiene work (commit 17bfc8a44) made all required fields reliably available.
