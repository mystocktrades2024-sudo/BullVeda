# SMC Composite Score — Validation (#7)

**Harness:** `scripts/backtest_smc_score.py` — point-in-time replay. For each ticker,
score SMC on `bars[:t]` only (causal indicators, no lookahead) and measure realized
forward returns at t+5 / t+10 / t+20. Re-runnable any time (principle 11).

## Result (48 liquid names, ~1,250 samples, daily, ~2025–26 — a single bull-ish regime)

| Score band | n | 5d mean / wr | 10d mean / wr | 20d mean / wr |
|---|---|---|---|---|
| 65–80 | 911 | +0.54% / 53% | +0.89% / 52% | +2.10% / 52% |
| 80–100 | 334 | +0.49% / 51% | +1.40% / 53% | +4.00% / 55% |

```
corr(score, fwd-5d)  = -0.033
corr(score, fwd-10d) = -0.007
corr(score, fwd-20d) = +0.029
```

Bias × zone (fwd 10d): bull-premium **+1.32%** ≥ bull-discount **+1.09%**;
bear-premium +1.54% (wr 57%) ≥ bear-discount +0.53%.

## Findings (honest)
1. **The composite score is ~uncorrelated with forward returns** (corr ≈ 0). It ranks
   *structural cleanliness*, not expected return.
2. **The discount-bonus / premium-penalty is unsupported** in this regime — premium
   (momentum) outperformed discount (pullback). Consistent with the system-wide factor
   finding that momentum > mean-reversion in trend regimes.
3. There is a **weak 20-day tilt** (80–100 beats 65–80 at 20d), but it's noisy and
   absent at 5/10d.

## Decision
- **Do NOT overfit-retune the weights on this single regime** (principle 5 & 20). One
  bull-ish window is not evidence to flip the discount/premium logic.
- **Relabel the score honestly in the UI**: it is a *structure-quality* read, not a
  return forecast. Removed "Entry Grade" / "conviction" framing that implied prediction.
- **Re-run multi-regime** (include a risk-off / 2022-type window) before any weight
  change. That's the gate to either (a) tune or (b) keep as structural-only.

## Status
Score kept (transparent, bar-derived) but **presented as structure quality, with the
corr≈0 caveat surfaced**. Predictive tuning deferred pending multi-regime walk-forward.
