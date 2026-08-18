import { describe, expect, it } from 'vitest';
import cases from '../../tools/tests/fixtures/governance-cases.json';
import { decide, thresholdFor } from '../src/state/governance';
import type { BallotLike } from '../src/state/governance';
import { isBallotValue } from '../src/data/types';

/** The fixture is JSON, so every ballot value arrives as a bare string. It is
 *  narrowed through the same guard the app uses rather than cast: a typo in the
 *  shared fixture then fails here instead of quietly counting as a non-yes. */
function ballot(raw: { voter: string; value: string }): BallotLike {
  if (!isBallotValue(raw.value)) {
    throw new Error(`unknown ballot value in the shared fixture: ${raw.value}`);
  }
  return { voter: raw.voter, value: raw.value };
}

describe('the shared governance fixture', () => {
  it.each(cases.threshold_cases)('$name', ({ eligible, expected }) => {
    expect(thresholdFor(eligible)).toBe(expected);
  });

  it.each(cases.decision_cases)('$name', c => {
    const outcome = decide({
      board: c.board,
      unavailable: c.unavailable,
      ballots: c.ballots.map(ballot),
    });
    expect(outcome.eligible).toBe(c.eligible);
    expect(outcome.threshold).toBe(c.threshold);
    expect(outcome.yes).toBe(c.yes);
    expect(outcome.decided).toBe(c.decided);
    expect(outcome.suspended).toBe(c.suspended);
  });
});
