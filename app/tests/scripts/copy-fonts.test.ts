import { afterEach, describe, expect, it } from 'vitest';
import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { PUBLIC_FONTS_DIR, writeFonts } from '../../scripts/fonts-files.mjs';

// This suite exercises real filesystem paths under a temp directory, never
// the app's own `public/fonts/` -- `copy-fonts.mjs` itself (the script that
// writes there, and exits the process on a missing source) is never
// imported here, the same reason `copy-signing-keys.test.ts` never imports
// `copy-signing-keys.mjs`.

// app/tests/.. = app/
const APP_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../..');
// app/tests/../../assets/fonts = the one shared source both site/ and app/ read.
const SHARED_FONTS_DIR = resolve(APP_ROOT, '..', 'assets', 'fonts');

describe('PUBLIC_FONTS_DIR is the exact directory tokens.css\'s @font-face rules resolve against', () => {
  it('resolves to app/public/fonts, independent of cwd', () => {
    expect(PUBLIC_FONTS_DIR).toBe(resolve(APP_ROOT, 'public', 'fonts'));
  });
});

describe('writeFonts', () => {
  let root: string;

  afterEach(async () => {
    if (root) await rm(root, { recursive: true, force: true });
  });

  it('copies every file directly under srcDir into dstDir, verbatim', async () => {
    root = await mkdtemp(join(tmpdir(), 'convener-copy-fonts-'));
    const srcDir = join(root, 'fonts');
    await mkdir(srcDir, { recursive: true });
    await writeFile(join(srcDir, 'a.woff2'), 'binary-stand-in-a');
    await writeFile(join(srcDir, 'b-LICENSE.txt'), 'licence text');
    const dstDir = join(root, 'public', 'fonts');

    const { files } = await writeFonts(srcDir, dstDir);

    expect(files).toEqual(['a.woff2', 'b-LICENSE.txt']);
    expect(await readFile(join(dstDir, 'a.woff2'), 'utf8')).toBe('binary-stand-in-a');
    expect(await readFile(join(dstDir, 'b-LICENSE.txt'), 'utf8')).toBe('licence text');
  });

  it('clears a stale file left over from a previous publish', async () => {
    root = await mkdtemp(join(tmpdir(), 'convener-copy-fonts-'));
    const srcDir = join(root, 'fonts');
    await mkdir(srcDir, { recursive: true });
    await writeFile(join(srcDir, 'current.woff2'), 'current');
    const dstDir = join(root, 'public', 'fonts');
    await mkdir(dstDir, { recursive: true });
    await writeFile(join(dstDir, 'retired.woff2'), 'a font nobody self-hosts any more');

    const { files } = await writeFonts(srcDir, dstDir);

    expect(files).toEqual(['current.woff2']);
    await expect(readFile(join(dstDir, 'retired.woff2'), 'utf8')).rejects.toThrow();
  });

  it('reports an empty list for a source directory that does not exist, rather than throwing', async () => {
    root = await mkdtemp(join(tmpdir(), 'convener-copy-fonts-'));
    const dstDir = join(root, 'public', 'fonts');
    const { files } = await writeFonts(join(root, 'does-not-exist'), dstDir);
    expect(files).toEqual([]);
  });

  it('publishes every real file the shared assets/fonts/ directory holds today', async () => {
    // Not a stand-in: the same directory site/.eleventy.js's own
    // passthrough copy and copy-fonts.mjs both read, proving this is a
    // real shared source rather than a path that merely resolves.
    root = await mkdtemp(join(tmpdir(), 'convener-copy-fonts-'));
    const dstDir = join(root, 'public', 'fonts');

    const { files } = await writeFonts(SHARED_FONTS_DIR, dstDir);

    expect(files.length).toBeGreaterThan(0);
    expect(files).toEqual(
      expect.arrayContaining([
        'archivo-latin-standard-normal.woff2',
        'archivo-latin-ext-standard-normal.woff2',
        'jetbrains-mono-latin-400-normal.woff2',
      ]),
    );
  });
});
