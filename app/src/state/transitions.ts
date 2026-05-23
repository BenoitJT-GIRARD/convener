import type { Speaker, SpeakerStatus } from '../data/types';

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
  | 'auto-deliver'
  | 'mark-wrapped'
  | 'auto-archive'
  | 'override';

export interface LockDatePayload {
  date: string;
  edition_code: string;
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
      return s.status === 'approved';
    case 'invited-accept':
    case 'invited-decline':
      return s.status === 'invited';
    case 'lock-date':
      return s.status === 'confirmed';
    case 'mark-wrapped':
      return s.status === 'delivered';
    case 'auto-deliver':
      return s.status === 'scheduled';
    case 'auto-archive':
      return s.status === 'wrapped';
    case 'override':
      return true;
    default:
      return false;
  }
}

export function applyTransition(
  s: Speaker,
  t: Transition,
  actor: string,
  voteThreshold: number,
  today: string,
  payload?: LockDatePayload | OverridePayload,
): Speaker {
  switch (t) {
    case 'lead-vote': {
      const votes = Array.from(new Set([...s.selection.votes_for, actor]));
      const decided = votes.length >= voteThreshold;
      return {
        ...s,
        status: decided ? 'approved' : 'lead',
        selection: {
          votes_for: votes,
          decided_on: decided ? today : s.selection.decided_on,
        },
      };
    }
    case 'lead-vote-withdraw': {
      const votes = s.selection.votes_for.filter(v => v !== actor);
      return { ...s, selection: { ...s.selection, votes_for: votes } };
    }
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
      return {
        ...s,
        status: 'confirmed',
        runbook_progress: { ...s.runbook_progress, 'invited/response-logged': true },
      };
    case 'invited-decline':
      return {
        ...s,
        status: 'decline-speaker',
        runbook_progress: { ...s.runbook_progress, 'invited/response-logged': true },
      };
    case 'lock-date': {
      const p = payload as LockDatePayload;
      return {
        ...s,
        status: 'scheduled',
        date: p.date,
        edition_code: p.edition_code,
        runbook_progress: { ...s.runbook_progress, 'confirmed/date-locked': true },
      };
    }
    case 'auto-deliver':
      return { ...s, status: 'delivered' };
    case 'mark-wrapped':
      return { ...s, status: 'wrapped' };
    case 'auto-archive':
      return { ...s, status: 'archived' };
    case 'override': {
      const p = payload as OverridePayload;
      return { ...s, status: p.status };
    }
  }
}
