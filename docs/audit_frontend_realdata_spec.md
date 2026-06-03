# BullVeda Frontend Real-Data Spec — Audit Fixes #6/#7/#8

Source: quant-trader signal-integrity audit, 2026-06-03. Backend false-signal fixes
(#1–#4) shipped in `cc30017d5`. Desktop #5 (route Elite/BUY/Momentum to real gated
universe) shipped in `6fb0c5856` (source `workspaces.jsx`; lands in bundle on next
`node build_bullveda.cjs`). This doc specs the remaining frontend fixes for whichever
session owns the BullVeda build, to avoid two sessions racing the same bundle.

**Build:** edit `infra/prototype/bullveda/src/*.jsx`, then `node build_bullveda.cjs`
(reads `BullVeda.dev.html` → bundles → `BullVeda.html`). Never hand-edit `BullVeda.html`.

---

## #6 — Per-mode verdicts must read the engine's `decisions_by_mode`
**File:** `src/composite-verdict.jsx` (~7–50)
**Bug:** recomputes BUY/WATCH client-side from pillar scores with hardcoded fallbacks
(`tech ?? 60`, `wilson ?? 47`, `aiPup ?? 55`). The bundle's authoritative
`decisions_by_mode.{swing,position,invest}` can be **WATCH** while top-level
`decision.verdict` is **BUY** — so swing "BUY" shows for a ticker the engine flagged
WATCH for swing. A trader sizes into a mode the engine didn't greenlight.
**Fix:** read `row._raw.decisions_by_mode[mode].verdict` (real) as the source of truth;
fall back to the client recompute only when that field is genuinely absent, and label it
"derived" when you do. Verify `/api/universe` row carries `decisions_by_mode`
(`server.py` universe `row()`); if not, add it there from `r.get("decisions_by_mode")`.

## #7 — Scan timestamp + staleness on desktop
**Files:** `bullveda-boot.js` (expose `BV.scanMeta = {ts, ageMin}` from
`/api/universe` / `last_bundle.run_timestamp`), a shell header chip, `server.py`.
**Bugs:**
- No scan age anywhere on desktop — a 3-day-old bundle looks identical to today's.
  (Mobile companion already does this right: `SCAN_META.ts`.)
- `/api/universe` is mtime-cached with **no staleness flag**; if the scan launchd job
  failed it serves yesterday silently. Add `stale` + `age_min` + `run_timestamp` to the
  `/api/universe` payload (read `bundle.get("run_timestamp")`; stale if > ~20h old).
- `insUsd → 0` and `sent → neutral` when the field is **absent** (boot.js ~147,163) —
  renders "$0M insider" / neutral chip instead of "—". Make absent → null → "—".
**Fix:** surface a "as of HH:MM PT · Nh old" chip in the desktop shell, amber when stale;
absent insider/sentiment render "—" not 0.

## #8 — De-mock the synthetic surfaces (the active session's wiring mandate)
These render fabricated data as actionable signals. Priority = decision surfaces first.
- `ai-predict-data.jsx` — board/forecast/cone/analogs/`CALIB`/`resolved()` are seeded
  PRNG. Backtest (Model Accuracy tab) already real via `8e107ce8b`. Wire the **board**
  to `/api/ai_predict` rows (real `p_up`, verdict) instead of `mulberry()` per ticker.
- `surface-momentum.jsx` — RS/sharpe/stage/sparkline from `Math.sin()+random` and ASCII
  math. Wire to **`/api/momentum-signals`** (already live, built `0bbe3c519`) + real
  `rs_rank`/`perf_*` from `/api/universe`.
- `patterns-mlforecast.jsx` / `patterns-montecarlo.jsx` — 7-theory "ensemble" + 2000-path
  MC are seeded RNG. Either wire to a real source or label "illustrative" prominently.
- `surface-earnings-predictions.jsx` — mock fallback fabricates beat direction/confidence
  biased to look calibrated. Wire to `BV.earningsBeat` (`data_earnings.json`
  `earnings_beat_predictions`); show "—" when absent.
- `workspaces.jsx` specialized renderers (WSOptions/WSSectors/WSThemes/WSStrats/WSPerf/
  WSAccuracy/WSFactor/WSLeaders/WSPairs/WSMacro/WSCrypto/WSEvents) — all hardcoded tables.
  Wire to real feeds or mark each with a `scaffold` freshness pill (not "live 18s").

**Rule for all:** never fabricate a number that implies an edge. Absent → "—". A
`scaffold`/`demo` freshness pill on an un-wired surface is honest; a "live" pill on
seeded RNG is not.
