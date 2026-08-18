/**
 * The governance rule, for display.
 *
 * `tools/convener_ops/governance.py` implements the same rule for writing, and both
 * are pinned by `tools/tests/fixtures/governance-cases.json`. A change here that
 * is not mirrored there is a defect, not a divergence of opinion: the volunteer
 * would see one threshold while the scheduled job applied another.
 */

/** A vote needs at least this many yes ballots in absolute terms, whatever the
 *  ratio says. Guards a board shrunk by recusals from approving on two voices. */
export const MINIMUM_YES = 3;

/** Below this many eligible members the vote is suspended rather than decided
 *  on a bar that has become meaningless. */
export const MINIMUM_ELIGIBLE = 3;

export interface BallotLike {
  voter: string;
  value: 'yes' | 'abstain' | 'recused';
}

export interface DecideInput {
  board: string[];
  unavailable: string[];
  ballots: BallotLike[];
}

export interface Outcome {
  eligible: number;
  threshold: number;
  yes: number;
  decided: boolean;
  suspended: boolean;
}

/** Two thirds of the eligible board, rounded up. 6 -> 4 and 9 -> 6, matching the
 *  two examples the handbook states. */
export function thresholdFor(eligible: number): number {
  return Math.max(Math.ceil((2 * eligible) / 3), MINIMUM_YES);
}

/** Who still counts in the denominator: active members, minus those who declared
 *  themselves unavailable, minus those who recused themselves on this lead. */
export function eligibleVoters(input: DecideInput): string[] {
  const away = new Set(input.unavailable);
  const recused = new Set(
    input.ballots.filter(b => b.value === 'recused').map(b => b.voter),
  );
  return input.board.filter(login => !away.has(login) && !recused.has(login));
}

export function decide(input: DecideInput): Outcome {
  const eligible = eligibleVoters(input).length;
  const threshold = thresholdFor(eligible);
  const voters = new Set(eligibleVoters(input));
  // Count distinct voters, not distinct ballots: a hand-edited ballot list
  // may repeat a voter, and repetition must not inflate a yes count.
  const yesVoters = new Set(
    input.ballots
      .filter(b => b.value === 'yes' && voters.has(b.voter))
      .map(b => b.voter),
  );
  const yes = yesVoters.size;
  const suspended = eligible < MINIMUM_ELIGIBLE;
  return {
    eligible,
    threshold,
    yes,
    decided: !suspended && yes >= threshold,
    suspended,
  };
}
