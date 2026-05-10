---
name: swing-subtab-models
description: Operational runbook for the Models · Forward Distribution surface. Use when debugging the render, fixing data binding, or extending behavior. Module-based extraction via CapStudio loader.
---

# Models · Forward Distribution — operational skill

## Source
- Module: `infra/prototype/subtabs/models/horizons.js`
  - `infra/prototype/subtabs/models/elliott.js`
  - `infra/prototype/subtabs/models/multimethod.js`
- Per-folder rules: same dir as module (CLAUDE.md if present)
- Capability registry: `data/capability_registry.json` → `sub_tabs.subtab-models`

## Default roles
admin, quant

## How it loads
- Loaded via core/elite-detail-shell.js on page boot.
- Module exports `render()` which overrides window.renderXxx.
- Inline body in elite-detail.html is now a 1-line stub — modules are the only render path.

## Common debugging
- Check console for `[detail-shell] rendered tab 'subtab-models' from module …`
- If blank: paste any `[shell] module render 'subtab-models' threw:` error
- If missing helper: add `window.X = X` exposure in the source HTML for the let/const referenced

## Plan reference
`~/.claude/plans/wiggly-popping-pearl.md`
