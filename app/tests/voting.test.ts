import { describe, it, expect } from 'vitest';
import { voteThreshold, voteState } from '../src/data/voting';

describe('voting', () => {
  it('two-thirds threshold (rounded up)', () => {
    expect(voteThreshold(6)).toBe(4);
    expect(voteThreshold(9)).toBe(6);
    expect(voteThreshold(4)).toBe(3);
    expect(voteThreshold(1)).toBe(1);
  });
  it('state: open when below threshold', () => {
    expect(voteState(['A', 'B'], 6)).toEqual({ count: 2, threshold: 4, state: 'open' });
  });
  it('state: passed when at threshold', () => {
    expect(voteState(['A', 'B', 'C', 'D'], 6).state).toBe('passed');
  });
});
