// The product's own Appropriate Legal Notice -- the showcase's side of it.
//
// `NOTICE.json` at the repository root is the one declaration; this reads it
// for Eleventy, `app/scripts/notice.mjs` reads it for the cockpit's build.
// Two readers of one file, one per side of the language boundary, is the
// arrangement `published.cjs` beside this file already follows for
// `config/instance.json` (D-14). What neither of them holds is a value.
//
// CommonJS and `.cjs` rather than `.js`, for the reason `published.cjs`
// states for itself: `.eleventy.js` is CommonJS and `require`s this at
// config load time.
//
// Why the showcase carries this at all, rather than only the cockpit:
// section 5 of the licence obliges a modified version's interactive
// interfaces to display an Appropriate Legal Notice only where the original's
// do. The showcase is one of this product's two interfaces, so leaving it out
// would leave half the obligation unstated -- and the showcase is the half a
// stranger actually reaches.
//
// Throws rather than defaulting. A page that renders three quarters of a
// notice is not an Appropriate Legal Notice under section 0 of the licence,
// and it is indistinguishable, from the outside, from one that is (D-25).

const { readFileSync } = require('node:fs');
const path = require('node:path');

const DECLARATION = path.join(__dirname, '..', '..', 'NOTICE.json');
const NAMED = 'NOTICE.json';

/** Every key the declaration has to carry, and the whole of it. Exported so
 *  that the check "each of these reaches a rendered page" is a sweep of this
 *  list rather than four assertions somebody has to remember to extend. */
const FIELDS = ['product', 'copyright', 'terms', 'warranty', 'licence_name', 'licence_url'];

/** The notice, as the fields a template prints. */
function notice() {
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
          'notice is displayed, and a page missing one of them displays no ' +
          'Appropriate Legal Notice at all'
      );
    }
    out[field] = value;
  }
  return out;
}

module.exports = { notice, FIELDS };
