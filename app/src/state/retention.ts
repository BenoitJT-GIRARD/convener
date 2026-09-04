import { addCalendarDays } from './sla';

/**
 * When an event's registrations stop being readable.
 *
 * The window is **90 days** from the day of the talk, and it is not a
 * setting: retention is a commitment made to every participant in the
 * confirmation e-mail and on the event page, not a number an operator tunes
 * per event. `tools/convener_ops/journey/eventkeys.py::RETENTION_DAYS` is the
 * writer that acts on it -- `convener-retention-sweep` destroys the key that
 * could ever read that event's data, and `instance/data/event-key-destructions.yml`
 * records the day each one actually went.
 *
 * This module states the same window a fifth time, which is one restatement
 * more than there was, so it joins the binding that already holds the other
 * four together: `tools/tests/journey/test_confirmation.py::
 * test_the_retention_window_is_the_same_number_everywhere` reads the figure
 * out of `confirmation.py`, the docs copy, `eventkeys.py`, `site/src/event.njk`
 * and this file, and fails the moment one of them says something else.
 *
 * **What this can honestly say, and what it cannot.** It computes the day the
 * window *ends*. It cannot say the data is gone: only the registry above
 * records that, the cockpit does not read it, and a page claiming a
 * destruction it has not seen would be the worst kind of wrong on exactly the
 * subject this product exists to be trusted about.
 */
export const RETENTION_WINDOW_DAYS = 90;

/**
 * The day an event's registration data is due to stop being readable, or
 * `null` where the record carries no day of the talk to count from.
 *
 * Inclusive of the boundary, exactly as `eventkeys.is_due_for_destruction`
 * reads it: the sweep is due *on* day 90, not the day after.
 */
export function destructionDue(eventDate: string): string | null {
  return addCalendarDays(eventDate, RETENTION_WINDOW_DAYS);
}
