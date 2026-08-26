/**
 * The product's own Appropriate Legal Notice -- the cockpit build's side of
 * it.
 *
 * `NOTICE.json` at the repository root is the one declaration;
 * `site/scripts/notice.cjs` reads it for the showcase's Eleventy build and
 * this reads it for `vite.config.ts`, which carries the result into every
 * bundle as a define. The cockpit's footer runs in a browser, where no file
 * can be read at all, exactly as the instance's identity already does.
 *
 * Why the cockpit carries it as well as the showcase: section 5 of the
 * licence obliges a modified version's interactive interfaces to display an
 * Appropriate Legal Notice wherever the original's do. Two interfaces, two
 * notices, or the obligation only covers one of them.
 *
 * Throws rather than defaulting, the rule `published.mjs` beside this file
 * already follows: three quarters of a notice is not an Appropriate Legal
 * Notice under section 0 of the licence, and from the outside it looks
 * exactly like one that is (D-25).
 */
import { readFileSync } from 'node:fs';

/** This repository's own root, from this file's location -- the app's build
 *  runs with `app/` as its working directory, so a path relative to the
 *  process is not the same thing. */
const DECLARATION = new URL('../../NOTICE.json', import.meta.url);
const NAMED = 'NOTICE.json';

/** Every key the declaration has to carry, and the whole of it. Exported so
 *  the browser-side reader can hold the shape it is handed against this list
 *  rather than against a second spelling of it. */
export const FIELDS = ['product', 'copyright', 'terms', 'warranty', 'licence_name', 'licence_url'];

/** The notice, as the fields the footer prints. */
export function notice() {
  const declaration = JSON.parse(readFileSync(DECLARATION, 'utf8'));
  if (declaration.v !== 1) {
    throw new Error(`${NAMED} is not a supported format version`);
  }
  const out = {};
  for (const field of FIELDS) {
    const value = declaration[field];
    if (typeof value !== 'string' || value.trim() === '') {
      throw new Error(
        `${NAMED}: ${field} must be a non-empty string -- every field of the ` +
          'notice is displayed, and a bundle missing one of them displays no ' +
          'Appropriate Legal Notice at all',
      );
    }
    out[field] = value;
  }
  return out;
}
