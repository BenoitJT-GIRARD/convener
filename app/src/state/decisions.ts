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
  | 'speaker-delete';

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
  'speaker-delete': 'delete the record of',
};

/** The exact line to commit. The `Decision` type admits nothing malformed, so
 *  this is total: every value it can be given produces a line
 *  `parse_decision` reads back to that same value. */
export function formatDecision(d: Decision): string {
  const line = `data: ${ACTS[d.kind]} ${d.entity} by ${d.actor}`;
  return 'detail' in d ? `${line} (${d.detail})` : line;
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
