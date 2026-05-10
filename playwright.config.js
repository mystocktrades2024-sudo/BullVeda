// Playwright config for SwingTrade V2 dashboard browser tests.
// Tests assume the local dev server is running on http://localhost:7432.
// Auth: pass SWING_USER + SWING_PASS as env vars.
//
// Run:    npx playwright test                                  (headless)
//         npx playwright test --headed                         (watch in real Chrome)
//         npx playwright test --ui                             (interactive UI)
// Report: npx playwright show-report
//
// (CapStudio test coverage 2026-05-09 — augments scripts/smoke_test_modules.py)

import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  timeout: 30_000,
  expect: { timeout: 8_000 },
  fullyParallel: false,        // dashboard has shared state — serialize
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [
    ['list'],
    ['html', { open: 'never', outputFolder: 'tests/playwright-report' }],
  ],
  use: {
    baseURL: 'http://localhost:7432',
    httpCredentials: process.env.SWING_USER && process.env.SWING_PASS
      ? { username: process.env.SWING_USER, password: process.env.SWING_PASS }
      : undefined,
    viewport: { width: 1440, height: 900 },
    screenshot: 'only-on-failure',
    trace: 'on-first-retry',
    ignoreHTTPSErrors: true,
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
  outputDir: 'tests/test-results',
});
