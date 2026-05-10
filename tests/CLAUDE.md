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

## What this catches

- Module file missing or 404
- JS syntax error in any module
- shell.js fails to install overrides (CapStudio loader broken)
- A tab's module render throws (`module render 'X' threw: …`)
- A sub-tab module fails to install via window-binding
- `window.__getDetailTicker` race / naming mismatch
- Pre-existing console errors (filtered: backtest-report 404, EODHD WS — known harmless)

## Future

Pixel-diff regression: capture baseline screenshots of every tab + sub-tab via Playwright. Compare on each test run. Fails on any visual delta. Build on top of the existing tabs-walk + elite-detail tests.

Generation: `npx playwright test --update-snapshots` after a known-good state.
