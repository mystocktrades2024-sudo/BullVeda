# core/ — V2 dashboard shared modules

This directory holds the singleton state and cross-tab utilities. **No tab-specific logic here.** If a helper is used by exactly one tab, it lives in that tab's folder, not here.

## Files

- `shared.js` — `getData()`, `getTickers()`, `$`, `escapeHtml`, `fmt`, `px`, `dollar`, `logoHtml`, `updateSidebarCounts`, `expandPanel`. Single source for state read access.
- `shell.js` — entrypoint loaded as `<script type="module">`. Wires per-tab loaders into `window.TAB_RENDERERS`.
- `drawer.js` *(future, Phase 2)* — `_renderInlineDrawer` body once Options Flow is extracted.
- `floor.js` *(future)* — Floor-tape + system-status banner if extracted.

## Rules when editing core/

- **Single writer rule:** only the data-poll path in `dashboard.html` mutates `window.DATA`. Anything in `core/` reads via `getData()`.
- Every export must work without any tab module loaded — `core/` cannot import from `tabs/`.
- Avoid silent renames; downstream tabs import by name.
- When adding a util used by 2+ tabs, prefer extending `shared.js` over creating a new core file unless the util is large (>50 lines).
- After editing, smoke-test by loading `http://localhost:7432/v2/` and clicking 3 tabs — no console errors.

## What's still in dashboard.html (intentionally)

- 30 tab markup stubs (~574 lines)
- 775-line `<style>` block (prefix-namespaced per tab)
- Live data poll (`_pollDataRefresh`, `_pollLivePrices`)
- The 20 small renderers under 120 lines (e.g. `_renderWatchlistTab`, `renderReference`, etc.)

These are **out of scope** for `core/` — see plan at `~/.claude/plans/wiggly-popping-pearl.md`.
