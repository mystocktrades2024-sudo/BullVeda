---
name: swing-optionsflow
description: Operational runbook for the V2 dashboard Options Flow tab — UOA imbalance scanner showing tickers with abnormal call/put activity. Use when debugging the options flow render or regenerating its data.
---

# Options Flow tab — operational skill

## Source
- Module: `infra/prototype/tabs/optionsflow/optionsflow.js` (extracted 2026-05-09 from dashboard.html:5593-5690)
- Scanner: `options_flow_scanner.py` — produces `options_flow_top30` candidates
- Data builder: `infra/prototype/build_data.py` writes `data.options_flow_top30` to `data.json`

## How to regen
1. Run options scan via Schwab — `com.swingtrade.optionsflow` launchd job, or manually: `python3 options_flow_scanner.py`
2. Rebuild dashboard data: `python3 infra/prototype/build_data.py`
3. Reload `/v2/#optionsflow`

## How to debug
1. **No candidates** → either Schwab options chain re-auth needed (`com.swingtrade.schwabtoken`) or no tickers passed UOA filter (P/C < 0.5, ≥1000 vol, ≥$1M est. dollar volume).
2. **All STRONG missing** → upstream scanner didn't tag status. Check `options_flow_scanner.py` for `status =` assignment.
3. **Earnings within 3 days excluded** is by design — options flow may be hedging not directional.

## Filter thresholds (from the scanner)
- STRONG: P/C < 0.2 AND UOA confirmed
- MODERATE: P/C < 0.3 OR UOA
- WEAK: meets minimum volume but neither

## Trade plan defaults
Stop: −3% · Target: +7% · Hold: 5–10 days · Entry: next day open.

## Plan reference
`~/.claude/plans/wiggly-popping-pearl.md`
