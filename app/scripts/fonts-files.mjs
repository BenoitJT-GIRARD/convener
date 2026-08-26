/* Which font files `copy-fonts.mjs` publishes, and where -- kept apart from
 * the copy script itself, the same reason `signing-keys-files.mjs` is kept
 * apart from `copy-signing-keys.mjs`: a rule `app/tests/copy-fonts.test.ts`
 * can call directly, rather than one only ever exercised by running the
 * whole script against the real `fonts/` tree.
 *
 * `fonts/` at the repository root is the one committed copy of these files.
 * The designer's own faces (Akzidenz-Grotesk, Neue Machina) are commercial;
 * Archivo and JetBrains Mono are the self-hosted substitutes D-17 requires
 * instead of a webfont request, which discloses every visitor's address.
 * `site/` already serves this same directory (`site/.eleventy.js`'s own
 * passthrough copy, `{'../fonts': 'fonts'}`); this is the application's
 * side of that one shared source -- the
 * application once kept no copy of its own at all and asked Google for these
 * faces instead, on the exact pages (signup, certificate verification, the
 * survey) that exist to keep personal data out of third-party hands.
 */
import { existsSync } from 'node:fs';
import { cp, mkdir, readdir, rm } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

/** `app/public/fonts/`, computed from this file's own location rather than
 *  `process.cwd()` -- the exact directory `src/design/tokens.css`'s
 *  `@font-face` rules reference at `/fonts/...`. */
export const PUBLIC_FONTS_DIR = resolve(
  dirname(fileURLToPath(import.meta.url)),
  '..',
  'public',
  'fonts',
);

/**
 * Every file directly under `srcDir`, copied verbatim into `dstDir`.
 *
 * `dstDir` is cleared first (removed and recreated), so a font retired
 * from `srcDir` does not linger in the published bundle -- the same
 * discipline `writeSigningKeys` applies to `public/keys/signing/`. Unlike
 * that copy, an absent or empty `srcDir` is not treated as a normal state
 * to degrade out of here: this function still reports it faithfully
 * (`files: []`) so it can be tested in isolation, but `copy-fonts.mjs`,
 * the script that actually runs before a build, fails loudly on it --
 * the repository's own font files disappearing is a broken checkout, not
 * an unconfigured integration.
 */
export async function writeFonts(srcDir, dstDir) {
  if (existsSync(dstDir)) await rm(dstDir, { recursive: true });
  await mkdir(dstDir, { recursive: true });

  if (!existsSync(srcDir)) return { files: [] };

  const entries = await readdir(srcDir, { withFileTypes: true });
  const files = entries
    .filter(entry => entry.isFile())
    .map(entry => entry.name)
    .sort();
  for (const name of files) {
    await cp(join(srcDir, name), join(dstDir, name));
  }
  return { files };
}
