# Audit tab

Per-signal grid: live %Δ, D1–D5, W1–W5, M1–M6 cells with verdict pills, filtered by symbol/date/strategy/verdict/PnL/regime/conviction/exit-reason/elite.

## Data source
- `DATA.performance.audit_trail` — emitted by `infra/prototype/build_data.py` (signal log enriched with returns + verdict + status)
- Live price overlay via `/api/live/quote?tickers=...` (Schwab → EODHD fallback)

## DOM targets
`auditMeta`, `auditSummary`, `auditCoverageNotice`, `auditThead`, `auditTbody`, sidebar `sbAuditCt`, scanner-strip `fsAuditCt`. Plus the 14 filter `<input>`/`<select>` IDs (`auditFilterSymbol`, `auditFilterDateFrom`, etc.).

## CSS prefix
None dedicated — uses inline styles + shared `.stat-tile`, `.audit-row`, `.audit-today`, `.audit-pctnow`, `.audit-d{1..5}-pct`.

## Imports allowed
- `core/shared.js`: `getData`. Local `setText` helper inlined (was a one-liner).

## External deps (window.*)
- `auditToggleExpand` (row click) — stays in `dashboard.html`
- `_auditLivePoll` — stays in `dashboard.html`; polls every 5s, kicked off at end of render
- `AUDIT_DAY_COLS`, `AUDIT_WEEK_COLS`, `AUDIT_MONTH_COLS` — exposed to window in `dashboard.html`

## Dispose
No-op. `_auditPollIntervalId` is module-private inside dashboard.html; existing behavior leaves the poller running across tab switches. **Do not introduce a clearInterval here without first refactoring the timer ownership** — quietly clearing it from this module risks killing the poll for users on other tabs that share the trail.

## Common failure modes
- Empty trail → `signal_log_enriched.json` not built. Run `python3 build_signal_log.py`.
- All cells `—` → live-quote fetch failing (Schwab token expired). Check `com.swingtrade.schwabtoken`.
- Filter dropdowns empty → `_auditFiltersInit` flag stuck. Force reload: `delete window._auditFiltersInit`.
