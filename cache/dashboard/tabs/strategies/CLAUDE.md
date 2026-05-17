# Strategies tab

Strategy Engine dashboard — multi-strategy alpha showcase (active scanners with WR/PF/N/edge), regime-aware filtering, recent picks per strategy.

## Data source
- `DATA.performance.tickers_by_strategy` — recent picks grouped by setup family
- `DATA.regime.regime4` — current regime (drives DEFERRED state)
- `DATA.setup_counts`, `DATA.verdict_counts` — distribution bars

## DOM targets
`strategiesBanner`, `strategiesList`, `setupCountsBody`, `verdictCountsBody`.

## CSS prefix
`.se-*`, `.strat-*` (per-card classes).

## Imports allowed
- `core/shared.js`: `getData`, `$`.

## External deps (window.*)
- `STRATEGIES` const — large data array (~100 lines). Defined in `dashboard.html` and exposed via `window.STRATEGIES = STRATEGIES`.
- `seFilterStrategies(filter, btn)` — chip click handler. Stays in `dashboard.html`.
- `STRATEGY_ALIASES` — local to module (mapping of display name → aliases for `tickers_by_strategy` lookup).

## Dispose
No-op.

## Common failure modes
- Banner shows blank `Blended WR` → no active strategies have win-rate strings; check `STRATEGIES` const for malformed entries.
- All cards say DEFERRED → regime mismatch (e.g., currently in Risk-Off, but most strategies tagged for Risk-On Trending). Expected behavior.
- Filter chips don't fire → `seFilterStrategies` not on window. Check `dashboard.html` line ~6729.
