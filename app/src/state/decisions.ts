/**
 * The grammar of decision commits, browser side.
 *
 * There is no database. Every act this app records lands in `data/*.yml`
 * through one commit, and that commit subject is the only place the *who* and
 * the *why now* survive. So the subject is a data format:
 *
 *     data: <act> <entity> by <actor>
 *     data: <act> <entity> by <actor> (<qualifier>)
 *
 * `tools/convener_ops/commit_format.py` holds the same table and can read these
 * lines back; `tools/tests/fixtures/governance-cases.json` pins the two
 * copies together, so a phrase changed on one side fails on the other.
 *
 * P2-8, applied to prose. No caller of this module ever assembles a message:
 * there is no slot for one. A caller names a `kind` from a closed union, the
 * two identifiers, and -- only where the act has one -- a qualifier from that
 * act's own closed union. A message missing its actor, carrying two acts,
 * running to two lines, or qualified with a value its act does not admit is
 * not rejected here; it cannot be written down. `validate_messages` on the
 * Python side exists for the messages people type by hand, which is the only
 * way a malformed one can still enter the register.
 *
 * The same construction is what keeps a message from judging a volunteer. The
 * verb is never the caller's: it comes from `ACTS`, every entry of which names
 * a record -- a ballot, a nomination, a vote, an invitation, a recording. The
 * six words `tools/tests/test_inactivity.py` bans in the sweep's wording are
 * not banned here one by one; the grammatical position they would occupy does
 * not exist.
 */

import type {
  BallotValue,
  ConsentDecision,
  ObjectionResolution,
  SpeakerStatus,
} from '../data/types';
import type { FieldKey } from './phases';
import type {
  BallotPayload,
  ConsentPayload,
  OverridePayload,
  ResolutionPayload,
  Transition,
  TransitionPayload,
} from './transitions';

/**
 * An identifier the register is allowed to point at.
 *
 * Mirrors `_TOKEN` in `tools/convener_ops/commit_format.py`, and the pair is
 * pinned by `identifier_cases` in
 * `tools/tests/fixtures/governance-cases.json`. A speaker id (`spk-001`), a
 * GitHub login, or `board` -- never a person's name. A name is prose about a
 * person, and a commit subject is permanent and unrewritable: once
 * `data: open a nomination for Jane Doe (CNRS) by ada` is pushed there is no
 * taking it back, and `parse_decision` cannot read it either, so the
 * register silently loses the decision it was meant to record.
 */
const TOKEN = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;

declare const identifierBrand: unique symbol;

/** A string that has been checked against `TOKEN`. The brand is what makes
 *  the malformed line unconstructible rather than merely detected: `Decision`
 *  has no `string` slot for an identifier, so free text cannot reach
 *  `formatDecision` without going through `identifier` below and the compiler
 *  says so at the call site. */
export type Identifier = string & { readonly [identifierBrand]: true };

export function isIdentifier(value: string): value is Identifier {
  return TOKEN.test(value);
}

/** Raised when a caller tries to point the register at something that is not
 *  an identifier. Every caller in the app asks its own rule first -- see
 *  `board.nominationBlocker` -- so this is a backstop, and its sentence is
 *  one a volunteer can act on because `github/errors.ts` relays it as-is. */
export class DecisionRejected extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'DecisionRejected';
  }
}

/** The only way to obtain an `Identifier`. */
export function identifier(value: string): Identifier {
  if (!isIdentifier(value)) {
    throw new DecisionRejected(
      `"${value}" is not an identifier. The register points at records -- a speaker ` +
        'reference, a GitHub username, or the board -- never at a person by name.',
    );
  }
  return value;
}

/** Acts that take no qualifier: the kind alone says what was recorded. */
export type PlainDecisionKind =
  | 'ballot-withdraw'
  | 'lead-park'
  | 'lead-decline'
  | 'reactivate'
  | 'vote-reopen'
  | 'send-invitation'
  | 'invited-accept'
  | 'invited-decline'
  | 'lock-date'
  | 'publication-approve'
  | 'publication-object'
  | 'finalize-archive'
  | 'nomination-open'
  | 'nomination-object'
  | 'nomination-withdraw-objection'
  | 'nomination-resolve'
  | 'speaker-create'
  | 'speaker-delete'
  | 'date-propose';

/**
 * One act of the register.
 *
 * The four acts that carry a qualifier each name the union it comes from, so
 * `{ kind: 'ballot-cast', detail: 'lift' }` is a type error rather than a
 * line somebody has to notice in a log two years from now, and a plain kind
 * has no `detail` property to set at all.
 */
/**
 * What a member recorded about their own availability.
 *
 * Not a field of the data model -- `BoardMember.unavailable_until` holds a
 * day or `''` -- but the closed pair of things the act can say, and the
 * register needs the pair rather than the day: `data: record the
 * availability of ada by ada (away)` is a sentence about the record that
 * changed, in the same shape as every other decision. The day itself is in
 * the diff, exactly as `lock-date`'s date is.
 */
export type AvailabilityChange = 'away' | 'back';

/**
 * What a speaker's reply about one offered day said.
 *
 * `accepted` and `declined` are `DateAnswer`; `cleared` is the third thing
 * the act can record and the record cannot -- a reply taken back, which
 * `data/speakers.yml` stores as `answer: ''` and which reads as "not answered
 * yet" once it is written. The register needs the three because the act is
 * what happened, not what the field now holds.
 *
 * The day itself is not here, and not in the subject. It is in the diff,
 * exactly as `lock-date`'s date and `availability-set`'s day are -- and here
 * it matters more than there: `candidate_dates` is classified
 * `NEVER_PUBLISHED` (`state/consent.ts`) because which evenings a researcher
 * turned down is their availability and not the programme, and a commit
 * subject is the one place in this repository nothing can be taken back
 * from.
 */
export type DateReply = 'accepted' | 'declined' | 'cleared';

export type Decision =
  | { kind: 'availability-set'; entity: Identifier; actor: Identifier; detail: AvailabilityChange }
  | { kind: 'ballot-cast'; entity: Identifier; actor: Identifier; detail: BallotValue }
  | { kind: 'consent-set'; entity: Identifier; actor: Identifier; detail: ConsentDecision }
  | {
      kind: 'publication-resolve';
      entity: Identifier;
      actor: Identifier;
      detail: ObjectionResolution;
    }
  | { kind: 'date-answer'; entity: Identifier; actor: Identifier; detail: DateReply }
  | { kind: 'override'; entity: Identifier; actor: Identifier; detail: SpeakerStatus }
  | { kind: PlainDecisionKind; entity: Identifier; actor: Identifier };

export type DecisionKind = Decision['kind'];

/** The imperative phrase each act is written with, ending in the preposition
 *  that introduces the record. Mirrors `ACTS` in `commit_format.py`. */
export const ACTS: Record<DecisionKind, string> = {
  'availability-set': 'record the availability of',
  'ballot-cast': 'record a ballot on',
  'ballot-withdraw': 'withdraw a ballot on',
  'lead-park': 'park',
  'lead-decline': 'decline',
  reactivate: 'reopen the review of',
  'vote-reopen': 'reopen the vote on',
  'send-invitation': 'send the invitation for',
  'invited-accept': 'record an accepted invitation for',
  'invited-decline': 'record a declined invitation for',
  'date-propose': 'propose a date for',
  'date-answer': 'record a date reply for',
  'lock-date': 'lock the date of',
  'consent-set': 'record the recording consent of',
  'publication-approve': 'approve publication of',
  'publication-object': 'record an objection to publishing',
  'publication-resolve': 'resolve the objections on',
  'finalize-archive': 'publish the recording of',
  'nomination-open': 'open a nomination for',
  'nomination-object': 'record an objection to the nomination of',
  'nomination-withdraw-objection': 'withdraw an objection to the nomination of',
  'nomination-resolve': 'settle the nomination of',
  override: 'override the status of',
  'speaker-create': 'record a new lead for',
  'speaker-delete': 'delete the record of',
};

declare const subjectBrand: unique symbol;

/**
 * A commit subject this module assembled.
 *
 * The same move as `Identifier`, one level up. `mutateSpeakers` and
 * `mutateConfig` (`data/DataContext.tsx`) take a `Subject`, not a `string`,
 * so a subject written anywhere else does not compile -- however it is
 * spelled. That matters because the alternatives are all spellings of one
 * defect: `'data: add lead ' + name` concatenated rather than interpolated,
 * a template split so the prefix sits in its own chunk, a `const prefix =
 * 'data:'` in a helper module of its own. A source walk recognises the
 * spellings somebody thought to write down; a brand recognises the position,
 * and the position is what the rule is about. The walk in
 * `app/tests/decisions.test.ts` stays as the second net, for the one route
 * around the brand a compiler cannot close -- a cast.
 */
export type Subject = string & { readonly [subjectBrand]: true };

declare const itemKeyBrand: unique symbol;

/** A journey key: the name of one line of the runbook, as `phaseItems`
 *  gives it. `promotion/forum`, `scheduled/T-30/visuals`. */
export type ItemKey = string & { readonly [itemKeyBrand]: true };

/** The shape of a journey key -- slash-separated segments of word
 *  characters, dots and hyphens. No space, no `=`, no punctuation a sentence
 *  would carry, so a field value cannot pass for a key even where the caller
 *  holds an untyped `string` from a DOM event. */
const ITEM_KEY = /^[A-Za-z0-9][A-Za-z0-9._-]*(?:\/[A-Za-z0-9][A-Za-z0-9._-]*)*$/;

/** The only way to obtain an `ItemKey`. */
export function itemKey(value: string): ItemKey {
  if (!ITEM_KEY.test(value)) {
    throw new DecisionRejected(
      `"${value}" is not a line of the journey. A subject names the line that ` +
        'moved -- the key the runbook gives it -- never what was written on it.',
    );
  }
  return value as ItemKey;
}

/**
 * Which part of a record a bookkeeping edit moved.
 *
 * `what` used to be a bare `string`, with a sentence in the doc comment
 * asking callers not to put a value in it. Prose is not a control: widening
 * `SpeakerPage.tsx`'s `set ${k}` to `set ${k}=${v}` put the typed field
 * value into a permanent commit subject and left every test green. So the
 * parameter is a closed union instead, in the same shape as `Decision`: five
 * parts, and where a part names something, the name is a `FieldKey` from the
 * journey's own union or an `ItemKey` checked against `ITEM_KEY`. There is
 * no slot a value fits in -- `runbook-box`'s `ticked` is the box's own state
 * and says nothing about anyone.
 *
 * The rendered phrases are pinned against `commit_message_ordinary` in
 * `tools/tests/fixtures/governance-cases.json`, so a reword here fails on
 * the Python side too (D-14 rule 3).
 */
export type Edit =
  | { part: 'admin-fields' }
  | { part: 'post-archive-metrics' }
  | { part: 'field'; key: FieldKey }
  | { part: 'runbook-box'; key: ItemKey; ticked: boolean }
  | { part: 'owner'; key: ItemKey; cleared: boolean };

/** Total: every value `Edit` admits renders to one phrase, and no phrase
 *  takes anything the caller wrote freehand. */
function editPart(edit: Edit): string {
  switch (edit.part) {
    case 'admin-fields':
      return 'admin edit';
    case 'post-archive-metrics':
      return 'update post-archive metrics';
    case 'field':
      return `set ${edit.key}`;
    case 'runbook-box':
      return `runbook ${edit.key}=${edit.ticked}`;
    case 'owner':
      return edit.cleared ? `owner cleared on ${edit.key}` : `owner for ${edit.key}`;
  }
}

/**
 * The subject for a `data:` commit that records no decision.
 *
 * Five screens write to `data/speakers.yml` without deciding anything: a
 * runbook box ticked, a talk detail typed in, a name put against a line of
 * the journey, the post-archive numbers, and the admin form saving the fields
 * it was given. They are bookkeeping -- the file catching up with something
 * that already happened elsewhere -- and `validate_messages` is right to leave
 * them alone: a grammar that made every commit an obstacle would be abandoned
 * inside a week (`tools/convener_ops/commit_format.py`).
 *
 * They are routed through here all the same, and not because the string needs
 * building. It is so that the next reader finds a decision about them rather
 * than five ad-hoc template literals that read as a pattern to copy; and so
 * that the one rule they do share with the register is stated in one place:
 * the subject points at a record -- `entity` is an `Identifier`, so a name
 * cannot reach it -- and `what` says which part of it moved, never who a
 * person is and never a value that discloses something about a third party. A
 * commit subject is permanent and unrewritable whether or not a grammar reads
 * it back.
 *
 * `app/tests/decisions.test.ts` checks that no other `data:` subject is
 * assembled anywhere in `src/`, and `Subject` above is what makes that check
 * a backstop rather than the only net.
 */
export function dataEdit(entity: Identifier, edit: Edit): Subject {
  return `data: ${entity} ${editPart(edit)}` as Subject;
}

/** The exact line to commit. The `Decision` type admits nothing malformed, so
 *  this is total: every value it can be given produces a line
 *  `parse_decision` reads back to that same value. */
export function formatDecision(d: Decision): Subject {
  const line = `data: ${ACTS[d.kind]} ${d.entity} by ${d.actor}`;
  return ('detail' in d ? `${line} (${d.detail})` : line) as Subject;
}

/**
 * The decision a `Transition` records, with its qualifier taken from the very
 * payload the transition is applied with -- so the line cannot say `abstain`
 * about a ballot cast as `recused`. The four qualified transitions are the
 * four that carry a closed vocabulary in their payload; the rest say
 * everything they have to say with their kind.
 */
export function transitionDecision(
  t: Transition,
  entity: Identifier,
  actor: Identifier,
  payload?: TransitionPayload,
): Decision {
  switch (t) {
    case 'ballot-cast':
      return { kind: t, entity, actor, detail: (payload as BallotPayload).value };
    case 'consent-set':
      return { kind: t, entity, actor, detail: (payload as ConsentPayload).consent };
    case 'publication-resolve':
      return { kind: t, entity, actor, detail: (payload as ResolutionPayload).resolution };
    case 'override':
      return { kind: t, entity, actor, detail: (payload as OverridePayload).status };
    default:
      return { kind: t, entity, actor };
  }
}
