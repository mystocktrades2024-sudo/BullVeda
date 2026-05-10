---
name: swing-performance
description: Operational runbook for the V2 dashboard Performance tab — system edge verdict, P&L tiles ($10K notional default), Setup Family Podium (Wilson CI), Score Calibration bars, auto-generated action items, Trade Journal aggregate by setup. Use when debugging the verdict, fixing $-PnL math, or interpreting score-calibration drift.
---

# Performance tab — operational skill

## Source
- Module: `infra/prototype/tabs/performance/performance.js` (extracted 2026-05-09; 368 lines — biggest single renderer)
- Per-folder rules: `infra/prototype/tabs/performance/CLAUDE.md`
- Data builders: `build_signal_log.py`, `build_setup_attribution.py`, `portfolio_tracker.py`

## How to regen
```
python3 build_signal_log.py      # → cache/signal_log_enriched.json
python3 build_setup_attribution.py
python3 infra/prototype/build_data.py
```

## Edge verdict thresholds
- **STRONG EDGE**: WR ≥ 55% AND MFE_avg / |MAE_avg| ≥ 1.5
- **MARGINAL EDGE**: WR ≥ 45%
- **NO EDGE**: WR < 45%
- **AWAITING DATA**: closed < 30

These are duplicated in `decision_engine.py` — keep them in sync if you edit.

## P&L sizing
- Default: `$10,000` per signal
- Override: `window.PERF_NOTIONAL = 5000` in browser console
- This is a MOCK sizing for visualization only — actual sizing in production trades comes from `decision_engine.py:size_position()` which uses risk-based 0.75% × equity.

## Wilson 95% CI (Setup Family Podium)
- Inlined in module as `_wilsonCI(wins, n)` — was a tab-private helper
- z = 1.96, returns `{lo, hi}` for binomial proportion
- N < 30 → CI is wide; module shows `±X%` derived from `(hi - lo) * 50` (half-width as percentage)

## Score calibration interpretation
- If 90+ buckets win at higher rates than 60-69 buckets → score is predictive
- If flat → score is noise, recalibrate weights in `analysis.py`
- Surfaces `Need 30+ closed trades` warning when sample is too thin

## Common scenarios
- Trade Journal empty → portfolio_tracker hasn't recorded closures, OR `cache/last_bundle.json.portfolio.closed` is empty.
- "Setup P&L Ranking — Live" instead of Winners Podium → `setup_attribution` is empty (no closed-trade data yet); falls back to open-position ranking.
- Action items section blank with no entries → `closed === 0` AND no per-strategy outliers found.

## Plan reference
`~/.claude/plans/wiggly-popping-pearl.md`
