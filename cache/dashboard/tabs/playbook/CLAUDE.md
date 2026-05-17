# Playbook tab

100% static rulebook — every gate, score, tier, and exit rule the system uses. **No DATA reads.** Pure documentation surface.

## Data source
None. The Playbook is the canonical reference for the system's rules; if a rule changes elsewhere, this tab must be hand-updated.

## DOM target
`playbookBody`.

## CSS prefix
`.pb-*`, plus shared `.mono`.

## Imports allowed
- `core/shared.js`: `$`. Nothing else.

## External deps
None.

## Dispose
No-op.

## When to update
Whenever ANY of these change in code:
- `config/config.json` thresholds (regime BUY mins, weight shifts, conviction tier rules)
- `analysis.py` 5-pillar scoring weights
- `tier1_signals.py` detector logic
- Position-sizing formula in `decision_engine.py`

## How to update
The playbook is structured as 13 `sec()` calls with hardcoded HTML. To add a section: copy an existing one, give it a unique icon + title + body, then append to the final `$('playbookBody').innerHTML = ...` chain.

## Source-of-truth note
The footer says "All thresholds in this Playbook live in `config/config.json` · scoring logic in `analysis.py` · Tier 1 detectors in `tier1_signals.py`. Last rebuild: 2026-05-03." Bump that date when you edit.
