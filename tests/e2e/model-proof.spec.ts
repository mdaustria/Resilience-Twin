import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { expect, test } from '@playwright/test';

const reports = join(process.cwd(), 'release', 'validation', 'reports');

for (const area of ['qc', 'guiguinto']) {
  test(`${area} source gaps and evaluated local proof stay separate and offline`, async ({ browser }) => {
    const context = await browser.newContext({ javaScriptEnabled: false, offline: true });
    let requests = 0;
    await context.route('**/*', route => {
      requests += 1;
      return route.abort();
    });
    const page = await context.newPage();
    const gap = readFileSync(join(reports, `${area}-gap_only.html`), 'utf8');
    await page.setContent(gap);
    await expect(page.getByRole('heading', { name: 'Readiness gaps' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Measured outcomes' })).toHaveCount(0);
    await expect(page.getByText('No operational assumptions accepted in this source-only view')).toBeVisible();

    const evaluated = readFileSync(join(reports, `${area}-evaluated.html`), 'utf8');
    await page.setContent(evaluated);
    await expect(page.getByRole('heading', { name: 'Measured outcomes' })).toBeVisible();
    await expect(page.getByText('Road closure at time zero', { exact: false })).toBeVisible();
    const record = JSON.parse(readFileSync(join(reports, `${area}-pilot-proof.json`), 'utf8'));
    expect(record.comparison_status).toBe('complete');
    expect(record.review_ready_to_run).toBe(true);
    expect(record.baseline).toHaveLength(2);
    expect(record.variant).toHaveLength(2);
    expect(record.baseline[0].outcome.on_time_people).toBe(20);
    expect(record.baseline[1].outcome.on_time_people).toBe(0);
    expect(record.variant.every((member: { outcome: { water_unmet_ml: number } }) =>
      member.outcome.water_unmet_ml === 0)).toBe(true);
    expect(requests).toBe(0);
    await context.close();
  });
}
