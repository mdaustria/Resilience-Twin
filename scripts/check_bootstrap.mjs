import { spawnSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import assert from 'node:assert/strict';

if (process.argv.includes('--check')) {
  const steps = [
    ['uv', ['run', 'python', '-m', 'scripts.generate_client', '--check']],
    ['uv', ['run', 'pytest', 'tests/contracts/test_bootstrap.py']],
    ['uv', ['run', 'ruff', 'check', '.']],
    ['uv', ['run', 'mypy', 'packages', 'services']],
    ['pnpm', ['test']],
    ['pnpm', ['lint']],
    ['pnpm', ['typecheck']],
    ['pnpm', ['build']],
  ];
  for (const [command, args] of steps) {
    console.log(`> ${command} ${args.join(' ')}`);
    const result = spawnSync(command, args, { stdio: 'inherit', shell: process.platform === 'win32' });
    if (result.error) {
      console.error(result.error.message);
      process.exit(1);
    }
    if (result.status !== 0) process.exit(result.status ?? 1);
  }
} else {
  test('bootstrap workspace has a real generated API type', () => {
    const generated = readFileSync('apps/web/src/generated/bootstrap.ts', 'utf8');
    assert.match(generated, /\/api\/v1\/bootstrap/);
    assert.match(generated, /BootstrapStatus/);
  });

  test('root scripts launch checks and both local services', () => {
    const manifest = JSON.parse(readFileSync('package.json', 'utf8'));
    assert.match(manifest.scripts.dev, /scripts\/dev\.mjs/);
    assert.match(manifest.scripts['check:bootstrap'], /scripts\/check_bootstrap\.mjs/);
  });
}
