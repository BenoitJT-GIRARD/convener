import { afterEach, describe, expect, it } from 'vitest';
import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  INDEX_FILENAME,
  PUBLIC_KEYS_DIR,
  readPublicKeys,
  sortDescending,
  writeSigningKeys,
} from '../scripts/signing-keys-files.mjs';
import { KEYS_INDEX_FILENAME } from '../src/verify/publicKeys';
import cases from '../../tools/tests/fixtures/certificate-verification.json';

// This suite exercises real filesystem paths under a temp directory, never
// the app's own `public/keys/signing/` -- `copy-signing-keys.mjs` itself
// (the script that writes there) is never imported here, the same reason
// `handbook-files.mjs`'s own tests never import `copy-handbook.mjs`: a
// top-level script has side effects the moment it is imported, which a
// test suite must not trigger against the real working tree.
// `writeSigningKeys`, below, is exempt from that concern: it is a plain
// exported function with no top-level effect of its own.

// app/tests/.. = app/
const APP_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');

describe('the manifest filename copy-signing-keys.mjs writes and publicKeys.ts fetches (Minor 6: two literals, pinned equal, not one shared import)', () => {
  it('pins scripts/signing-keys-files.mjs::INDEX_FILENAME to src/verify/publicKeys.ts::KEYS_INDEX_FILENAME', () => {
    expect(INDEX_FILENAME).toBe(KEYS_INDEX_FILENAME);
  });
});

describe('PUBLIC_KEYS_DIR is the exact directory publicKeys.ts fetches from (Important 2)', () => {
  it('resolves to app/public/keys/signing, independent of cwd', () => {
    // Independently re-derived from this test file's own location. Before
    // this test, no test ever ran either copy script or asserted its
    // destination path at all -- the exact mutant this round's own
    // ruling names (`DST` -> `public/keys/signing-v2`) survived a fully
    // green suite.
    expect(PUBLIC_KEYS_DIR).toBe(resolve(APP_ROOT, 'public', 'keys', 'signing'));
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

describe('writeSigningKeys -- the real write, run against a temporary tree (Important 2)', () => {
  let root: string;

  afterEach(async () => {
    if (root) await rm(root, { recursive: true, force: true });
  });

  it('writes index.json directly under dstDir, with no extra nesting -- the exact path publicKeys.ts fetches, relative to BASE/keys/signing/', async () => {
    root = await mkdtemp(join(tmpdir(), 'convener-verify-write-keys-'));
    const srcDir = join(root, 'signing');
    await mkdir(srcDir, { recursive: true });
    await writeFile(join(srcDir, '2026-08-20.pub'), cases.signed_example.public_pem);
    const dstDir = join(root, 'public', 'keys', 'signing');

    const { pems, indexPath } = await writeSigningKeys(srcDir, dstDir);

    // publicKeys.ts's keysUrl() is `${BASE}/keys/signing/${KEYS_INDEX_FILENAME}`
    // -- so the manifest's own path, relative to the directory this
    // script was told to write into, must equal INDEX_FILENAME exactly.
    expect(relative(dstDir, indexPath)).toBe(INDEX_FILENAME);
    expect(pems).toEqual([cases.signed_example.public_pem]);
    expect(await readFile(join(dstDir, '2026-08-20.pub'), 'utf8')).toBe(cases.signed_example.public_pem);
  });

  it('clears a stale key left over from a previous publish', async () => {
    root = await mkdtemp(join(tmpdir(), 'convener-verify-write-keys-'));
    const srcDir = join(root, 'signing');
    await mkdir(srcDir, { recursive: true });
    await writeFile(join(srcDir, '2026-08-20.pub'), 'NEW KEY');
    const dstDir = join(root, 'public', 'keys', 'signing');
    await mkdir(dstDir, { recursive: true });
    await writeFile(join(dstDir, 'retired.pub'), 'a key that was retired');

    const { pems } = await writeSigningKeys(srcDir, dstDir);
    expect(pems).toEqual(['NEW KEY']);
    await expect(readFile(join(dstDir, 'retired.pub'), 'utf8')).rejects.toThrow();
  });

  it('writes an empty index.json when the source directory does not exist -- the ordinary D-13 state', async () => {
    root = await mkdtemp(join(tmpdir(), 'convener-verify-write-keys-'));
    const dstDir = join(root, 'public', 'keys', 'signing');
    const { pems, indexPath } = await writeSigningKeys(join(root, 'does-not-exist'), dstDir);
    expect(pems).toEqual([]);
    expect(JSON.parse(await readFile(indexPath, 'utf8'))).toEqual([]);
  });
});
