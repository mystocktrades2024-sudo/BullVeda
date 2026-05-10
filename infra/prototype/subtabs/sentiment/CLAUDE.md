# Sentiment sub-tab

## Module
`subtabs/sentiment/sentiment.js` — extracted from elite-detail.html 2026-05-09 via CapStudio modular loader.

## Default roles
admin, trader, quant

## Loader path
core/elite-detail-shell.js — sets window.renderXxx = module.render after import

## Imports allowed
- `core/shared.js`: getData, $, fmt, dollar, escapeHtml, etc. **Nothing else from sibling modules.**

## Forbidden
- Importing from sibling tab modules
- Mutating shared state (DATA, T) outside the data-poll path
- Inline `<script>` injection — use module render only

## Common debug
- Console: look for `[detail-shell] rendered tab 'sentiment' from module …`
- Module render error: `[detail-shell] module render 'sentiment' threw: …`
- Missing helper: add `window.X = X` exposure in source HTML

## Capability registry
`data/capability_registry.json` → `sub_tabs.sentiment`

## Plan
`~/.claude/plans/wiggly-popping-pearl.md`
