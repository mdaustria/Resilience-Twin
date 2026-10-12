import { spawn } from 'node:child_process';

const windows = process.platform === 'win32';
const commands = [
  ['API', 'uv', ['run', 'uvicorn', 'services.api.main:app', '--host', '127.0.0.1', '--port', '8000']],
  ['Web', 'pnpm', ['--filter', '@resilience-twin/web', 'dev']],
];
const children = commands.map(([label, command, args]) => {
  const env = label === 'API'
    ? { ...process.env, RESILIENCE_TWIN_ENV: 'development', RESILIENCE_TWIN_LOCAL_FIXTURES: '1' }
    : process.env;
  const child = spawn(command, args, { stdio: 'inherit', shell: windows, env });
  child.on('error', (error) => {
    console.error(`${label} failed to start: ${error.message}`);
    stop(1);
  });
  child.on('exit', (code) => {
    console.error(`${label} exited with code ${code}`);
    stop(code ?? 1);
  });
  return child;
});

let stopping = false;
function stop(code) {
  if (stopping) return;
  stopping = true;
  for (const child of children) child.kill();
  process.exitCode = code;
}
process.on('SIGINT', () => stop(0));
process.on('SIGTERM', () => stop(0));
