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

const INSTANCE_DECLARATION = new URL('../../instance/config.json', import.meta.url);
const INSTANCE_NAMED = 'instance/config.json';

/** Every key the declaration has to carry, and the whole of it. Exported so
 *  the browser-side reader can hold the shape it is handed against this list
 *  rather than against a second spelling of it. */
export const FIELDS = ['product', 'copyright', 'terms', 'warranty', 'licence_name', 'licence_url'];

/** The two names an instance gives the thing it is running, in the order a
 *  duplicate is likeliest to have reached for one of them.
 *
 *  `product` is the one field of this notice a duplicate is ever tempted to
 *  edit, and `TRADEMARK.md` told it, in as many words, to put the *series'*
 *  name there. That is the inversion read for below: both footers print
 *  `product` against `copyright`, which sections 4 and 5 oblige a duplicate
 *  to keep, so a series' name in `product` publishes somebody else's
 *  copyright over that series -- while the showcase's masthead has been
 *  printing `identity.organisation` and `identity.series` at the top of
 *  every page all along. A sentence alone was not enough: its own author
 *  misread it. */
export const INSTANCE_NAMES = ['series', 'organisation'];

/** Which of those names `product` has been set to, or `null` for a notice
 *  naming the software rather than the series running on it.
 *
 *  Pure, and given both sides already in hand, so the refusal can be proved
 *  against declarations this repository does not ship -- the shape
 *  `published.mjs::unconfiguredFrom` beside this file is split out of its
 *  own file reader for. Trimmed and case-folded, because a name set in
 *  another case is the same name and what this refuses is not a typo. */
export function namesTheInstance(product, declared) {
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
 *  Raw rather than through `published.mjs::identity()`, deliberately: the
 *  question is about the text somebody typed, and it has to stay answerable
 *  for a declaration that reader would refuse over an unrelated field --
 *  the same reading `published.mjs::declaredValues` takes, for the same
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
        'restore it rather than publish a notice nothing was able to check',
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

/** What a duplicate that put its series' name in `product` is told, and why
 *  the message is a function rather than a string built where it is thrown:
 *  `site/scripts/notice.cjs` refuses the same declaration on the other side
 *  of the language boundary, and the two are held to one word by
 *  `tools/tests/repository/test_notice.py`. */
export function refusal(product, field) {
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
  const taken = namesTheInstance(out.product, instanceNames());
  if (taken !== null) {
    throw new Error(refusal(out.product, taken));
  }
  return out;
}
