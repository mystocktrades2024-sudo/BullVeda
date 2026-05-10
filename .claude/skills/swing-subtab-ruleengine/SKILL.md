---
name: swing-subtab-ruleengine
description: Operational runbook for the Why-this-is-X · Rule Engine surface. Use when debugging the render, fixing data binding, or extending behavior. Module-based extraction via CapStudio loader.
---

# Why-this-is-X · Rule Engine — operational skill

## Source
- Module: `infra/prototype/subtabs/ruleengine/rule_engine.js`

- Per-folder rules: same dir as module (CLAUDE.md if present)
- Capability registry: `data/capability_registry.json` → `sub_tabs.subtab-ruleengine`

## Default roles
admin, quant

## How it loads
- Loaded via core/elite-detail-shell.js on page boot.
- Module exports `render()` which overrides window.renderXxx.
- Inline body in elite-detail.html is now a 1-line stub — modules are the only render path.

## Common debugging
- Check console for `[detail-shell] rendered tab 'subtab-ruleengine' from module …`
- If blank: paste any `[shell] module render 'subtab-ruleengine' threw:` error
- If missing helper: add `window.X = X` exposure in the source HTML for the let/const referenced

## Plan reference
`~/.claude/plans/wiggly-popping-pearl.md`
