# Earnings tab

Earnings watchlist (US tickers reporting next 14 days) with beat-prediction tier, prior beat/miss/inline counts, sector + verdict cross-ref, days-to-earnings risk coloring.

## Data source
- `DATA.earnings_watchlist` — built by `build_earnings_watchlist.py` (5:30am PT cron)
- `DATA.earnings_outcomes_30d` — last 30d of prior reports (BEAT/MISS/INLINE)
- `DATA.earnings_beat_predictions` — composite beat-probability score (`build_earnings_beat_alert.py`)
- Cross-refs `DATA.short_term`/`medium_term`/`long_term` for verdict + score + sector enrichment
- Cross-refs `DATA.portfolio.positions` for OWNED tag

## DOM targets
`earnBody`, `earnMeta`, sidebar `sbEarnCt`, scanner-strip `fsEarnCt`. Filter UI uses `_earnFilters` window state.

## CSS prefix
None dedicated — uses inline styles + theme tokens.

## Imports allowed
- `core/shared.js`: `getData`.

## External deps (window.*)
- `_earnFilters` — state object (filter values). Stays in `dashboard.html`.
- `_earnFilterChange(key, val)` + `_earnSearch(val)` — handlers referenced by inline `onchange`/`oninput`. Stay in `dashboard.html`.

## Dispose
No-op.

## Common failure modes
- "Earnings watchlist not built yet" → run `python3 build_earnings_watchlist.py` or wait for 5:30am PT cron
- BEAT% column all `—` → `build_earnings_beat_alert.py` hasn't run; the cron is `com.swingtrade.beatpredict`
- Sector col `—` → ticker missing from short_term/medium_term/long_term scan output
- OWNED tag absent for tickers I hold → portfolio_tracker hasn't refreshed; check `cache/last_bundle.json`
