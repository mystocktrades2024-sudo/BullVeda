---
name: swing-subtab-options
description: Operational runbook for the Options surface. Use when debugging the render, fixing data binding, or extending behavior. Module-based extraction via CapStudio loader.
---

# Options — operational skill

## Source
- Module: `infra/prototype/subtabs/options/options.js`

- Per-folder rules: same dir as module (CLAUDE.md if present)
- Capability registry: `data/capability_registry.json` → `sub_tabs.subtab-options`

## Default roles
admin, trader, quant

## How it loads
- Loaded via core/elite-detail-shell.js on page boot.
- Module exports `render()` which overrides window.renderXxx.
- Inline body in elite-detail.html is now a 1-line stub — modules are the only render path.

## Common debugging
- Check console for `[detail-shell] rendered tab 'subtab-options' from module …`
- If blank: paste any `[shell] module render 'subtab-options' threw:` error
- If missing helper: add `window.X = X` exposure in the source HTML for the let/const referenced

## Plan reference
`~/.claude/plans/wiggly-popping-pearl.md`
