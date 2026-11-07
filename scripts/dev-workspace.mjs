import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = fileURLToPath(new URL('../', import.meta.url));
const python = path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
if (!existsSync(python)) {
  process.stderr.write('Set up the local Python environment first. See WORKSPACE-PREVIEW.md.\n');
  process.exit(1);
}

const commands = [
  [python, ['-m', 'uvicorn', 'enterprise_preview:create_app', '--factory', '--host', '127.0.0.1', '--port', '8001']],
  [process.execPath, [path.join(root, 'node_modules/vite/bin/vite.js'), '--host', '127.0.0.1', '--port', '5173', '--strictPort']],
];
const children = [];
let stopping = false;
function stop(code) {
  if (stopping) return;
  stopping = true;
  for (const child of children) child.kill();
  process.exitCode = code;
}
for (const [command, args] of commands) {
  const child = spawn(command, args, {
    cwd: root, stdio: 'inherit', windowsHide: true,
    env: { ...process.env, LOAMY_LOCAL_PREVIEW: '1', ENABLE_SCHEDULER: 'false' },
  });
  children.push(child);
  child.on('error', (error) => { process.stderr.write(`${error.message}\n`); stop(1); });
  child.on('exit', (code) => stop(code ?? 1));
}
process.on('SIGINT', () => stop(0));
process.on('SIGTERM', () => stop(0));
process.stdout.write('Open http://127.0.0.1:5173/business to test your business workspace.\n');
