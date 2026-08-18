export type SpeakerStatus =
  | 'lead' | 'approved' | 'invited' | 'confirmed'
  | 'scheduled' | 'delivered' | 'archived'
  | 'parked' | 'decline-board' | 'decline-speaker';

export const GENDERS = ['M', 'F', 'NB', 'undisclosed'] as const;
export type Gender = (typeof GENDERS)[number];
export function isGender(v: string): v is Gender {
  return (GENDERS as readonly string[]).includes(v);
}

export const CAREER_STAGES = [
  'phd', 'postdoc', 'independent', 'group-leader', 'other', 'undisclosed',
] as const;
export type CareerStage = (typeof CAREER_STAGES)[number];
export function isCareerStage(v: string): v is CareerStage {
  return (CAREER_STAGES as readonly string[]).includes(v);
}

export interface SpeakerMetrics {
  registrations: number | null;
  live_peak: number | null;
  youtube_views_30d: number | null;
  forum_replies: number | null;
}

export const BALLOT_VALUES = ['yes', 'abstain', 'recused'] as const;
export type BallotValue = (typeof BALLOT_VALUES)[number];
export function isBallotValue(v: string): v is BallotValue {
  return (BALLOT_VALUES as readonly string[]).includes(v);
}

export interface Ballot {
  voter: string;
  value: BallotValue;
  /** Optional on every ballot. Asked for by the Board so a decision can be read
   *  years later without asking whoever cast it. */
  comment: string;
  /** Required when value is 'recused'. A recusal without a written reason is
   *  not recorded — see governance.ts. */
  coi_reason: string;
  date: string;
}

export interface SpeakerSelection {
  ballots: Ballot[];
  opened_on: string;
  decided_on: string;
}

/** `''` is a real stored value, not an oversight: `scripts/migrate_v3.py`
 *  writes it for every speaker whose status never reached a publishable
 *  state, and `tools/convener_ops/validate.py` accepts it. It is spelled out here
 *  so that code reading `consent` has to face it -- neither `''` nor
 *  `pending` is an agreement, and the gate treats them identically. */
export type PublicationConsent = 'granted' | 'refused' | 'pending' | '';

/**
 * What a board member may actually *decide* about a speaker's consent.
 *
 * `pending` is a legal stored value -- it is where the migration starts every
 * delivered speaker -- but it is deliberately absent from this vocabulary, so
 * no transition can write it. Consent is only ever moved by relaying an answer
 * the speaker actually gave (P2-8: the ambiguous value is not guarded, it does
 * not exist here to be written).
 */
export const CONSENT_DECISIONS = ['granted', 'refused'] as const;
export type ConsentDecision = (typeof CONSENT_DECISIONS)[number];

/**
 * How a board objection to publishing is closed.
 *
 * There is no `publish` value here, and that is the point: resolving an
 * objection returns the record to the publication gate, it never walks
 * through it. `outcome: 'published'` has exactly one writer in this codebase
 * (`transitions.ts::finalize-archive`) and that writer is behind
 * `governance.canArchive`.
 */
export const OBJECTION_RESOLUTIONS = ['lift', 'withhold'] as const;
export type ObjectionResolution = (typeof OBJECTION_RESOLUTIONS)[number];

/** An objection as raised: who, why, when. */
export interface Objection {
  member: string;
  reason: string;
  date: string;
}

/**
 * A publication objection, which additionally records the day it was closed.
 *
 * Empty means it still stands. "Unresolved" is therefore a *stored fact*, not
 * something inferred by comparing dates against the approval -- and a
 * hand-written objection that omits the key reads as standing, which is the
 * safe direction.
 *
 * Nomination objections (G-08) use the plain `Objection`: an objection there
 * is never resolved, it defers the candidate to the annual meeting.
 */
export interface PublicationObjection extends Objection {
  resolved_on: string;
}

export interface Publication {
  consent: PublicationConsent;
  approved_by: string;
  approved_on: string;
  objections: PublicationObjection[];
  outcome: 'published' | 'withheld' | '';
}

export interface BoardMember {
  login: string;
  joined_on: string;
  status: 'active' | 'inactive';
  /** Inclusive end date of a declared absence. Empty when available. */
  unavailable_until: string;
}

export interface Nomination {
  candidate: string;
  sponsor: string;
  opened_on: string;
  objections: Objection[];
  outcome: 'accepted' | 'deferred' | 'waiting' | '';
}

export interface Speaker {
  id: string;
  name: string;
  gender: Gender;
  career_stage: CareerStage;
  email: string;
  affiliation: string;
  country: string;

  title: string;
  abstract: string;
  conflicts_of_interest: string;

  source: 'form' | 'outreach' | 'organizer';
  /** Who suggested this speaker, as self-reported at submission time -- often
   *  someone outside the team. Kept verbatim: it is the only record of who to
   *  tell if the Board declines the lead. Never overwritten by assignment. */
  proposed_by: string;
  /** Which board member currently looks after this lead, assigned by rotation
   *  (see `state/board.ts::assignLead`). Distinct from `proposed_by` -- do not
   *  merge the two: one is who nominated the speaker, the other is who is
   *  handling the follow-up. Empty until an assignment is made. */
  assigned_to: string;
  links: string[];

  host_1: string;
  host_2: string;

  status: SpeakerStatus;
  selection: SpeakerSelection;
  publication: Publication;

  edition_code: string;
  date: string;
  time: string;

  zoom_link: string;
  youtube_url: string;
  forum_thread: string;

  runbook_progress: Record<string, boolean>;
  metrics: SpeakerMetrics;
  notes: string;
}

export interface Config {
  season: number;
  vw_counter: number;
  overlap_window_days: number;
  seminar_duration_minutes: number;
  /** Replaces the flat board_members list. */
  board: BoardMember[];
  nominations: Nomination[];
  board_min: number;
  board_max: number;
  vote_window_days: number;
  objection_window_working_days: number;
  inactivity_months: number;
  balance_window_months: number;
  sla_days: {
    lead_decision: number;
    invitation_follow_up: number;
    summary_after_delivery: number;
    recording_after_delivery: number;
  };
}
