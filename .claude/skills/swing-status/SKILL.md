---
name: swing-status
description: Operational runbook for the System Status surface. Use when debugging the render, fixing data binding, or extending behavior. Module-based extraction via CapStudio loader.
---

# System Status — operational skill

## Source
- Module: `infra/prototype/tabs/status/status.js`

- Per-folder rules: same dir as module (CLAUDE.md if present)
- Capability registry: `data/capability_registry.json` → `tabs.status`

## Default roles
admin

## How it loads
- Loaded via core/shell.js on page boot.
- Module exports `render()` which is wrapped into TAB_RENDERERS via shell.js override.
- Inline body in dashboard.html is now a 1-line stub — modules are the only render path.

## Common debugging
- Check console for `[shell] rendered tab 'status' from module …`
- If blank: paste any `[shell] module render 'status' threw:` error
- If missing helper: add `window.X = X` exposure in the source HTML for the let/const referenced

## Plan reference
`~/.claude/plans/wiggly-popping-pearl.md`
