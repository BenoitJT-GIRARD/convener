'use strict';

/* Phase 10, task 2: what the showcase's own build actually resolves this
 * project's published address to, printed as JSON for
 * `tools/tests/test_published.py` to compare against the same declaration
 * read from Python.
 *
 * `site/` carries no JS test runner of its own (no new dependency), so
 * this is a plain, dependency-free Node script rather than a spec -- the
 * same arrangement `check-paris-standing-start.cjs` already uses and
 * explains, run the same way, by `subprocess.run(["node", ...])`.
 *
 * Two answers, not one, and the second is the point. `publishedAddress()`
 * is what `scripts/published.cjs` reads out of `config/instance.json`;
 * `pathPrefix` is what `.eleventy.js` -- the real, committed one,
 * `require`d here and *called* with a stub, never read as text -- actually
 * hands Eleventy at the end of its factory. A reader that agreed with the
 * declaration while the build served at a different prefix is exactly the
 * class of defect D-26 exists for, and reading the source of the file
 * instead of running it could not tell the two apart.
 *
 * The stub records nothing: the four registration methods `.eleventy.js`
 * calls (`addPassthroughCopy`, `addFilter`, `addGlobalData`,
 * `addTransform`) have no bearing on the returned configuration object,
 * which is the only thing this script is asking about.
 */

const { publishedAddress } = require('./published.cjs');

const noop = () => {};
const stub = {
  addPassthroughCopy: noop,
  addFilter: noop,
  addGlobalData: noop,
  addTransform: noop,
};

const resolved = require('../.eleventy.js')(stub);

console.log(
  JSON.stringify({
    reader: publishedAddress(),
    eleventyPathPrefix: resolved.pathPrefix,
  })
);
