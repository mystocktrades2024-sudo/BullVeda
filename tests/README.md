# SwingTrade Playwright tests — MOD-3

## Suite layout

| File | What it tests | Auth required? |
|------|---------------|----------------|
| `00-no-auth-routes.spec.js` | Public/static routes accessible without login | ❌ no |
| `01-dashboard-smoke.spec.js` | Dashboard boot, regime strip, sidebar, tab nav | ✅ yes |
| `02-tabs-walk.spec.js` | Click each top-level tab; assert no console errors | ✅ yes |
| `03-elite-detail.spec.js` | Per-ticker page boot + sub-tab walk | ✅ yes |

## Running locally

The auth-required suites need `SWING_USER` + `SWING_PASS` env vars. The
server uses HTTP Basic Auth (FastAPI `HTTPBasic`).

```bash
# One-shot
SWING_USER=gari SWING_PASS=swing2026 npx playwright test

# Persisted (add to your shell profile or local .envrc)
export SWING_USER=gari
export SWING_PASS=swing2026
npx playwright test                      # all suites
npx playwright test 00-no-auth           # just the no-auth suite
npx playwright test --headed             # visible browser
npx playwright test --debug              # pause-on-error inspector
```

## Running in CI

Add `SWING_USER` and `SWING_PASS` as **encrypted secrets** in the CI
provider (GitHub Actions / GitLab / etc.). Reference in the workflow:

```yaml
env:
  SWING_USER: ${{ secrets.SWING_USER }}
  SWING_PASS: ${{ secrets.SWING_PASS }}
- run: npx playwright test
```

## What gets validated

`playwright.config.js` sets `httpCredentials` only when both env vars
are present, so missing creds → tests skip the auth-required scenarios
gracefully (browser sees 401, test marks as skipped not failed).

The auth-required suites cover:

1. **Boot timing**: `__perfReport()` snapshot must show `init-end < 800ms`
   (per PERF-1d budget). Regression > 100ms fails the test.
2. **Module loading**: every `core/*.js` and `tabs/*.js` module load
   without console errors.
3. **Sub-tab render**: each elite-detail sub-tab (overview/plan/thesis/
   smc/models/...) renders without throwing — verified via
   `data-rendered="true"` attribute the modules set on success.
4. **CapStudio gating**: action buttons disabled per role; admin-only
   buttons hidden for non-admin roles.

## Adding new tests

For UI-only changes, add a smoke test to `02-tabs-walk.spec.js`. For
per-ticker page features, add to `03-elite-detail.spec.js`.

For pixel-diff regression (MOD-2 follow-up), use:

```javascript
await page.screenshot({ path: 'tests/snapshots/dashboard-bull.png', fullPage: true });
expect(await page.screenshot()).toMatchSnapshot('dashboard-bull.png', {
  threshold: 0.001  // 0.1% pixel diff tolerance
});
```

(See OpenItemTracker MOD-2 for the snapshot baselining workflow.)

## Troubleshooting

- **All auth tests skip** → SWING_USER / SWING_PASS not set
- **All tests fail with ECONNREFUSED** → server not running on localhost:7432.
  Start it: `python3 server.py --no-reload` in another terminal.
- **Pixel-diff tests fail with no baseline** → first run baseline:
  `npx playwright test --update-snapshots`
- **Headed mode fails on CI** → CI runners are headless-only. Don't pass
  `--headed`.
