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
export type Decision =
  | { kind: 'ballot-cast'; entity: string; actor: string; detail: BallotValue }
  | { kind: 'consent-set'; entity: string; actor: string; detail: ConsentDecision }
  | { kind: 'publication-resolve'; entity: string; actor: string; detail: ObjectionResolution }
  | { kind: 'override'; entity: string; actor: string; detail: SpeakerStatus }
  | { kind: PlainDecisionKind; entity: string; actor: string };

export type DecisionKind = Decision['kind'];

/** The imperative phrase each act is written with, ending in the preposition
 *  that introduces the record. Mirrors `ACTS` in `commit_format.py`. */
export const ACTS: Record<DecisionKind, string> = {
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
  'nomination-resolve': 'apply the nominations due on',
  override: 'override the status of',
  'speaker-delete': 'delete the record of',
};

/** The board taken as a whole, for the one act that is not about a single
 *  record. Never a person's name -- the register points at records. */
export const BOARD_ENTITY = 'board';

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
  entity: string,
  actor: string,
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
