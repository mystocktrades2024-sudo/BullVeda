// 00-no-auth-routes.spec.js — verifies all module routes are registered
// (return 401, not 404) WITHOUT requiring credentials. Always-passing
// smoke test for CI without secrets.

import { test, expect } from '@playwright/test';

const STATIC_ROUTES = [
  '/kairos.html',
  '/kairos.html',
  '/v2/_v',
  '/v2/core/shell.js',
  '/v2/core/shared.js',
  '/v2/core/drawer.js',
  '/v2/core/actions.js',
  '/v2/core/widgets.js',
  '/v2/core/elite-detail-shell.js',
  '/v2/tabs/portfolio/portfolio.js',
  '/v2/tabs/audit/audit.js',
  '/v2/tabs/strategies/strategies.js',
  '/v2/tabs/playbook/playbook.js',
  '/v2/subtabs/plan/plan.js',
  '/v2/subtabs/tv/tv.js',
];

const API_ROUTES = [
  '/api/capability-registry',
  '/api/roles',
  '/api/me',
];

test.describe('No-auth route registration', () => {
  test('all static module routes return 401 (registered + auth-gated)', async ({ request }) => {
    for (const r of STATIC_ROUTES) {
      const resp = await request.head(r, { failOnStatusCode: false });
      expect(resp.status(), `route ${r}`).toBe(401);
    }
  });

  test('all API routes return 401 (registered)', async ({ request }) => {
    for (const r of API_ROUTES) {
      const resp = await request.get(r, { failOnStatusCode: false });
      expect(resp.status(), `api ${r}`).toBe(401);
    }
  });
});
