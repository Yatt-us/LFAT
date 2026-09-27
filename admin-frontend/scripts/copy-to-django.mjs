import { cpSync, existsSync, rmSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join, resolve } from 'node:path';

const workspace = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const source = join(workspace, 'dist', 'admin-frontend', 'browser');
const destination = resolve(workspace, '..', 'dashboard', 'static', 'dashboard', 'admin-angular');

if (!existsSync(join(source, 'main.js')) || !existsSync(join(source, 'styles.css'))) {
  throw new Error('Angular build is incomplete: main.js or styles.css is missing.');
}
rmSync(destination, { recursive: true, force: true });
cpSync(source, destination, { recursive: true });
console.log('Angular admin assets copied to', destination);
