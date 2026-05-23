/* Copy ../docs/**.md into public/handbook/ so the app can render handbook
 * content from a same-origin static path (no GitHub API call needed,
 * works in demo mode). Runs before `vite dev` and `vite build`.
 */
import { cp, mkdir, rm, readdir, stat } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { resolve, dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const SRC = resolve(__dirname, '..', '..', 'docs');
const DST = resolve(__dirname, '..', 'public', 'handbook');

const SKIP_DIRS = new Set(['superpowers', 'assets', 'stylesheets']);

async function walk(dir, base = '') {
  const out = [];
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const rel = join(base, entry.name);
    if (entry.isDirectory()) {
      if (SKIP_DIRS.has(entry.name)) continue;
      out.push(...(await walk(join(dir, entry.name), rel)));
    } else if (entry.isFile() && entry.name.endsWith('.md')) {
      out.push(rel);
    }
  }
  return out;
}

if (!existsSync(SRC)) {
  console.error(`copy-handbook: source not found at ${SRC}`);
  process.exit(1);
}

if (existsSync(DST)) await rm(DST, { recursive: true });
await mkdir(DST, { recursive: true });

const files = await walk(SRC);
let copied = 0;
for (const rel of files) {
  const from = join(SRC, rel);
  const to = join(DST, rel);
  await mkdir(dirname(to), { recursive: true });
  await cp(from, to);
  copied++;
}

console.log(`copy-handbook: copied ${copied} markdown files → ${relative(process.cwd(), DST)}`);
