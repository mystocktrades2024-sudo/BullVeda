# IPO · Splits tab

## Module
`tabs/events/events.js` — extracted from dashboard.html 2026-05-09 via CapStudio modular loader.

## Default roles
admin, quant

## Loader path
core/shell.js — wraps into TAB_RENDERERS via override

## Imports allowed
- `core/shared.js`: getData, $, fmt, dollar, escapeHtml, etc. **Nothing else from sibling modules.**

## Forbidden
- Importing from sibling tab modules
- Mutating shared state (DATA, T) outside the data-poll path
- Inline `<script>` injection — use module render only

## Common debug
- Console: look for `[shell] rendered tab 'events' from module …`
- Module render error: `[shell] module render 'events' threw: …`
- Missing helper: add `window.X = X` exposure in source HTML

## Capability registry
`data/capability_registry.json` → `tabs.events`

## Plan
`~/.claude/plans/wiggly-popping-pearl.md`
