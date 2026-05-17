# Portfolio tab

Renders open positions, closed trades, monthly realized P&L, factor-exposure heatmap, cross-mode-exposure tile.

## Data source
- `DATA.portfolio.{equity, cash, positions[], closed[], monthly_pnl}`
- `DATA.short_term`, `DATA.medium_term`, `DATA.long_term` (filtered to `stage === 'BUY'` for the cross-mode + factor tiles)

Built by `infra/prototype/build_data.py` from `cache/last_bundle.json` (the live portfolio + scan output).

## DOM targets
`portfolioMeta`, `pfSummary`, `factorHeatmap`, `crossModeExposure`, `openPosMeta`, `openPosBody`, `closedPosMeta`, `closedPosBody`, `monthlyPnlBody`.

## CSS prefix
`.pf-*` (`.pf-pill`, `.pos-act-btn`), plus shared `.fac-*` and `.cme-*` (factor + cross-mode exposure), `.hc-*` (heatmap row), `.stat-tile`, `.simple` (shared table), `.sym`, `.pnl-up`/`.pnl-dn`. The `.fac-*`/`.cme-*` are owned here even though name doesn't say "pf" — they only render in this tab.

## Imports allowed
- `core/shared.js`: `getData`, `$`. **Nothing else.**
- **Forbidden:** importing from any sibling tab.

## External dependencies (window.*)
- `posMoveToBE`, `posTrailStop`, `posClosePosition` — global handlers in `dashboard.html`. Wired via inline `onclick="..."` strings in the rendered HTML. **Do not move these without updating handler call sites.**

## Renderer signature
`export function render(): void` — synchronous, idempotent. Re-paints the DOM whenever called (no diffing).

## Dispose contract
`export function dispose(): void` — no-op. Portfolio holds no timers, no listeners outside the inline onclick handlers (those die with the DOM).

## Common failure modes
- `factorHeatmap` empty → check that `DATA.short_term[].rs_rank` is populated. Often happens if a scan ran with stale RS ranks.
- All positions show `current_price=0` → live-price poll (`_pollLivePrices` in dashboard.html) hasn't run yet, or quote feed is stale.
- Cross-mode exposure tile missing sectors → `r.sector` is `null` for the BUY rows. Fix upstream in `analysis.py` (sector enrichment).

## How to retest
1. `curl -s http://localhost:7432/v2/ -u $USER:$PASS | head -c 1000` — ensure shell loads.
2. Open `http://localhost:7432/v2/#portfolio` in a browser, hard-refresh (Cmd-Shift-R).
3. Confirm: meta strip + 5 stat tiles + factor heatmap + cross-mode tile + open table + closed table + monthly P&L.
4. Click Performance tab, click back to Portfolio — second render should be instant (no console errors).
