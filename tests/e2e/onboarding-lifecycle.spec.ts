import { expect, test, type BrowserContext } from '@playwright/test';

type SessionRecord = { workspace: string; expires: number; absolute: number; ended: boolean };

async function installSessionApi(context: BrowserContext) {
  const records = new Map<string, SessionRecord>();
  let next = 0;
  const events: string[] = [];
  await context.route(/\/api\/v1\/temporary-sessions(?:\/.*)?$/, async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const handle = /(?:^|;\s*)__session=([^;]+)/.exec(request.headers().cookie ?? '')?.[1];
    const record = handle ? records.get(handle) : undefined;
    const valid = record && !record.ended && record.expires > Date.now() && record.absolute > Date.now();
    const headers = { 'Cache-Control': 'private, no-store', 'Content-Type': 'application/json' };
    const respond = (status: number, body = '') => route.fulfill({ status, headers, body });
    const status = (item: SessionRecord) => JSON.stringify({
      workspace_id: item.workspace,
      expires_at: new Date(item.expires).toISOString(),
      absolute_expires_at: new Date(item.absolute).toISOString(),
      csrf_token: `csrf-${item.workspace}`,
    });
    if (request.method() === 'GET' && path.endsWith('/current')) {
      await respond(valid ? 200 : 401, valid ? status(record) : '');
    } else if (request.method() === 'POST' && path.endsWith('/temporary-sessions')) {
      if (valid) { await respond(403); return; }
      next += 1;
      const created = { workspace: `workspace-${next}`, expires: Date.now() + 2 * 60 * 60_000, absolute: Date.now() + 24 * 60 * 60_000, ended: false };
      records.set(`handle-${next}`, created);
      events.push('start');
      await route.fulfill({ status: 201, headers: { ...headers, 'Set-Cookie': `__session=handle-${next}; Path=/; HttpOnly; Secure; SameSite=Lax` }, body: status(created) });
    } else if (request.method() === 'POST' && path.endsWith('/current/activity')) {
      if (!valid) { await respond(401); return; }
      if (request.headers()['x-csrf-token'] !== `csrf-${record.workspace}`) { await respond(403); return; }
      record.expires = Math.min(Date.now() + 2 * 60 * 60_000, record.absolute);
      events.push('renew');
      await respond(200, status(record));
    } else if (request.method() === 'DELETE' && path.endsWith('/current')) {
      if (!valid) { await respond(401); return; }
      if (request.headers()['x-csrf-token'] !== `csrf-${record.workspace}`) { await respond(403); return; }
      record.ended = true;
      events.push('end');
      await route.fulfill({ status: 204, headers: { 'Set-Cookie': '__session=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0' } });
    } else {
      await respond(404);
    }
  });
  return { records, events };
}

test('guest lifecycle retains valid work, then blocks lost, expired and ended sessions', async ({ page, context }) => {
  const api = await installSessionApi(context);
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Start analysis' })).toBeVisible();
  await expect(page.getByText('This is not zero storage.', { exact: false })).toBeVisible();
  await expect(page.getByText('Closing a tab does not delete it.', { exact: false })).toBeVisible();
  await expect(page.getByText('Download reports before expiry.', { exact: false })).toBeVisible();
  await expect(page.getByRole('button', { name: /sign in|log in/i })).toHaveCount(0);
  await page.getByRole('button', { name: 'Start analysis' }).click();
  await expect(page.getByText('Analysis active · workspace workspace-1')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Review the synthetic case' })).toBeVisible();
  await page.reload();
  await expect(page.getByText('Analysis active · workspace workspace-1')).toBeVisible();

  const second = await context.newPage();
  await second.goto('/');
  await expect(second.getByText('Analysis active · workspace workspace-1')).toBeVisible();
  api.records.get('handle-1')!.expires = Date.now() + 15 * 60_000;
  await page.reload();
  await expect(page.getByText('This analysis expires soon.', { exact: false })).toBeVisible();
  await page.getByRole('button', { name: 'Renew session' }).click();
  await expect(page.getByText('This analysis expires soon.', { exact: false })).toHaveCount(0);
  expect(api.events).toContain('renew');

  await context.clearCookies();
  await page.reload();
  await expect(page.getByRole('button', { name: 'Start analysis' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Review the synthetic case' })).toHaveCount(0);
  await page.getByRole('button', { name: 'Start analysis' }).click();
  await expect(page.getByText('Analysis active · workspace workspace-2')).toBeVisible();
  api.records.get('handle-2')!.expires = Date.now() - 1;
  await page.reload();
  await expect(page.getByRole('button', { name: 'Start analysis' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Review the synthetic case' })).toHaveCount(0);

  await page.getByRole('button', { name: 'Start analysis' }).click();
  await expect(page.getByText('Analysis active · workspace workspace-3')).toBeVisible();
  await page.getByRole('button', { name: 'End and delete' }).click();
  await expect(page.getByText('Analysis ended and deletion requested.', { exact: false })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Review the synthetic case' })).toHaveCount(0);
  await expect(second.getByRole('button', { name: 'Start analysis' })).toBeVisible();
  expect(api.events).toEqual(['start', 'renew', 'start', 'start', 'end']);
});
