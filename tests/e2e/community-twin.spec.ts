import { spawn, spawnSync, type ChildProcess } from 'node:child_process';
import { statSync, writeFileSync } from 'node:fs';
import { delimiter, join } from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import { expect, test, type BrowserContext } from '@playwright/test';

const root = process.cwd();
const emulatorPort = 8097;
const apiPort = 8001;
const sourceByCase = {
  qc: {
    digest: '95b5c5e1177946c45f71412599df914de365feb6f6694c684d9fabaefde4990b',
    size: 2_943_608, pages: 112, location: 'Quezon City, Metro Manila',
    folder: 'pilot-qc-temporary', title: 'Quezon City DRRMP Volume 1', citationPage: 82,
  },
  guiguinto: {
    digest: 'b355207cefdee01f3a67876b1f11b442b90c1acb7b7c6b49ad48433c29aafb95',
    size: 9_418_109, pages: 191, location: 'Guiguinto, Bulacan',
    folder: 'pilot-guiguinto-saved', title: 'Guiguinto MDRRM Plan', citationPage: 121,
  },
} as const;

let emulator: ChildProcess | undefined;
let api: ChildProcess | undefined;
let emulatorOutput = '';
let apiOutput = '';

async function waitFor(url: string, process: ChildProcess, output: () => string) {
  for (let attempt = 0; attempt < 90; attempt += 1) {
    if (process.exitCode !== null) throw new Error(`Guest test service exited: ${output()}`);
    try { await fetch(url); return; }
    catch { await delay(1000); }
  }
  throw new Error(`Guest test service unavailable at ${url}: ${output()}`);
}

function stopTree(child: ChildProcess | undefined) {
  if (!child?.pid) return;
  if (process.platform === 'win32') {
    spawnSync('taskkill', ['/PID', String(child.pid), '/T', '/F'], { stdio: 'ignore' });
  } else {
    child.kill();
  }
}

test.beforeAll(async () => {
  test.setTimeout(120_000);
  const configArgument = '.runtime/tmp/guest-e2e-firebase.json';
  const config = join(root, configArgument);
  writeFileSync(config, JSON.stringify({
    firestore: { rules: join(root, 'firestore.rules'), indexes: join(root, 'firestore.indexes.json') },
    emulators: { firestore: { host: '127.0.0.1', port: emulatorPort }, ui: { enabled: false }, singleProjectMode: true },
  }));
  const environment = {
    ...process.env,
    JAVA_HOME: join(root, '.runtime', 'jdk-21.0.12.1+1'),
    PATH: `${join(root, '.runtime', 'jdk-21.0.12.1+1', 'bin')};${process.env.PATH ?? ''}`,
    XDG_CONFIG_HOME: join(root, '.runtime', 'firebase-config'),
    NO_UPDATE_NOTIFIER: '1',
    FIRESTORE_EMULATOR_HOST: `127.0.0.1:${emulatorPort}`,
    PYTHONPATH: [root, process.env.PYTHONPATH].filter(Boolean).join(delimiter),
  };
  emulator = spawn('pnpm.cmd', ['exec', 'firebase', 'emulators:start', '--only', 'firestore',
    '--project', 'demo-resilience-twin', '--config', configArgument],
    { cwd: root, shell: true, env: environment });
  emulator.stdout?.on('data', (chunk: Buffer) => { emulatorOutput += chunk.toString(); });
  emulator.stderr?.on('data', (chunk: Buffer) => { emulatorOutput += chunk.toString(); });
  await waitFor(`http://127.0.0.1:${emulatorPort}/`, emulator, () => emulatorOutput);
  api = spawn(join(root, '.runtime', 'uv', 'uv.exe'), ['run', 'uvicorn', 'guest_server:app', '--app-dir', 'tests/e2e',
    '--host', '127.0.0.1', '--port', String(apiPort)],
  { cwd: root, env: environment });
  api.stdout?.on('data', (chunk: Buffer) => { apiOutput += chunk.toString(); });
  api.stderr?.on('data', (chunk: Buffer) => { apiOutput += chunk.toString(); });
  await waitFor(`http://127.0.0.1:${apiPort}/api/v1/bootstrap`, api, () => apiOutput);
});

test.afterAll(() => {
  stopTree(api);
  stopTree(emulator);
});

async function useGuestApi(context: BrowserContext) {
  await context.route(/\/api\/v1\/(?:temporary-sessions|workspaces)(?:\/.*)?$/, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const headers = { ...request.headers(), origin: 'https://resilience.example' };
    delete headers.host;
    delete headers['content-length'];
    const postData = !['GET', 'HEAD'].includes(request.method()) ? request.postDataBuffer() : null;
    const response = await fetch(`http://127.0.0.1:${apiPort}${url.pathname}${url.search}`, {
      method: request.method(), headers,
      body: postData ?? undefined,
    });
    const body = Buffer.from(await response.arrayBuffer());
    await route.fulfill({ status: response.status, headers: Object.fromEntries(response.headers), body });
  });
}

for (const [label, source] of Object.entries(sourceByCase)) {
  test(`${label} full PDF uploads and keeps its cited source-only review after reconnect`, async ({ page, context }) => {
    test.setTimeout(180_000);
    await useGuestApi(context);
    await page.goto('/');
    await page.getByRole('button', { name: 'Start analysis' }).click();
    const panel = page.getByRole('region', { name: 'PDF and evidence review' });
    await expect(panel).toBeVisible();
    const file = join(root, '.runtime', 'task32-intake', source.folder, 'documents', `${source.digest}.pdf`);
    expect(statSync(file).size).toBe(source.size);
    await panel.getByLabel('Public plan PDF').setInputFiles(file);
    await panel.getByLabel('Source title').fill(source.title);
    await panel.getByLabel('Publication reference or public URL').fill('Supplied public PDF');
    await panel.getByLabel('Textual study location').fill(source.location);
    await panel.getByLabel('Scenario date').fill('2026-10-16');
    await panel.getByRole('button', { name: 'Upload and begin review' }).click();
    await expect(panel.getByText(`Complete PDF intake: ${source.pages} of ${source.pages} physical pages mapped;`, { exact: false }))
      .toBeVisible({ timeout: 140_000 });
    await expect(panel.getByText(`Source hash: ${source.digest}.`, { exact: false })).toBeVisible();
    await expect(panel.getByText('Simulation is blocked;', { exact: false })).toBeVisible();
    await expect(panel.getByRole('heading', { name: 'Source-only documentation gaps' })).toBeVisible();
    await panel.getByText('Page coverage list').click();
    await expect(panel.getByText(`Page ${source.pages}: processed (text)`)).toBeVisible();
    await page.reload();
    await expect(panel.getByText('Review revision 1.', { exact: false })).toBeVisible();
    const second = await context.newPage();
    await second.goto('/');
    await expect(second.getByRole('region', { name: 'PDF and evidence review' })
      .getByText('Review revision 1.', { exact: false })).toBeVisible();
    await panel.getByRole('button', { name: `Inspect cited page ${source.citationPage}` }).first().click();
    await expect(panel.getByTitle(`Source PDF page ${source.citationPage}`)).toBeVisible({ timeout: 60_000 });
    await panel.getByRole('button', { name: 'Close citation' }).click();
    await panel.getByLabel('Candidate').selectOption({ index: 1 });
    await panel.getByLabel('Review decision and limitations').fill('Retained as documentary context; not current usable capacity.');
    await panel.getByRole('button', { name: 'Mark claim contested' }).click();
    await expect(panel.getByText('Review revision 2.', { exact: false })).toBeVisible();
    const stalePanel = second.getByRole('region', { name: 'PDF and evidence review' });
    await stalePanel.getByLabel('Candidate').selectOption({ index: 1 });
    await stalePanel.getByLabel('Review decision and limitations').fill('Stale competing decision');
    await stalePanel.getByRole('button', { name: 'Accept reviewed claim' }).click();
    await expect(stalePanel.getByRole('alert')).toContainText('changed in another tab');
    await expect(stalePanel.getByText('Review revision 2.', { exact: false })).toBeVisible();
    await panel.getByLabel('Corrected value').fill(label === 'qc' ? '1' : '3987');
    await panel.getByLabel('Corrected statement type').selectOption(
      label === 'qc' ? 'proposed_target' : 'reported_existing');
    await panel.getByLabel('Correction explanation').fill(label === 'qc'
      ? 'This is a future project target, not an operating shelter capacity.'
      : 'The listed family subtotals equal 3,987; the printed 4,087 total remains contested.');
    await panel.getByRole('button', { name: 'Record correction' }).click();
    await expect(panel.getByText('Review revision 3.', { exact: false })).toBeVisible();
    await expect(panel.getByText('(correction,', { exact: false })).toBeVisible();
    await expect(panel.getByRole('heading', { name: 'Study area and road access' })).toBeVisible();
    await panel.getByRole('button', { name: 'Confirm selected study area and connectors' }).click();
    await expect(panel.getByText('Review revision 4.', { exact: false })).toBeVisible();
    await expect(panel.getByText('Reviewed location scope:', { exact: false })).toBeVisible();
    const supplements = [
      ['evacuee_people', '100', 'Illustrative bounded pilot cohort', 'No current selected-cell population'],
      ['shelter_capacity_people', '150', 'Illustrative one-facility capacity', 'Not verified operational capacity'],
      ['vehicle_seats', '20', 'Illustrative pilot vehicle seats', 'No current fleet inventory'],
      ['opening_water_ml', '500000', 'Illustrative starting potable stock', 'No dated stock measurement'],
    ] as const;
    for (const [field, value, reason, limitations] of supplements) {
      await panel.getByLabel('Missing input').selectOption(field);
      await panel.getByLabel('Nonnegative integer value').fill(value);
      await panel.getByLabel('Reason').fill(reason);
      await panel.getByLabel('Limitations', { exact: true }).fill(limitations);
      await panel.getByRole('button', { name: 'Declare explicit assumption' }).click();
      await expect(panel.getByText(`${field}: ${value}`, { exact: false })).toBeVisible();
    }
    await expect(panel.getByText('Review revision 8.', { exact: false })).toBeVisible();
    await expect(panel.getByText('evacuee_people: 100 PERSON.', { exact: false })).toBeVisible();
    await expect(panel.getByRole('heading', { name: 'Source-only documentation gaps' })).toBeVisible();
    await page.reload();
    await expect(panel.getByText('Review revision 8.', { exact: false })).toBeVisible();
    await panel.getByRole('button', { name: 'Seal evidence review' }).click();
    await expect(panel.getByText('Sealed snapshot.', { exact: false })).toBeVisible();
    await panel.getByRole('button', { name: 'Acknowledge assumptions after location review' }).click();
    await expect(panel.getByText('Simulation is ready;', { exact: false })).toBeVisible();
    await panel.getByRole('button', { name: 'Seal immutable baseline' }).click();
    await expect(panel.getByText('Immutable baseline sealed.', { exact: false })).toBeVisible();
    await second.reload();
    await expect(second.getByRole('region', { name: 'PDF and evidence review' })
      .getByText('Immutable baseline sealed.', { exact: false })).toBeVisible();
  });
}

test('upload limit and remaining lifetime show actionable errors', async ({ page, context }) => {
  await useGuestApi(context);
  await page.goto('/');
  await page.getByRole('button', { name: 'Start analysis' }).click();
  const panel = page.getByRole('region', { name: 'PDF and evidence review' });
  await panel.getByLabel('Public plan PDF').setInputFiles({
    name: 'too-large.pdf', mimeType: 'application/pdf', buffer: Buffer.alloc(10_000_001),
  });
  await panel.getByLabel('Source title').fill('Limit probe');
  await panel.getByLabel('Publication reference or public URL').fill('Synthetic boundary fixture');
  await panel.getByLabel('Textual study location').fill('Quezon City');
  await panel.getByRole('button', { name: 'Upload and begin review' }).click();
  await expect(panel.getByRole('alert')).toContainText('file too large');
  const expiresAt = await page.evaluate(async () => {
    const response = await fetch('/api/v1/temporary-sessions/current');
    return ((await response.json()) as { expires_at: string }).expires_at;
  });
  await page.clock.install({ time: new Date(Date.parse(expiresAt) - 30_000) });
  await panel.getByRole('button', { name: 'Upload and begin review' }).click();
  await expect(panel.getByRole('alert')).toContainText('Renew the session before uploading');
});
