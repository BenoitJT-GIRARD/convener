/* Copy the handbook pages `../src/content/registry.ts` names -- and the
 * visual-kit assets `PUBLIC_ASSETS` names alongside them -- from `../docs`
 * into `public/docs/`, so the app can render handbook content and hand
 * over the visual kit from a same-origin static path (no GitHub API call
 * needed, works in demo mode). Runs before `vite dev` and `vite build`.
 *
 * This used to copy every file under `docs/` with a recognised extension
 * (`.md`, `.svg`, `.png` -- an extension allowlist) that did not sit in one
 * of three skipped directories (`superpowers`, `stylesheets`, `app` -- a
 * directory denylist). Both existed; neither was the allowlist
 * `public_data.py` describes. The denylist named three directories and
 * never `docs/reference/`, so any `.md` page added there shipped, whichever
 * it was -- `docs/reference/operations.md`, which names every secret and
 * every procedure, did exactly that, verified by a real build before this
 * change. The extension allowlist covered `.png`, and `docs/handbook/assets/` was
 * never skipped, so a `.png` dropped there shipped too -- verified the same
 * way, and one such file was a past speaker's own photograph and name (see
 * `PUBLIC_ASSETS`'s own comment on `docs/assets/flyer-example.png`).
 * The allowlist that decides what the app *renders*
 * already existed -- `CONTENT_REGISTRY` -- it just was not the thing
 * deciding what this script *copied*. It is now: see
 * `handbook-registry.mjs::publishedPaths`, and the sweep in
 * `app/tests/copy-handbook.test.ts` that fails if a file absent from that
 * allowlist ever reaches `public/docs/` again.
 */
import { existsSync } from 'node:fs';
import { readFile } from 'node:fs/promises';
import { dirname, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { copyHandbook } from './handbook-registry.mjs';

const __dirname = dirname(fileURLToPath(import.meta.url));
const DOCS = resolve(__dirname, '..', '..', 'docs');
const REGISTRY = resolve(__dirname, '..', 'src', 'content', 'registry.ts');
const DST = resolve(__dirname, '..', 'public', 'docs');

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
