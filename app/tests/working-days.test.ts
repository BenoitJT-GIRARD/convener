/**
 * The working-day cases live in `tools/tests/fixtures/governance-cases.json`
 * and are read from there by both languages, the way `board.test.ts` reads
 * `active_board_cases`: calendar arithmetic is exactly the kind of rule that
 * drifts between two implementations while both suites stay green. Anything
 * below the fixture blocks is TypeScript-only behaviour, and pins nothing the
 * Python side has to agree with.
 */
import { describe, expect, it } from 'vitest';
import cases from '../../tools/tests/fixtures/governance-cases.json';
import { addWorkingDays, workingDaysElapsed } from '../src/state/working-days';

describe('the shared working-day fixture', () => {
  it.each(cases.working_day_cases.add)('$name', c => {
    expect(addWorkingDays(c.from, c.days)).toBe(c.expected);
  });

  it.each(cases.working_day_cases.elapsed)('$name', c => {
    expect(workingDaysElapsed(c.from, c.to)).toBe(c.expected);
  });

  it.each(cases.working_day_cases.add)('inverts: $name', c => {
    // A case that cannot be computed inverts to nothing: there is no day to
    // count to.
    expect(workingDaysElapsed(c.from, c.expected)).toBe(c.expected === '' ? 0 : c.days);
  });
});

describe('addWorkingDays', () => {
  it('crosses a month and a year boundary', () => {
    // 2026-12-31 is a Thursday: +2 is Friday the 1st of January and Monday the 4th.
    expect(addWorkingDays('2026-12-31', 2)).toBe('2027-01-04');
  });

  it('counts a long window one working day at a time', () => {
    // Ten working days from a Monday is a fortnight later, to the day.
    expect(addWorkingDays('2026-08-17', 10)).toBe('2026-08-31');
  });

  it('treats a negative count as the identity rather than walking backwards', () => {
    expect(addWorkingDays('2026-08-19', -3)).toBe('2026-08-19');
  });
});

describe('workingDaysElapsed', () => {
  it('counts every weekday of a long span', () => {
    expect(workingDaysElapsed('2026-08-17', '2026-08-31')).toBe(10);
  });

  it('agrees with addWorkingDays for every start day of one week', () => {
    // Monday through Sunday, each opening a three-working-day window.
    for (const from of [
      '2026-08-17',
      '2026-08-18',
      '2026-08-19',
      '2026-08-20',
      '2026-08-21',
      '2026-08-22',
      '2026-08-23',
    ]) {
      const deadline = addWorkingDays(from, 3);
      expect(workingDaysElapsed(from, deadline)).toBe(3);
      // The window has not run the day before its deadline.
      const dayBefore = new Date(Date.parse(`${deadline}T00:00:00Z`) - 86_400_000)
        .toISOString()
        .slice(0, 10);
      expect(workingDaysElapsed(from, dayBefore)).toBeLessThan(3);
    }
  });
});
