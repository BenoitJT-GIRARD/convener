import { describe, it, expect } from 'vitest';
import { RETENTION_WINDOW_DAYS, destructionDue } from '../../src/state/retention';

/**
 * The one day a closed event still has ahead of it.
 *
 * The window itself is bound across the languages by
 * `tools/tests/journey/test_confirmation.py::
 * test_the_retention_window_is_the_same_number_everywhere`, which reads the
 * figure out of this module's source along with the four other places it is
 * stated. What is held here is the arithmetic and the boundary.
 */
describe('when an event’s registrations stop being readable', () => {
  it('is the day of the talk plus the window, counted in calendar days', () => {
    expect(RETENTION_WINDOW_DAYS).toBe(90);
    // 2026-03-12 is 20 days from the end of March, then April, May and ten
    // days of June: 20 + 30 + 31 + 9 = 90.
    expect(destructionDue('2026-03-12')).toBe('2026-06-10');
  });

  it('counts across a leap day rather than around it', () => {
    // 2028 is a leap year: 2028-01-01 plus 90 lands on 31 March, where a
    // common year would give 1 April.
    expect(destructionDue('2028-01-01')).toBe('2028-03-31');
    expect(destructionDue('2027-01-01')).toBe('2027-04-01');
  });

  it('has no day to name when the record carries none', () => {
    // A record with no date is a state only a hand-edited file reaches on a
    // talk that has been given, and an absent day is the honest answer to
    // it -- never today, and never a guess.
    expect(destructionDue('')).toBeNull();
    expect(destructionDue('soon')).toBeNull();
    expect(destructionDue('2026-02-30')).toBeNull();
  });
});
