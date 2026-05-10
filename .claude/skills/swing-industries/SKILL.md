---
name: swing-industries
description: Operational runbook for the Industries surface. Use when debugging the render, fixing data binding, or extending behavior. Module-based extraction via CapStudio loader.
---

# Industries — operational skill

## Source
- Module: `infra/prototype/tabs/industries/industries.js`

- Per-folder rules: same dir as module (CLAUDE.md if present)
- Capability registry: `data/capability_registry.json` → `tabs.industries`

## Default roles
admin, trader, quant

## How it loads
- Loaded via core/shell.js on page boot.
- Module exports `render()` which is wrapped into TAB_RENDERERS via shell.js override.
- Inline body in dashboard.html is now a 1-line stub — modules are the only render path.

## Common debugging
- Check console for `[shell] rendered tab 'industries' from module …`
- If blank: paste any `[shell] module render 'industries' threw:` error
- If missing helper: add `window.X = X` exposure in the source HTML for the let/const referenced

## Plan reference
`~/.claude/plans/wiggly-popping-pearl.md`
