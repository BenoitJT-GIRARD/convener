/* Publishes `../../public-data/certificates-public.json` into
 * `public/certificates.json`, for `src/verify/register.ts` to fetch at
 * runtime -- so it ships as part of the app's own built output
 * (`dist/certificates.json`) rather than depending on a second, separate
 * write into the showcase repository racing against `deploy.yml`'s own
 * wholesale `rm -rf app && cp -r dist/. app/` (see that workflow's own
 * comment for why a second writer into that same subtree would be
 * silently clobbered the next time either job ran).
 *
 * `instance/public-data/certificates-public.json` itself is CI-generated, gitignored
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
 * The actual write (`writeProjection`) and the destination directory
 * (`PUBLIC_DIR`) both live in `certificates-projection.mjs` now, not
 * here -- this file is a thin wrapper around them so
 * `app/tests/copy-certificates.test.ts` can run the real write against a
 * temporary directory without triggering this file's own side effect.
 *
 * Runs before `vite dev` and `vite build`, alongside the other copy
 * scripts.
 */
import { relative, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { publicDataDir } from './instance-paths.mjs';
import { PUBLIC_DIR, writeProjection } from './certificates-projection.mjs';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, '..', '..');
const SRC = resolve(ROOT, publicDataDir(), 'certificates-public.json');

const { rows, dest } = await writeProjection(SRC, PUBLIC_DIR);

console.log(
  `copy-certificates: published ${rows.length} certificate state(s) -> ${relative(process.cwd(), dest)}`,
);
