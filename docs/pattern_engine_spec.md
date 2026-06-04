# Pattern Engine Spec — BullVeda Patterns lens (real-data wiring)

You are adding ONE real, mode-aware technical-analysis detector to the BullVeda
Patterns lens, replacing a hardcoded fixture. Follow this spec exactly. A
working reference implementation already exists — **study it first**:

- `engines/wyckoff.py` + `wyckoff_engine.py`  (the Python detector)
- `src/patterns-wyckoff.jsx`                   (the rewired React view)
- `pattern_data.py`, `pattern_engines.py`      (the shared foundation)
- `src/patterns-core.jsx`                       (the shared React hook + chart)

Project root: `/Volumes/MyMacDisk/Claude Skills/SwingTrade`

## What "done" means
The sub-tab shows REAL, ticker-specific output computed from live bars, and the
SWING / POSITION / INVEST toggle changes the timeframe (daily / weekly / monthly)
and therefore the read. When the server is absent (standalone showcase) or the
feed has no usable structure, it falls back to the EXISTING fixture and the
source badge says so honestly. Never white-screen, never throw.

## Part A — the Python engine: `engines/<engine>.py`

```python
from __future__ import annotations
NAME = "<engine>"      # MUST equal the engine string the JSX uses (see Part B)
LABEL = "<Display>"

def detect(df, meta, ticker):
    # df: pandas DataFrame, DatetimeIndex ASC, columns:
    #   Open High Low Close Volume  + enriched:
    #   spread, atr (ewm14), avgvol (50), rvol (vol/avgvol),
    #   spread_atr (spread/atr), clv (close-location 0..1), ema20, ema50
    # meta: {"tf": "Daily"|"Weekly"|"Monthly", "horizon": "...", "mode": "SWING"|"POSITION"|"INVESTMENT"}
    # ticker: str
    # RETURN: a JSON-serializable dict (see contract below). MUST NOT raise.
    ...
```

Rules:
- Auto-discovered by `pattern_engines.py` — no registration needed, just the file.
- Python 3.9. Start with `from __future__ import annotations`. Use numpy/pandas.
- **Honesty (principle 4):** if there's no usable structure, return
  `{"ok": True, "source": "real", "<engine>": None or "state":"none",
    "message": "<plain reason>", "cur_close": <float>}` — do NOT fabricate.
- **Mechanism (principle 2):** one-line comment stating WHY the pattern has edge.
- **Timeframe-aware:** windows must scale with `meta["tf"]` (a 40-bar lookback is
  ~2 months daily but ~3.5 years monthly). See `_TFW` in `wyckoff_engine.py`.
- Round prices to 2dp; include a `bars` array (windowed, last ~80–120) of
  `{"o","c","hi","lo","v"}` (v = rvol) whenever the view draws a chart.
- Keep it fast (<300ms): vectorize, no per-bar Python loops over the whole frame
  when avoidable.

### Return contract (superset — include what your view renders)
```jsonc
{
  "ok": true, "source": "real",
  "state": "real",                       // or "none" when nothing usable
  "confidence": 0.0-1.0,
  "bars": [{"o":..,"c":..,"hi":..,"lo":..,"v":..}],   // real, windowed
  "stat": { ... small header fields ... },
  "levels"|"events"|"lines"|"zones"|"profile"|...: [...],  // theory-specific
  "read": "<one-sentence plain-English verdict>",
  "cur_close": <float>
}
```
The exact sub-keys are whatever YOUR existing JSX view renders — read the view
first, then make the engine produce those fields from real data.

Test before finishing:
```bash
cd "/Volumes/MyMacDisk/Claude Skills/SwingTrade"
python3 -c "import pattern_engines as pe; d=pe.detect('<engine>','AAPL','SWING'); print({k:(len(v) if isinstance(v,list) else v) for k,v in d.items() if k!='bars'})"
python3 -c "import pattern_engines as pe; print(pe.detect('<engine>','NVDA','POSITION').get('state'), pe.detect('<engine>','WMB','INVESTMENT').get('meta'))"
```
All three modes must return `ok:True` and either real fields or an honest `none`.

## Part B — the React view: `src/patterns-<file>.jsx`

The view signature becomes `function <X>View({ ticker, dir, mode })`. Wire it:

```jsx
function use<X>Model(ticker, mode) {
  const { real, state, sym } = usePatternModel("<engine>", ticker, mode);
  const tf = (real && real.meta && real.meta.tf) || null;
  const usable = state === "loaded" && real && real.ok && /* your usability test, e.g. real.bars && real.levels */;
  if (usable) return { model: /* map real -> the shape your sub-components expect */, state: "real", sym, tf, usable: true };
  if (state === "loaded" && real && real.ok) return { model: FIXTURE_MODEL, state: "none", sym, tf, usable: false, message: real.message };
  return { model: FIXTURE_MODEL, state: state === "loading" ? "loading" : "mock", sym, tf, usable: false };
}
```

- Keep the EXISTING fixture constants as `FIXTURE_MODEL` (rename/wrap, don't delete) so the standalone showcase still renders.
- Convert sub-components to take data as PROPS (currently they read module-level
  constants) — exactly like `patterns-wyckoff.jsx` was refactored. Guard every
  field (`(model.levels || [])`, `(x || {}).y`). Never throw on a missing key.
- Add the badge at the top of the view:
  `<div className="pv-srcbar"><PatternSrcBadge state={state} usable={usable} sym={sym} tier={real && real.tier} tf={tf} /></div>`
- Charts: use the global `CandleChart` (see its prop contract at the top of
  `src/patterns-core.jsx`: bars, height, bands, hlines, markers, skeleton,
  lines, zones, profile, cloud, accent, span, projectFrom). Feed it `model.bars`.
- Globals available WITHOUT import (classic scripts): `React`, `usePatternModel`,
  `PatternSrcBadge`, `CandleChart`, `ConfBar`, `MiniTable`, `SubTabs`, `Field`,
  `SectionHeader`, `Pill`, `seedFromSym`, `buildSeries`, plus anything the file
  already references. Do not add import/require statements.
- Preserve all three layout directions (dir A/B/C) the view already supports.

## HARD CONSTRAINTS
- Edit ONLY: `engines/<engine>.py` (new) and `src/patterns-<file>.jsx`.
- Do NOT touch: `server.py`, `bullveda-boot.js`, `src/lens-patterns-v2.jsx`,
  `src/patterns-core.jsx`, `pattern_data.py`, `pattern_engines.py`,
  `engines/wyckoff.py`, `wyckoff_engine.py`, the CSS files, or any other engine.
- Do NOT rebuild the bundle (`build_bullveda.cjs`) or restart the server — the
  orchestrator does that once after all engines land.
- The `NAME` in your Python engine MUST equal the string passed to
  `usePatternModel("...")` in your JSX. Pick the tab id (see your task).
- Return your final summary as: engine name, what it computes, the usability
  test you used, and the 3-mode test output.
```
