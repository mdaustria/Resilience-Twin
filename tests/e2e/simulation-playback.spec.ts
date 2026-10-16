import { spawn, spawnSync, type ChildProcess } from 'node:child_process';
import { writeFileSync } from 'node:fs';
import { delimiter, join } from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import { expect, test, type BrowserContext } from '@playwright/test';

const root = process.cwd();
const emulatorPort = 8100;
const apiPort = 8004;
let emulator: ChildProcess | undefined;
let api: ChildProcess | undefined;
let emulatorOutput = '';
let apiOutput = '';

async function ready(url: string, child: ChildProcess, output: () => string) {
  for (let attempt = 0; attempt < 90; attempt += 1) {
    if (child.exitCode !== null) throw new Error(`Guest service exited: ${output()}`);
    try { await fetch(url); return; }
    catch { await delay(1000); }
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
  const configPath = '.runtime/tmp/playback-e2e-firebase.json';
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
    delete headers.host;
    delete headers['content-length'];
    const data = !['GET', 'HEAD'].includes(request.method()) ? request.postDataBuffer() : null;
    const response = await fetch(`http://127.0.0.1:${apiPort}${url.pathname}${url.search}`, {
      method: request.method(), headers, body: data ?? undefined,
    });
    await route.fulfill({ status: response.status, headers: Object.fromEntries(response.headers),
      body: Buffer.from(await response.arrayBuffer()) });
  });
}

async function fixture(workspaceId: string, action: string, jobId?: string): Promise<string> {
  const response = await fetch(`http://127.0.0.1:${apiPort}/_fixture/run`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ workspace_id: workspaceId, action, job_id: jobId }),
  });
  if (!response.ok) throw new Error(`Fixture ${action} failed: ${await response.text()}`);
  return ((await response.json()) as { job_id: string }).job_id;
}

test('committed playback reconnects without duplicates and separates pause from cancellation', async ({ page, context }) => {
  test.setTimeout(120_000);
  await guestApi(context);
  await page.goto('/');
  await page.getByRole('button', { name: 'Start analysis' }).click();
  await expect(page.getByRole('region', { name: 'Temporary analysis' }).getByRole('status'))
    .toContainText('Analysis active');
  const session = await page.evaluate(async () =>
    (await (await fetch('/api/v1/temporary-sessions/current')).json()) as {
      workspace_id: string; expires_at: string;
    });
  const runId = await fixture(session.workspace_id, 'create');
  const playback = page.getByRole('region', { name: 'Run playback' });
  await playback.getByLabel('Run ID').fill(runId);
  await playback.getByRole('button', { name: 'Connect to run' }).click();
  await expect(playback.getByRole('status')).toContainText('2 committed events', { timeout: 15_000 });
  await playback.getByRole('button', { name: 'Pause playback' }).click();
  const pausedPosition = await playback.getByLabel(/Playback position/).inputValue();
  await fixture(session.workspace_id, 'finish', runId);
  await expect(playback.getByRole('status')).toContainText('Job complete', { timeout: 15_000 });
  await expect(playback.getByRole('status')).toContainText('4 committed events');
  expect(await playback.getByLabel(/Playback position/).inputValue()).toBe(pausedPosition);
  await playback.getByRole('button', { name: 'Resume playback' }).click();
  await expect(playback.getByRole('button', { name: 'Inspect event 4' })).toBeVisible();
  await playback.getByRole('button', { name: 'Inspect event 4' }).click();
  await expect(playback.getByText('Event detail: sequence 4;', { exact: false })).toBeVisible();
  await page.reload();
  await expect(playback.getByRole('status')).toContainText('4 committed events', { timeout: 15_000 });
  await playback.getByRole('button', { name: 'Show latest committed event' }).click();
  await expect(playback.getByRole('button', { name: 'Inspect event 4' })).toHaveCount(1);
  await expect(playback.getByRole('img', { name: 'Schematic event map by simulation time and target' })).toBeVisible();
  const afterPolling = await page.evaluate(async () =>
    (await (await fetch('/api/v1/temporary-sessions/current')).json()) as { expires_at: string });
  expect(afterPolling.expires_at).toBe(session.expires_at);

  const failedId = await fixture(session.workspace_id, 'create');
  await fixture(session.workspace_id, 'fail', failedId);
  await playback.getByLabel('Run ID').fill(failedId);
  await playback.getByRole('button', { name: 'Connect to run' }).click();
  await expect(playback.getByText('Computation failed.', { exact: false })).toBeVisible();
  await expect(playback.getByText('Partial run:', { exact: false })).toBeVisible();

  const cancelId = await fixture(session.workspace_id, 'create');
  await playback.getByLabel('Run ID').fill(cancelId);
  await playback.getByRole('button', { name: 'Connect to run' }).click();
  await expect(playback.getByRole('status')).toContainText('Job running');
  await playback.getByRole('button', { name: 'Cancel computation' }).click();
  await expect(playback.getByText('Computation was cancelled.', { exact: false })).toBeVisible({ timeout: 15_000 });
  await context.unrouteAll({ behavior: 'ignoreErrors' });
});
