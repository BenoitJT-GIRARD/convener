/* Which signing public keys `copy-signing-keys.mjs` publishes, in what
 * order, and where. Kept apart from the copy script itself, the same
 * reason `handbook-files.mjs` is kept apart from `copy-handbook.mjs`: a
 * rule `app/tests/scripts/copy-signing-keys.test.ts` can call directly, rather
 * than one only ever exercised by running the whole script against the
 * real `instance/keys/signing/` tree.
 */
import { existsSync } from 'node:fs';
import { cp, mkdir, readFile, readdir, rm, writeFile } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

/** The manifest filename `copy-signing-keys.mjs` writes, and
 *  `src/verify/publicKeys.ts::KEYS_INDEX_FILENAME` fetches. These are
 *  two literals in two files, not one constant
 *  imported by both -- `app/tests/scripts/copy-signing-keys.test.ts` pins them
 *  equal directly, which is a weaker, but honestly-described, guarantee
 *  than "defined once, imported by both" would be. */
export const INDEX_FILENAME = 'index.json';

/** `app/public/keys/signing/`, computed from this file's own location
 *  rather than `process.cwd()` -- the exact directory
 *  `copy-signing-keys.mjs` writes into and `publicKeys.ts`'s `keysUrl()`
 *  is relative to. Exported (pure path math, no I/O) so a test can assert
 *  it resolves to that same directory, not merely that a filename
 *  constant matches one imported elsewhere. Before this,
 *  `copy-signing-keys.mjs`'s own `DST` could move to a
 *  different subtree entirely and every existing test stayed green. */
export const PUBLIC_KEYS_DIR = resolve(
  dirname(fileURLToPath(import.meta.url)),
  '..',
  'public',
  'keys',
  'signing',
);

/**
 * `.pub` filenames sorted newest first (descending).
 *
 * `instance/keys/signing/<YYYY-MM-DD>.pub` names sort the same way the keys age
 * (`signing.py`'s own "Key layout" section) -- a plain descending string
 * sort on ISO 8601 dates *is* chronological order, newest first, with no
 * separate manifest to keep in sync. That is the order
 * `signing.py::verify`'s docstring and `instance/keys/signing/README.md` both
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
 * `instance/keys/signing/README.md` documents this as the current, real, normal
 * state until an operator generates the first signing key, and the same
 * "empty is normal" discipline `copy-event-keys.mjs` already applies to
 * `instance/keys/events/`.
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

/**
 * The whole publish: every `*.pub` file under `srcDir`, copied verbatim
 * into `dstDir`, plus `dstDir/INDEX_FILENAME` -- the manifest
 * `publicKeys.ts` fetches. `dstDir` is cleared first (removed and
 * recreated), the same "no stale key left behind after one is retired"
 * discipline the script always had.
 *
 * Exported so
 * `app/tests/scripts/copy-signing-keys.test.ts` can run this for real, against a
 * temporary directory, and assert the path it actually produces --
 * before this, no test ever exercised the destination path at all.
 */
export async function writeSigningKeys(srcDir, dstDir) {
  if (existsSync(dstDir)) await rm(dstDir, { recursive: true });
  await mkdir(dstDir, { recursive: true });

  if (existsSync(srcDir)) {
    const entries = await readdir(srcDir, { withFileTypes: true });
    for (const entry of entries) {
      if (!entry.isFile() || !entry.name.endsWith('.pub')) continue;
      await cp(join(srcDir, entry.name), join(dstDir, entry.name));
    }
  }

  const pems = await readPublicKeys(srcDir);
  const indexPath = join(dstDir, INDEX_FILENAME);
  await writeFile(indexPath, JSON.stringify(pems), 'utf8');
  return { pems, indexPath };
}
