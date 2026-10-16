import { expect, test } from '@playwright/test';

test('source-only gap stays reviewable; assumption, seal and edit change readiness', async ({ page }) => {
  await page.goto('/');
  const panel = page.getByRole('region', { name: 'Evidence and run readiness' });
  await expect(panel).toBeVisible();
  await expect(panel.getByText('Document review: available')).toBeVisible();
  await expect(panel.getByText('Run readiness: missing inputs')).toBeVisible();
  await expect(panel.getByText('Missing annex: water inventory annex')).toBeVisible();
  await expect(panel.getByText(/opening_water_ml: Only proposed or target resources/)).toBeVisible();
  await expect(panel.getByText(/physical page 2/)).toBeVisible();

  const assumptionResponse = page.waitForResponse((response) =>
    response.url().endsWith('/api/v1/local/review/assumption') && response.request().method() === 'POST');
  await panel.getByRole('button', { name: 'Declare usable assumption' }).click();
  expect((await assumptionResponse).status()).toBe(200);
  await expect(panel.getByText('Run readiness: needs acknowledgment')).toBeVisible();
  await expect(panel.getByText(/opening_water_ml: Only proposed or target resources/)).toBeVisible();

  await panel.getByRole('button', { name: 'Seal review' }).click();
  await expect(panel.getByText('Revision 2.')).toBeVisible();
  await panel.getByRole('button', { name: 'Acknowledge assumptions' }).click();
  await expect(panel.getByText('Run readiness: ready to run')).toBeVisible();

  await panel.getByLabel('Assumed opening water (mL)').fill('6000');
  await panel.getByRole('button', { name: 'Declare usable assumption' }).click();
  await expect(panel.getByText('Run readiness: needs acknowledgment')).toBeVisible();
  await expect(panel.getByText('Revision 4.')).toBeVisible();

  const stale = await page.request.post('/api/v1/local/review/seal', {
    headers: { 'X-Fixture-Owner': 'fixture-a' },
    data: { expected_revision: 0 },
  });
  expect(stale.status()).toBe(409);
});

test('both public plan cases show their own citations, conflicts and missing inputs', async ({ page }) => {
  await page.goto('/');
  const panel = page.getByRole('region', { name: 'Evidence and run readiness' });
  await panel.getByLabel('Review case').selectOption('qc');
  await expect(panel.getByText(/Source: Quezon City DRRMP 2021-2027 Volume 1/)).toBeVisible();
  await expect(panel.getByText(/Missing annex: Annex A contingency plans/)).toBeVisible();
  await expect(panel.getByText(/physical page 82/)).toBeVisible();
  await expect(panel.getByText('Run readiness: missing inputs')).toBeVisible();
  await panel.getByLabel('evacuee_people (PERSON)').fill('200');
  await panel.getByRole('button', { name: 'Apply reviewed defaults' }).click();
  await expect(panel.getByText('Revision 1.')).toBeVisible();
  await expect(panel.getByText('Run readiness: needs location and scenario review')).toBeVisible();

  await panel.getByLabel('Review case').selectOption('guiguinto');
  await expect(panel.getByText(/Source: Guiguinto MDRRM Plan 2023-2025/)).toBeVisible();
  await expect(panel.getByText(/shelter_capacity_people: 3987 FAMILY/)).toBeVisible();
  await expect(panel.getByText(/shelter_capacity_people: 4087 FAMILY/)).toBeVisible();
  await expect(panel.getByText(/physical page 121/).first()).toBeVisible();
  await expect(panel.getByText('Run readiness: missing inputs')).toBeVisible();
});
