import type { Config, Speaker, SpeakerStatus } from '../data/types';
import { castBallot, withdrawBallot } from './ballots';
import { activeBoard } from './board';
import { decide } from './governance';

export type Role = 'board' | 'organizer';

export type Transition =
  | 'lead-vote'
  | 'lead-vote-withdraw'
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

const BOARD_ONLY: Transition[] = [
  'lead-vote',
  'lead-vote-withdraw',
  'lead-park',
  'lead-decline',
  'reactivate',
  'override',
];

export function canTransition(s: Speaker, t: Transition, role: Role): boolean {
  if (BOARD_ONLY.includes(t) && role !== 'board') return false;
  switch (t) {
    case 'lead-vote':
    case 'lead-vote-withdraw':
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
  payload?: LockDatePayload | OverridePayload,
): Speaker {
  switch (t) {
    case 'lead-vote': {
      // `castBallot` replaces any earlier ballot from `actor`, so voting twice
      // records one ballot and cannot inflate the yes count.
      const selection = castBallot(s.selection, actor, 'yes', '', '', today);
      const { logins, unavailable } = activeBoard(config, today);
      const { decided } = decide({ board: logins, unavailable, ballots: selection.ballots });
      return {
        ...s,
        status: decided ? 'approved' : 'lead',
        selection: {
          ...selection,
          decided_on: decided ? today : s.selection.decided_on,
        },
      };
    }
    case 'lead-vote-withdraw':
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
