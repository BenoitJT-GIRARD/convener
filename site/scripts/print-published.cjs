'use strict';

/* What the showcase's own build actually resolves this
 * project's published address to, printed as JSON for
 * `tools/tests/declaration/test_published.py` to compare against the same declaration
 * read from Python.
 *
 * `site/` carries no JS test runner of its own (no new dependency), so
 * this is a plain, dependency-free Node script rather than a spec -- the
 * same arrangement `check-paris-standing-start.cjs` already uses and
 * explains, run the same way, by `subprocess.run(["node", ...])`.
 *
 * Two answers, not one, and the second is the point. `publishedAddress()`
 * is what `scripts/published.cjs` reads out of `instance/config.json`;
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

const { publishedAddress, identity } = require('./published.cjs');

const noop = () => {};
// `addGlobalData` is recorded rather than dropped: `site.*` is composed in
// `.eleventy.js` itself, so what the real, committed
// config hands every template is only observable by watching it register
// it. Everything else genuinely has no bearing on the returned object.
const globals = {};
const stub = {
  addPassthroughCopy: noop,
  addFilter: noop,
  addGlobalData: (name, value) => {
    globals[name] = typeof value === 'function' ? value() : value;
  },
  addTransform: noop,
};

const resolved = require('../.eleventy.js')(stub);

console.log(
  JSON.stringify({
    reader: publishedAddress(),
    eleventyPathPrefix: resolved.pathPrefix,
    // Who this side thinks runs the series, and what
    // `.eleventy.js` -- the real, committed config, called here the way
    // Eleventy calls it -- actually registers as the global `site`. Same
    // distinction as `eleventyPathPrefix` above: a reader
    // that agreed with the declaration while the templates were fed
    // something else would look exactly like this passing.
    identity: identity(),
    siteData: globals.site,
  })
);
