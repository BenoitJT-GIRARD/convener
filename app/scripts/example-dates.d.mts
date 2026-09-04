/* Types for example-dates.mjs, so example-instance.mjs's own types and the
 * test suite can both import it typed. The script itself stays plain ESM --
 * see handbook-files.d.mts for why. */

/** The day `examples/the-example-collective/instance/data/` is written for.
 *  Mirrors `tools/scripts/example_dates.py`'s own `ANCHOR`. */
export declare const ANCHOR: string;

/** The one environment variable that replaces the clock. */
export declare const TODAY_ENV: string;

/** The day the example's records are read against: the pinned one when it is
 *  set, the real one otherwise. Throws on a pinned value that is not an ISO
 *  day. */
export declare function today(env?: Record<string, string | undefined>): string;

/** Whole days -- a multiple of seven, negative before the anchor -- from the
 *  anchor to the week `day` falls in. */
export declare function shiftDays(day: string): number;

/** `text` with every ISO day in it moved into the week of `day`. */
export declare function shifted(text: string, day: string): string;
