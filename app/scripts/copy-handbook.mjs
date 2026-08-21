/* Copy the handbook pages `../src/content/registry.ts` names -- and the
 * visual-kit assets `PUBLIC_ASSETS` names alongside them -- from `../docs`
 * into `public/handbook/`, so the app can render handbook content and hand
 * over the visual kit from a same-origin static path (no GitHub API call
 * needed, works in demo mode). Runs before `vite dev` and `vite build`.
 *
 * This used to copy every file under `docs/` that had a recognised
 * extension and was not in a skipped directory -- no allowlist, only an
 * extension filter and a directory skip-list, so a page added under
 * `docs/reference/` or a new top-level directory such as
 * `docs/superpowers/` shipped into this same public bundle the moment it
 * existed, whether or not it was meant for a reader outside this
 * application. `docs/reference/operations.md` did exactly that. The
 * allowlist that decides what the app renders already existed --
 * `CONTENT_REGISTRY` -- it just was not the thing deciding what this script
 * copied. It is now: see `handbook-registry.mjs::publishedPaths`, and the
 * sweep in `app/tests/copy-handbook.test.ts` that fails if a file absent
 * from that allowlist ever reaches `public/handbook/` again.
 */
import { existsSync } from 'node:fs';
import { readFile } from 'node:fs/promises';
import { dirname, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { copyHandbook } from './handbook-registry.mjs';

const __dirname = dirname(fileURLToPath(import.meta.url));
const DOCS = resolve(__dirname, '..', '..', 'docs');
const REGISTRY = resolve(__dirname, '..', 'src', 'content', 'registry.ts');
const DST = resolve(__dirname, '..', 'public', 'handbook');

if (!existsSync(DOCS)) {
  console.error(`copy-handbook: source not found at ${DOCS}`);
  process.exit(1);
}

const registrySource = await readFile(REGISTRY, 'utf-8');
const { files, counts } = await copyHandbook({ docsDir: DOCS, registrySource, dst: DST });

const summary =
  [...counts]
    .sort()
    .map(([ext, n]) => `${n} ${ext.slice(1)}`)
    .join(', ') || 'nothing';
console.log(
  `copy-handbook: copied ${summary} (${files.length} file(s)) → ${relative(process.cwd(), DST)}`,
);
