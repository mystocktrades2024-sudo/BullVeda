// 04-pixel-diff.spec.js — MOD-2 (2026-05-10): pixel-diff regression baseline.
//
// Captures screenshots of canonical surfaces and compares against committed
// baselines. Fails on any visual delta above threshold (1% by default).
//
// FIRST RUN (after a known-good state):
//   SWING_USER=admin SWING_PASS='...' npx playwright test tests/04-pixel-diff.spec.js \
//       --update-snapshots
//
// SUBSEQUENT RUNS:
//   SWING_USER=admin SWING_PASS='...' npx playwright test tests/04-pixel-diff.spec.js
//
// Snapshots live in tests/04-pixel-diff.spec.js-snapshots/.
// Naming: {surface}-{viewport}.png
//
// Threshold tuning (in `expect(...).toMatchSnapshot({ threshold: ... })`):
//   - 0.01 = strict (1%) — what we ship
//   - 0.05 = lenient (5%) — useful while baselines stabilize
//
// CI integration: this file is run by the smoke-test pre-commit hook only
// when SWINGTRADE_PIXEL_BASELINE=1 is set. Otherwise it's manual-only to avoid
// false flags from data churn (regime cards rebuild every scan).

import { test, expect } from '@playwright/test';

// Helper: stabilize the page before snapshot — disables animations, hides
// any data badge that updates per-scan, waits for idle.
async function stabilize(page) {
  await page.addStyleTag({ content: `
    *, *::before, *::after {
      animation-duration: 0s !important;
      animation-delay: 0s !important;
      transition-duration: 0s !important;
      caret-color: transparent !important;
    }
    /* Hide elements that change every scan — pixel-diff is for STRUCTURE, not data */
    .scan-time, .last-scan, .as-of, .timestamp,
    [data-volatile="true"], .live-indicator,
    /* Regime cards animate price tickers — freeze them */
    .regime-tick, .live-pulse {
      visibility: hidden !important;
    }
  `});
  // Let any in-flight network requests settle
  await page.waitForLoadState('networkidle').catch(() => {});
  await page.waitForTimeout(400);
}

test.describe('Pixel-diff regression (MOD-2)', () => {

  // ── 1. Main dashboard at desktop (1440x900) ──────────────────────────
  test('dashboard.html @ desktop 1440', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/kairos.html', { waitUntil: 'networkidle' });
    await page.waitForFunction(
      () => window.TAB_RENDERERS && Object.keys(window.TAB_RENDERERS).length > 0,
      { timeout: 15_000 }
    );
    await stabilize(page);
    expect(await page.screenshot({ fullPage: false, animations: 'disabled' }))
      .toMatchSnapshot('dashboard-desktop-1440.png', {
        threshold: 0.01,
        maxDiffPixelRatio: 0.01,
      });
  });

  // ── 2. Main dashboard at tablet portrait (810x1080) ─────────────────
  test('dashboard.html @ tablet portrait 810', async ({ page }) => {
    await page.setViewportSize({ width: 810, height: 1080 });
    await page.goto('/kairos.html', { waitUntil: 'networkidle' });
    await page.waitForFunction(
      () => window.TAB_RENDERERS && Object.keys(window.TAB_RENDERERS).length > 0,
      { timeout: 15_000 }
    );
    await stabilize(page);
    expect(await page.screenshot({ fullPage: false, animations: 'disabled' }))
      .toMatchSnapshot('dashboard-tablet-810.png', {
        threshold: 0.01,
        maxDiffPixelRatio: 0.01,
      });
  });

  // ── 3. Main dashboard at phone (390x844, iPhone 13) ─────────────────
  test('dashboard.html @ phone 390', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/kairos.html', { waitUntil: 'networkidle' });
    await page.waitForFunction(
      () => window.TAB_RENDERERS && Object.keys(window.TAB_RENDERERS).length > 0,
      { timeout: 15_000 }
    );
    await stabilize(page);
    expect(await page.screenshot({ fullPage: false, animations: 'disabled' }))
      .toMatchSnapshot('dashboard-phone-390.png', {
        threshold: 0.01,
        maxDiffPixelRatio: 0.01,
      });
  });

  // ── 4. Elite-detail Overview tab at desktop ──────────────────────────
  test('elite-detail Overview @ desktop 1440', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    // Pick a stable ticker — AVT was BUY in recent runs, but any will do.
    // We fail soft if the ticker doesn't exist (registry might be empty).
    await page.goto('/kairos.html?t=AVT', { waitUntil: 'networkidle' });
    await page.waitForTimeout(1000);
    await stabilize(page);
    expect(await page.screenshot({ fullPage: false, animations: 'disabled' }))
      .toMatchSnapshot('elite-detail-overview-desktop-1440.png', {
        threshold: 0.02,  // slightly lenient — per-ticker data varies
        maxDiffPixelRatio: 0.02,
      });
  });

  // ── 5. Elite-detail Plan sub-tab @ desktop ──────────────────────────
  test('elite-detail Plan @ desktop 1440', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/kairos.html?t=AVT', { waitUntil: 'networkidle' });
    await page.waitForTimeout(800);
    // Click Plan sub-tab
    const planTab = page.locator('.fd-tab[data-tab="plan"]').first();
    if (await planTab.count() > 0) {
      await planTab.click();
      await page.waitForTimeout(500);
    }
    await stabilize(page);
    expect(await page.screenshot({ fullPage: false, animations: 'disabled' }))
      .toMatchSnapshot('elite-detail-plan-desktop-1440.png', {
        threshold: 0.02,
        maxDiffPixelRatio: 0.02,
      });
  });

  // ── 6. Elite-detail Overview @ phone (390) — checks MOB-1/MOB-2 ───
  test('elite-detail Overview @ phone 390', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/kairos.html?t=AVT', { waitUntil: 'networkidle' });
    await page.waitForTimeout(800);
    await stabilize(page);
    expect(await page.screenshot({ fullPage: false, animations: 'disabled' }))
      .toMatchSnapshot('elite-detail-overview-phone-390.png', {
        threshold: 0.02,
        maxDiffPixelRatio: 0.02,
      });
  });

});
