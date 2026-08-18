/**
 * Pure transformations of a single ballot within a `SpeakerSelection`. No
 * clock, no state, no side effects: every input needed to decide the outcome
 * -- including today's date -- is a parameter, so these can run inside a
 * `mutate` transformation that may be replayed against a freshly-read value
 * after a concurrent write.
 */
import type { Ballot, BallotValue, SpeakerSelection } from '../data/types';

/** A ballot that cannot be recorded as given. The message is a plain
 *  sentence saying what to do -- it reaches a volunteer's screen as-is. */
export class BallotRejected extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'BallotRejected';
  }
}

/**
 * Record `voter`'s ballot, replacing any earlier ballot from the same
 * voter rather than adding a second one -- a board member changing their
 * mind must produce one ballot, not two. A replaced ballot keeps its
 * original position in the list: `data/speakers.yml` is read by hand and
 * reviewed as a diff, and reordering the list on a simple vote change would
 * bury the actual change in noise; ballot order also carries information
 * (roughly who voted when) that moving an entry to the end would destroy.
 * Never mutates `selection`, and the ballots carried over by reference are
 * shared safely only because `Ballot` holds nothing but primitives -- if a
 * nested/object field is ever added to `Ballot`, this function would need
 * to copy rather than share those unchanged entries.
 */
export function castBallot(
  selection: SpeakerSelection,
  voter: string,
  value: BallotValue,
  comment: string,
  coiReason: string,
  today: string,
): SpeakerSelection {
  if (value === 'recused' && coiReason.trim() === '') {
    throw new BallotRejected(
      'A recusal needs a written reason. Add a short note explaining the conflict of interest before submitting.',
    );
  }

  const ballot: Ballot = {
    voter,
    value,
    comment,
    coi_reason: coiReason,
    date: today,
  };

  const hasExisting = selection.ballots.some(b => b.voter === voter);
  const ballots = hasExisting
    ? selection.ballots.map(b => (b.voter === voter ? ballot : b))
    : [...selection.ballots, ballot];

  return { ...selection, ballots };
}

/**
 * Remove `voter`'s ballot, if any. A no-op for a voter who never voted.
 * Never mutates `selection`.
 */
export function withdrawBallot(selection: SpeakerSelection, voter: string): SpeakerSelection {
  return {
    ...selection,
    ballots: selection.ballots.filter(b => b.voter !== voter),
  };
}
