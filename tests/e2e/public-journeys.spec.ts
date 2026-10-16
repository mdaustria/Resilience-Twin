import { spawn, spawnSync, type ChildProcess } from 'node:child_process';
import { createHash } from 'node:crypto';
import { readFileSync, statSync, writeFileSync } from 'node:fs';
import { delimiter, join } from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import { expect, test, type BrowserContext } from '@playwright/test';

const root = process.cwd();
const emulatorPort = 8103;
const apiPort = 8007;
const sources = {
  qc: { digest: '95b5c5e1177946c45f71412599df914de365feb6f6694c684d9fabaefde4990b',
    size: 2_943_608, pages: 112, folder: 'pilot-qc-temporary',
    title: 'Quezon City DRRMP Volume 1', location: 'Quezon City, Metro Manila' },
  guiguinto: { digest: 'b355207cefdee01f3a67876b1f11b442b90c1acb7b7c6b49ad48433c29aafb95',
    size: 9_418_109, pages: 191, folder: 'pilot-guiguinto-saved',
    title: 'Guiguinto MDRRM Plan', location: 'Guiguinto, Bulacan' },
} as const;
let emulator: ChildProcess | undefined;
let api: ChildProcess | undefined;
let emulatorOutput = '';
let apiOutput = '';
const partialRecords: { case: string; source_sha256: string; source_byte_size: number;
  physical_pages: number; gap_report_sha256: string; original_bytes_preserved: boolean }[] = [];

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
  const configPath = '.runtime/tmp/public-journeys-firebase.json';
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
test.afterAll(() => {
  stop(api); stop(emulator);
  if (partialRecords.length === 2) writeFileSync(
    join(root, 'release/validation/milestone-b/source-only-browser.json'),
    `${JSON.stringify({ schema_version: 'milestone-b-source-only.partial.v1',
      cases: partialRecords.sort((left, right) => left.case.localeCompare(right.case)),
      full_journey_verified: false }, null, 2)}\n`);
});

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

for (const [caseId, source] of Object.entries(sources)) {
  test(`${caseId} exact public PDF completes source-only guest export stage`, async ({ page, context }) => {
    test.setTimeout(240_000);
    await guestApi(context);
    await page.goto('/');
    await expect(page.getByRole('button', { name: /sign in|log in/i })).toHaveCount(0);
    await page.getByRole('button', { name: 'Start analysis' }).click();
    await expect(page.getByRole('region', { name: 'Temporary analysis' }).getByRole('status'))
      .toContainText('Analysis active');
    const workspaceId = await page.evaluate(async () =>
      ((await (await fetch('/api/v1/temporary-sessions/current')).json()) as { workspace_id: string }).workspace_id);
    const path = join(root, '.runtime', 'task32-intake', source.folder, 'documents', `${source.digest}.pdf`);
    expect(statSync(path).size).toBe(source.size);
    expect(createHash('sha256').update(readFileSync(path)).digest('hex')).toBe(source.digest);
    const review = page.getByRole('region', { name: 'PDF and evidence review' });
    await review.getByLabel('Public plan PDF').setInputFiles(path);
    await review.getByLabel('Source title').fill(source.title);
    await review.getByLabel('Publication reference or public URL').fill('Supplied public PDF');
    await review.getByLabel('Textual study location').fill(source.location);
    await review.getByLabel('Scenario date').fill('2026-10-16');
    await review.getByRole('button', { name: 'Upload and begin review' }).click();
    await expect(review.getByText(`Complete PDF intake: ${source.pages} of ${source.pages}`, { exact: false }))
      .toBeVisible({ timeout: 140_000 });
    await expect(review.getByText(`Source hash: ${source.digest}.`, { exact: false })).toBeVisible();
    await expect(review.getByRole('heading', { name: 'Source-only documentation gaps' })).toBeVisible();
    const reports = page.getByRole('region', { name: 'Download reports' });
    await reports.getByRole('button', { name: 'Create Source-only gap report' }).click();
    const jobId = await reports.locator('[data-report-job]').getAttribute('data-report-job');
    expect(jobId).toBeTruthy();
    const worker = await fetch(`http://127.0.0.1:${apiPort}/_fixture/report`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ workspace_id: workspaceId, job_id: jobId }),
    });
    if (!worker.ok) throw new Error(`Report worker failed: ${await worker.text()} ${apiOutput}`);
    const button = reports.getByRole('button', { name: 'Download Source-only gap report PDF' });
    await expect(button).toBeVisible();
    const event = page.waitForEvent('download');
    await button.click();
    const download = await event;
    const pdfPath = await download.path();
    const pdf = readFileSync(pdfPath);
    expect(pdf.subarray(0, 5).toString()).toBe('%PDF-');
    const inspected = spawnSync(join(root, '.venv', 'Scripts', 'python.exe'),
      ['tests/fixtures/reports/inspect_pdf.py', pdfPath], { cwd: root, encoding: 'utf8' });
    if (inspected.status !== 0) throw new Error(inspected.stderr);
    expect(inspected.stdout).toContain(source.digest);
    expect(inspected.stdout).toContain('gap only');
    expect(inspected.stdout).not.toContain('Measured outcomes');
    const artifactId = await page.evaluate(async (workspace) =>
      ((await (await fetch(`/api/v1/workspaces/${workspace}/reviews/main`)).json()) as {
        content: { draft: { sources: { source_id: string }[] } };
      }).content.draft.sources[0].source_id, workspaceId);
    const browserHash = await page.evaluate(async ([workspace, artifact]) => {
      const response = await fetch(`/api/v1/workspaces/${workspace}/artifacts/${artifact}/download`);
      const digest = await crypto.subtle.digest('SHA-256', await response.arrayBuffer());
      return Array.from(new Uint8Array(digest)).map((byte) => byte.toString(16).padStart(2, '0')).join('');
    }, [workspaceId, artifactId] as const);
    expect(browserHash).toBe(source.digest);
    partialRecords.push({ case: caseId, source_sha256: source.digest,
      source_byte_size: source.size, physical_pages: source.pages,
      gap_report_sha256: createHash('sha256').update(pdf).digest('hex'),
      original_bytes_preserved: true });
    await context.unrouteAll({ behavior: 'ignoreErrors' });
  });
}
