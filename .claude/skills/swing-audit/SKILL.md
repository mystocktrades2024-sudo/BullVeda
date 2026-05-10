---
name: swing-audit
description: Operational runbook for the V2 dashboard Audit tab — per-signal grid showing live %Δ, D1-D5/W1-W5/M1-M6 returns, verdict pills, with 14 filters. Use when debugging the audit render, fixing live-quote staleness, or investigating why a specific signal's cells are empty.
---

# Audit tab — operational skill

## Source
- Module: `infra/prototype/tabs/audit/audit.js` (extracted 2026-05-09)
- Per-folder rules: `infra/prototype/tabs/audit/CLAUDE.md`
- Data builder: `infra/prototype/build_data.py` → `data.performance.audit_trail`
- Underlying enrichment: `signal_log.py` + `build_signal_log.py`

## How to regen
1. Run scan (populates `signal_log.json`)
2. `python3 build_signal_log.py` — enriches with returns + status
3. `python3 infra/prototype/build_data.py` — emits `data.json`

## How to debug a blank/stale render
1. Open `/v2/#audit`, check console.
2. `window.DATA.performance.audit_trail` non-empty? If empty → enrichment didn't run.
3. Today + %Δ cells `—` → live-quote feed dead. Check `/api/live/quote?tickers=AAPL` returns valid JSON.
4. D1-D5 cells empty for recent signals → `_auditLivePoll` hasn't fired yet, or `_tradingDaysSince` returning null.
5. Filter dropdowns empty → `window._auditFiltersInit` is true but rebuild not triggered. Force: `delete window._auditFiltersInit; renderAudit()`.

## Live polling
- `_auditLivePoll()` fires every 5s (top 250 tickers, batched into 2× 125-quote requests)
- Recent rows (entry within 7 trading days) ALWAYS get polled — keeps D1-D5 filling
- Older rows: only the first 100 visible (for browse-mode liveness)

## Common scenarios
- "Why is BBBB's D3 cell empty?" → entry was Friday, today's Monday = D1. D2/D3 require Tuesday/Wednesday parquet writes. Until those land, only synthesized D1 fills.
- Schwab token expired → `com.swingtrade.schwabtoken` cron should refresh. Manual: `python3 schwab_token_refresh.py`.

## Plan reference
`~/.claude/plans/wiggly-popping-pearl.md`
