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
 * *representable*; this one does not (P2-8).
 *
 * Public holidays are deliberately not modelled -- see
 * `tools/tests/fixtures/governance-cases.json`. The board's members do not all
 * work under the same national calendar, so a holiday list that is right for
 * France would be wrong for the others; and an unmodelled holiday only ever
 * makes an objection window effectively *longer*, which is the prudent
 * direction. The shared fixture pins that choice with 1 May 2026 counted as an
 * ordinary Friday, so it reads as a decision rather than an oversight.
 *
 * `tools/convener_ops/governance.py` implements the same arithmetic for the
 * unattended job, and `tools/tests/fixtures/governance-cases.json`'s
 * `working_day_cases` pins the two together.
 */

const MS_PER_DAY = 86_400_000;

/** Midnight UTC of an ISO day. UTC throughout, so the result never depends on
 *  the browser's own timezone. */
function epochOf(day: string): number {
  return Date.parse(`${day}T00:00:00Z`);
}

function isoOf(epoch: number): string {
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
  let epoch = epochOf(from);
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
  const end = epochOf(to);
  let elapsed = 0;
  for (let epoch = epochOf(from); epoch < end; ) {
    epoch += MS_PER_DAY;
    if (!isWeekend(epoch)) elapsed += 1;
  }
  return elapsed;
}
