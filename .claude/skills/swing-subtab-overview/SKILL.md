---
name: swing-subtab-overview
description: Operational runbook for the 01 Overview · Verdict surface. Use when debugging the render, fixing data binding, or extending behavior. Module-based extraction via CapStudio loader.
---

# 01 Overview · Verdict — operational skill

## Source
- Module: `infra/prototype/subtabs/overview/overview.js`
  - `infra/prototype/subtabs/overview/earnings_banner.js`
  - `infra/prototype/subtabs/overview/head.js`
  - `infra/prototype/subtabs/overview/verdict.js`
  - `infra/prototype/subtabs/overview/scorecard.js`
- Per-folder rules: same dir as module (CLAUDE.md if present)
- Capability registry: `data/capability_registry.json` → `sub_tabs.subtab-overview`

## Default roles
admin, trader, quant, viewer

## How it loads
- Loaded via core/elite-detail-shell.js on page boot.
- Module exports `render()` which overrides window.renderXxx.
- Inline body in elite-detail.html is now a 1-line stub — modules are the only render path.

## Common debugging
- Check console for `[detail-shell] rendered tab 'subtab-overview' from module …`
- If blank: paste any `[shell] module render 'subtab-overview' threw:` error
- If missing helper: add `window.X = X` exposure in the source HTML for the let/const referenced

## Plan reference
`~/.claude/plans/wiggly-popping-pearl.md`
