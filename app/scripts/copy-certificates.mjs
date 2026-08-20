/* Publishes `../../public-data/certificates-public.json` into
 * `public/certificates.json`, for `src/verify/register.ts` to fetch at
 * runtime -- so it ships as part of the app's own built output
 * (`dist/certificates.json`) rather than depending on a second, separate
 * write into the showcase repository racing against `deploy.yml`'s own
 * wholesale `rm -rf app && cp -r dist/. app/` (see that workflow's own
 * comment for why a second writer into that same subtree would be
 * silently clobbered the next time either job ran).
 *
 * `public-data/certificates-public.json` itself is CI-generated, gitignored
 * output (`uv run convener-certificates-public-data`, see
 * `.github/workflows/deploy.yml`'s "Build public data" step) -- not
 * committed source, so it will not exist for a plain local `npm run dev`
 * or `npm run build` unless that command was run first. An absent source
 * is a normal state here, not an error: it produces an empty projection
 * (`[]`), the same "empty is normal" discipline every copy script in this
 * directory follows, never a build failure. `certificates-projection.mjs`
 * is where "absent, or unreadable, or not shaped like a projection at
 * all" all fold into that same `[]`.
 *
 * Runs before `vite dev` and `vite build`, alongside the other copy
 * scripts.
 */
import { mkdir, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { resolve, dirname, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { DEST_FILENAME, readProjection } from './certificates-projection.mjs';

const __dirname = dirname(fileURLToPath(import.meta.url));
const SRC = resolve(__dirname, '..', '..', 'public-data', 'certificates-public.json');
const DST_DIR = resolve(__dirname, '..', 'public');

if (!existsSync(DST_DIR)) await mkdir(DST_DIR, { recursive: true });

const rows = await readProjection(SRC);
const dest = resolve(DST_DIR, DEST_FILENAME);
await writeFile(dest, JSON.stringify(rows), 'utf8');

console.log(
  `copy-certificates: published ${rows.length} certificate state(s) -> ${relative(process.cwd(), dest)}`,
);
