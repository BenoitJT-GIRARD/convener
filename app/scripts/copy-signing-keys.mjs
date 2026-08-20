/* Publishes every `../../keys/signing/*.pub` this repository has ever
 * committed into `public/keys/signing/`, for `src/verify/publicKeys.ts` to
 * fetch at runtime -- the same idiom `copy-event-keys.mjs` already applies
 * to `keys/events/`, adapted for a page with no single event id to key a
 * fetch off of (see `keys/signing/README.md`'s "What task 13 needs from
 * this directory").
 *
 * Two things are written, not one:
 * - Every `.pub` file, copied verbatim -- transparency: a key can be
 *   inspected directly at its own published URL, the same as any
 *   `keys/events/<id>.pub` today.
 * - `index.json`, one array of every key's PEM text, newest first (see
 *   `signing-keys-files.mjs::sortDescending`) -- what the app actually
 *   fetches, in one request, rather than one request per key with no
 *   directory listing to discover their names from.
 *
 * Runs before `vite dev` and `vite build`, alongside the other copy
 * scripts. `keys/signing/` legitimately holds no key at all until an
 * operator generates the first one -- an absent or empty source directory
 * produces an empty `index.json` (`[]`), not a build failure, the same
 * "empty is normal" discipline every copy script in this directory
 * follows.
 */
import { cp, mkdir, readdir, rm, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { resolve, dirname, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { INDEX_FILENAME, readPublicKeys } from './signing-keys-files.mjs';

const __dirname = dirname(fileURLToPath(import.meta.url));
const SRC = resolve(__dirname, '..', '..', 'keys', 'signing');
const DST = resolve(__dirname, '..', 'public', 'keys', 'signing');

if (existsSync(DST)) await rm(DST, { recursive: true });
await mkdir(DST, { recursive: true });

if (existsSync(SRC)) {
  const entries = await readdir(SRC, { withFileTypes: true });
  for (const entry of entries) {
    if (!entry.isFile() || !entry.name.endsWith('.pub')) continue;
    await cp(resolve(SRC, entry.name), resolve(DST, entry.name));
  }
}

const pems = await readPublicKeys(SRC);
await writeFile(resolve(DST, INDEX_FILENAME), JSON.stringify(pems), 'utf8');

console.log(
  `copy-signing-keys: published ${pems.length} signing key(s) -> ${relative(process.cwd(), resolve(DST, INDEX_FILENAME))}`,
);
