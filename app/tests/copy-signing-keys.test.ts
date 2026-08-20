import { afterEach, describe, expect, it } from 'vitest';
import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { INDEX_FILENAME, readPublicKeys, sortDescending } from '../scripts/signing-keys-files.mjs';
import { KEYS_INDEX_FILENAME } from '../src/verify/publicKeys';
import cases from '../../tools/tests/fixtures/certificate-verification.json';

// This suite exercises real filesystem paths under a temp directory, never
// the app's own `public/keys/signing/` -- `copy-signing-keys.mjs` itself
// (the script that writes there) is never imported here, the same reason
// `handbook-files.mjs`'s own tests never import `copy-handbook.mjs`: a
// top-level script has side effects the moment it is imported, which a
// test suite must not trigger against the real working tree.

describe('the manifest filename copy-signing-keys.mjs writes and publicKeys.ts fetches are the same string', () => {
  it('pins scripts/signing-keys-files.mjs::INDEX_FILENAME to src/verify/publicKeys.ts::KEYS_INDEX_FILENAME', () => {
    expect(INDEX_FILENAME).toBe(KEYS_INDEX_FILENAME);
  });
});

describe('sortDescending', () => {
  it('sorts YYYY-MM-DD filenames newest first', () => {
    expect(sortDescending(['2026-01-01.pub', '2026-08-20.pub', '2025-12-31.pub'])).toEqual([
      '2026-08-20.pub',
      '2026-01-01.pub',
      '2025-12-31.pub',
    ]);
  });

  it('does not mutate its argument', () => {
    const input = ['2026-01-01.pub', '2026-08-20.pub'];
    const copy = [...input];
    sortDescending(input);
    expect(input).toEqual(copy);
  });
});

describe('readPublicKeys', () => {
  let dir: string;

  afterEach(async () => {
    if (dir) await rm(dir, { recursive: true, force: true });
  });

  it('returns [] for a directory that does not exist -- the real, current state of keys/signing/', async () => {
    expect(await readPublicKeys(join(tmpdir(), 'convener-verify-test-does-not-exist'))).toEqual([]);
  });

  it('returns [] for an empty directory', async () => {
    dir = await mkdtemp(join(tmpdir(), 'convener-verify-keys-'));
    expect(await readPublicKeys(dir)).toEqual([]);
  });

  it('ignores non-.pub files and returns every .pub file\'s text, newest first', async () => {
    dir = await mkdtemp(join(tmpdir(), 'convener-verify-keys-'));
    await writeFile(join(dir, '2026-01-01.pub'), 'OLD KEY TEXT');
    await writeFile(join(dir, '2026-08-20.pub'), 'NEW KEY TEXT');
    await writeFile(join(dir, 'README.md'), 'not a key');
    expect(await readPublicKeys(dir)).toEqual(['NEW KEY TEXT', 'OLD KEY TEXT']);
  });

  it('round-trips the fixture\'s own real public key text unchanged', async () => {
    dir = await mkdtemp(join(tmpdir(), 'convener-verify-keys-'));
    await mkdir(dir, { recursive: true });
    await writeFile(join(dir, '2026-08-20.pub'), cases.signed_example.public_pem);
    expect(await readPublicKeys(dir)).toEqual([cases.signed_example.public_pem]);
  });
});
