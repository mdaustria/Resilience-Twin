import { spawn, spawnSync, type ChildProcess } from 'node:child_process';
import { statSync, writeFileSync } from 'node:fs';
import { delimiter, join } from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import { expect, test, type BrowserContext } from '@playwright/test';

const root = process.cwd();
const emulatorPort = 8099;
const apiPort = 8003;
const digest = '95b5c5e1177946c45f71412599df914de365feb6f6694c684d9fabaefde4990b';
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
  const configPath = '.runtime/tmp/scenario-e2e-firebase.json';
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

test('reviewed baseline seals a structured scenario with server validation', async ({ page, context }) => {
  test.setTimeout(180_000);
  await guestApi(context);
  await page.goto('/');
  await page.getByRole('button', { name: 'Start analysis' }).click();
  const twin = page.getByRole('region', { name: 'PDF and evidence review' });
  const file = join(root, '.runtime/task32-intake/pilot-qc-temporary/documents', `${digest}.pdf`);
  expect(statSync(file).size).toBe(2_943_608);
  await twin.getByLabel('Public plan PDF').setInputFiles(file);
  await twin.getByLabel('Source title').fill('Quezon City DRRMP Volume 1');
  await twin.getByLabel('Publication reference or public URL').fill('Supplied public PDF');
  await twin.getByLabel('Textual study location').fill('Quezon City, Metro Manila');
  await twin.getByRole('button', { name: 'Upload and begin review' }).click();
  await expect(twin.getByText('Complete PDF intake: 112 of 112 physical pages mapped;', { exact: false }))
    .toBeVisible({ timeout: 100_000 });
  await twin.getByRole('button', { name: 'Confirm selected study area and connectors' }).click();
  await expect(twin.getByText('Reviewed location scope:', { exact: false })).toBeVisible();
  for (const [field, value] of [
    ['evacuee_people', '100'], ['shelter_capacity_people', '150'],
    ['vehicle_seats', '20'], ['opening_water_ml', '500000'],
  ]) {
    await twin.getByLabel('Missing input').selectOption(field);
    await twin.getByLabel('Nonnegative integer value').fill(value);
    await twin.getByLabel('Reason').fill(`Illustrative ${field} for the reviewed pilot`);
    await twin.getByLabel('Limitations', { exact: true }).fill('No current field verification');
    await twin.getByRole('button', { name: 'Declare explicit assumption' }).click();
    await expect(twin.getByText(`${field}: ${value}`, { exact: false })).toBeVisible();
  }
  await twin.getByRole('button', { name: 'Seal evidence review' }).click();
  await twin.getByRole('button', { name: 'Acknowledge assumptions after location review' }).click();
  await twin.getByRole('button', { name: 'Seal immutable baseline' }).click();
  await expect(twin.getByText('Immutable baseline sealed.', { exact: false })).toBeVisible();

  const scenario = page.getByRole('region', { name: 'Structured Scenario editor' });
  await expect(scenario.getByText('Owner-scoped baseline and scenario targets loaded.')).toBeVisible();
  await scenario.getByLabel('Reviewed target ID').fill('missing-edge');
  await scenario.getByRole('button', { name: 'Add structured event' }).click();
  await scenario.getByRole('button', { name: 'Review and seal scenario' }).click();
  await expect(scenario.getByRole('alert')).toContainText('invalid_target');
  await scenario.getByRole('button', { name: 'Remove event' }).click();
  const edge = await scenario.locator('#scenario-targets option').first().getAttribute('value');
  expect(edge).toBeTruthy();
  await scenario.getByLabel('Reviewed target ID').fill(edge!);
  await scenario.getByRole('button', { name: 'Add structured event' }).click();
  await scenario.getByLabel('Operational effect').selectOption('vehicle_outage');
  await scenario.getByLabel('Reviewed target ID').fill('missing-vehicle');
  await scenario.getByRole('button', { name: 'Add structured event' }).click();
  await scenario.getByRole('button', { name: 'Review and seal scenario' }).click();
  await expect(scenario.getByRole('alert')).toContainText('invalid_target');
  await scenario.getByRole('button', { name: 'Remove event' }).last().click();
  await scenario.getByLabel('Reviewed target ID').fill('pilot-vehicle');
  await scenario.getByLabel('Hazard or assumption reference').fill('Explicit power outage makes the pilot vehicle unavailable');
  await scenario.getByRole('button', { name: 'Add structured event' }).click();
  await scenario.getByLabel('Power consequence').selectOption({ index: 2 });
  await scenario.getByLabel('Communication consequence').selectOption({ index: 1 });
  await scenario.getByLabel('Deadline (minutes after start)').fill('300');
  await scenario.getByRole('button', { name: 'Review and seal scenario' }).click();
  await expect(scenario.getByRole('alert')).toContainText('invalid_interval');
  await scenario.getByLabel('Deadline (minutes after start)').fill('120');
  await scenario.getByRole('button', { name: 'Review and seal scenario' }).click();
  await expect(scenario.getByText('Sealed deterministic input summary')).toBeVisible();
  await expect(scenario.getByText('100 people; deadline: 7200 seconds;', { exact: false })).toBeVisible();
  await expect(scenario.getByText('Asia/Manila', { exact: false })).toBeVisible();
  await page.reload();
  await expect(scenario.getByText('Sealed deterministic input summary')).toBeVisible();
  await expect(scenario.getByText('Power effect event:', { exact: false })).toBeVisible();
  const retry = await page.evaluate(async () => {
    const session = await (await fetch('/api/v1/temporary-sessions/current')).json() as {
      workspace_id: string; csrf_token: string;
    };
    const path = `/api/v1/workspaces/${session.workspace_id}/scenarios/main`;
    const current = await (await fetch(path)).json() as {
      content: { baseline_hash: string; scenario: { horizon_seconds: number; events: unknown[] };
        editor: Record<string, unknown> };
    };
    const response = await fetch(path, { method: 'PUT', headers: {
      'Content-Type': 'application/json', 'X-CSRF-Token': session.csrf_token,
      'If-Match': '1', 'Idempotency-Key': crypto.randomUUID(),
    }, body: JSON.stringify({ ...current.content.editor, scenario_title: 'Changed narrative only',
      baseline_id: 'main', baseline_hash: current.content.baseline_hash,
      horizon_seconds: current.content.scenario.horizon_seconds,
      events: current.content.scenario.events }) });
    return { status: response.status, body: await response.json() as { code?: string } };
  });
  expect(retry).toEqual({ status: 409, body: expect.objectContaining({ code: 'version_conflict' }) });
  await expect(scenario.getByText('Reviewed pilot scenario.', { exact: false })).toBeVisible();
  await scenario.getByRole('textbox', { name: 'Scenario ID', exact: true }).fill('alternative');
  await expect(scenario.getByRole('button', { name: 'Review and seal scenario' })).toBeVisible();
  await scenario.getByLabel('Scenario title (display only)').fill('Alternative narrative label');
  await scenario.getByRole('button', { name: 'Review and seal scenario' }).click();
  await expect(scenario.getByText('Alternative narrative label.', { exact: false })).toBeVisible();
  await scenario.getByLabel('Sealed scenario IDs (comma separated)').fill('main, alternative');
  await scenario.getByRole('button', { name: 'Seal selected scenario suite' }).click();
  await expect(scenario.getByText('Immutable suite retained in this temporary session.', { exact: false })).toBeVisible();
  await page.reload();
  await expect(scenario.getByText('Members: main, alternative;', { exact: false })).toBeVisible();
  const numeric = await page.evaluate(async () => {
    const session = await (await fetch('/api/v1/temporary-sessions/current')).json() as { workspace_id: string };
    const prefix = `/api/v1/workspaces/${session.workspace_id}/scenarios`;
    const [main, alternative] = await Promise.all(['main', 'alternative'].map(async (id) =>
      (await (await fetch(`${prefix}/${id}`)).json()) as { content: { scenario: {
        horizon_seconds: number; events: unknown[] }; editor: { demand_people: number; deadline_seconds: number } } }));
    return { main: main.content, alternative: alternative.content };
  });
  expect(numeric.alternative.scenario.horizon_seconds).toBe(numeric.main.scenario.horizon_seconds);
  expect(numeric.alternative.scenario.events).toEqual([]);
  expect(numeric.alternative.editor.demand_people).toBe(numeric.main.editor.demand_people);
  expect(numeric.alternative.editor.deadline_seconds).toBe(numeric.main.editor.deadline_seconds);
  await context.unrouteAll({ behavior: 'ignoreErrors' });
});
