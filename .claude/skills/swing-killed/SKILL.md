---
name: swing-killed
description: Operational runbook for the Killed / AVOID surface. Use when debugging the render, fixing data binding, or extending behavior. Module-based extraction via CapStudio loader.
---

# Killed / AVOID — operational skill

## Source
- Module: `infra/prototype/tabs/killed/killed.js`

- Per-folder rules: same dir as module (CLAUDE.md if present)
- Capability registry: `data/capability_registry.json` → `tabs.killed`

## Default roles
admin, trader, quant

## How it loads
- Loaded via core/shell.js on page boot.
- Module exports `render()` which is wrapped into TAB_RENDERERS via shell.js override.
- Inline body in dashboard.html is now a 1-line stub — modules are the only render path.

## Common debugging
- Check console for `[shell] rendered tab 'killed' from module …`
- If blank: paste any `[shell] module render 'killed' threw:` error
- If missing helper: add `window.X = X` exposure in the source HTML for the let/const referenced

## Plan reference
`~/.claude/plans/wiggly-popping-pearl.md`
