import { describe, expect, it } from 'vitest';
import { castBallot, withdrawBallot, BallotRejected } from '../src/state/ballots';
import type { SpeakerSelection } from '../src/data/types';

const empty: SpeakerSelection = { ballots: [], opened_on: '2026-01-01', decided_on: '' };

describe('castBallot', () => {
  it('records a yes with its date', () => {
    const s = castBallot(empty, 'alice', 'yes', '', '', '2026-01-05');
    expect(s.ballots).toEqual([
      { voter: 'alice', value: 'yes', comment: '', coi_reason: '', date: '2026-01-05' },
    ]);
  });

  it('keeps an optional comment', () => {
    const s = castBallot(empty, 'alice', 'yes', 'strong fit', '', '2026-01-05');
    expect(s.ballots[0].comment).toBe('strong fit');
  });

  it('replaces a voter earlier ballot rather than adding a second', () => {
    const once = castBallot(empty, 'alice', 'yes', '', '', '2026-01-05');
    const twice = castBallot(once, 'alice', 'abstain', '', '', '2026-01-06');
    expect(twice.ballots).toHaveLength(1);
    expect(twice.ballots[0]).toMatchObject({ value: 'abstain', date: '2026-01-06' });
  });

  it('refuses a recusal with no written reason', () => {
    expect(() => castBallot(empty, 'alice', 'recused', '', '', '2026-01-05'))
      .toThrow(BallotRejected);
  });

  it('refuses a recusal whose reason is only whitespace', () => {
    expect(() => castBallot(empty, 'alice', 'recused', '', '   ', '2026-01-05'))
      .toThrow(BallotRejected);
  });

  it('accepts a recusal with a reason', () => {
    const s = castBallot(empty, 'alice', 'recused', '', 'co-author', '2026-01-05');
    expect(s.ballots[0]).toMatchObject({ value: 'recused', coi_reason: 'co-author' });
  });

  it('does not mutate the selection it was given', () => {
    const before = JSON.stringify(empty);
    castBallot(empty, 'alice', 'yes', '', '', '2026-01-05');
    expect(JSON.stringify(empty)).toBe(before);
  });
});

describe('withdrawBallot', () => {
  it('removes only that voter ballot', () => {
    let s = castBallot(empty, 'alice', 'yes', '', '', '2026-01-05');
    s = castBallot(s, 'bob', 'yes', '', '', '2026-01-05');
    expect(withdrawBallot(s, 'alice').ballots.map(b => b.voter)).toEqual(['bob']);
  });

  it('is a no-op for a voter who never voted', () => {
    const s = castBallot(empty, 'alice', 'yes', '', '', '2026-01-05');
    expect(withdrawBallot(s, 'carol').ballots).toHaveLength(1);
  });
});
