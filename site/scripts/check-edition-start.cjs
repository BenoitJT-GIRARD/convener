'use strict';

/* D-14: the shared cross-language fixture for "an edition's start hour comes
 * off its own record, falling back to the series' standing hour"
 * (`tools/tests/fixtures/edition-start.json`), checked here against
 * `.eleventy.js::eventStartLocal` -- the third of three independent
 * implementations of the identical rule
 * (`tools/convener_ops/publication/visual.py::start_local` and
 * `app/src/state/derived.ts::startLocal` are the other two, each checked
 * against the same file from its own test suite:
 * `tools/tests/repository/test_edition_start_fixture.py`,
 * `app/tests/content/announce-drafts.test.ts`).
 *
 * A separate fixture and a separate script from `check-paris-standing-
 * start.cjs` beside it, deliberately: that one binds the Europe/Paris
 * *seasonal* rule and needs dates either side of both DST transitions in two
 * years to do it, while this one binds *where the hour comes from* and needs
 * recorded hours above, below and equal to the convention, plus the blank.
 * Folding the two together would have made one list that proved each thing
 * half as well, and the arithmetic justifying either list's size would have
 * stopped holding.
 *
 * Why the rule needs binding at all: this build hard-typed the standing
 * 12:30 until `time` became a published column, and an edition the record
 * held at 18:00 was published, labelled, syndicated and calendared at 12:30.
 * Three languages now read the record instead, and a change to the rule in
 * any one of them has to break the other two.
 *
 * `site/` carries no JS test runner of its own (no new dependency), so this
 * is a plain, dependency-free Node script rather than a jest/vitest spec --
 * exit-code driven, run from
 * `test_edition_start_fixture.py::test_eleventy_js_matches_the_shared_fixture`
 * via `subprocess.run(["node", ...])`.
 *
 * `eventStartLocal` takes the whole row, which is the point of its
 * signature: a Nunjucks pipe carries one value, so a filter over
 * `event.date` could not be handed the hour and every template that used one
 * stated the convention. The cases below are therefore applied as rows, the
 * same shape `events.json` holds.
 */

const { readFileSync } = require('node:fs');
const path = require('node:path');
const { eventStartLocal, parisStandingStart } = require('../.eleventy.js');

const fixturePath = path.join(
  __dirname,
  '..',
  '..',
  'tools',
  'tests',
  'fixtures',
  'edition-start.json',
);
const cases = JSON.parse(readFileSync(fixturePath, 'utf8'));

let failures = 0;
for (const testCase of cases) {
  const { iso_date: isoDate, recorded_time: recorded, start_local: expected, offset } = testCase;
  const row = { date: isoDate, time: recorded };

  const resolved = eventStartLocal(row);
  if (resolved !== expected) {
    console.error(`${isoDate} (time ${recorded || 'blank'}): ${resolved} !== expected ${expected}`);
    failures += 1;
  }

  // The composition the templates actually render, so a correct
  // `eventStartLocal` wired into nothing would still be caught: this is the
  // string that reaches the JSON-LD `startDate` and the visible label.
  const { startDate, label } = parisStandingStart(isoDate, resolved);
  const expectedStart = `${isoDate}T${expected}:00${offset}`;
  if (startDate !== expectedStart) {
    console.error(`${isoDate}: startDate ${startDate} !== expected ${expectedStart}`);
    failures += 1;
  }
  if (!label.startsWith(`${expected} `)) {
    console.error(`${isoDate}: label ${label} does not state ${expected}`);
    failures += 1;
  }
}

// A fixture that failed to load, or one somebody emptied, would let every
// loop above pass by never running -- the same positive control
// `check-paris-standing-start.cjs` leans on its own case count for.
if (cases.length < 6) {
  console.error(`edition-start fixture: ${cases.length} case(s), expected at least 6`);
  failures += 1;
}

if (failures > 0) {
  console.error(`edition-start fixture: ${failures} mismatch(es) of ${cases.length} case(s)`);
  process.exit(1);
}
console.log(`edition-start fixture: ${cases.length} case(s) OK`);
