/**
 * The one address this project is published at, read from
 * `config/instance.json` -- this build's side of it.
 *
 * `tools/convener_ops/published.py` is Python's reader of the same file and
 * `site/scripts/published.cjs` the showcase's. Three readers of one
 * declaration, one per side of the language boundary, is D-14 applied
 * literally; three *copies* of the address is the defect it replaces,
 * and the difference is that none of these three holds a value.
 *
 * Read at Vite config load time, in Node, with `node:fs` -- a build
 * configuration genuinely can read a file, so this is a real derivation
 * and not a comment claiming one. `vite.config.ts` uses it twice: for
 * every `base` (the main cockpit build and the three islands, which must
 * agree -- an island publishing under a different base 404s its own
 * fetches once served from the real deployment) and for the one value
 * that has to survive into the browser, injected through Vite's own
 * `define` as `import.meta.env.VITE_PUBLISHED_URL`, because
 * `src/content/render.ts` computes a public registration link inside a
 * volunteer's browser, where no file can be read at all.
 *
 * Throws rather than defaulting. A build that cannot read this file must
 * stop: every asset URL in its output would otherwise be resolved
 * against a root this project is not served from, which is invisible on
 * a bare `localhost` and total once published (D-26).
 */

import { readFileSync } from 'node:fs';

/** `config/instance.json`, from this file's own location -- the app's
 *  build runs with `app/` as its working directory, so a path relative
 *  to the process is not the same thing. */
const DECLARATION = new URL('../../config/instance.json', import.meta.url);

const NAMED = 'config/instance.json';

/**
 * The published address and the parts of the build that need it.
 *
 * The checks below mirror `published.py::from_data` clause for clause,
 * and deliberately so: each one is a shape that reads plausible and
 * publishes wrong. A missing trailing slash eats a path segment the
 * moment anything is appended; a bare origin with no path publishes at a
 * domain root this project does not own.
 */
export function published() {
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
    /** The whole address, trailing slash included. */
    url,
    /** `https://host`, no path -- what a browser sends as `Origin`. */
    origin: parsed.origin,
    /** `/repository/` -- the one path segment GitHub Pages serves a
     *  project repository under, leading and trailing slash included. */
    pathPrefix: parsed.pathname,
    /** `/repository/app/` -- Vite's own `base`: a path, not an absolute
     *  URL, which is what that option means. */
    appBase: `${parsed.pathname}app/`,
  };
}

/**
 * Who runs this series, and what it is called -- the other half of the
 * same declaration, read the same way.
 * `tools/convener_ops/published.py::load_identity` is Python's reader of it
 * and `site/scripts/published.cjs::identity` the showcase's.
 *
 * `vite.config.ts` injects the result into every bundle through Vite's
 * own `define`, for the reason it already injects the published address:
 * `src/content/render.ts` resolves the `{{ instance.* }}` namespace
 * inside a volunteer's browser, where no file can be read at all, and
 * the same names appear in the cockpit's own chrome.
 *
 * The checks mirror `published.py::identity_from_data` clause for
 * clause. Every field is prose somebody outside this project reads, so a
 * missing one stops the build rather than shipping the word "undefined"
 * into an e-mail a speaker is about to be sent.
 */
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

/** What this repository writes into a declared value nobody has filled in
 *  yet -- the same token the two relays' own `wrangler.toml` files carry
 *  as `REPLACE_WITH_KV_NAMESPACE_ID`. Mirrors
 *  `published.py::PLACEHOLDER_MARKER` and `DEGRADABLE_FIELDS`, clause for
 *  clause like everything else here: refused in every field there is
 *  nothing to print in place of, tolerated in the one the showcase has a
 *  fallback for. This build never renders `proposal_form` -- it only
 *  carries it into the bundle's identity define -- so there is nothing to
 *  derive here, only something to refuse. */
const PLACEHOLDER_MARKER = 'REPLACE';
const DEGRADABLE_FIELDS = ['proposal_form'];

export function identity() {
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
    if (value.includes(PLACEHOLDER_MARKER) && !DEGRADABLE_FIELDS.includes(field)) {
      throw new Error(
        `${NAMED}: identity.${field} is still a placeholder (${value}) -- ` +
          `${PLACEHOLDER_MARKER} is how this repository writes a value nobody ` +
          'has filled in, and there is nothing to print in place of this one'
      );
    }
    out[field] = value;
  }
  /** `www.example.org` -- the forum's address as prose names it, with no
   *  scheme, derived so a duplicate never writes its forum down twice. */
  out.forum_host = new URL(out.forum).host;
  return out;
}

/**
 * The prefix this instance numbers its editions under -- the third part
 * of the same declaration, read the same way.
 * `tools/convener_ops/published.py::load_edition_prefix` is Python's reader of
 * it, and `EDITION_PREFIX_RE` there is the same expression as below.
 *
 * The showcase has no reader of its own for this and needs none: it
 * prints the edition codes `site/src/_data/events.json` hands it and
 * never composes one. This build does compose one -- `src/state/agenda.
 * ts::nextEditionCode` suggests the next code inside a volunteer's
 * browser, where no file can be read -- so `vite.config.ts` carries the
 * value into every bundle through its own `define`, exactly as it
 * already does for the address and the identity.
 *
 * Upper case, ASCII, a letter first, at most eight characters and no
 * separator of its own: an event id is the edition code lower-cased
 * (D-19), so the case has to be fixed here for the two to stay one
 * identifier, and `eventkeys.secret_name` folds any further `.` or `-`
 * into `_`, which would give two editions one repository secret. See
 * `published.py::EDITION_PREFIX_RE` for the whole argument, stated once
 * against the place each restriction comes from.
 */
const EDITION_PREFIX_MAX_LENGTH = 8;
const EDITION_PREFIX_RE = new RegExp(`^[A-Z][A-Z0-9]{0,${EDITION_PREFIX_MAX_LENGTH - 1}}$`);

/** Whether `value` is a prefix this product will number editions under.
 *  Exported so the boundary is a worked example rather than a claim:
 *  `tools/tests/fixtures/edition-prefix.json` holds the cases and both
 *  sides answer them -- `app/tests/edition-prefix.test.ts` here,
 *  `tools/tests/test_published.py` against `EDITION_PREFIX_RE` there. A
 *  prefix the build accepts and the validator refuses is a repository
 *  that can be built and cannot be validated. */
export function isEditionPrefix(value) {
  return typeof value === 'string' && EDITION_PREFIX_RE.test(value);
}

export function editionPrefix() {
  const declaration = JSON.parse(readFileSync(DECLARATION, 'utf8'));
  if (declaration.v !== 1) {
    throw new Error(`${NAMED} is not a supported format version`);
  }
  const value = declaration.edition_prefix;
  if (typeof value !== 'string' || value === '') {
    throw new Error(
      `${NAMED}: edition_prefix must be the prefix this instance numbers its ` +
        `editions under, got ${value} -- it is the first half of every edition ` +
        'code, of every event page address and of every certificate issued under it'
    );
  }
  if (!isEditionPrefix(value)) {
    throw new Error(
      `${NAMED}: edition_prefix must be ${EDITION_PREFIX_MAX_LENGTH} ASCII ` +
        `capitals or digits at most, starting with a letter, got ${value} -- an ` +
        'event id is the edition code lower-cased (D-19), and the product puts ' +
        'the one hyphen an edition code has between this and the number'
    );
  }
  return value;
}

/**
 * Whether this instance is still publishing the identity the *product*
 * ships as its worked example.
 *
 * `tools/convener_ops/published.py::unconfigured` is Python's answer to the
 * same question and `site/scripts/published.cjs::unconfigured` the
 * showcase build's; the whole rule is stated once in the first of those
 * -- what counts as unconfigured, why it is a value-by-value comparison
 * and not a file-against-file one, and why the `REPLACE` marker
 * deliberately decides nothing here.
 *
 * What this side adds is the cockpit's own surface. `vite.config.ts`
 * carries the result into every bundle through Vite's own `define`, for
 * the reason it already carries the address and the identity: the chrome
 * that has to print the warning runs in a browser, which can read no
 * file. `src/components/UnconfiguredBanner.tsx` is what prints it, above
 * the sign-in screen a visitor lands on and above the cockpit itself.
 */
const EXAMPLE_DECLARATION = new URL(
  '../../instances/example/config/instance.json',
  import.meta.url
);
const EXAMPLE_NAMED = 'instances/example/config/instance.json';

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
 *  read, the same rule `example-instance.mjs` already applies to the same
 *  directory: with nothing to compare against nothing can be proved, and
 *  a check that says "fine" when it could not run is D-25's own
 *  definition of not being one. */
export function unconfigured() {
  let example;
  try {
    example = JSON.parse(readFileSync(EXAMPLE_DECLARATION, 'utf8'));
  } catch (err) {
    throw new Error(
      `${EXAMPLE_NAMED} cannot be read (${err.message}), so there is nothing to ` +
        "tell this instance's declaration apart from the example the product " +
        'ships -- restore it rather than build a cockpit that cannot say ' +
        'whether it is configured'
    );
  }
  const ours = declaredValues(JSON.parse(readFileSync(DECLARATION, 'utf8')));
  const theirs = declaredValues(example);
  return Object.keys(ours)
    .filter((name) => theirs[name] === ours[name])
    .sort();
}
