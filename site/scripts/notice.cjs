// The product's own Appropriate Legal Notice -- the showcase's side of it.
//
// `NOTICE.json` at the repository root is the one declaration; this reads it
// for Eleventy, `app/scripts/notice.mjs` reads it for the cockpit's build.
// Two readers of one file, one per side of the language boundary, is the
// arrangement `published.cjs` beside this file already follows for
// `instance/config.json` (D-14). What neither of them holds is a value.
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

const INSTANCE_DECLARATION = path.join(__dirname, '..', '..', 'instance', 'config.json');
const INSTANCE_NAMED = 'instance/config.json';

/** Every key the declaration has to carry, and the whole of it. Exported so
 *  that the check "each of these reaches a rendered page" is a sweep of this
 *  list rather than four assertions somebody has to remember to extend. */
const FIELDS = ['product', 'copyright', 'terms', 'warranty', 'licence_name', 'licence_url'];

/** The two names an instance gives the thing it is running, in the order a
 *  duplicate is likeliest to have reached for one of them.
 *
 *  `product` is the one field of this notice a duplicate is ever tempted to
 *  edit, and `TRADEMARK.md` told it, in as many words, to put the *series'*
 *  name there. That is the inversion read for below: `_includes/layout.njk`
 *  prints `product` against `copyright`, which sections 4 and 5 oblige a
 *  duplicate to keep, so a series' name in `product` publishes somebody
 *  else's copyright over that series -- while the masthead in the same
 *  template has been printing `identity.organisation` and `identity.series`
 *  at the top of every page all along. A sentence alone was not enough:
 *  its own author misread it. */
const INSTANCE_NAMES = ['series', 'organisation'];

/** Which of those names `product` has been set to, or `null` for a notice
 *  naming the software rather than the series running on it.
 *
 *  Pure, and given both sides already in hand, so the refusal can be proved
 *  against declarations this repository does not ship -- the shape
 *  `app/scripts/published.mjs::unconfiguredFrom` is split out of its own
 *  file reader for. Trimmed and case-folded, because a name set in another
 *  case is the same name and what this refuses is not a typo. */
function namesTheInstance(product, declared) {
  const asked = String(product).trim().toLowerCase();
  if (asked === '') return null;
  for (const field of INSTANCE_NAMES) {
    const value = declared[field];
    if (typeof value === 'string' && value.trim().toLowerCase() === asked) {
      return field;
    }
  }
  return null;
}

/** What this instance declares itself called, raw.
 *
 *  Raw rather than through `published.cjs::identity()`, deliberately: the
 *  question is about the text somebody typed, and it has to stay answerable
 *  for a declaration that reader would refuse over an unrelated field --
 *  the same reading `published.cjs::declaredValues` takes, for the same
 *  reason. Throws when the file cannot be read at all: with nothing to
 *  compare against, nothing is proved, and a check that reports "fine"
 *  when it could not run is D-25's own definition of not being one. */
function instanceNames() {
  let declaration;
  try {
    declaration = JSON.parse(readFileSync(INSTANCE_DECLARATION, 'utf8'));
  } catch (err) {
    throw new Error(
      `${INSTANCE_NAMED} cannot be read (${err.message}), so nothing can tell ` +
        `${NAMED}'s product apart from the name of the series running on it -- ` +
        'restore it rather than publish a notice nothing was able to check'
    );
  }
  const raw =
    declaration === null || typeof declaration !== 'object' ? null : declaration.identity;
  const found = {};
  if (raw !== null && typeof raw === 'object') {
    for (const field of INSTANCE_NAMES) {
      const value = raw[field];
      if (typeof value === 'string') found[field] = value;
    }
  }
  return found;
}

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
  const taken = namesTheInstance(out.product, instanceNames());
  if (taken !== null) {
    throw new Error(refusal(out.product, taken));
  }
  return out;
}

/** What a duplicate that put its series' name in `product` is told, and why
 *  the message is a function rather than a string built where it is thrown:
 *  `app/scripts/notice.mjs` refuses the same declaration on the other side
 *  of the language boundary, and the two are held to one word by
 *  `tools/tests/repository/test_notice.py`. */
function refusal(product, field) {
  return (
    `${NAMED}: product is ${JSON.stringify(product)}, which is what ` +
    `${INSTANCE_NAMED} declares as identity.${field}. product names the ` +
    'software, never the series running on it: the footer prints it against ' +
    'the copyright line sections 4 and 5 of the licence oblige you to keep, so ' +
    "a series' name here hangs somebody else's copyright on your series -- and " +
    'the masthead prints identity.organisation and identity.series already. ' +
    'Leave product naming the software you are actually running, and change it ' +
    'only once you have modified that software into a product of your own ' +
    '(TRADEMARK.md).'
  );
}

module.exports = { notice, FIELDS, INSTANCE_NAMES, namesTheInstance, refusal };
