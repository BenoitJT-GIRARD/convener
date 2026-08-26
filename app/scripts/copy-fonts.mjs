/* Copies `../../fonts` -- the one, shared copy of the self-hosted Archivo
 * and JetBrains Mono files `site/` already serves -- into `public/fonts/`,
 * so the application can declare `@font-face` against a same-origin path
 * instead of requesting them from Google (the
 * application's `tokens.css` and `index.html` both once asked
 * fonts.googleapis.com/fonts.gstatic.com for these faces, on the exact
 * pages -- signup, certificate verification, the survey -- that exist to
 * keep personal data out of third-party hands).
 *
 * Runs before `vite dev` and `vite build`, alongside the other copy
 * scripts. Unlike the signing-key or event-key copies, an absent or empty
 * source here is not a normal state to degrade out of: the repository's
 * own font files disappearing is a broken checkout, not an unconfigured
 * integration, so this fails loudly rather than silently shipping a
 * fontless build.
 */
import { existsSync } from 'node:fs';
import { dirname, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { PUBLIC_FONTS_DIR, writeFonts } from './fonts-files.mjs';

const __dirname = dirname(fileURLToPath(import.meta.url));
const SRC = resolve(__dirname, '..', '..', 'fonts');

if (!existsSync(SRC)) {
  console.error(`copy-fonts: source not found at ${SRC}`);
  process.exit(1);
}

const { files } = await writeFonts(SRC, PUBLIC_FONTS_DIR);

if (files.length === 0) {
  console.error(`copy-fonts: ${SRC} exists but holds no files`);
  process.exit(1);
}

console.log(
  `copy-fonts: copied ${files.length} file(s) -> ${relative(process.cwd(), PUBLIC_FONTS_DIR)}`,
);
