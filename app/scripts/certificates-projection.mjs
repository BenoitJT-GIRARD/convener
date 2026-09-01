/* Reading and writing `instance/public-data/certificates-public.json`, the way
 * `copy-certificates.mjs` needs to. Kept apart from that script, the same
 * reason `handbook-files.mjs` is kept apart from `copy-handbook.mjs`: a
 * rule `app/tests/copy-certificates.test.ts` can call directly, including
 * the write itself (see `writeProjection`'s
 * own comment).
 */
import { existsSync } from 'node:fs';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

/** The filename `copy-certificates.mjs` writes under `public/`, and
 *  `src/verify/register.ts::REGISTER_FILENAME` fetches. These are
 *  two literals in two files, not one constant
 *  imported by both -- `app/tests/copy-certificates.test.ts` pins them
 *  equal directly, which is a weaker, but honestly-described, guarantee
 *  than "defined once, imported by both" would be. */
export const DEST_FILENAME = 'certificates.json';

/** `app/public/`, computed from this file's own location rather than
 *  `process.cwd()` -- the exact directory `copy-certificates.mjs` writes
 *  into and Vite serves at `BASE_URL`'s own root. Exported (pure path
 *  math, no I/O) so a test can assert it resolves to the same directory
 *  `register.ts`'s fetch URL is relative to, not merely that a filename
 *  constant matches one imported elsewhere. Before this,
 *  `copy-certificates.mjs`'s own `DST_DIR` could move to a
 *  different subtree entirely and every existing test stayed green. */
export const PUBLIC_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..', 'public');

/**
 * The public certificate register projection, read from `srcPath` -- a
 * **bare JSON array** of `{"identifier", "state"}` objects, exactly what
 * `tools/convener_ops/cli/journey/certificate.py::certificates_public_data` writes (see that
 * function's own `test_certificates_public_data_aggregates_every_events_register`,
 * which asserts precisely this shape on disk).
 *
 * Absent or unreadable source is a normal state, returned as `[]`, not
 * thrown: no certificate has ever been issued yet, or this is a local
 * `npm run dev` with nobody having run
 * `uv run convener-certificates-public-data` first -- the same "empty is
 * normal" discipline `signing-keys-files.mjs::readPublicKeys` applies to
 * an absent `instance/keys/signing/`.
 */
export async function readProjection(srcPath) {
  let text;
  try {
    text = await readFile(srcPath, 'utf8');
  } catch {
    return [];
  }
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    return [];
  }
  return Array.isArray(data) ? data : [];
}

/**
 * Reads the projection from `srcPath` and writes it to
 * `<dstDir>/DEST_FILENAME`, creating `dstDir` if needed. Returns the rows
 * written and the resolved destination path.
 *
 * This is the whole write, not only the read
 * -- exported so `app/tests/copy-certificates.test.ts` can run it for
 * real, against a temporary directory, and assert the path it actually
 * produces. Before this, no test ever exercised the destination path at
 * all: `copy-certificates.mjs` itself is never imported by a test (it has
 * a side effect the moment it runs), so the directory it wrote into could
 * drift from what `register.ts`'s fetch URL expects with every existing
 * test still green. Two constants agreeing on a filename is not the same
 * claim as a served file landing where it is fetched from.
 */
export async function writeProjection(srcPath, dstDir) {
  if (!existsSync(dstDir)) await mkdir(dstDir, { recursive: true });
  const rows = await readProjection(srcPath);
  const dest = resolve(dstDir, DEST_FILENAME);
  await writeFile(dest, JSON.stringify(rows), 'utf8');
  return { rows, dest };
}
