import { expect, test } from '@playwright/test';

test('review, run, and recover against the local API and engine', async ({ page }) => {
  let active = false;
  await page.route(/\/api\/v1\/temporary-sessions(?:\/.*)?$/, async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (request.method() === 'GET' && path.endsWith('/current')) {
      await route.fulfill(active
        ? { status: 200, json: { workspace_id: 'synthetic-smoke', expires_at: new Date(Date.now() + 60 * 60_000).toISOString(), absolute_expires_at: new Date(Date.now() + 24 * 60 * 60_000).toISOString(), csrf_token: 'smoke-csrf' } }
        : { status: 401 });
    } else if (request.method() === 'POST' && path.endsWith('/temporary-sessions')) {
      active = true;
      await route.fulfill({ status: 201, json: { workspace_id: 'synthetic-smoke', expires_at: new Date(Date.now() + 60 * 60_000).toISOString(), absolute_expires_at: new Date(Date.now() + 24 * 60 * 60_000).toISOString(), csrf_token: 'smoke-csrf' } });
    } else {
      await route.fulfill({ status: 404 });
    }
  });
  await page.goto('/');
  await page.getByRole('button', { name: 'Start analysis' }).click();

  await expect(page.getByRole('heading', { name: 'Review the synthetic case' })).toBeVisible();
  await expect(page.getByText('Synthetic training fixture; no source plan')).toBeVisible();
  await expect(page.getByText('One direct vehicle trip; arrival water allowance only')).toBeVisible();

  const runResponse = page.waitForResponse((response) =>
    response.url().endsWith('/api/v1/local/cases/one-trip-water/run') && response.request().method() === 'POST');
  await page.getByRole('button', { name: 'Run analysis' }).click();
  const response = await runResponse;
  expect(response.status()).toBe(200);
  const result = await response.json();
  expect(result.arrived_people).toBe(6);
  expect(result.water_shortfall_ml).toBe(2000);
  await expect(page.getByRole('heading', { name: 'Computed outcome' })).toBeVisible();
  const resultPanel = page.getByRole('region', { name: 'Computed outcome' });
  await expect(resultPanel.getByText('6', { exact: true })).toBeVisible();
  await expect(resultPanel.getByText('2,000 mL', { exact: true })).toBeVisible();

  await page.getByLabel('Case ID').fill('unknown-case');
  await page.getByRole('button', { name: 'Open case' }).click();
  await expect(page.getByRole('alert')).toContainText('Opening the case failed (404)');
  await page.getByLabel('Case ID').fill('one-trip-water');
  await page.getByRole('button', { name: 'Try again' }).click();
  await expect(page.getByRole('heading', { name: 'Review the synthetic case' })).toBeVisible();
  await expect(page.getByRole('alert')).toHaveCount(0);
});
