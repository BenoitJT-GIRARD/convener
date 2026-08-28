/* Copy ../../keys/events/*.pub into public/keys/events/ so the registration
 * page (`src/signup/SignupForm.tsx`) -- and the post-event
 * survey page (`src/survey/SurveyForm.tsx`), which fetches the identical
 * file under the identical event id -- can fetch an event's published
 * public half from the same origin the app itself is served from -- the same
 * reasoning `copy-handbook.mjs` gives for `docs/`, applied to a directory
 * that is public for a different reason: nothing under `instance/keys/events/*.pub`
 * is a secret (see `tools/convener_ops/eventkeys.py`'s module docstring), only
 * `.pub` files exist here at all -- the private half never touches disk
 * outside a CI job, and `.gitignore` refuses everything under
 * `instance/keys/events/` except `*.pub` by construction.
 *
 * Runs before `vite dev` and `vite build`, alongside copy-handbook.mjs.
 *
 * No event may have been created yet, and that is a normal state, not an
 * error: an absent `instance/keys/events/` directory produces an empty destination
 * rather than failing the build. A registration page whose event id has no
 * published key then gets a 404 fetching it -- which is exactly the
 * "public key cannot be fetched" case `SignupForm` refuses to send through,
 * not a build-time concern.
 */
import { cp, mkdir, readdir, rm } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { resolve, dirname, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { keysDir } from './instance-paths.mjs';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, '..', '..');
const SRC = resolve(ROOT, keysDir(), 'events');
const DST = resolve(__dirname, '..', 'public', 'keys', 'events');

if (existsSync(DST)) await rm(DST, { recursive: true });
await mkdir(DST, { recursive: true });

if (!existsSync(SRC)) {
  console.log(`copy-event-keys: no ${keysDir()}events/ yet -- 0 .pub, nothing to publish`);
  process.exit(0);
}

const entries = await readdir(SRC, { withFileTypes: true });
let count = 0;
for (const entry of entries) {
  if (!entry.isFile() || !entry.name.endsWith('.pub')) continue;
  await cp(resolve(SRC, entry.name), resolve(DST, entry.name));
  count++;
}

console.log(`copy-event-keys: copied ${count} .pub -> ${relative(process.cwd(), DST)}`);
