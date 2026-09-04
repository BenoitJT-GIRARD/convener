import type {
  BallotValue,
  Config,
  ConsentDecision,
  ObjectionResolution,
  Speaker,
  SpeakerStatus,
} from '../data/types';
import { BallotRejected, castBallot, withdrawBallot } from './ballots';
import { activeBoard, isBoardMember } from './board';
import { DateRejected, acceptedDates, answerDate, lockDate } from './dates';
import { PublicationBlocked, canArchive, decide, standingObjections } from './governance';

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
  | 'consent-set'
  | 'publication-approve'
  | 'publication-object'
  | 'publication-resolve'
  | 'vote-reopen'
  | 'override';

/** What the lock-in is applied with. There is no `time`: the hour comes from
 *  the slot the speaker accepted (`state/dates.ts`), so a lock-in cannot name
 *  an evening other than the one that was offered and agreed.
 *
 *  `invited-accept` is applied with the same shape and ignores
 *  `edition_code`: an acceptance is the acceptance *of an evening*, and the
 *  edition number is not chosen until the date is frozen a status later. */
export interface LockDatePayload {
  date: string;
  edition_code: string;
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

/**
 * Relaying what the speaker actually answered about their recording (G-06).
 *
 * `ConsentDecision` is `granted | refused` and nothing else. `pending` is a
 * legal stored value but is absent from the vocabulary a transition can
 * write, so there is no way to express "assume, for now" and no way for an
 * elapsed delay to arrive at one: the only values this carries are answers a
 * named person heard the speaker give.
 */
export interface ConsentPayload {
  consent: ConsentDecision;
}

/** One board member's objection to publishing a recording (G-07). The reason
 *  is required for the same reason a recusal's is: it stops publication of a
 *  named researcher's talk, so the register has to say why. */
export interface ObjectionPayload {
  reason: string;
}

/** Closing the objections that stand on a recording. `resolution` is
 *  `lift | withhold` -- there is deliberately no value meaning "publish", so
 *  no resolution can bypass `canArchive`. `note` says what was decided and
 *  is kept alongside the original objection. */
export interface ResolutionPayload {
  resolution: ObjectionResolution;
  note: string;
}

/** Everything a transition can be applied with. Named once so
 *  `state/decisions.ts` writes the commit line from the very same value
 *  `applyTransition` acts on, rather than from a parallel guess at it. */
export type TransitionPayload =
  | LockDatePayload
  | OverridePayload
  | BallotPayload
  | HiddenCoiPayload
  | ConsentPayload
  | ObjectionPayload
  | ResolutionPayload;

const BOARD_ONLY: Transition[] = [
  'ballot-cast',
  'ballot-withdraw',
  'lead-park',
  'lead-decline',
  'reactivate',
  'consent-set',
  'publication-approve',
  'publication-object',
  'publication-resolve',
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
      // Also reachable from `archived` when the recording is not currently
      // published -- an objection took it down and was later lifted. It goes
      // back through this one gated transition rather than through a second
      // path that could publish on its own authority.
      return s.status === 'delivered' || (s.status === 'archived' && s.publication.outcome !== 'published');
    case 'consent-set':
      // Recordable from the moment there is a recording to talk about, and
      // never closed: a speaker may withdraw permission at any time (G-06).
      return s.status === 'delivered' || s.status === 'archived';
    case 'publication-approve':
      return s.status === 'delivered' || s.status === 'archived';
    case 'publication-object':
      return s.status === 'delivered' || s.status === 'archived';
    case 'publication-resolve':
      return (
        (s.status === 'delivered' || s.status === 'archived') &&
        (standingObjections(s.publication).length > 0 || s.publication.outcome === 'withheld')
      );
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
  payload?: TransitionPayload,
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
    case 'invited-accept': {
      // One gesture, not two. The speaker's yes and the evening they said it
      // about used to be separate controls -- a global *Speaker accepted*
      // beside a per-date *they accepted* -- and a record could carry either
      // without the other: accepted with no evening named, or an evening
      // agreed on a record still reading `invited`. The click on the date is
      // now both, so neither half is expressible on its own.
      const p = payload as LockDatePayload | undefined;
      if (!p?.date) {
        throw new DateRejected(
          'An acceptance is an acceptance of one evening. Click the date the speaker agreed ' +
            'to, so the record shows which one it was.',
        );
      }
      // `answerDate` refuses a day nobody was offered, so an acceptance
      // cannot appear against an evening this record never put to them.
      return { ...answerDate(s, p.date, 'accepted').speaker, status: 'confirmed' };
    }
    case 'invited-decline':
      return { ...s, status: 'decline-speaker' };
    case 'lock-date': {
      // The date is not taken from the payload and written: it is looked up
      // among the ones this record says the speaker accepted, and only that
      // lookup can produce the `AcceptedDate` that `lockDate` takes. A date
      // the speaker never agreed to has no route through here -- see
      // `state/dates.ts`. The lookup reads `s`, the value `mutate` handed
      // this transformation, so a reply recorded between the read and the
      // write is the one that decides.
      const p = payload as LockDatePayload;
      const accepted = acceptedDates(s).find(d => d === p.date);
      if (!accepted) {
        throw new DateRejected(
          `${p.date} is not a date this speaker has accepted. Record their reply first — ` +
            'locking a date commits them to that evening.',
        );
      }
      return lockDate(s, accepted, p.edition_code);
    }
    case 'finalize-archive': {
      // The single writer of `outcome: 'published'` in this codebase, and it
      // cannot run unless the gate opens. Every contradictory shape the
      // validator used to have to catch -- refused consent published,
      // published with an objection standing, published with no approval,
      // published inside the objection window -- is unreachable because the
      // only door into `published` is this one, and this one asks first.
      const gate = canArchive(s, config, today);
      if (!gate.allowed) throw new PublicationBlocked(gate.reason);
      return {
        ...s,
        status: 'archived',
        publication: { ...s.publication, outcome: 'published' },
      };
    }
    case 'consent-set': {
      const p = payload as ConsentPayload;
      // A refusal is not only a block, it is a takedown (G-06): it
      // *un-publishes* on the spot, so the pair (refused, published) cannot
      // exist even for an instant, on any ordering of events.
      //
      // Un-published, not `withheld`. `withheld` is the board resolving to
      // hold a recording back, and the board resolves nothing when a speaker
      // withdraws their permission -- writing it here made `boardBlocker`
      // tell a volunteer "The board decided to withhold this recording"
      // about a decision nobody took, and left the record stuck there when
      // the speaker changed their mind again: clearing it would have meant
      // resolving objections that do not exist. The takedown belongs to the
      // consent field, which is where it is now read from
      // (`tools/convener_ops/publication/public_data.py::recording_withheld`).
      //
      // Granting consent publishes nothing by itself -- it clears one of two
      // permissions, and `finalize-archive` still has to be run by a person,
      // which asks the whole gate again.
      const refused = p.consent === 'refused';
      return {
        ...s,
        publication: {
          ...s.publication,
          consent: p.consent,
          outcome:
            refused && s.publication.outcome === 'published' ? '' : s.publication.outcome,
        },
      };
    }
    case 'publication-approve':
      // A named member, on a named day. `actor` comes from the signed-in
      // session, so no scheduled job can produce an approval -- and an
      // approval is what starts the objection window running.
      return {
        ...s,
        publication: { ...s.publication, approved_by: actor, approved_on: today },
      };
    case 'publication-object': {
      const p = payload as ObjectionPayload;
      const reason = p.reason.trim();
      if (reason === '') {
        throw new PublicationBlocked(
          'An objection to publishing a recording needs a written reason. ' +
            'Add a short note saying what the problem is before submitting.',
        );
      }
      return {
        ...s,
        publication: {
          ...s.publication,
          // Replaces this member's own standing objection rather than
          // stacking a second one; everyone else's is left untouched, and
          // resolved ones stay as the record of what happened.
          objections: [
            ...s.publication.objections.filter(o => !(o.member === actor && !o.resolved_on)),
            { member: actor, reason, date: today, resolved_on: '' },
          ],
          // An objection against a recording that is already online takes it
          // down while the objection is examined. This is what keeps
          // (published, objection standing) out of reach in the one ordering
          // the gate cannot cover, publication first and objection after.
          //
          // Un-published, not `withheld`, for the same reason as above: one
          // member objecting is not the board resolving anything, and the
          // objection recorded just above is what says why the recording is
          // offline. `publication-resolve` is reachable on a standing
          // objection, so lifting it is a matter of resolving the objection
          // that actually exists.
          outcome: s.publication.outcome === 'published' ? '' : s.publication.outcome,
        },
      };
    }
    case 'publication-resolve': {
      const p = payload as ResolutionPayload;
      const note = p.note.trim();
      if (note === '') {
        throw new PublicationBlocked(
          'Resolving an objection needs a written note saying what was decided. ' +
            'One line is enough, and it is kept next to the objection.',
        );
      }
      const objections = s.publication.objections.map(o =>
        o.resolved_on
          ? o
          : {
              ...o,
              // Appended rather than replaced: the register adds, it never
              // rewrites, so the objection keeps saying what it said.
              reason: `${o.reason} (resolved by ${actor} on ${today}: ${note})`,
              resolved_on: today,
            },
      );
      // `ObjectionResolution` has no value that publishes. Lifting returns
      // the record to the gate -- `finalize-archive` still has to be run, and
      // still asks `canArchive` -- while withholding is a decision the board
      // has to lift explicitly before anything can move again.
      const outcome =
        p.resolution === 'withhold'
          ? ('withheld' as const)
          : s.publication.outcome === 'withheld'
            ? ('' as const)
            : s.publication.outcome;
      return { ...s, publication: { ...s.publication, objections, outcome } };
    }
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
      // The escape hatch, and deliberately a narrow one: it writes `status`
      // and touches nothing else. Forcing `archived` therefore skips
      // `canArchive` -- that is the point of an override -- but it leaves
      // `publication` exactly as it was, so it cannot produce
      // `outcome: 'published'`, and `public_data.recording_withheld` reads
      // that outcome rather than the status. An override moves a record; it
      // is not a way to put a recording on the open web.
      const p = payload as OverridePayload;
      return { ...s, status: p.status, publication: s.publication };
    }
  }
}
