import { expect, test } from '@playwright/test';

test('synthetic geography remains table-readable when basemap fails', async ({ page }) => {
  await page.goto('/');
  const panel = page.getByRole('region', { name: 'Geography review' });
  await expect(panel.getByRole('img', { name: 'Study area map' })).toBeVisible();
  await expect(panel.getByText('Basemap unavailable; schematic and table remain available.')).toBeVisible();
  await expect(panel.getByRole('table', { name: 'Matching map table' })).toBeVisible();
  await expect(panel.getByText('Availability and permission unknown')).toBeVisible();
  await expect(panel.getByText('Run readiness: unresolved connector and real study area.')).toBeVisible();
  await panel.getByLabel('Review training connector').check();
  await expect(panel.getByText('Training connector reviewed; real study area remains unresolved.')).toBeVisible();
});

test('both public-plan pilot cells show scoped routes and manual review controls', async ({ page }) => {
  await page.goto('/');
  const panel = page.getByRole('region', { name: 'Geography review' });
  await panel.getByLabel('Geography case').selectOption('qc');
  await expect(panel.getByText('Talayan-centered QC pilot cell.')).toBeVisible();
  await expect(panel.getByRole('table', { name: 'Matching map table' })).toContainText('Rest of Quezon City');
  await expect(panel.getByText('Reviewed road route: found, 211 s, 2053257 mm.')).toBeVisible();
  await expect(panel.getByText('Basemap unavailable; schematic and table remain available.')).toBeVisible();
  await expect(panel.getByText('Pilot geography awaits personal scenario review.')).toBeVisible();
  await panel.getByRole('button', { name: 'Confirm pilot scope and reset pending assumptions' }).click();
  await expect(panel.getByText('Pilot geography reviewed for this local case.')).toBeVisible();
  await page.getByLabel('Review case').selectOption('qc');
  await expect(page.getByText(/Scenario location review: complete/)).toBeVisible();

  await panel.getByLabel('Geography case').selectOption('guiguinto');
  await expect(panel.getByText('Poblacion-centered Guiguinto pilot cell.')).toBeVisible();
  await expect(panel.getByRole('table', { name: 'Matching map table' })).toContainText('Rest of Guiguinto');
  await expect(panel.getByText('Reviewed road route: found, 64 s, 569296 mm.')).toBeVisible();
  await expect(panel.getByText('their availability and permission are unknown')).toBeVisible();
  await panel.getByRole('button', { name: 'Confirm pilot scope and reset pending assumptions' }).click();
  await expect(panel.getByText('Pilot geography reviewed for this local case.')).toBeVisible();
});
