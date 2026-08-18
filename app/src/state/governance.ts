/**
 * The governance rule, for display.
 *
 * `tools/convener_ops/governance.py` implements the same rule for writing, and both
 * are pinned by `tools/tests/fixtures/governance-cases.json`. A change here that
 * is not mirrored there is a defect, not a divergence of opinion: the volunteer
 * would see one threshold while the scheduled job applied another.
 */

import type { Config, Publication, PublicationObjection, Speaker } from '../data/types';
import { addWorkingDays, workingDaysElapsed } from './working-days';

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

/* ------------------------------------------------------------------ *
 * The publication gate (G-10, G-15)
 *
 * After a seminar, the recording goes online only when two separate
 * permissions are in hand, from two separate parties, and neither may be
 * read off the other:
 *
 *   - the speaker's, which must be *present*. `consentBlocker` below takes
 *     no date. That is not an oversight and not a style choice: with no
 *     clock in its signature, "enough time has passed, so they must agree"
 *     is not a sentence this code can express. Silence from a speaker is
 *     silence.
 *
 *   - the board's, which must be *absent* -- an objection is the thing that
 *     has to show up, and `boardBlocker` is the only half that takes a date,
 *     because the board's silence really is converted into permission once
 *     the objection window has run.
 *
 * The asymmetry is the whole rule, so it is carved into the two signatures
 * rather than left to a comment: one cannot accidentally acquire the other's
 * behaviour without changing its arguments.
 *
 * This gate is implemented in TypeScript only. No unattended path archives a
 * seminar -- `tools/convener_ops/sweep.py` writes the scheduled -> delivered
 * transition and nothing past it -- so there is no second implementation to
 * pin, and `tools/tests/fixtures/governance-cases.json` is deliberately not
 * extended for it. The working-day arithmetic this leans on *is* shared, and
 * is already pinned there by `working_day_cases`.
 * ------------------------------------------------------------------ */

/** An archiving that a governance rule refuses. The message is a plain
 *  sentence a volunteer can act on and reaches the screen as-is through
 *  `github/errors.ts`. `PublicationGate` asks `canArchive` first and keeps
 *  the control disabled, so this is a backstop -- but a rule about somebody's
 *  consent must never surface as "GitHub is not responding". */
export class PublicationBlocked extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'PublicationBlocked';
  }
}

/** Whether the gate lets this recording be published, and if not, why -- as a
 *  sentence, not a code. `reason` is what the volunteer reads beside the
 *  disabled button, so it is never empty when `allowed` is false. */
export interface ArchiveGate {
  allowed: boolean;
  reason: string;
}

/**
 * The objections that still stand.
 *
 * An objection with no `resolved_on` is open, including one hand-written
 * without the key at all: absent reads as standing, never as settled.
 */
export function standingObjections(p: Publication): PublicationObjection[] {
  return p.objections.filter(o => !o.resolved_on);
}

/** The day the board's objection window closes, counted in working days from
 *  the approval (G-10). Only meaningful once there *is* an approval. */
export function objectionWindowCloses(p: Publication, config: Config): string {
  return addWorkingDays(p.approved_on, config.objection_window_working_days);
}

/**
 * Why the *speaker* has not permitted publication, as a sentence -- or `''`
 * when they have.
 *
 * Takes no date. See the block comment above: consent cannot be produced by
 * the passage of time, so time is not available here to produce it.
 */
function consentBlocker(p: Publication): string {
  if (p.consent === 'granted') return '';
  if (p.consent === 'refused') {
    return (
      'The speaker has refused permission for their recording to be published. ' +
      'It cannot be archived, and any copy already online has to be taken down.'
    );
  }
  return (
    'The speaker has not given permission for their recording to be published. ' +
    'Ask them, then record their answer above -- not hearing back is not a yes.'
  );
}

/**
 * Why the *board* has not cleared publication, as a sentence -- or `''` when
 * it has. The only half that reads the clock.
 */
function boardBlocker(p: Publication, config: Config, today: string): string {
  if (p.outcome === 'withheld') {
    return (
      'The board decided to withhold this recording. A board member has to lift ' +
      'that decision below before it can be published.'
    );
  }
  if (!p.approved_by || !p.approved_on) {
    return 'No board member has approved this recording for publication yet.';
  }
  const standing = standingObjections(p);
  if (standing.length > 0) {
    const first = standing[0];
    return (
      `${first.member} objected on ${first.date} and the objection is still open ` +
      `("${first.reason}"). It has to be resolved below before this can be published.`
    );
  }
  const window = config.objection_window_working_days;
  if (workingDaysElapsed(p.approved_on, today) < window) {
    return (
      `${p.approved_by} approved this on ${p.approved_on}. The board has ${window} ` +
      `working days to object, so publication opens on ${objectionWindowCloses(p, config)}.`
    );
  }
  return '';
}

/**
 * Whether this recording may be published, and why not when it may not.
 *
 * Pure in its arguments, `today` included, so it runs unchanged inside a
 * `mutate` transformation replayed against freshly-read data.
 */
export function canArchive(speaker: Speaker, config: Config, today: string): ArchiveGate {
  // The speaker first. Their answer is the one nobody on the board can give
  // for them, so it is also the one reported first when several rules block.
  const blocker = consentBlocker(speaker.publication) || boardBlocker(speaker.publication, config, today);
  return { allowed: blocker === '', reason: blocker };
}
