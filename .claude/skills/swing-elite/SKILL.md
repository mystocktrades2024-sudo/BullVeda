---
name: swing-elite
description: Operational runbook for the V2 dashboard Elite Picks tab — top-5 picks per (mode × stage) cell with conviction arc, 8-factor breakdown, MC P(target/stop), CVaR, fwd Sharpe, why-confident + watch-out narratives. Use when debugging the 9-cell grid, suppressed picks, or why an expected ticker isn't showing.
---

# Elite Picks tab — operational skill

## Source
- Module: `infra/prototype/tabs/elite/elite.js` (extracted 2026-05-09)
- Per-folder rules: `infra/prototype/tabs/elite/CLAUDE.md`
- Builder: `build_elite_picks.py` — composite 8-factor scorer
- Outputs: `data.elite_picks.{Swing,Position,Invest}.{BUY,WATCH,SHORT}` arrays

## How to regen
```
python3 build_elite_picks.py     # writes cache/elite_picks.json
python3 infra/prototype/build_data.py
```

## 8 factors (out of 100 raw, mode multipliers can boost)
| Factor | Max | What |
|--------|-----|------|
| Score Band | 20 | Band's historical WR from accuracy framework |
| Forward Edge | 25 | MC P(target first) − P(stop first) |
| HMM Regime | 10 | Regime probability matches direction |
| Cross-Asset | 5 | Risk-on/off matches stage |
| Tier-1 Stack | 10 | Validated detectors firing (Spring weighted full) |
| Sector Rank | 10 | sector_pct_rank percentile |
| Conviction | 10 | T1=10 / T2=7 / T3=4 |
| Entry Quality | 10 | FRESH=10 / PULLBACK=8 / VALID=5 / EXTENDED=0 |

## Hard gates (auto-disqualify)
- R:R inconsistent (target ≤ entry, etc.)
- Earnings ≤ 3 days
- Stop ≥ entry (long) or stop ≤ entry (short)
- Score < 50
- Tail-loss filter demoted (BUY only)
- Stage filter mismatch (e.g., BUY but verdict says SHORT)

## Suppressed-mode (red banner)
`ep.meta.blocked = true` happens when:
- VIX spike kill-switch (VIX > 5d avg × 1.4)
- Drawdown exceeds 15% (Phase 2 sizing rule)
- Regime = Panic
Reason in `ep.meta.reason`, note in `ep.meta.note`.

## Common scenarios
- Cell empty → check `n_passing_hard_gates`. If 0 across all 9 cells, gates are too strict OR upstream scan emitted nothing.
- "Elite picks computation error" → `cache/logs/build_elite_picks_*.log` has stack trace.
- Pick missing watch-out flags despite weak factor → builder didn't tag it. Check `_compose_narrative()` in `build_elite_picks.py`.

## Plan reference
`~/.claude/plans/wiggly-popping-pearl.md`
