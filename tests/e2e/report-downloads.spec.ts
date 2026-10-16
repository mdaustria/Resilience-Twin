import { spawn, spawnSync, type ChildProcess } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
import { delimiter, join } from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import { createHash } from 'node:crypto';
import { expect, test, type BrowserContext, type Download } from '@playwright/test';

const root = process.cwd();
const emulatorPort = 8102;
const apiPort = 8006;
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
  const configPath = '.runtime/tmp/reports-e2e-firebase.json';
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
    const responseHeaders = Object.fromEntries(response.headers);
    delete responseHeaders['content-length']; delete responseHeaders['transfer-encoding'];
    await route.fulfill({ status: response.status, headers: responseHeaders,
      body: Buffer.from(await response.arrayBuffer()) });
  });
}
async function fixture(path: string, data: Record<string, string>): Promise<Record<string, unknown>> {
  const response = await fetch(`http://127.0.0.1:${apiPort}/_fixture/${path}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error(`Fixture ${path}: ${await response.text()} ${apiOutput}`);
  return await response.json() as Record<string, unknown>;
}
function pdfText(download: Download): Promise<string> {
  return download.path().then((path) => {
    const bytes = readFileSync(path);
    expect(bytes.subarray(0, 5).toString()).toBe('%PDF-');
    const inspect = spawnSync(join(root, '.venv', 'Scripts', 'python.exe'),
      ['tests/fixtures/reports/inspect_pdf.py', path], { cwd: root, encoding: 'utf8' });
    if (inspect.status !== 0) throw new Error(inspect.stderr);
    return inspect.stdout;
  }).catch((error: unknown) => { throw new Error(`${String(error)}\n${apiOutput}`); });
}

test('owner downloads independent gap, findings and untested revision PDFs; expiry revokes access', async ({ page, context, browser }) => {
  test.setTimeout(180_000);
  await guestApi(context);
  await page.goto('/');
  await page.getByRole('button', { name: 'Start analysis' }).click();
  await expect(page.getByRole('region', { name: 'Temporary analysis' }).getByRole('status'))
    .toContainText('Analysis active');
  const session = await page.evaluate(async () =>
    (await (await fetch('/api/v1/temporary-sessions/current')).json()) as { workspace_id: string });
  const workspaceId = session.workspace_id;
  const seeded = await fixture('report-source', { workspace_id: workspaceId });
  const sourceHash = seeded.source_sha256 as string;
  const sourceBytes = await page.evaluate(async (workspace) => {
    const response = await fetch(`/api/v1/workspaces/${workspace}/artifacts/report-source/download`);
    return Array.from(new Uint8Array(await response.arrayBuffer()));
  }, workspaceId);
  expect(createHash('sha256').update(Buffer.from(sourceBytes)).digest('hex')).toBe(sourceHash);
  const panel = page.getByRole('region', { name: 'Download reports' });
  await panel.getByRole('button', { name: 'Create Source-only gap report' }).click();
  const gapId = await panel.locator('[data-report-job]').first().getAttribute('data-report-job');
  expect(gapId).toBeTruthy();
  await fixture('report', { workspace_id: workspaceId, job_id: gapId! });
  const gapLink = panel.getByRole('button', { name: 'Download Source-only gap report PDF' });
  await expect(gapLink).toBeVisible();
  const gapEvent = page.waitForEvent('download');
  await gapLink.click();
  const gapText = await pdfText(await gapEvent);
  expect(gapText).toContain('gap only');
  expect(gapText).toContain(sourceHash);
  expect(gapText).not.toContain('Measured outcomes');

  await fixture('comparison', { workspace_id: workspaceId, action: 'seed' });
  await page.evaluate(() => window.dispatchEvent(new Event('private-baseline-sealed')));
  const findings = page.getByRole('region', { name: 'Findings and hypothetical changes' });
  await findings.getByLabel('Receiving water store').selectOption('pickup');
  await findings.getByLabel('Water quantity (mL)').fill('500000');
  await findings.getByLabel('Declared supply source').fill('Synthetic additional supply');
  await findings.getByRole('button', { name: 'Seal hypothetical proposal' }).click();
  await expect(findings.getByText('Exact resource diff')).toBeVisible();
  await panel.getByRole('button', { name: 'Create Hypothetical revision report' }).click();
  const revisionId = await panel.locator('[data-report-job]').filter({ hasText: 'queued' }).last().getAttribute('data-report-job');
  expect(revisionId).toBeTruthy();
  await fixture('report', { workspace_id: workspaceId, job_id: revisionId! });
  const revisionLink = panel.getByRole('button', { name: 'Download Hypothetical revision report PDF' });
  await expect(revisionLink).toBeVisible();
  const revisionEvent = page.waitForEvent('download');
  await revisionLink.click();
  const revisionText = await pdfText(await revisionEvent);
  expect(revisionText).toContain('untested');
  expect(revisionText).toContain('Hypothetical revision');
  expect(revisionText).toContain('100000 to 600000 mL');
  expect(revisionText).not.toContain('Measured outcomes');

  const pairs = await fixture('comparison', { workspace_id: workspaceId, action: 'complete' });
  await panel.getByLabel('Baseline member run IDs (for findings)').fill((pairs.baseline_job_ids as string[]).join(', '));
  await panel.getByLabel('Variant member run IDs (for findings)').fill((pairs.variant_job_ids as string[]).join(', '));
  await panel.getByRole('button', { name: 'Create Evaluated findings report' }).click();
  const findingsId = await panel.locator('[data-report-job]').filter({ hasText: 'queued' }).last().getAttribute('data-report-job');
  expect(findingsId).toBeTruthy();
  await fixture('report', { workspace_id: workspaceId, job_id: findingsId! });
  const findingsLink = panel.getByRole('button', { name: 'Download Evaluated findings report PDF' });
  await expect(findingsLink).toBeVisible();
  const findingsEvent = page.waitForEvent('download');
  await findingsLink.click();
  const findingsText = await pdfText(await findingsEvent);
  expect(findingsText).toContain('complete');
  expect(findingsText).toContain('Measured outcomes');
  expect(findingsText).toContain('variant minus baseline water unmet');
  expect(findingsText).toContain('recurrence 2/2 completed members');
  expect(findingsText).toContain(sourceHash);

  const after = await page.evaluate(async (workspace) => {
    const response = await fetch(`/api/v1/workspaces/${workspace}/artifacts/report-source/download`);
    return Array.from(new Uint8Array(await response.arrayBuffer()));
  }, workspaceId);
  expect(Buffer.from(after)).toEqual(Buffer.from(sourceBytes));
  const other = await browser.newContext();
  await guestApi(other);
  const otherPage = await other.newPage();
  await otherPage.goto('/');
  await otherPage.getByRole('button', { name: 'Start analysis' }).click();
  await expect(otherPage.getByRole('region', { name: 'Temporary analysis' }).getByRole('status'))
    .toContainText('Analysis active');
  const otherStatus = await otherPage.evaluate(async ([workspace, job]) =>
    (await fetch(`/api/v1/workspaces/${workspace}/reports/jobs/${job}/download`)).status,
    [workspaceId, gapId!] as const);
  expect(otherStatus).toBe(404);
  await other.unrouteAll({ behavior: 'ignoreErrors' });
  await other.close();
  await fixture('report-expire', { workspace_id: workspaceId });
  const expiredStatus = await page.evaluate(async ([workspace, job]) =>
    (await fetch(`/api/v1/workspaces/${workspace}/reports/jobs/${job}/download`)).status,
    [workspaceId, gapId!] as const);
  expect(expiredStatus).toBe(404);
  await context.unrouteAll({ behavior: 'ignoreErrors' });
});
