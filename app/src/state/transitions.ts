import type { BallotValue, Config, Speaker, SpeakerStatus } from '../data/types';
import { BallotRejected, castBallot, withdrawBallot } from './ballots';
import { activeBoard, isBoardMember } from './board';
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
  | 'vote-reopen'
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

/** Recording a conflict of interest a voter did *not* declare when they
 *  voted -- see `vote-reopen` in `applyTransition`. `member` is the board
 *  login whose ballot was cast under the concealed conflict; `reason` says
 *  what the conflict was, and is required for exactly the same reason a
 *  recusal's is: it changes how many yes votes this lead needs, so the
 *  register has to say why. */
export interface HiddenCoiPayload {
  member: string;
  reason: string;
}

const BOARD_ONLY: Transition[] = [
  'ballot-cast',
  'ballot-withdraw',
  'lead-park',
  'lead-decline',
  'reactivate',
  'vote-reopen',
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
    case 'vote-reopen':
      // Everything except the three outcomes a reopening could not undo: a
      // talk already given (`delivered`, `archived`) is history, and a
      // speaker who declined (`decline-speaker`) removed themselves, so
      // there is no board acceptance left to cancel. Anywhere else -- the
      // vote still open, or the speaker already invited, confirmed or on
      // the calendar -- the acceptance is still live and can be withdrawn.
      return (
        s.status !== 'delivered' && s.status !== 'archived' && s.status !== 'decline-speaker'
      );
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
  payload?: LockDatePayload | OverridePayload | BallotPayload | HiddenCoiPayload,
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
    case 'vote-reopen': {
      // A conflict of interest that was never declared comes to light.
      //
      // The acceptance this board reached is cancelled, full stop. It was
      // obtained on a false basis -- the denominator included someone who
      // should not have been in it -- so it is not re-examined and not put
      // back to the same people for confirmation: the speaker returns to
      // `lead` and the window reopens from today. Whether the board approves
      // them again is a fresh question, answered by fresh ballots.
      //
      // This is deliberately NOT re-decided here from the new count, even
      // when the count would still clear the (now lower) bar. Re-deciding
      // inside this transition would mean an undeclared conflict could be
      // recorded and the acceptance survive untouched, which is the opposite
      // of the rule. The recomputed tally is shown immediately by
      // `ActionButtons`, and the next `ballot-cast` can carry the vote again.
      //
      // Only a signed-in board member reaches this (`BOARD_ONLY`), and
      // `actor` is written into the register alongside the reason: no
      // scheduled job has an author, so none can produce this state.
      const p = payload as HiddenCoiPayload;
      const reason = p.reason.trim();
      if (reason === '') {
        throw new BallotRejected(
          'Recording an undeclared conflict of interest needs a written reason. ' +
            'Add a short note explaining the conflict before submitting.',
        );
      }
      if (!isBoardMember(config, p.member, today)) {
        throw new BallotRejected(
          `${p.member} is not an active board member, so there is no ballot of theirs ` +
            'to reopen. Check the name and try again.',
        );
      }
      const existing = s.selection.ballots.find(b => b.voter === p.member);
      if (existing?.value === 'recused') {
        throw new BallotRejected(
          `${p.member} already recused themselves on this lead, so nothing was concealed. ` +
            'Their ballot is already out of the count.',
        );
      }
      const selection = castBallot(
        s.selection,
        p.member,
        'recused',
        // Their own comment is kept rather than blanked: the register is a
        // historical record, and one member's action should not erase
        // another's words about the same lead.
        existing?.comment ?? '',
        `${reason} (not declared when the ballot was cast; recorded by ${actor} on ${today})`,
        today,
      );
      return {
        ...s,
        // Cancelled, not re-decided. `date` and `edition_code` are left as
        // they are: a `lead` is outside `agenda.findOverlaps`' public
        // statuses, so a stale date blocks nothing, and keeping it records
        // which slot had been planned if the board approves again.
        status: 'lead',
        selection: { ...selection, opened_on: today, decided_on: '' },
      };
    }
    case 'override': {
      const p = payload as OverridePayload;
      return { ...s, status: p.status };
    }
  }
}
