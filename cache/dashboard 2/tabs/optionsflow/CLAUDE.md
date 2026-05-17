# Options Flow tab

Daily UOA (unusual options activity) imbalance scanner. Surfaces tickers with P/C < 0.5, ≥1000 volume, ≥$1M est. dollar volume.

## Data source
- `DATA.options_flow_top30` — emitted by `infra/prototype/build_data.py` from `options_flow_scanner.py` output.

## DOM targets
`opFlowMeta`, `opFlowBody`, sidebar count badges `sbOpFlowCt` and `fsOpFlowCt`.

## Imports allowed
- `core/shared.js`: `getData`. Nothing else.

## Forbidden
- Importing from any sibling tab.

## CSS prefix
None — uses inline styles + shared `var(--pass)/var(--warn)/var(--ink-*)`. Do not introduce a `.of-*` prefix; the styling is per-row inline.

## External deps (none)
No window functions, no timers.

## Common failure modes
- `flow` is empty → either Schwab options chain re-auth required, or no tickers passed UOA filter today. Surface upstream in `options_flow_scanner.py`.
- Status missing on rows → upstream scanner didn't tag STRONG/MODERATE/WEAK.

## Retest
1. Open `/v2/#optionsflow` after a scan that includes options chain pulls.
2. Confirm STRONG/MODERATE/WEAK count in the meta strip matches `wc -l` on the underlying signal log.
