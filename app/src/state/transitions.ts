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
import {
  PublicationBlocked,
  canArchive,
  decide,
  publicationRefused,
  standingObjections,
} from './governance';
import { deliveryRecordable } from './derived';

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
  | 'mark-delivered'
  | 'cancel-edition'
  | 'finalize-archive'
  | 'archive-unpublished'
  | 'consent-set'
  | 'publication-approve'
  | 'publication-object'
  | 'publication-resolve'
  | 'publication-reopen'
  | 'vote-reopen'
  | 'override';

/** What the lock-in is applied with. There is no `time`: the hour comes from
 *  the slot the speaker accepted (`state/dates.ts`), so a lock-in cannot name
 *  an evening other than the one that was offered and agreed.
 *
 *  `invited-accept` is applied with the same shape and ignores
 *  `edition_code` and `zoom_link`: an acceptance is the acceptance *of an
 *  evening*, and neither the edition number nor the room is settled until the
 *  date is frozen a status later.
 *
 *  `zoom_link` rides along rather than being written on its own because the
 *  two belong to one act. `lockBlockers` refuses a lock-in with no way into
 *  the room, and the link the volunteer just typed is what satisfies it -- so
 *  it has to be part of the value the precondition is judged against, not a
 *  second write that might not follow. It is the record's own link; an empty
 *  string is the ordinary answer on an instance whose series instructions
 *  carry the address for every session (D-06). */
export interface LockDatePayload {
  date: string;
  edition_code: string;
  zoom_link: string;
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
 * Relaying what the speaker actually answered about their recording (G-07).
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

/** One board member's objection to publishing a recording (G-08). The reason
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
  | ResolutionPayload
  | CancelPayload;

/** Why an announced edition was cancelled, as the register records it.
 *
 *  A closed vocabulary, mirrored in `commit_format.py::QUALIFIERS` and pinned
 *  across the boundary by `tools/tests/fixtures/governance-cases.json`. It is
 *  closed for the reason every other qualifier is: a commit subject is
 *  permanent and unrewritable, and a reason typed at a keyboard is the one
 *  thing in this grammar that could name a person's illness.
 *
 *  Four, and deliberately no catch-all. A vocabulary with an `other` in it is
 *  a vocabulary that stops being read.
 */
export const CANCELLATION_REASONS = [
  'speaker-withdrew',
  'board-withdrew',
  'date-unworkable',
  'series-paused',
] as const;
export type CancellationReason = (typeof CANCELLATION_REASONS)[number];

export interface CancelPayload {
  reason: CancellationReason;
}

const BOARD_ONLY: Transition[] = [
  'ballot-cast',
  // Withdrawing a commitment the series has already made in public, to a
  // speaker and to everyone who registered. The same weight as declining a
  // lead, and the same hand.
  'cancel-edition',
  'ballot-withdraw',
  'lead-park',
  'lead-decline',
  'reactivate',
  'consent-set',
  'publication-approve',
  'publication-object',
  'publication-resolve',
  'publication-reopen',
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
    case 'mark-delivered':
      // Offered from the day before, and only on a dated record. The day is
      // read by `applyTransition` as well, which is where a click that
      // arrives before it is refused; this is what decides whether the
      // control is drawn at all.
      return s.status === 'scheduled' && !!s.date;
    case 'cancel-edition':
      // `scheduled` and nowhere else. Before it there is nothing announced to
      // withdraw -- a confirmed speaker who falls through is the date
      // negotiation's business, and a lead is `lead-decline`'s. After it the
      // talk has happened, and a talk that happened cannot be cancelled.
      return s.status === 'scheduled';
    case 'finalize-archive':
      // `delivered` and nowhere else. It used to be reachable from
      // `archived` as well, for the record whose recording an objection had
      // taken down and a resolution had since cleared -- which meant an
      // archived record still carrying the gate that publishes, on a page
      // whose whole meaning is that the question is settled. That record
      // now comes back through `publication-reopen` first, so there is one
      // status the publication question can be open in and one door into
      // it.
      return s.status === 'delivered';
    case 'archive-unpublished':
      // Only where somebody has actually said no. A record still waiting on
      // an answer has a gate that will open; this is the door for the one
      // that will not.
      return s.status === 'delivered' && publicationRefused(s.publication);
    case 'consent-set':
      // Recordable from the moment there is a recording to talk about, and
      // never closed: a speaker may withdraw permission at any time (G-07).
      return s.status === 'delivered' || s.status === 'archived';
    case 'publication-approve':
    case 'publication-object':
      // The board's half of the gate, and `delivered` is the whole of where
      // it is asked. An archived record reports what the board decided
      // (`components/ClosedRecord.tsx`); it does not offer the board a way
      // to decide it again in place.
      return s.status === 'delivered';
    case 'publication-resolve':
      return (
        s.status === 'delivered' &&
        (standingObjections(s.publication).length > 0 || s.publication.outcome === 'withheld')
      );
    case 'publication-reopen':
      // The one control an archived event carries, and it is a door rather
      // than a decision: it puts the record back where the publication
      // question can be asked, and writes nothing about the answer. The
      // same shape `reactivate` gives a parked lead.
      return s.status === 'archived';
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
      // Judged against the record *including* the room about to be written.
      // The volunteer typing a link in the panel is what satisfies
      // `lockBlockers`, and a precondition that read the stored value would
      // refuse the very write that fixes it.
      const withRoom = p.zoom_link === s.zoom_link ? s : { ...s, zoom_link: p.zoom_link };
      return lockDate(withRoom, accepted, p.edition_code, config);
    }
    case 'cancel-edition':
      // The status and nothing else. The edition code stays on the record and
      // stays consumed: it was announced under that code, and a second
      // edition wearing it would make two different talks share one address.
      // `next_edition_number` is a high-water mark for exactly this reason
      // (`state/agenda.ts::raisedEditionCounter`), so nothing has to be
      // wound back here.
      //
      // What the public sees follows on its own: `cli/publication.py` filters
      // the events feed to `scheduled`, and `mint-event-keys.yml` selects on
      // the same value, so a cancelled edition leaves the showcase and stops
      // being minted for without either of them learning a new word.
      return { ...s, status: 'cancelled' };
    case 'mark-delivered': {
      // The hand on the transition the clock used to make on its own. It
      // writes exactly what `tools/convener_ops/maintenance/sweep.py` writes
      // -- one status, nothing else -- so the two paths cannot leave two
      // different shapes of record behind.
      if (!deliveryRecordable(s, today)) {
        throw new DateRejected(
          `This talk is on ${s.date || 'a day the record does not give'}, and it can be ` +
            'recorded as delivered from the day before. Until then the runbook above is ' +
            'still the work in front of you.',
        );
      }
      return { ...s, status: 'delivered' };
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
    case 'publication-reopen':
      // Status and nothing else. What was recorded about the publication
      // stays recorded -- the consent, the approval, the objections and
      // their resolutions are the history of this record, and reopening it
      // is not an act of the board about any of them. The gate reads them
      // all again the moment the record is back in front of it.
      return { ...s, status: 'delivered' };
    case 'archive-unpublished': {
      // Closing a record whose recording is not going online. It writes the
      // status and nothing else -- `publication` is carried through
      // untouched, so this transition cannot produce `outcome: 'published'`
      // and cannot clear a refusal on its way past one.
      //
      // A record whose permissions are merely unanswered has no route here:
      // that is a wait, and turning a wait into a closed record is exactly
      // what the consent gate exists to stop.
      if (!publicationRefused(s.publication)) {
        throw new PublicationBlocked(
          'Nobody has refused publication of this recording, so there is nothing to ' +
            'archive around. Record the answer you have — the speaker’s, or the ' +
            'board’s — and the gate above will say what is left.',
        );
      }
      return { ...s, status: 'archived', publication: s.publication };
    }
    case 'consent-set': {
      const p = payload as ConsentPayload;
      // A refusal is not only a block, it is a takedown (G-07): it
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
