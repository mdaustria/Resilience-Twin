import { spawn, spawnSync, type ChildProcess } from 'node:child_process';
import { writeFileSync } from 'node:fs';
import { delimiter, join } from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import { expect, test, type BrowserContext } from '@playwright/test';

const root = process.cwd();
const emulatorPort = 8101;
const apiPort = 8005;
let emulator: ChildProcess | undefined;
let api: ChildProcess | undefined;
let emulatorOutput = '';
let apiOutput = '';

async function ready(url: string, child: ChildProcess, output: () => string) {
  for (let attempt = 0; attempt < 90; attempt += 1) {
    if (child.exitCode !== null) throw new Error(`Guest service exited: ${output()}`);
    try { await fetch(url); return; } catch { await delay(1000); }
  }
  throw new Error(`Guest service unavailable: ${output()}`);
}
function stop(child: ChildProcess | undefined) {
  if (!child?.pid) return;
  if (process.platform === 'win32') spawnSync('taskkill', ['/PID', String(child.pid), '/T', '/F'], { stdio: 'ignore' });
  else child.kill();
}

test.beforeAll(async () => {
  test.setTimeout(120_000);
  const configPath = '.runtime/tmp/findings-e2e-firebase.json';
  writeFileSync(join(root, configPath), JSON.stringify({
    firestore: { rules: join(root, 'firestore.rules'), indexes: join(root, 'firestore.indexes.json') },
    emulators: { firestore: { host: '127.0.0.1', port: emulatorPort }, ui: { enabled: false }, singleProjectMode: true },
  }));
  const environment = { ...process.env,
    JAVA_HOME: join(root, '.runtime', 'jdk-21.0.12.1+1'),
    PATH: `${join(root, '.runtime', 'jdk-21.0.12.1+1', 'bin')};${process.env.PATH ?? ''}`,
    XDG_CONFIG_HOME: join(root, '.runtime', 'firebase-config'), NO_UPDATE_NOTIFIER: '1',
    FIRESTORE_EMULATOR_HOST: `127.0.0.1:${emulatorPort}`,
    PYTHONPATH: [root, process.env.PYTHONPATH].filter(Boolean).join(delimiter),
  };
  emulator = spawn('pnpm.cmd', ['exec', 'firebase', 'emulators:start', '--only', 'firestore',
    '--project', 'demo-resilience-twin', '--config', configPath], { cwd: root, shell: true, env: environment });
  emulator.stdout?.on('data', (chunk: Buffer) => { emulatorOutput += chunk.toString(); });
  emulator.stderr?.on('data', (chunk: Buffer) => { emulatorOutput += chunk.toString(); });
  await ready(`http://127.0.0.1:${emulatorPort}/`, emulator, () => emulatorOutput);
  api = spawn(join(root, '.runtime', 'uv', 'uv.exe'), ['run', 'uvicorn', 'guest_server:app',
    '--app-dir', 'tests/e2e', '--host', '127.0.0.1', '--port', String(apiPort)],
  { cwd: root, env: environment });
  api.stdout?.on('data', (chunk: Buffer) => { apiOutput += chunk.toString(); });
  api.stderr?.on('data', (chunk: Buffer) => { apiOutput += chunk.toString(); });
  await ready(`http://127.0.0.1:${apiPort}/api/v1/bootstrap`, api, () => apiOutput);
});
test.afterAll(() => { stop(api); stop(emulator); });

async function guestApi(context: BrowserContext) {
  await context.route(/\/api\/v1\/(?:temporary-sessions|workspaces)(?:\/.*)?$/, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const headers = { ...request.headers(), origin: 'https://resilience.example' };
    delete headers.host; delete headers['content-length'];
    const data = !['GET', 'HEAD'].includes(request.method()) ? request.postDataBuffer() : null;
    const response = await fetch(`http://127.0.0.1:${apiPort}${url.pathname}${url.search}`, {
      method: request.method(), headers, body: data ?? undefined,
    });
    await route.fulfill({ status: response.status, headers: Object.fromEntries(response.headers),
      body: Buffer.from(await response.arrayBuffer()) });
  });
}
async function fixture(workspaceId: string, action: string): Promise<Record<string, unknown>> {
  const response = await fetch(`http://127.0.0.1:${apiPort}/_fixture/comparison`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ workspace_id: workspaceId, action }),
  });
  if (!response.ok) throw new Error(`Comparison fixture ${action} failed: ${await response.text()}`);
  return await response.json() as Record<string, unknown>;
}

test('hypothetical proposal shows exact diff and only verified paired results', async ({ page, context }) => {
  test.setTimeout(180_000);
  await guestApi(context);
  await page.goto('/');
  await page.getByRole('button', { name: 'Start analysis' }).click();
  await expect(page.getByRole('region', { name: 'Temporary analysis' }).getByRole('status'))
    .toContainText('Analysis active');
  const session = await page.evaluate(async () =>
    (await (await fetch('/api/v1/temporary-sessions/current')).json()) as { workspace_id: string });
  await fixture(session.workspace_id, 'seed');
  await page.evaluate(() => window.dispatchEvent(new Event('private-baseline-sealed')));
  const findings = page.getByRole('region', { name: 'Findings and hypothetical changes' });
  await expect(findings.getByRole('button', { name: 'Seal hypothetical proposal' })).toBeVisible();
  await findings.getByLabel('Receiving water store').selectOption('pickup');
  await findings.getByLabel('Water quantity (mL)').fill('500000');
  await findings.getByLabel('Declared supply source').fill('Synthetic additional supply');
  await findings.getByRole('button', { name: 'Seal hypothetical proposal' }).click();
  await expect(findings.getByText('Exact resource diff')).toBeVisible();
  await expect(findings.getByRole('row', { name: 'pickup 100000 600000 500000' })).toBeVisible();
  await expect(findings.getByText('Untested proposal. No measured improvement', { exact: false })).toBeVisible();

  const pair = await fixture(session.workspace_id, 'complete');
  const baselineIds = pair.baseline_job_ids as string[];
  const variantIds = pair.variant_job_ids as string[];
  await findings.getByLabel('Baseline member run IDs (comma separated)').fill(baselineIds.join(', '));
  await findings.getByLabel('Variant member run IDs (comma separated)').fill(variantIds.join(', '));
  await findings.getByRole('button', { name: 'Evaluate paired evidence' }).click();
  await expect(findings.getByText('Paired comparison: complete')).toBeVisible();
  await expect(findings.getByText('Measured improvement within this modeled suite.', { exact: false })).toBeVisible();
  await expect(findings.getByRole('row', { name: /normal 0 0 -380099 0 none/ })).toBeVisible();
  await expect(findings.getByText('recurrence 2/2 completed members', { exact: false })).toBeVisible();
  await expect(findings.getByText('Evidence: 0:terminal', { exact: false })).toBeVisible();

  const pendingResponse = await fetch(`http://127.0.0.1:${apiPort}/_fixture/run`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ workspace_id: session.workspace_id, action: 'create' }),
  });
  expect(pendingResponse.ok).toBeTruthy();
  const pendingId = ((await pendingResponse.json()) as { job_id: string }).job_id;
  await findings.getByLabel('Variant member run IDs (comma separated)').fill(`${variantIds[0]}, ${pendingId}`);
  await findings.getByRole('button', { name: 'Evaluate paired evidence' }).click();
  await expect(findings.getByText('Paired comparison: partial')).toBeVisible();
  await expect(findings.getByText('No measured improvement claim.', { exact: false })).toBeVisible();

  await findings.getByLabel('Variant member run IDs (comma separated)').fill('');
  await findings.getByRole('button', { name: 'Evaluate paired evidence' }).click();
  await expect(findings.getByText('Paired comparison: untested')).toBeVisible();
  await expect(findings.getByText('No measured improvement claim.', { exact: false })).toBeVisible();
  await page.reload();
  await expect(findings.getByText('Exact resource diff')).toBeVisible();
  await context.unrouteAll({ behavior: 'ignoreErrors' });
});
