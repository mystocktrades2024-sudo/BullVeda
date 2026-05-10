---
name: swing-strategies
description: Operational runbook for the V2 dashboard Strategies tab — multi-strategy alpha showcase with regime-aware ACTIVE/DEFERRED/PLANNED states, blended WR/PF, recent picks per scanner. Use when debugging strategy state, regime gating, or the recent-picks roster.
---

# Strategies tab — operational skill

## Source
- Module: `infra/prototype/tabs/strategies/strategies.js` (extracted 2026-05-09)
- Per-folder rules: `infra/prototype/tabs/strategies/CLAUDE.md`
- STRATEGIES const: `dashboard.html` ~line 6517 (large data array, ~100 lines)

## How to regen
The Strategies tab is mostly static — only `tickers_by_strategy` and `regime` come from data.json.
```
# After a scan:
python3 infra/prototype/build_data.py
```

## How strategy state is computed
- `ACTIVE` — `s.status === 'ACTIVE'` AND current regime is in `s.regimes[]`
- `DEFERRED` — `ACTIVE` but regime mismatch (paused this regime)
- `PLANNED` — code stub, not yet wired into nightly scan

Regime keys: RoT (Risk-On Trending), RoC (Risk-On Choppy), Off (Risk-Off Trending), Panic.

## Strategy aliases
The `STRATEGY_ALIASES` map (in module) bridges display names → upstream `tickers_by_strategy` keys. Example: "Volume Breakout" pulls from both "Volume Breakout" AND "EMA21 Pullback" arrays. Update this map when renaming a scanner.

## Common scenarios
- All cards DEFERRED → regime gating expected; check `DATA.regime.regime4`. If it's wrong, fix upstream regime detection in `regime_detector.py`.
- Empty recent-picks roster for a known-active scanner → check `DATA.performance.tickers_by_strategy` keys; alias mismatch likely.
- "Best edge" / "Thinnest sample" wrong → driven by WR midpoint parsing. Check that `s.wr` strings match `\d+-\d+%` regex.

## Plan reference
`~/.claude/plans/wiggly-popping-pearl.md`
