import { describe, expect, it } from 'vitest';
import cases from '../../tools/tests/fixtures/governance-cases.json';
import { decide, thresholdFor } from '../src/state/governance';

describe('the shared governance fixture', () => {
  it.each(cases.threshold_cases)('$name', ({ eligible, expected }) => {
    expect(thresholdFor(eligible)).toBe(expected);
  });

  it.each(cases.decision_cases)('$name', c => {
    const outcome = decide({
      board: c.board,
      unavailable: c.unavailable,
      ballots: c.ballots,
    });
    expect(outcome.eligible).toBe(c.eligible);
    expect(outcome.threshold).toBe(c.threshold);
    expect(outcome.yes).toBe(c.yes);
    expect(outcome.decided).toBe(c.decided);
    expect(outcome.suspended).toBe(c.suspended);
  });
});
