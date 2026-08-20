import { afterEach, describe, expect, it } from 'vitest';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { DEST_FILENAME, readProjection } from '../scripts/certificates-projection.mjs';
import { REGISTER_FILENAME, isProjection } from '../src/verify/register';
import cases from '../../tools/tests/fixtures/certificate-verification.json';

// This suite exercises real filesystem paths under a temp directory, never
// the app's own `public/certificates.json` -- `copy-certificates.mjs`
// itself is never imported here, the same reason `handbook-files.mjs`'s
// own tests never import `copy-handbook.mjs`: a top-level script has side
// effects the moment it is imported.
//
// tools/convener_ops/cli.py::certificates_public_data writes a bare JSON array
// -- see that function's own
// test_certificates_public_data_aggregates_every_events_register -- so
// every "real projection" fixture below is the fixture's own two worked
// rows reshaped into that real, bare-array wire shape, not the
// `{"certificates": [...]}` object certificate-verification.json's own
// `projection_example` property happens to be named after.
const REAL_PROJECTION = cases.projection_example.certificates;

describe('the filename copy-certificates.mjs writes and register.ts fetches are the same string', () => {
  it('pins scripts/certificates-projection.mjs::DEST_FILENAME to src/verify/register.ts::REGISTER_FILENAME', () => {
    expect(DEST_FILENAME).toBe(REGISTER_FILENAME);
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
