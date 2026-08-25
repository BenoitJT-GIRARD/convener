// The one address this project is published at, read from
// `config/instance.json` -- the showcase's side of it.
//
// `tools/convener_ops/published.py` is Python's reader of the same file and
// `app/scripts/published.mjs` the application build's. Three readers of
// one declaration, one per side of the language boundary, is D-14 applied
// literally; three *copies* of the address is the defect it replaces, and
// the difference is that none of these three holds a value.
//
// CommonJS, and `.cjs` rather than `.js`: `.eleventy.js` is CommonJS (this
// package.json carries no "type": "module") and `require`s this at config
// load time, while `check-a11y.mjs` and `check-performance-budget.mjs` are
// ES modules and import it as a default. `.cjs` is the one extension both
// can reach without either of them being rewritten -- the same reasoning
// `check-paris-standing-start.cjs` already states for itself.
//
// Before this, those two checkers read `PATH_PREFIX` back out of
// `.eleventy.js` with a regular expression, because that was where the
// prefix was written down. It no longer is, and a checker scraping the
// source of the file that reads the declaration would be one indirection
// further from the answer for no gain.
//
// Throws rather than defaulting: a build that cannot read this file must
// stop. Every internal link the showcase emits is resolved against the
// prefix below, and a missing one resolves to the *domain* root -- one
// path segment above where this project is actually served, invisible on
// a bare `localhost` and total once published (D-26).

const { readFileSync } = require('node:fs');
const path = require('node:path');

const DECLARATION = path.join(__dirname, '..', '..', 'config', 'instance.json');
const NAMED = 'config/instance.json';

// The checks mirror `published.py::from_data` clause for clause, and
// deliberately so: each one is a shape that reads plausible and publishes
// wrong.
function publishedAddress() {
  const declaration = JSON.parse(readFileSync(DECLARATION, 'utf8'));
  if (declaration.v !== 1) {
    throw new Error(`${NAMED} is not a supported format version`);
  }
  const url = declaration.published_url;
  if (typeof url !== 'string' || url.trim() !== url || url === '') {
    throw new Error(`${NAMED}: published_url must be this project's address, got ${url}`);
  }
  const parsed = new URL(url);
  if (parsed.protocol !== 'https:') {
    throw new Error(`${NAMED}: published_url must be an https address, got ${url}`);
  }
  if (parsed.search || parsed.hash) {
    throw new Error(
      `${NAMED}: published_url carries a query or a fragment (${url}) -- it is ` +
        'the root every other address is built on, and nothing can be appended after either'
    );
  }
  if (!parsed.pathname.endsWith('/')) {
    throw new Error(
      `${NAMED}: published_url must end in '/' (${url}) -- every address derived ` +
        'from it is built by appending, so a missing slash quietly eats a path segment'
    );
  }
  return {
    // The whole address, trailing slash included.
    url,
    // `https://host`, no path -- what a link leaving this document for a
    // context with no address of its own has to carry.
    origin: parsed.origin,
    // `/repository/` -- Eleventy's own `pathPrefix` takes exactly this
    // shape, leading and trailing slash included.
    pathPrefix: parsed.pathname,
  };
}

module.exports = { publishedAddress };
