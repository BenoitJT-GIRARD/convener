/**
 * The example instance's records, as old today as they were written to be.
 *
 * The whole of the rule, and why it is a rule rather than a fresher fixture,
 * is stated once in `tools/scripts/example_dates.py`. This is the same rule in
 * the language the cockpit's build speaks: the demonstration's own records are
 * compiled into the bundle by `./example-instance.mjs`, and no Python runs
 * where that happens.
 *
 * The two are pinned to each other by `tools/tests/fixtures/example-dates.json`
 * -- the same anchor, the same worked cases, read from both sides (D-14). A
 * shift the build applied and the second-instance build did not would put the
 * cockpit's own copy of a session on a different evening from the showcase's,
 * which is the one thing a demonstration of a single instance may not do.
 *
 * `CONVENER_EXAMPLE_TODAY` is read here for the same single caller:
 * `tools/scripts/render_readme_shots.py` sets it for the whole build so that
 * the pictures `README.md` shows stay byte-identical between two runs on
 * different days.
 */

/** The day `examples/the-example-collective/instance/data/` is written for.
 *  Mirrors `example_dates.ANCHOR`. */
export const ANCHOR = '2026-09-03';

/** The one environment variable that replaces the clock here. */
export const TODAY_ENV = 'CONVENER_EXAMPLE_TODAY';

/** An ISO day, bounded on both sides so a longer run of digits is not
 *  half-matched. Mirrors `example_dates.ISO_DAY`. */
const ISO_DAY = /(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)/g;

const MS_PER_DAY = 86_400_000;

/** Midnight UTC of an ISO day, or `null` when the calendar has no such day.
 *  The round trip is what refuses `2026-02-30`, which `Date.parse` accepts
 *  and rolls forward to 2 March -- `app/src/state/sla.ts::parsedDay` refuses
 *  it the same way and for the same reason. */
function parse(day) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) return null;
  const epoch = Date.parse(`${day}T00:00:00Z`);
  if (Number.isNaN(epoch)) return null;
  return new Date(epoch).toISOString().slice(0, 10) === day ? epoch : null;
}

function isoOf(epoch) {
  return new Date(epoch).toISOString().slice(0, 10);
}

/**
 * The day the example's records are read against.
 *
 * Throws on a value that is set and unreadable, the way the Python side does:
 * a renderer that meant to pin the clock and misspelled the day would
 * otherwise photograph a moving fixture and report success (D-25).
 */
export function today(env = process.env) {
  const pinned = env[TODAY_ENV] ?? '';
  if (!pinned) return new Date().toISOString().slice(0, 10);
  if (parse(pinned) === null) {
    throw new Error(
      `${TODAY_ENV} is ${JSON.stringify(pinned)}, which is not a YYYY-MM-DD day -- ` +
        "it is read to pin the example instance's own records to one moment, and a " +
        'value nothing can parse would leave them moving'
    );
  }
  return pinned;
}

/** Whole days -- always a multiple of seven -- from the anchor to the week
 *  `day` falls in. `Math.floor` and not a truncation: the shift is negative
 *  for a day before the anchor, which is the ordinary case for a pinned
 *  renderer, and truncating would round it the wrong way. */
export function shiftDays(day) {
  const now = parse(day);
  if (now === null) throw new Error(`${JSON.stringify(day)} is not a YYYY-MM-DD day`);
  const anchor = parse(ANCHOR);
  return Math.floor((now - anchor) / MS_PER_DAY / 7) * 7;
}

/** `text` with every ISO day in it moved into the week of `day`. A date the
 *  calendar does not have is left exactly as it was found. */
export function shifted(text, day) {
  const days = shiftDays(day);
  if (days === 0) return text;
  return text.replace(ISO_DAY, (whole) => {
    const found = parse(whole);
    return found === null ? whole : isoOf(found + days * MS_PER_DAY);
  });
}
