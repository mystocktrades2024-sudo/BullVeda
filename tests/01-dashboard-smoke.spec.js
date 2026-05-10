// 01-dashboard-smoke.spec.js — V2 dashboard module-loader smoke test.
//
// Asserts:
//   1. Page loads without 4xx/5xx
//   2. CapStudio module loader prints expected console lines
//   3. window.TAB_RENDERERS has 28 module overrides installed
//   4. No red console errors (console.error) during boot
//   5. window.__capStudioMetrics is populated after first tab paint
//
// (CapStudio test coverage 2026-05-09)

import { test, expect } from '@playwright/test';

const BOOT_LINES = [
  /\[shell\] CapStudio module loader booting/,
  /\[shell\] module cache-bust version: \d+/,
  /\[shell\] loaded registry: \d+ tabs, \d+ sub-tabs/,
  /\[shell\] installed 28 module override\(s\) for tabs/,
  /\[shell\] drawer module loaded/,
  /\[shell\] widgets module loaded/,
  /\[shell\] actions module loaded: \d+ handlers/,
];

test.describe('Dashboard boot', () => {
  test('loads cleanly + module loader prints expected lines', async ({ page }) => {
    const consoleLines = [];
    const errors = [];
    page.on('console', msg => {
      consoleLines.push(`[${msg.type()}] ${msg.text()}`);
      if (msg.type() === 'error') errors.push(msg.text());
    });
    page.on('pageerror', err => errors.push('pageerror: ' + err.message));

    const resp = await page.goto('/v2/dashboard.html', { waitUntil: 'networkidle' });
    expect(resp.status(), 'dashboard.html HTTP status').toBeLessThan(400);

    // Wait for the loader's final boot line to appear
    await page.waitForFunction(
      () => window.__capStudioMetrics && Object.keys(window.__capStudioMetrics.moduleLoadMs).length > 0,
      { timeout: 15_000 }
    );

    // Each expected boot line should be present
    for (const pat of BOOT_LINES) {
      const found = consoleLines.some(l => pat.test(l));
      expect(found, `Expected console line matching ${pat}\nGot:\n${consoleLines.slice(0, 30).join('\n')}`).toBe(true);
    }

    // window.TAB_RENDERERS should have at least 28 module overrides
    const overrideCount = await page.evaluate(() => {
      const renderers = window.TAB_RENDERERS || {};
      return Object.values(renderers).filter(f => typeof f === 'function' && f.name === '_moduleRender').length;
    });
    expect(overrideCount, 'module override count').toBeGreaterThanOrEqual(28);

    // No unrelated red errors (filter pre-existing backtest-report 404)
    const unexpectedErrors = errors.filter(e =>
      !/backtest-report/.test(e) &&
      !/eodhd/.test(e) &&
      !/WebSocket/.test(e) &&
      !/Failed to load resource/.test(e)
    );
    expect(unexpectedErrors, 'unexpected console errors:\n' + unexpectedErrors.join('\n')).toEqual([]);
  });
});
