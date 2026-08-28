/* Publishes every `../../keys/signing/*.pub` this repository has ever
 * committed into `public/keys/signing/`, for `src/verify/publicKeys.ts` to
 * fetch at runtime -- the same idiom `copy-event-keys.mjs` already applies
 * to `instance/keys/events/`, adapted for a page with no single event id to key a
 * fetch off of (see `instance/keys/signing/README.md`'s "How a verifier should use
 * this directory").
 *
 * Two things are written, not one:
 * - Every `.pub` file, copied verbatim -- transparency: a key can be
 *   inspected directly at its own published URL, the same as any
 *   `instance/keys/events/<id>.pub` today.
 * - `index.json`, one array of every key's PEM text, newest first (see
 *   `signing-keys-files.mjs::sortDescending`) -- what the app actually
 *   fetches, in one request, rather than one request per key with no
 *   directory listing to discover their names from.
 *
 * The actual write (`writeSigningKeys`) and the destination directory
 * (`PUBLIC_KEYS_DIR`) both live in `signing-keys-files.mjs` now, not
 * here -- this file is a thin wrapper around them so
 * `app/tests/copy-signing-keys.test.ts` can run the real write against a
 * temporary directory without triggering this file's own side effect.
 *
 * Runs before `vite dev` and `vite build`, alongside the other copy
 * scripts. `instance/keys/signing/` legitimately holds no key at all until an
 * operator generates the first one -- an absent or empty source directory
 * produces an empty `index.json` (`[]`), not a build failure, the same
 * "empty is normal" discipline every copy script in this directory
 * follows.
 */
import { relative, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { keysDir } from './instance-paths.mjs';
import { PUBLIC_KEYS_DIR, writeSigningKeys } from './signing-keys-files.mjs';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, '..', '..');
const SRC = resolve(ROOT, keysDir(), 'signing');

const { pems, indexPath } = await writeSigningKeys(SRC, PUBLIC_KEYS_DIR);

console.log(
  `copy-signing-keys: published ${pems.length} signing key(s) -> ${relative(process.cwd(), indexPath)}`,
);
