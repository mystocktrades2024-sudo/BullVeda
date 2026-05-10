# Elite Picks tab

3 modes (Swing/Position/Invest) × 3 stages (BUY/WATCH/SHORT) = 9-cell grid. Top 5 picks per cell with conviction arc, factor-bar breakdown, why-confident + watch-out narratives, MC P(target/stop), CVaR, fwd Sharpe, earnings-days warning.

## Data source
- `DATA.elite_picks` — built by `build_elite_picks.py` (composite 8-factor scorer)
  - `.{Swing,Position,Invest}.{BUY,WATCH,SHORT}` arrays of pick dicts
  - `.meta.{computed_at, n_passing_hard_gates, n_candidates_evaluated, blocked, reason, note}`
- `.error` field if computation failed

## DOM targets
`elitePicksBody`, `elitePicksMeta`, sidebar `sbEliteCt`.

## CSS prefix
`.ep-*` (50+ classes — all owned here).

## Imports allowed
- `core/shared.js`: `getData`. (No `$` because module uses `document.getElementById` directly for one-off lookups.)

## External deps
None — module is fully self-contained including arc SVG, factor-bar, pick-card, cell renderers (`renderPickCard`, `renderCell`).

## Dispose
No-op.

## Common failure modes
- Banner shows "🔴 SUPPRESSED" → `ep.meta.blocked = true` (system circuit breaker — VIX spike, drawdown band, regime panic). Check upstream `build_elite_picks.py` gating logic.
- All 9 cells empty → `n_passing_hard_gates = 0`. Hard gates are: R:R inconsistent, earnings ≤ 3d, stop ≥ entry, score < 50, tail-loss filter, stage-filter mismatch.
- "Elite picks computation error" → `ep.error` is set. Stack trace in `cache/logs/build_elite_picks_*.log`.

## Coherence note
The 8 factors here mirror the data emitted by `build_elite_picks.py` exactly. If you change factor weights in Python, update the legend at the bottom of this module (`<div class="ep-legend">`) so the user-facing explanation matches the math.
