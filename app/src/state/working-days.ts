/**
 * Working-day arithmetic for the governance windows counted in working days.
 *
 * Several deadlines the board is held to are counted in working days rather
 * than calendar days -- `config.objection_window_working_days`, the
 * publication objection gate (G-10) -- because the people bound by them are
 * unpaid volunteers with day jobs: a window that burns through a weekend is a
 * window that has silently shortened itself. Not every window is: the
 * nomination window (`board.ts::NOMINATION_WINDOW_DAYS`, G-08) and
 * `config.vote_window_days` are calendar days by rule, and nothing here should
 * be applied to them -- converting one unit into the other would move a real
 * decision by a real day.
 *
 * These take and return ISO `YYYY-MM-DD` days and read no clock, so there is no
 * timezone for them to get wrong: the caller supplies the day, already anchored
 * on Europe/Paris the way `tools/convener_ops/sweep.py::_paris_today` anchors it. A
 * signature taking a `Date` would have made a UTC-versus-Paris off-by-one day
 * *representable*; this one does not.
 *
 * Public holidays are deliberately not modelled -- see
 * `tools/tests/fixtures/governance-cases.json`. The board's members do not all
 * work under the same national calendar, so a holiday list that is right for
 * France would be wrong for the others; and an unmodelled holiday only ever
 * makes an objection window effectively *longer*, which is the prudent
 * direction. The shared fixture pins that choice with 1 May 2026 counted as an
 * ordinary Friday, so it reads as a decision rather than an oversight.
 *
 * `tools/convener_ops/governance/governance.py` implements the same arithmetic for the
 * unattended job, and `tools/tests/fixtures/governance-cases.json`'s
 * `working_day_cases` pins the two together.
 */

const MS_PER_DAY = 86_400_000;

/** An ISO calendar day the calendar actually has.
 *
 * The regex alone is not enough, and neither is `Date.parse`: JavaScript
 * accepts `2026-02-30` and silently rolls it forward to 2 March, while
 * `date.fromisoformat` in the Python twin raises. So the parsed day is
 * formatted back and compared, and year zero -- which JavaScript has and the
 * `datetime` module does not -- is refused outright. `working_day_cases`
 * pins the pair on exactly these inputs.
 */
const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;

function parsedDay(day: string): number {
  if (!ISO_DAY.test(day) || day < '0001-01-01') return Number.NaN;
  const epoch = Date.parse(`${day}T00:00:00Z`);
  if (Number.isNaN(epoch)) return Number.NaN;
  // eslint-disable-next-line no-restricted-syntax -- a fixed epoch, not "now".
  return new Date(epoch).toISOString().slice(0, 10) === day ? epoch : Number.NaN;
}

/** Midnight UTC of an ISO day, or `NaN` when the string is not one. UTC
 *  throughout, so the result never depends on the browser's own timezone.
 *
 *  `NaN` rather than a throw: `data/validate.ts` narrows every field's *type*
 *  and checks no date's *shape*, so `opened_on: 'soon'` reaches here from a
 *  hand-edited file and used to crash the Pipeline with a bare
 *  `RangeError: Invalid time value`. The Python twin returns `''`/`0` for the
 *  same input, and the two are pinned by `working_day_cases`. */
function epochOf(day: string): number {
  return parsedDay(day);
}

/** The inverse of `epochOf`. UTC here is not the UTC-day defect: the epoch being
 *  formatted is one this module built from an ISO day at midnight UTC, never a
 *  reading of the clock, so `parisToday()` would be the wrong tool. */
function isoOf(epoch: number): string {
  // eslint-disable-next-line no-restricted-syntax -- see above: a fixed epoch, not "now".
  return new Date(epoch).toISOString().slice(0, 10);
}

/** Saturday (6) and Sunday (0) as `getUTCDay` reports them. */
function isWeekend(epoch: number): boolean {
  const weekday = new Date(epoch).getUTCDay();
  return weekday === 0 || weekday === 6;
}

/**
 * The ISO day `n` working days after `from`, weekends skipped.
 *
 * The count is of the days *after* `from`: three working days from a Thursday
 * is the following Tuesday, and three from a Friday, a Saturday or a Sunday are
 * all the following Wednesday -- a window opened over a weekend gets its full
 * three working days, which is the whole point of counting them this way.
 *
 * `n` of zero is the identity, `from` itself, including when `from` falls on a
 * weekend: a zero-length window closes the moment it opens, and rounding a
 * Saturday forward to the Monday would quietly grant a window nobody voted for.
 */
export function addWorkingDays(from: string, n: number): string {
  // `''` -- never a throw -- when `from` is not an ISO day or `n` is not a
  // whole number, as a hand-edited file may well hold. The caller reads that
  // as "no deadline can be computed" and leaves the window standing open, so
  // nothing acts on a date it could not parse. `add_working_days` in
  // `tools/convener_ops/governance/governance.py` answers `''` to the same input.
  let epoch = epochOf(from);
  if (Number.isNaN(epoch) || !Number.isInteger(n)) return '';
  for (let counted = 0; counted < n; ) {
    epoch += MS_PER_DAY;
    if (!isWeekend(epoch)) counted += 1;
  }
  return isoOf(epoch);
}

/**
 * Working days from `from` to `to`, counting the days after `from` up to and
 * including `to` -- the exact inverse of `addWorkingDays`, so a window opened on
 * `from` with `n` working days has run once this reaches `n`.
 *
 * Zero when `to` is not after `from`, so a window can never read as having run
 * backwards.
 */
export function workingDaysElapsed(from: string, to: string): number {
  // Zero when either end is not an ISO day: an unparsable date reads as "no
  // time has passed", so a window stays open rather than closing on a value
  // nothing could make sense of. Same answer as `working_days_elapsed`.
  const end = epochOf(to);
  const start = epochOf(from);
  if (Number.isNaN(end) || Number.isNaN(start)) return 0;
  let elapsed = 0;
  for (let epoch = start; epoch < end; ) {
    epoch += MS_PER_DAY;
    if (!isWeekend(epoch)) elapsed += 1;
  }
  return elapsed;
}
