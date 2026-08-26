import { afterEach, describe, expect, it } from 'vitest';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { DEST_FILENAME, PUBLIC_DIR, readProjection, writeProjection } from '../scripts/certificates-projection.mjs';
import { REGISTER_FILENAME, isProjection } from '../src/verify/register';
import cases from '../../tools/tests/fixtures/certificate-verification.json';

// This suite exercises real filesystem paths under a temp directory, never
// the app's own `public/certificates.json` -- `copy-certificates.mjs`
// itself is never imported here, the same reason `handbook-files.mjs`'s
// own tests never import `copy-handbook.mjs`: a top-level script has side
// effects the moment it is imported. `writeProjection`, below, is exempt
// from that concern: it is a plain exported function with no top-level
// effect of its own, called here against a temp directory it never
// touches the real `public/` tree from.
//
// tools/convener_ops/cli.py::certificates_public_data writes a bare JSON array
// -- see that function's own
// test_certificates_public_data_aggregates_every_events_register.
// projection_example itself used to be nested
// under a `{"certificates": [...]}` key, which read as the wire shape and
// was not -- corrected in the fixture directly, so this is now the same
// bare array `readProjection` and `isProjection` actually accept.
const REAL_PROJECTION = cases.projection_example;

// app/tests/.. = app/
const APP_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');

describe('the filename copy-certificates.mjs writes and register.ts fetches -- two literals, pinned equal, not one shared import', () => {
  it('pins scripts/certificates-projection.mjs::DEST_FILENAME to src/verify/register.ts::REGISTER_FILENAME', () => {
    expect(DEST_FILENAME).toBe(REGISTER_FILENAME);
  });
});

describe('PUBLIC_DIR is the exact directory register.ts fetches from', () => {
  it('resolves to app/public, independent of cwd', () => {
    // Independently re-derived from this test file's own location,
    // rather than compared against nothing -- if copy-certificates.mjs's
    // own destination directory ever moved to a different subtree (the
    // exact mutant this round's own ruling names: `public/data`), this
    // is what would catch it. Before this test, no test ever ran either
    // copy script or asserted its destination path at all.
    expect(PUBLIC_DIR).toBe(resolve(APP_ROOT, 'public'));
  });
});

describe('readProjection', () => {
  let dir: string;

  afterEach(async () => {
    if (dir) await rm(dir, { recursive: true, force: true });
  });

  it('returns [] when public-data/certificates-public.json does not exist -- a normal state, no certificate issued yet', async () => {
    expect(await readProjection(join(tmpdir(), 'convener-verify-test-does-not-exist.json'))).toEqual([]);
  });

  it('returns [] for unparsable content rather than throwing', async () => {
    dir = await mkdtemp(join(tmpdir(), 'convener-verify-cert-'));
    const path = join(dir, 'certificates-public.json');
    await writeFile(path, 'not json at all');
    expect(await readProjection(path)).toEqual([]);
  });

  it('returns [] for valid JSON that is not an array', async () => {
    dir = await mkdtemp(join(tmpdir(), 'convener-verify-cert-'));
    const path = join(dir, 'certificates-public.json');
    await writeFile(path, JSON.stringify({ certificates: REAL_PROJECTION }));
    expect(await readProjection(path)).toEqual([]);
  });

  it('round-trips the real, bare-array projection unchanged, end to end into what register.ts accepts', async () => {
    // The strongest form of "pin the two ends together": the exact bytes
    // this script would read from `public-data/certificates-public.json`
    // are handed straight to register.ts's own shape validator, using one
    // shared fixture on both sides.
    dir = await mkdtemp(join(tmpdir(), 'convener-verify-cert-'));
    const path = join(dir, 'certificates-public.json');
    await writeFile(path, JSON.stringify(REAL_PROJECTION));

    const rows = await readProjection(path);
    expect(rows).toEqual(REAL_PROJECTION);
    expect(isProjection(rows)).toBe(true);
  });
});

describe('writeProjection -- the real write, run against a temporary tree', () => {
  let root: string;

  afterEach(async () => {
    if (root) await rm(root, { recursive: true, force: true });
  });

  it('writes to <dstDir>/<REGISTER_FILENAME> with no extra nesting -- the exact path register.ts fetches, relative to BASE', async () => {
    root = await mkdtemp(join(tmpdir(), 'convener-verify-write-cert-'));
    const src = join(root, 'certificates-public.json');
    await writeFile(src, JSON.stringify(REAL_PROJECTION));
    const dstDir = join(root, 'public');

    const { rows, dest } = await writeProjection(src, dstDir);

    // register.ts's registerUrl() is `${BASE}/${REGISTER_FILENAME}`, and
    // Vite serves everything under `public/` at BASE's own root -- so the
    // write's own path, relative to the directory it was told to write
    // into, must equal REGISTER_FILENAME exactly, with nothing in
    // between. A mutant that nested the write one directory deeper (or
    // shallower) would fail this, which the filename-only pin above
    // cannot.
    expect(relative(dstDir, dest)).toBe(REGISTER_FILENAME);
    expect(rows).toEqual(REAL_PROJECTION);
  });

  it('creates dstDir when it does not exist yet', async () => {
    root = await mkdtemp(join(tmpdir(), 'convener-verify-write-cert-'));
    const src = join(root, 'certificates-public.json');
    await writeFile(src, JSON.stringify(REAL_PROJECTION));
    const dstDir = join(root, 'public', 'nested', 'once', 'more');

    const { dest } = await writeProjection(src, dstDir);
    expect(await readProjection(dest)).toEqual(REAL_PROJECTION);
  });

  it('writes [] when the source is absent -- the ordinary D-13 state, no certificate issued yet', async () => {
    root = await mkdtemp(join(tmpdir(), 'convener-verify-write-cert-'));
    const dstDir = join(root, 'public');
    const { rows, dest } = await writeProjection(join(root, 'does-not-exist.json'), dstDir);
    expect(rows).toEqual([]);
    expect(await readProjection(dest)).toEqual([]);
  });
});
