import type { BallotValue, Config, Speaker, SpeakerStatus } from '../data/types';
import { castBallot, withdrawBallot } from './ballots';
import { activeBoard } from './board';
import { decide } from './governance';

export type Role = 'board' | 'organizer';

export type Transition =
  | 'ballot-cast'
  | 'ballot-withdraw'
  | 'lead-park'
  | 'lead-decline'
  | 'reactivate'
  | 'send-invitation'
  | 'invited-accept'
  | 'invited-decline'
  | 'lock-date'
  | 'finalize-archive'
  | 'override';

export interface LockDatePayload {
  date: string;
  edition_code: string;
  time: string;
}

export interface OverridePayload {
  status: SpeakerStatus;
}

/** What a board member actually casts. `value` carries the three ballots the
 *  handbook recognises -- a `yes`, an `abstain`, and a `recused` that takes
 *  its caster out of the denominator -- and `coiReason` is required for the
 *  last of them (`ballots.castBallot` refuses a recusal without one). */
export interface BallotPayload {
  value: BallotValue;
  comment: string;
  coiReason: string;
}

const BOARD_ONLY: Transition[] = [
  'ballot-cast',
  'ballot-withdraw',
  'lead-park',
  'lead-decline',
  'reactivate',
  'override',
];

export function canTransition(s: Speaker, t: Transition, role: Role): boolean {
  if (BOARD_ONLY.includes(t) && role !== 'board') return false;
  switch (t) {
    case 'ballot-cast':
    case 'ballot-withdraw':
    case 'lead-park':
    case 'lead-decline':
      return s.status === 'lead';
    case 'reactivate':
      return s.status === 'parked' || s.status === 'decline-board';
    case 'send-invitation':
      return s.status === 'approved' && !!s.host_1 && !!s.host_2;
    case 'invited-accept':
    case 'invited-decline':
      return s.status === 'invited';
    case 'lock-date':
      return s.status === 'confirmed';
    case 'finalize-archive':
      return s.status === 'delivered';
    case 'override':
      return true;
    default:
      return false;
  }
}

/**
 * `config` rather than a pre-computed threshold: the threshold is derived from
 * the *eligible* board (active, available, not recused on this lead), which
 * changes with the ballots being cast here. A caller cannot compute it ahead of
 * the ballot it is about to record, so it hands over the board and lets
 * `governance.decide` do both halves at once.
 */
export function applyTransition(
  s: Speaker,
  t: Transition,
  actor: string,
  config: Config,
  today: string,
  payload?: LockDatePayload | OverridePayload | BallotPayload,
): Speaker {
  switch (t) {
    case 'ballot-cast': {
      const p = payload as BallotPayload;
      // `castBallot` replaces any earlier ballot from `actor`, so voting twice
      // records one ballot and cannot inflate the yes count. It throws
      // `BallotRejected` on a recusal with no written reason -- the caller
      // asks for the reason before getting here, and `github/errors.ts`
      // relays the sentence if one ever slips through.
      const selection = castBallot(s.selection, actor, p.value, p.comment, p.coiReason, today);
      const { logins, unavailable } = activeBoard(config, today);
      const { decided } = decide({ board: logins, unavailable, ballots: selection.ballots });
      return {
        ...s,
        // `s.status` rather than a literal `lead`: a ballot recorded on a
        // speaker who has moved on (a vote reopened, then re-decided) must
        // never drag the status backwards.
        status: decided ? 'approved' : s.status,
        selection: {
          ...selection,
          decided_on: decided ? today : s.selection.decided_on,
        },
      };
    }
    case 'ballot-withdraw':
      // Ballots only. The status is deliberately *not* recomputed: a decision
      // already taken does not come undone because one voter steps back, and
      // a speaker already told they were approved is not un-approved behind
      // their back. Only the concealed-conflict procedure reopens a vote.
      return { ...s, selection: withdrawBallot(s.selection, actor) };
    case 'lead-park':
      return { ...s, status: 'parked' };
    case 'lead-decline':
      return { ...s, status: 'decline-board' };
    case 'reactivate':
      return { ...s, status: 'lead' };
    case 'send-invitation':
      return {
        ...s,
        status: 'invited',
        runbook_progress: { ...s.runbook_progress, 'approved/invitation-sent': true },
      };
    case 'invited-accept':
      return { ...s, status: 'confirmed' };
    case 'invited-decline':
      return { ...s, status: 'decline-speaker' };
    case 'lock-date': {
      const p = payload as LockDatePayload;
      return {
        ...s,
        status: 'scheduled',
        date: p.date,
        edition_code: p.edition_code,
        time: p.time,
      };
    }
    case 'finalize-archive':
      return { ...s, status: 'archived' };
    case 'override': {
      const p = payload as OverridePayload;
      return { ...s, status: p.status };
    }
  }
}
