# Performance tab

System edge verdict (STRONG/MARGINAL/NO EDGE/AWAITING DATA) + P&L tiles + Setup Family Podium + Score Calibration bars + auto-generated action items. Plus a Trade Journal aggregate (closed trades grouped by setup family).

## Data source
- `DATA.performance.{total, closed, win_rate, wins, losses, mfe_avg, mae_avg, rr_avg}` — top-level perf rollup
- `DATA.performance.setup_attribution` — per-family WR/PF/expectancy
- `DATA.performance.by_score_bucket` — distribution across `90+ / 80-89 / 70-79 / 60-69 / <60`
- `DATA.performance.by_strategy` — fallback when setup_attribution is empty
- `DATA.performance.audit_trail[].pct_now` — live P&L per signal
- `DATA.portfolio.closed[]` — drives the Trade Journal aggregate

## DOM targets
`perfMeta`, `perfTiles`, `journalBody`, `journalMeta`, `perfAttribBody` (the module rewrites the parent's parent's innerHTML — see end of render).

## CSS prefix
None dedicated — uses inline styles. `pnl-up` / `pnl-dn` / theme tokens shared.

## Imports allowed
- `core/shared.js`: `getData`, `$`.

## External deps (window.*)
- `window.PERF_NOTIONAL` — optional override for $-per-signal sizing (default $10K). Read at render time.

## Self-contained helpers
- `_wilsonCI(wins, n)` — inlined into this module (was tab-private in dashboard.html). Used by Setup Family Podium for confidence-interval display.

## Dispose
No-op.

## Common failure modes
- "AWAITING DATA" verdict — fewer than 30 closed trades. Expected during early system run.
- Trade Journal shows 0 closed → `cache/last_bundle.json.portfolio.closed` is empty; portfolio_tracker hasn't recorded any closures yet.
- Best/Worst trade `—` → no signals have `pct_now` populated. Live-quote enrichment hasn't run.
- Setup attribution empty but `by_strategy` has values → falls back to "Setup P&L Ranking — Live" view (open-position $-PnL ordering).

## Coherence note
The verdict thresholds (WR ≥ 55 + MFE/MAE ≥ 1.5 = STRONG · WR ≥ 45 = MARGINAL · else NO EDGE) must stay in sync with the operational rules in `decision_engine.py`. Do not tweak in isolation.
