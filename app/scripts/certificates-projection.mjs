/* Reading `public-data/certificates-public.json`, the way
 * `copy-certificates.mjs` needs to. Kept apart from that script, the same
 * reason `handbook-files.mjs` is kept apart from `copy-handbook.mjs`: a
 * rule `app/tests/copy-certificates.test.ts` can call directly.
 */
import { readFile } from 'node:fs/promises';

/** The filename `copy-certificates.mjs` writes under `public/`, and
 *  `src/verify/register.ts::REGISTER_FILENAME` fetches -- defined once
 *  here, imported by both, rather than two literals that could drift.
 *  Pinned together with the TypeScript side in
 *  `app/tests/copy-certificates.test.ts`. */
export const DEST_FILENAME = 'certificates.json';

/**
 * The public certificate register projection, read from `srcPath` -- a
 * **bare JSON array** of `{"identifier", "state"}` objects, exactly what
 * `tools/convener_ops/cli.py::certificates_public_data` writes (see that
 * function's own `test_certificates_public_data_aggregates_every_events_register`,
 * which asserts precisely this shape on disk -- not the
 * `{"certificates": [...]}` a reader might expect from
 * `certificate-verification.json`'s own `projection_example` property
 * name, which only labels a slot *inside the fixture file*).
 *
 * Absent or unreadable source is a normal state, returned as `[]`, not
 * thrown: no certificate has ever been issued yet, or this is a local
 * `npm run dev` with nobody having run
 * `uv run convener-certificates-public-data` first -- the same "empty is
 * normal" discipline `signing-keys-files.mjs::readPublicKeys` applies to
 * an absent `keys/signing/`.
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
