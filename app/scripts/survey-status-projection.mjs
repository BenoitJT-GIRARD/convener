/* Reading and writing `public-data/survey-status.json`, the way
 * `copy-survey-status.mjs` needs to -- the identical split
 * `certificates-projection.mjs` uses for `copy-certificates.mjs`, kept as
 * its own module for the same reason: a rule
 * `app/tests/copy-survey-status.test.ts` can call directly, including the
 * write itself, without importing a script that has a side effect the
 * moment it loads.
 */
import { existsSync } from 'node:fs';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

/** The filename `copy-survey-status.mjs` writes under `public/`, and
 *  `src/survey/SurveyForm.tsx` fetches -- two literals, pinned equal by a
 *  test, not one shared import, the same honestly-described guarantee
 *  `certificates-projection.mjs::DEST_FILENAME`'s own comment gives. */
export const DEST_FILENAME = 'survey-status.json';

/** `app/public/`, computed from this file's own location -- identical to
 *  `certificates-projection.mjs::PUBLIC_DIR`, and deliberately re-derived
 *  rather than imported from it: the two projections are independent, and
 *  a change to one script's destination must not silently move the
 *  other's. */
export const PUBLIC_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..', 'public');

/**
 * The published survey-enabled set, read from `srcPath` -- a **bare JSON
 * array** of lower-cased event ids, exactly what
 * `tools/convener_ops/cli.py::survey_status_public_data` writes (see that
 * function's own `test_survey_status_public_data_writes_only_the_enabled_ids`,
 * which asserts precisely this shape on disk).
 *
 * Absent or unreadable source is a normal state, returned as `[]`, not
 * thrown: no event has the survey switch on yet, or this is a local
 * `npm run dev` with nobody having run
 * `uv run convener-survey-status-public-data` first -- the same "empty is
 * normal" discipline `certificates-projection.mjs::readProjection` and
 * `signing-keys-files.mjs::readPublicKeys` both apply to their own
 * absent sources. An empty list here means every event reads as closed,
 * which is the fail-closed direction the switch asks for: the page must never
 * treat "we could not determine the status" as "open".
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
 * `<dstDir>/DEST_FILENAME`, creating `dstDir` if needed. Returns the ids
 * written and the resolved destination path -- the same shape
 * `certificates-projection.mjs::writeProjection` returns, exported for
 * the identical reason: a test can run the real write against a
 * temporary directory and assert the path it actually produces, not only
 * that a filename constant matches one imported elsewhere.
 */
export async function writeProjection(srcPath, dstDir) {
  if (!existsSync(dstDir)) await mkdir(dstDir, { recursive: true });
  const ids = await readProjection(srcPath);
  const dest = resolve(dstDir, DEST_FILENAME);
  await writeFile(dest, JSON.stringify(ids), 'utf8');
  return { ids, dest };
}
