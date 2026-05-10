# tests/ — browser test suite (Playwright)

Two complementary layers:
- **`scripts/smoke_test_modules.py`** — pure-Python structural smoke test. No browser. Runs in ~2s. Checks file existence, JS syntax, registry consistency, route registration. Suitable for pre-commit. **No auth required.**
- **`tests/*.spec.js`** — real browser tests via Playwright + Chromium. Loads each tab, asserts module renders fire, captures screenshots. **Requires auth** (set `SWING_USER` + `SWING_PASS` env vars).

## Running

```
# No-auth structural test (always passes)
npx playwright test tests/00-no-auth-routes.spec.js

# Full browser walk (needs creds)
SWING_USER=admin SWING_PASS='your-pass' npx playwright test

# Single test
npx playwright test tests/01-dashboard-smoke.spec.js

# Headed mode (watch in real Chrome)
SWING_USER=admin SWING_PASS='...' npx playwright test --headed

# Interactive UI
npx playwright test --ui
```

## Files

| File | Purpose | Auth needed |
|------|---------|-------------|
| `00-no-auth-routes.spec.js` | All static + API routes registered (return 401) | NO |
| `01-dashboard-smoke.spec.js` | Dashboard boot — module loader prints expected console lines, 28 overrides install, no red errors | YES |
| `02-tabs-walk.spec.js` | Walks every modular tab, asserts module render fires for ≥8 tabs | YES |
| `03-elite-detail.spec.js` | Per-ticker page — 25 sub-tab module renderers exist on window, each tab clickable | YES |
| `04-pixel-diff.spec.js` | **MOD-2** Pixel-diff regression at 3 viewports (1440 / 810 / 390). Compares against committed snapshots. Generate baselines with `--update-snapshots`. Threshold 1–2%. | YES |

## What this catches

- Module file missing or 404
- JS syntax error in any module
- shell.js fails to install overrides (CapStudio loader broken)
- A tab's module render throws (`module render 'X' threw: …`)
- A sub-tab module fails to install via window-binding
- `window.__getDetailTicker` race / naming mismatch
- Pre-existing console errors (filtered: backtest-report 404, EODHD WS — known harmless)

## Pixel-diff (MOD-2) — shipped 2026-05-10

`tests/04-pixel-diff.spec.js` captures screenshots at 6 surfaces × viewports
and compares against committed PNG baselines.

**Coverage:**
1. dashboard.html @ desktop (1440x900)
2. dashboard.html @ tablet portrait (810x1080)
3. dashboard.html @ phone (390x844)
4. elite-detail Overview @ desktop
5. elite-detail Plan sub-tab @ desktop
6. elite-detail Overview @ phone

**Stability tricks** (applied via `stabilize()` helper):
- Disable all animations and transitions (`animation-duration: 0s`)
- Hide volatile elements (timestamps, scan-time, live-pulse)
- Wait for `networkidle` + 400ms settle

**First-run / baseline generation:**
```
SWING_USER=admin SWING_PASS='...' \
  npx playwright test tests/04-pixel-diff.spec.js --update-snapshots
git add tests/04-pixel-diff.spec.js-snapshots/
git commit -m "MOD-2: pixel-diff baseline snapshots"
```

**Subsequent runs** (CI / pre-commit, gated):
```
SWING_USER=admin SWING_PASS='...' \
  npx playwright test tests/04-pixel-diff.spec.js
```

**Why opt-in via env flag** (`SWINGTRADE_PIXEL_BASELINE=1`):
data churn between scans (regime cards, ticker prices) would cause
constant false-positive failures. Pixel-diff is for *structural*
regressions — run it manually after CSS or markup changes, not on
every commit.

**Threshold tuning:** `threshold: 0.01` (1%) for dashboard; `0.02`
(2%) for elite-detail (per-ticker variation). Adjust if baselines are
too brittle.
