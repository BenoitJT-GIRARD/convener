/* Copy ../docs into public/handbook/ so the app can render handbook content
 * — and hand over the visual kit — from a same-origin static path (no GitHub
 * API call needed, works in demo mode). Runs before `vite dev` and
 * `vite build`. Which files travel is decided in handbook-files.mjs.
 */
import { cp, mkdir, rm } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { resolve, dirname, join, relative, extname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { walk } from './handbook-files.mjs';

const __dirname = dirname(fileURLToPath(import.meta.url));
const SRC = resolve(__dirname, '..', '..', 'docs');
const DST = resolve(__dirname, '..', 'public', 'handbook');

if (!existsSync(SRC)) {
  console.error(`copy-handbook: source not found at ${SRC}`);
  process.exit(1);
}

if (existsSync(DST)) await rm(DST, { recursive: true });
await mkdir(DST, { recursive: true });

const files = await walk(SRC);
const counts = new Map();
for (const rel of files) {
  const from = join(SRC, rel);
  const to = join(DST, rel);
  await mkdir(dirname(to), { recursive: true });
  await cp(from, to);
  const ext = extname(rel).toLowerCase();
  counts.set(ext, (counts.get(ext) ?? 0) + 1);
}

const summary = [...counts]
  .sort()
  .map(([ext, n]) => `${n} ${ext.slice(1)}`)
  .join(', ');
console.log(`copy-handbook: copied ${summary} → ${relative(process.cwd(), DST)}`);
