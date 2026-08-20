/* Which signing public keys `copy-signing-keys.mjs` publishes, and in what
 * order. Kept apart from the copy script itself, the same reason
 * `handbook-files.mjs` is kept apart from `copy-handbook.mjs`: a rule
 * `app/tests/copy-signing-keys.test.ts` can call directly, rather than one
 * only ever exercised by running the whole script against the real
 * `keys/signing/` tree.
 */
import { readFile, readdir } from 'node:fs/promises';
import { join } from 'node:path';

/** The manifest filename `copy-signing-keys.mjs` writes, and
 *  `src/verify/publicKeys.ts::KEYS_INDEX_FILENAME` fetches -- defined once
 *  here, imported by both, rather than two literals that could drift.
 *  Pinned together with the TypeScript side in
 *  `app/tests/copy-signing-keys.test.ts`. */
export const INDEX_FILENAME = 'index.json';

/**
 * `.pub` filenames sorted newest first (descending).
 *
 * `keys/signing/<YYYY-MM-DD>.pub` names sort the same way the keys age
 * (`signing.py`'s own "Key layout" section) -- a plain descending string
 * sort on ISO 8601 dates *is* chronological order, newest first, with no
 * separate manifest to keep in sync. That is the order
 * `signing.py::verify`'s docstring and `keys/signing/README.md` both
 * recommend a caller build its key list in: most verifications are of a
 * certificate signed under the key currently in service, so trying that
 * one first makes the common case the cheapest -- correctness never
 * depends on getting the order right, only on the right key being
 * somewhere in the list.
 */
export function sortDescending(filenames) {
  return [...filenames].sort((a, b) => {
    if (a < b) return 1;
    if (a > b) return -1;
    return 0;
  });
}

/**
 * Every `*.pub` file's raw text under `dir`, newest first.
 *
 * An absent or empty directory returns `[]`, not an error --
 * `keys/signing/README.md` documents this as the current, real, normal
 * state until an operator generates the first signing key, and the same
 * "empty is normal" discipline `copy-event-keys.mjs` already applies to
 * `keys/events/`.
 */
export async function readPublicKeys(dir) {
  let entries;
  try {
    entries = await readdir(dir, { withFileTypes: true });
  } catch {
    return [];
  }
  const filenames = sortDescending(
    entries.filter(entry => entry.isFile() && entry.name.endsWith('.pub')).map(entry => entry.name),
  );
  const pems = [];
  for (const name of filenames) {
    pems.push(await readFile(join(dir, name), 'utf8'));
  }
  return pems;
}
