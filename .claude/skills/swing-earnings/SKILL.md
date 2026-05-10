---
name: swing-earnings
description: Operational runbook for the V2 dashboard Earnings tab — upcoming reports with beat-prediction tier (STRONG/SOLID/MODERATE), prior beat-rate, sector + verdict cross-ref. Use when debugging the watchlist, fixing missing beat predictions, or investigating sector enrichment.
---

# Earnings tab — operational skill

## Source
- Module: `infra/prototype/tabs/earnings/earnings.js` (extracted 2026-05-09)
- Per-folder rules: `infra/prototype/tabs/earnings/CLAUDE.md`
- Watchlist builder: `build_earnings_watchlist.py` (5:30am PT cron — `com.swingtrade.earnings`)
- Outcomes builder: `build_earnings_outcomes.py` (`com.swingtrade.earnoutcomes`)
- Beat predictions: `build_earnings_beat_alert.py` (`com.swingtrade.beatpredict`)

## How to regen
```
python3 build_earnings_watchlist.py
python3 build_earnings_beat_alert.py
python3 infra/prototype/build_data.py
```

## Composite beat-score breakdown (0-100 → STRONG ≥ 75, SOLID ≥ 60, MODERATE ≥ 40)
1. **Historical** beat rate from prior 8 reports (max 25)
2. **Runup 10d** prior to report — strong runup correlates with beat (max 15)
3. **Volume accumulation** — rising vol on shrinking range (max 15)
4. **Analyst upside** — recent EPS estimate revisions (max 15)
5. **Options flow** — pre-earnings UOA / call skew (max 15)
6. **Sector beats** — same-sector co-movers' recent reports (max 15)

Tooltip on the BEAT% column shows the breakdown: `H8/Run10/Vol8/An5/Op12/Sec3`.

## Common scenarios
- "Earnings watchlist not built yet" → cron failed. Check `cache/logs/build_earnings_watchlist_*.log`.
- BEAT% all `—` → beat-predictions not built, or report date too far out for prediction (>14d).
- OWNED tag missing → `cache/last_bundle.json.portfolio.positions` stale; portfolio_tracker hasn't run.
- Days column red (≤1d) → urgent risk if owned. Trim 50% within 5 days, full exit within 3 days per playbook.

## Plan reference
`~/.claude/plans/wiggly-popping-pearl.md`
