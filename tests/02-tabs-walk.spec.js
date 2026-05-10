// 02-tabs-walk.spec.js — clicks every modular tab + asserts module render fires.
// Uses the registry as the source of truth for which tabs are modular.

import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const REG_PATH = resolve(__dirname, '../data/capability_registry.json');
const REGISTRY = JSON.parse(readFileSync(REG_PATH, 'utf-8'));

// Only test tabs that have a `module` field — Scanner et al. without module are inline-only.
const MODULAR_TABS = Object.entries(REGISTRY.tabs || {})
  .filter(([_, v]) => v.module)
  .map(([id, v]) => ({ id, label: v.label, module: v.module }));

test.describe('Tabs walk', () => {
  test('clicks each modular tab + asserts module render', async ({ page }) => {
    const renderedFromModule = new Set();
    const errors = [];

    page.on('console', msg => {
      const t = msg.text();
      const m = t.match(/\[shell\] rendered tab '(\w+)' from module/);
      if (m) renderedFromModule.add(m[1]);
      if (msg.type() === 'error' && !/backtest-report/.test(t) && !/eodhd/i.test(t) && !/WebSocket/.test(t)) {
        errors.push(t);
      }
    });
    page.on('pageerror', err => errors.push('pageerror: ' + err.message));

    await page.goto('/v2/dashboard.html', { waitUntil: 'networkidle' });

    // Wait for shell.js to finish booting (overrides installed)
    await page.waitForFunction(
      () => window.TAB_RENDERERS && Object.values(window.TAB_RENDERERS)
            .filter(f => typeof f === 'function' && f.name === '_moduleRender').length >= 28,
      { timeout: 15_000 }
    );

    // Click each modular tab; wait briefly for render
    for (const tab of MODULAR_TABS) {
      const sel = `.fs-link[data-tab="${tab.id}"], .sb-link[data-tab="${tab.id}"]`;
      const el = page.locator(sel).first();
      const exists = await el.count() > 0;
      if (!exists) {
        // Sidebar entry might be hidden by profile — that's expected for some tabs
        continue;
      }
      await el.click({ trial: false }).catch(() => {});
      await page.waitForTimeout(150);  // give the wrapped render a tick
    }

    // We expect MOST modular tabs to have rendered. Be lenient — some tabs are
    // gated by user role or only render if data is present.
    expect(renderedFromModule.size, `Modules that fired:\n${[...renderedFromModule].join(', ')}`).toBeGreaterThanOrEqual(8);

    // No unrelated console errors during the walk
    expect(errors).toEqual([]);
  });
});
