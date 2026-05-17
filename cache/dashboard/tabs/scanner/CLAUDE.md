# Scanner tab

The DEFAULT V2 dashboard surface — Signal Scanner. Renders the per-ticker grid
filtered by FS_STATE: 13 filters + sort + chip-built signal rows + extra columns.

## Module
`tabs/scanner/scanner.js` — extracted from dashboard.html (renderFloorScanner)
and split into 4 sub-files via MOD-1 (2026-05-10).

  scanner.js    — entry orchestrator, calls each sub-module + handles DOM wiring
  filters.js    — applyFilters() + sortRows() (pure 13-filter chain)
  row.js        — buildRowHtml() + chip-stack builder (per-row template)
  sparkline.js  — buildSparkPath() (deterministic ticker-hashed mini chart)
  sectors.js    — buildSectorChips() (DOM injector for filter chip group)

## Default roles
admin, trader, quant, viewer (all profiles)

## Data source
- `DATA.short_term + medium_term + long_term` — flat list of all scan rows
- Cross-refs: `_getWatchlist()` (window-bound), DATA.run_timestamp

## DOM targets
`fsScannerCt`, `fsScannerSub`, `fsScannerWrap`, `fsScannerRows`, `sc2FootCt`,
`fsSectorGrp` (sector chips). Sort arrow updates on `.sc2-th.sortable`.

## CSS prefix
`.sc2-*`, `.fs-st-*`, `.rc` (ticker chips), `.density-*` (density modes).

## Imports allowed
- `core/shared.js`: `getData`. Sub-modules import from each other and resolve
  window-bound helpers explicitly via `window.X` references.

## External deps (window.*)
**State (must be on window):**
- `FS_STATE` — exposed via `window.FS_STATE = FS_STATE` in dashboard.html
  (let-binding fix from MOD-1 — was the latent ReferenceError that kept the
  module dead from yesterday's extraction).
- `_SC2_EXTRA_COLS`, `_SC2_NEW_TICKERS`, `_SC2_SELECTED` — Sets / objects.

**Helpers (function declarations, auto-bound to globalThis):**
- `_setupFamilyOf`, `_scoreRing`, `_logoHtml`, `_starsHtml`
- `_getWatchlist`, `_matchesPerfPattern`, `_sc2FmtExtra`, `setText`
- `_sc2RenderKpis`, `_sc2RenderActive`, `_sc2UpdateSavedCount`,
  `_sc2UpdateSeenTickers`, `_sc2InjectExtraHeaders`, `_sc2ApplyColVisibility`,
  `_sc2WireTickerPreview`, `_sc2InjectGroupDividers`, `_wireCtxMenu`
- `_handleRowClick`, `_toggleStar`, `sc2Clear`, `fsSetSector` (called from
  inline onclick handlers in the rendered HTML)

## Capability registry
`data/capability_registry.json` → `tabs.scanner.module = "tabs/scanner/scanner.js"`
(added in MOD-1, 2026-05-10). Loader: core/shell.js detects the field on boot
and overrides `window.TAB_RENDERERS.scanner` with a wrapped module render.

## Dispose
No-op. The renderFloorScanner pipeline has no timers; sort/filter state lives
in window.FS_STATE which persists across tab switches by design.

## Common failure modes
- Empty grid + no filters set → `DATA.short_term/medium_term/long_term` empty.
  Build pipeline didn't run; check cache/last_bundle.json.
- Empty grid + filters set, "No signals match" empty-state → over-filtered.
  Click "⟲ Clear all filters" button (calls `sc2Clear()`).
- Module fails silently (no console message) → `window.FS_STATE` not yet bound.
  Should not happen post-MOD-1; if regressed, check dashboard.html line ~2624.
- Bare `_setupFamilyOf` ReferenceError → function declarations in dashboard.html
  must be at top level (not inside an IIFE). Don't move them.

## Coherence note
The chip-builder in `row.js` derives the conviction tier from score thresholds
(88 → T1, 78 → T2, 70 → T3) — same thresholds the Plan tab and conviction
classifier use. If those thresholds change in `analysis.py: assign_conviction_tier`,
update both places.
