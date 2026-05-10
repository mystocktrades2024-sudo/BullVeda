---
name: swing-portfolio
description: Operational runbook for the V2 dashboard Portfolio tab — open/closed positions, P&L tiles, factor + cross-mode exposure heatmaps. Use when debugging Portfolio rendering, regenerating its data, or operating on position-level state.
---

# Portfolio tab — operational skill

## Source
- Module: `infra/prototype/tabs/portfolio/portfolio.js` (extracted 2026-05-09 from dashboard.html:7487-7687)
- Data builder: `infra/prototype/build_data.py` — keys `portfolio.{equity,cash,positions[],closed[],monthly_pnl}`
- Per-folder rules: `infra/prototype/tabs/portfolio/CLAUDE.md` (auto-loaded when editing the module)

## How to regen the tab's data
```
cd "/Volumes/MyMacDisk/Claude Skills/SwingTrade"
python3 infra/prototype/build_data.py
```
Reads `cache/last_bundle.json` (set by the latest scan + portfolio_tracker output) and writes `data.json` consumed by the dashboard.

## How to debug a blank or wrong render
1. Open `http://localhost:7432/v2/#portfolio` and check browser console.
2. Confirm `window.DATA.portfolio` is non-null in the console.
3. If render call is silent, check `window.TAB_RENDERERS.portfolio` — should be the wrapped module render (look for `_loadTab` in the function string), not the inline stub.
4. Position table empty → `cache/last_bundle.json.portfolio.positions` is empty; portfolio_tracker hasn't run.
5. `current_price=0` on rows → live-price poll (`_pollLivePrices` in dashboard.html:9863) hasn't run yet.
6. Factor heatmap `limited data` → `r.rs_rank`/`r.fund_pts`/`r.fwd_pe` missing on BUY rows; check upstream `analysis.py`.

## Common failure modes
- **Module 404** → `infra/prototype/tabs/portfolio/portfolio.js` missing or path typo. Server returns 404, console shows import failure.
- **Override not installed** → `core/shell.js` failed to load (check console for import error). Inline stub renders nothing.
- **Position click handlers fail** → `posMoveToBE`/`posTrailStop`/`posClosePosition` are global functions defined in `dashboard.html`. Don't move them when extracting.

## Downstream dependencies
- Sidebar count badges read from this tab's data — Portfolio tab opening triggers `_updateSidebarCounts()`.
- Cross-mode exposure tile (`crossModeExposure`) is unique to this tab, not used elsewhere.

## Plotly / chart IDs
None — Portfolio is HTML-only (no Plotly).

## Plan reference
Per-tab modularization plan: `~/.claude/plans/wiggly-popping-pearl.md`
