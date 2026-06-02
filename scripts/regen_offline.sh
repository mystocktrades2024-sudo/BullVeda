#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# Offline dashboard regen — rebuild data_*.json from the EXISTING bundle + ML
# predictions with ZERO EODHD network calls.
#
# data_*.json are pure projections of cache/last_bundle.json (already enriched),
# so rebuilding them needs no new data. EODHD_CACHE_ONLY=1 makes eodhd_client
# return cache (any age) or empty on every miss — never the network. Use this to
# apply build_data.py code changes instantly instead of `swing_trade.py regen`,
# which re-runs lite-universe bulk-fundamentals (~12K calls, bulk billed per-symbol).
#
# Tradeoff: the lite-universe extras (ML/earnings/options-only tickers NOT in the
# scan) are skipped — the next full scan restores them. For applying a build_data
# code fix to the main rows, that's exactly what you want.
#
# Usage:  bash scripts/regen_offline.sh
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")/.."

# Read EODHD usage before/after to PROVE the regen cost zero quota.
_token="$(grep -iE '^EODHD_API_KEY' .env 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"'\'' ' || true)"
_usage() { [ -n "${_token}" ] && curl -s "https://eodhd.com/api/user?api_token=${_token}&fmt=json" \
  | python3 -c "import sys,json;print(json.load(sys.stdin).get('apiRequests',0))" 2>/dev/null || echo "?"; }

_before="$(_usage)"
echo "▶ Offline regen — EODHD usage before: ${_before}"

EODHD_CACHE_ONLY=1 python3 infra/prototype/build_data.py

_after="$(_usage)"
if [ "${_before}" != "?" ] && [ "${_after}" != "?" ]; then
  echo "✓ Offline regen complete — EODHD usage after: ${_after}  (delta: $((_after - _before)) calls)"
else
  echo "✓ Offline regen complete (EODHD usage check unavailable)"
fi
