---
name: swing-playbook
description: Operational runbook for the V2 dashboard Playbook tab — the canonical rulebook (5 pillars, 4 regimes, conviction tiers, exit rules, daily workflow). 100% static; updated only when system rules change. Use when documenting a rule change or auditing what the system claims to do vs what it actually does.
---

# Playbook tab — operational skill

## Source
- Module: `infra/prototype/tabs/playbook/playbook.js` (extracted 2026-05-09)
- Per-folder rules: `infra/prototype/tabs/playbook/CLAUDE.md`
- **No data sources** — pure documentation

## When to update
**Whenever any of these change:**
- `config/config.json` thresholds (regime BUY mins, weight shifts, conviction tiers, sizing %)
- `analysis.py` 5-pillar scoring weights
- `tier1_signals.py` detector logic
- `decision_engine.py` position-sizing formula
- `regime_detector.py` regime triggers (VIX bands, breadth thresholds)

## Audit checklist — does the playbook match reality?
Run this monthly:
```
# Check current config against playbook claims:
python3 -c "
import json
c = json.load(open('config/config.json'))
print('Regime BUY mins:')
for k, v in c['regime4_thresholds'].items():
    print(f'  {k}: buy_min={v.get(\"buy_min_score\", \"?\")}')
print('Weight shifts:')
print(json.dumps(c.get('regime_weight_shifts', {}), indent=2))
"
```
Compare output to the 4-Regime table in playbook.js. If they diverge, the playbook is lying to the user — fix immediately.

## How to add a section
Copy an existing `sec(icon, title, sub, body)` call. Append to the final `$('playbookBody').innerHTML = ...` chain. Use the `.pb-*` class set; don't introduce new prefixes.

## Source-of-truth note
Footer says `Last rebuild: 2026-05-03`. Bump this date on every edit. Truthful date > polished design.

## Plan reference
`~/.claude/plans/wiggly-popping-pearl.md`
