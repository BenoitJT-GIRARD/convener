'use strict';

/* D-14: the shared cross-language fixture for the Europe/Paris
 * seasonal-offset rule (`tools/tests/fixtures/paris-standing-start.json`),
 * checked here against `.eleventy.js::parisStandingStart` -- the third of
 * three independent implementations of the identical rule
 * (`tools/convener_ops/publication/visual.py::paris_standing_start` and `app/src/state/
 * derived.ts::parisStandingStart` are the other two, each checked against
 * the same file from its own test suite: `tools/tests/
 * test_paris_standing_start_fixture.py`, `app/tests/announce-drafts.test.ts`).
 *
 * `site/` carries no JS test runner of its own (no new dependency), so this
 * is a plain, dependency-free Node script rather than a jest/vitest spec --
 * exit-code driven the same way `render-and-compare.mjs`'s own file-count
 * guard is for a build failure. Run from `tools/tests/
 * test_paris_standing_start_fixture.py::test_eleventy_js_matches_the_
 * shared_fixture` via `subprocess.run(["node", ...])`, the same way that
 * suite's own `built_site` fixture already invokes Eleventy's CLI directly.
 *
 * `.eleventy.js` has no full "date line" sentence of its own -- the
 * weekday/month wrapping around the offset is Nunjucks-side, already
 * covered by `test_site.py`'s own RFC-822/JSON-LD assertions -- so this
 * script checks only the one function `.eleventy.js` actually owns:
 * `startDate`'s UTC offset and the visible "12:30 CET"/"12:30 CEST" label.
 */

const { readFileSync } = require('node:fs');
const path = require('node:path');
const { parisStandingStart } = require('../.eleventy.js');

const fixturePath = path.join(
  __dirname,
  '..',
  '..',
  'tools',
  'tests',
  'fixtures',
  'paris-standing-start.json',
);
const cases = JSON.parse(readFileSync(fixturePath, 'utf8'));

let failures = 0;
for (const testCase of cases) {
  const isoDate = testCase.iso_date;
  const { offset, abbreviation } = testCase;
  const { startDate, label } = parisStandingStart(isoDate);
  const expectedStart = `${isoDate}T12:30:00${offset}`;
  const expectedLabel = `12:30 ${abbreviation}`;
  if (startDate !== expectedStart) {
    console.error(`${isoDate}: startDate ${startDate} !== expected ${expectedStart}`);
    failures += 1;
  }
  if (label !== expectedLabel) {
    console.error(`${isoDate}: label ${label} !== expected ${expectedLabel}`);
    failures += 1;
  }
}

if (failures > 0) {
  console.error(`paris-standing-start fixture: ${failures} mismatch(es) of ${cases.length} case(s)`);
  process.exit(1);
}
console.log(`paris-standing-start fixture: ${cases.length} case(s) OK`);
