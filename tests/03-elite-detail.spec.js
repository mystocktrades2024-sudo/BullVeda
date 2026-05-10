// 03-elite-detail.spec.js — per-ticker page: subtab modules load + render.

import { test, expect } from '@playwright/test';

test.describe('Elite-detail page', () => {
  test('loads + 25 sub-tab modules render', async ({ page }) => {
    const consoleLines = [];
    const errors = [];
    page.on('console', msg => {
      consoleLines.push(`[${msg.type()}] ${msg.text()}`);
      if (msg.type() === 'error' && !/eodhd/i.test(msg.text()) && !/WebSocket/.test(msg.text())) {
        errors.push(msg.text());
      }
    });
    page.on('pageerror', err => errors.push('pageerror: ' + err.message));

    const resp = await page.goto('/v2/elite-detail.html?t=AAPL', { waitUntil: 'networkidle' });
    expect(resp.status()).toBeLessThan(400);

    // Wait for the detail-shell to finish painting
    await page.waitForFunction(
      () => /painted \d+ sub-tab renderers/.test(performance.getEntriesByType('mark').map(m => m.name).join(' ')) ||
            // fallback: wait for sub-tab override to be window-bound
            (typeof window.renderHead === 'function' && typeof window.renderPlan === 'function'),
      { timeout: 15_000 }
    ).catch(() => { /* either signal works */ });

    // Expect ALL key sub-tab render functions to exist on window
    const present = await page.evaluate(() => {
      const names = ['renderEliteOverview','renderHead','renderVerdict','renderScorecard',
                     'renderThesisDetail','renderResearchDetail','renderPlan','renderRisk',
                     'renderBacktest','renderChart','renderHorizons','renderElliott',
                     'renderMultiMethod','renderTV','renderSMC','renderFund','renderIntel',
                     'renderSentimentTab','renderOptionsTab','renderNewsTab','renderInsider',
                     'renderInstitutional','renderRuleEngine'];
      return names.filter(n => typeof window[n] === 'function');
    });
    expect(present.length, `Sub-tab renderers on window: ${present.length}/23`).toBeGreaterThanOrEqual(23);

    // Click each sub-tab
    const fdtabs = await page.locator('.fd-tab[data-fdtab]').all();
    for (const tab of fdtabs) {
      const visible = await tab.isVisible().catch(() => false);
      if (!visible) continue;  // role-hidden tabs OK
      await tab.click().catch(() => {});
      await page.waitForTimeout(80);
    }

    expect(errors).toEqual([]);
  });
});
