---
name: swing-crypto
description: Operational runbook for the Crypto surface. Use when debugging the render, fixing data binding, or extending behavior. Module-based extraction via CapStudio loader.
---

# Crypto — operational skill

## Source
- Module: `infra/prototype/tabs/crypto/crypto.js`

- Per-folder rules: same dir as module (CLAUDE.md if present)
- Capability registry: `data/capability_registry.json` → `tabs.crypto`

## Default roles
admin, trader, quant

## How it loads
- Loaded via core/shell.js on page boot.
- Module exports `render()` which is wrapped into TAB_RENDERERS via shell.js override.
- Inline body in dashboard.html is now a 1-line stub — modules are the only render path.

## Common debugging
- Check console for `[shell] rendered tab 'crypto' from module …`
- If blank: paste any `[shell] module render 'crypto' threw:` error
- If missing helper: add `window.X = X` exposure in the source HTML for the let/const referenced

## Plan reference
`~/.claude/plans/wiggly-popping-pearl.md`
