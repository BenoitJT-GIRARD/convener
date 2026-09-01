// The one address this project is published at, read from
// `instance/config.json` -- the showcase's side of it.
//
// `tools/convener_ops/declaration/published.py` is Python's reader of the same file and
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
// There is deliberately no reader here for the declaration's third key,
// `edition_prefix`. This build never composes an
// edition code: it prints the ones `src/_data/events.json` hands it, and
// lower-cases them for the event page's own permalink (D-19). A reader
// nothing called would be a third statement of a rule with two
// consumers -- `tools/convener_ops/declaration/published.py` for the validator and the
// jobs, `app/scripts/published.mjs` for the cockpit's own build, bound to
// each other by `tools/tests/fixtures/edition-prefix.json`.
//
// The unconfigured banner does not change that, and the distinction is
// worth keeping: `unconfigured` at the foot of this file reads the key, but only
// to compare the string against the example's. It derives nothing from it,
// validates nothing about it and hands it to no template -- which is what
// "no reader here" means.
//
// Throws rather than defaulting: a build that cannot read this file must
// stop. Every internal link the showcase emits is resolved against the
// prefix below, and a missing one resolves to the *domain* root -- one
// path segment above where this project is actually served, invisible on
// a bare `localhost` and total once published (D-26).

const { readFileSync } = require('node:fs');
const path = require('node:path');

const DECLARATION = path.join(__dirname, '..', '..', 'instance', 'config.json');
const NAMED = 'instance/config.json';

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
  const suffix = '.github.io';
  const segments = parsed.pathname.split('/').filter(Boolean);
  return {
    // The whole address, trailing slash included.
    url,
    // `https://host`, no path -- what a link leaving this document for a
    // context with no address of its own has to carry.
    origin: parsed.origin,
    // `/repository/` -- Eleventy's own `pathPrefix` takes exactly this
    // shape, leading and trailing slash included.
    pathPrefix: parsed.pathname,
    // `owner/repository` -- where the built site is pushed, derived rather
    // than declared. GitHub Pages serves a project repository at
    // `https://<owner>.github.io/<repository>/` and nowhere else, so the
    // address is the push target spelled differently. Mirrors
    // `published.py::Published.publish_repository`, refusal included: a
    // custom domain says nothing about which repository serves it, and
    // there is no safe guess for where to push a whole site.
    get publishRepository() {
      if (!parsed.host.endsWith(suffix) || parsed.host.length <= suffix.length || segments.length !== 1) {
        throw new Error(
          `${NAMED}: ${url} is not a GitHub Pages project address ` +
            '(https://<owner>.github.io/<repository>/), so the repository the ' +
            'built site is pushed into cannot be derived from it'
        );
      }
      return `${parsed.host.slice(0, -suffix.length)}/${segments[0]}`;
    },
  };
}

// Who runs this series, and what it is called -- the other half of the
// same declaration, read the same way. `tools/convener_ops/declaration/published.py::
// load_identity` is Python's reader of it and `app/scripts/published.mjs::
// identity` the application build's.
//
// `site/.eleventy.js` is this side's one consumer: the four keys the
// showcase's templates read as `site.*` used to be a file of their own
// (`site/src/_data/site.json`), which was clean and was still a second
// home for the same notion -- the series' title there, the organisation's
// name in a hundred and fifty other places, free to disagree the day
// either moved. There is one now, and this is how the showcase reaches
// it.
//
// The checks mirror `published.py::identity_from_data` clause for clause.
// Every field is prose somebody outside this project reads, so a missing
// one stops the build rather than rendering the word "undefined" onto a
// public page.
const IDENTITY_FIELDS = [
  'organisation',
  'short_name',
  'series',
  'strapline',
  'tagline',
  'forum',
  'contact',
  'proposal_form',
  'repository',
];

// What this repository writes into a declared value nobody has filled in
// yet -- the same token `services/*/wrangler.toml` carries as
// `REPLACE_WITH_KV_NAMESPACE_ID` and the two relay deploys already grep
// for before deciding an integration is configured. Mirrors
// `published.py::PLACEHOLDER_MARKER` and `DEGRADABLE_FIELDS`: a
// placeholder is refused in every field the showcase has no fallback for,
// and tolerated in the one it does (`proposal_form` -- `/propose/` sends
// a visitor to the contact address instead, rather than to a link that
// resolves to nothing).
const PLACEHOLDER_MARKER = 'REPLACE';
const DEGRADABLE_FIELDS = ['proposal_form'];

function isPlaceholder(value) {
  return value.includes(PLACEHOLDER_MARKER);
}

function identity() {
  const declaration = JSON.parse(readFileSync(DECLARATION, 'utf8'));
  if (declaration.v !== 1) {
    throw new Error(`${NAMED} is not a supported format version`);
  }
  const raw = declaration.identity;
  if (raw === null || typeof raw !== 'object') {
    throw new Error(`${NAMED}: identity must be an object naming this instance`);
  }
  const out = {};
  for (const field of IDENTITY_FIELDS) {
    const value = raw[field];
    if (typeof value !== 'string' || value.trim() !== value || value === '') {
      throw new Error(
        `${NAMED}: identity.${field} must be a non-empty string, got ${value} -- ` +
          'every field here is printed to somebody outside this project'
      );
    }
    if (isPlaceholder(value) && !DEGRADABLE_FIELDS.includes(field)) {
      throw new Error(
        `${NAMED}: identity.${field} is still a placeholder (${value}) -- ` +
          `${PLACEHOLDER_MARKER} is how this repository writes a value nobody ` +
          'has filled in, and there is nothing to print in place of this one'
      );
    }
    out[field] = value;
  }
  // `www.example.org` -- the forum's address as prose names it, with no
  // scheme, derived so a duplicate never writes its forum down twice.
  out.forum_host = new URL(out.forum).host;
  return out;
}

// Whether this instance is still publishing the identity the *product*
// ships as its worked example -- `tools/convener_ops/declaration/published.py::
// unconfigured` is Python's answer to the same question and
// `app/scripts/published.mjs::unconfigured` the cockpit build's, mirrored
// here clause for clause like everything else in this file.
//
// The whole argument is stated once, in `published.py::unconfigured`'s own
// docstring: what counts as unconfigured, why it is a value-by-value
// comparison and not a file-against-file one, and why the `REPLACE` marker
// deliberately decides nothing here. What this side adds is the surface:
// `.eleventy.js` hands the result to every template as `site.unconfigured`
// and `_includes/layout.njk` prints a banner across every page of the
// showcase while it is not empty. A duplicate deployed before it was
// configured says so where a visitor reads it, rather than publishing the
// template's organisation, address and contact under its own roof in
// silence.
const EXAMPLE_DECLARATION = path.join(
  __dirname,
  '..',
  '..',
  'examples',
  'the-example-collective',
  'instance',
  'config.json'
);
const EXAMPLE_NAMED = 'examples/the-example-collective/instance/config.json';

/** The eleven values a declaration carries about *who* is publishing,
 *  under the declaration's own names. Raw, deliberately: the question is
 *  about the text somebody typed, and it has to stay answerable for a
 *  declaration `identity()` above would refuse. Mirrors
 *  `published.py::declared_values`. */
function declaredValues(declaration) {
  const values = {};
  if (declaration === null || typeof declaration !== 'object') return values;
  for (const key of ['published_url', 'edition_prefix']) {
    const value = declaration[key];
    if (typeof value === 'string' && value !== '') values[key] = value;
  }
  const raw = declaration.identity;
  if (raw !== null && typeof raw === 'object') {
    for (const field of IDENTITY_FIELDS) {
      const value = raw[field];
      if (typeof value === 'string' && value !== '') values[`identity.${field}`] = value;
    }
  }
  return values;
}

/** Which declared values are still the example's, sorted and named.
 *  Throws rather than answering "configured" when the example cannot be
 *  read: with nothing to compare against nothing can be proved, and a
 *  check that says "fine" when it could not run is D-25's own definition
 *  of not being one. */
function unconfigured() {
  let example;
  try {
    example = JSON.parse(readFileSync(EXAMPLE_DECLARATION, 'utf8'));
  } catch (err) {
    throw new Error(
      `${EXAMPLE_NAMED} cannot be read (${err.message}), so there is nothing to ` +
        "tell this instance's declaration apart from the example the product " +
        'ships -- restore it rather than publish a page that cannot say whether ' +
        'it is configured'
    );
  }
  const ours = declaredValues(JSON.parse(readFileSync(DECLARATION, 'utf8')));
  const theirs = declaredValues(example);
  return Object.keys(ours)
    .filter((name) => theirs[name] === ours[name])
    .sort();
}

module.exports = { publishedAddress, identity, isPlaceholder, unconfigured };
