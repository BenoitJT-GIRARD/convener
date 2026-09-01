import { describe, expect, it } from 'vitest';
import { isBallotValue, isCareerStage, BALLOT_VALUES, CAREER_STAGES } from '../../src/data/types';

describe('ballot values', () => {
  it('accepts exactly the three ballot values', () => {
    expect(BALLOT_VALUES).toEqual(['yes', 'abstain', 'recused']);
  });

  it.each(['yes', 'abstain', 'recused'])('accepts %s', v => {
    expect(isBallotValue(v)).toBe(true);
  });

  it.each(['no', 'YES', '', 'maybe'])('rejects %s', v => {
    expect(isBallotValue(v)).toBe(false);
  });
});

describe('career stages', () => {
  it('offers a declared-nothing option, so the field is never a forced guess', () => {
    expect(CAREER_STAGES).toContain('undisclosed');
  });

  it('covers the stages the editorial line distinguishes', () => {
    expect(CAREER_STAGES).toEqual([
      'phd', 'postdoc', 'independent', 'group-leader', 'other', 'undisclosed',
    ]);
  });

  it.each(['professor', '', 'PhD'])('rejects %s', v => {
    expect(isCareerStage(v)).toBe(false);
  });
});
