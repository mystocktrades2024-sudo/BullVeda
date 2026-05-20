# Phase-3 per-mode weight validation — 2026-05-19T11:11:12

**Status:** ⛔ FAIL

- Days: **30**
- Min score: **50**
- Universe: **top100**
- Top-N per day: **5**
- Hold days: **5**

## Per-pillar weights compared

| Pillar | Baseline (config.scoring_weights) | SWING | POSITION | INVESTMENT |
|---|---|---|---|---|
| trend_structure | 30 | 30.0 | 25.0 | 15.0 |
| rs_sector | 25 | 25.0 | 20.0 | 15.0 |
| catalyst_expansion | 20 | 25.0 | 20.0 | 10.0 |
| smart_money | 10 | 10.0 | 15.0 | 10.0 |
| quality_fundamentals | 5 | 5.0 | 15.0 | 45.0 |
| entry_rr | 10 | 5.0 | 5.0 | 5.0 |

## Backtest results

| metric | baseline | SWING | POSITION | INVESTMENT |
|---|---|---|---|---|
| total_trades | 4 | 4 | 4 | 4 |
| win_rate | 75.00 | 75.00 | 75.00 | 75.00 |
| profit_factor | 31.82 | 31.82 | 31.82 | 31.82 |
| total_return_pct | 6.20 | 6.20 | 6.20 | 6.20 |
| max_drawdown_pct | 0 | 0 | 0 | 0 |
| sharpe | 0.00 | 0.00 | 0.00 | 0.00 |
| avg_win_pct | 8.49 | 8.49 | 8.49 | 8.49 |
| avg_loss_pct | -0.80 | -0.80 | -0.80 | -0.80 |

## Pass/Fail criteria

Per `docs/per_mode_decisions_roadmap.md` Phase 3, revert flag if **any** mode shows:
- `profit_factor ≤ 1.0×` baseline  OR
- `win_rate ≤ baseline − 5pp`

## Verdict

⛔ **FAIL** — at least one mode degraded vs baseline:

- swing: PF 31.82 vs baseline 31.82 → 1.00× ≤ 1.0 (degrading)
- position: PF 31.82 vs baseline 31.82 → 1.00× ≤ 1.0 (degrading)
- investment: PF 31.82 vs baseline 31.82 → 1.00× ≤ 1.0 (degrading)

Action: revert by editing `config/config.json`:

```json
"per_mode_pillar_reweight": { "_enabled": false }
```

Or via env override in the next scan. The legacy single-composite scoring will resume immediately.
