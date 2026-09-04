/**
 * The example instance's records, dated on this side of the language
 * boundary.
 *
 * Two readers move the same days: `tools/scripts/example_dates.py` when the
 * second-instance build lays the example into a scratch tree, and
 * `app/scripts/example-dates.mjs` when `example-instance.mjs` compiles the
 * same records into the cockpit's bundle. A demonstration is one instance,
 * so a shift one of them applied and the other did not would have the
 * showcase and the cockpit naming two different evenings for one session.
 *
 * `tools/tests/fixtures/example-dates.json` is what stops that: the anchor
 * and every worked case are read out of it here and there, and neither side
 * writes a case of its own (D-14, the shape `edition-prefix.json` already
 * gives this boundary).
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { ANCHOR, TODAY_ENV, shiftDays, shifted, today } from '../../scripts/example-dates.mjs';

interface Shift {
  today: string;
  days: number;
  why: string;
}
interface Text {
  today: string;
  given: string;
  expected: string;
  why: string;
}

const FIXTURE = resolve(
  __dirname,
  '../..',
  '..',
  'tools',
  'tests',
  'fixtures',
  'example-dates.json',
);
const fixture = JSON.parse(readFileSync(FIXTURE, 'utf-8')) as {
  anchor: string;
  shifts: Shift[];
  texts: Text[];
};

describe('the day the example instance is written for', () => {
  it('is the one the other reader states', () => {
    expect(ANCHOR).toBe(fixture.anchor);
  });
});

describe('how far the records move', () => {
  it('answers every shared case the way the other reader does', () => {
    expect(fixture.shifts.length).toBeGreaterThan(4);
    for (const one of fixture.shifts) {
      expect(shiftDays(one.today), `${one.today}: ${one.why}`).toBe(one.days);
    }
  });

  it('moves by whole weeks in both directions, so a Thursday stays a Thursday', () => {
    // `Math.abs`, because JavaScript's `%` keeps the sign of the
    // dividend and `-0` is not `0` to a strict equality.
    for (const one of fixture.shifts) expect(Math.abs(one.days % 7)).toBe(0);
    expect(fixture.shifts.some(one => one.days > 0)).toBe(true);
    expect(fixture.shifts.some(one => one.days < 0)).toBe(true);
  });

  it('refuses a day the calendar has not got rather than rolling it forward', () => {
    expect(() => shiftDays('2026-02-30')).toThrow(/not a YYYY-MM-DD day/);
  });
});

describe('what a substitution does to a document', () => {
  it('answers every shared case the way the other reader does', () => {
    expect(fixture.texts.length).toBeGreaterThan(3);
    for (const one of fixture.texts) {
      expect(shifted(one.given, one.today), one.why).toBe(one.expected);
    }
  });
});

describe('the day the records are read against', () => {
  it('is the pinned one when a renderer has pinned it', () => {
    expect(today({ [TODAY_ENV]: '2026-08-20' })).toBe('2026-08-20');
  });

  it('is the real one when nothing has', () => {
    expect(today({})).toBe(new Date().toISOString().slice(0, 10));
  });

  it('stops on a pinned value nothing can read, rather than quietly moving', () => {
    // A renderer that meant to fix the clock and misspelled the day would
    // otherwise photograph a fixture that moves, and report success.
    expect(() => today({ [TODAY_ENV]: 'the day of the shoot' })).toThrow(TODAY_ENV);
  });
});
