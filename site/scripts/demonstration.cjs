// Whether this build of the showcase is the product's own demonstration.
//
// A demonstration is not a second site. It is this site, built from the
// worked example `examples/the-example-collective/` rather than from a
// series somebody runs, and published so that a visitor can click through
// what the software actually does before installing anything. The
// principle it answers to is the maintainer's own: *if the demonstration
// does not have the same structure and the same way of navigating as a
// deployed instance, that is an incoherence.* So this flag is allowed to
// change two things and nothing else:
//
//   * a band above the masthead saying whose records these are, alongside
//     the "not configured" band that already appears there for the same
//     kind of reason;
//   * `?demo=1` on the two links into the cockpit, so that following one
//     from inside the demonstration lands on the demonstration rather
//     than on a sign-in screen -- which is exactly what a visitor met
//     before this existed, and the worst first impression a product whose
//     argument is what it runs can make.
//
// It may not add a page, remove a page, or change where any link goes.
// `tools/tests/repository/test_navigation.py` builds this showcase both
// ways and refuses a page or a link that exists in one build and not in
// the other, so that rule is held rather than remembered.
//
// An environment variable rather than a key of `instance/config.json`,
// and that is the whole reason this file exists instead of a line in
// `published.cjs`: the declaration says who runs a series, and it is
// copied verbatim from `examples/the-example-collective/instance/config.json`
// into the demonstration's own tree. A key there would be a key every
// duplicate inherits and has to know to unset. This is a property of one
// *build*, and it lives where a build's own properties live.
//
// `.cjs` rather than `.js`: `.eleventy.js` is CommonJS and requires this
// at config load time, the same reason `published.cjs` gives for itself.

/** The one variable that turns it on. `tools/scripts/demonstration_build.py`
 *  sets it; nothing else in this repository does. Read by
 *  `tools/tests/repository/test_navigation.py` from this file rather than
 *  spelled a second time there. */
const DEMO_ENV = 'CONVENER_DEMO';

/** What a link into the cockpit carries in a demonstration, and the whole
 *  of what the cockpit needs to be told -- `app/src/data/demo.ts` reads
 *  `?demo=1` off its own address. */
const DEMO_QUERY = '?demo=1';

/** `'1'` and nothing else. A flag that answered to any truthy string would
 *  make an empty variable -- which is what a shell leaves behind for an
 *  unset one it has been asked to forward -- turn a real instance's
 *  publish into a demonstration announcing that nobody on its pages
 *  exists. */
function isDemonstration(env = process.env) {
  return env[DEMO_ENV] === '1';
}

/** `?demo=1` in a demonstration, and the empty string everywhere else.
 *  Appended to a prefixed path in the template rather than composed here:
 *  the prefix comes off Eleventy's own `url` filter, and a whole address
 *  built in this file would have to restate it. */
function cockpitQuery(env = process.env) {
  return isDemonstration(env) ? DEMO_QUERY : '';
}

module.exports = { DEMO_ENV, DEMO_QUERY, isDemonstration, cockpitQuery };
