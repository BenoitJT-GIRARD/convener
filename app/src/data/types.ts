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

/**
 * What a speaker has said about one proposed slot.
 *
 * There is no `pending` and no fourth value. An answer that has not come
 * back is `''` -- the same absence the rest of the model spells that way --
 * and there is deliberately nothing to write for "probably fine": a slot is
 * either one the speaker accepted, one they declined, or one nobody has
 * answered on yet. The lock-in transition chooses among the accepted ones,
 * so a value meaning "almost" would be a value the lock-in would have to
 * guess about.
 */
export const DATE_ANSWERS = ['accepted', 'declined', ''] as const;
export type DateAnswer = (typeof DATE_ANSWERS)[number];
export function isDateAnswer(v: string): v is DateAnswer {
  return (DATE_ANSWERS as readonly string[]).includes(v);
}

/**
 * One slot put to the speaker, and their answer to it.
 *
 * The invitation has always proposed several dates while the model stored
 * one, so the negotiation happened by e-mail and only its conclusion was
 * ever written down. These are the proposals themselves; `Speaker.date` and
 * `Speaker.time` stay what they were -- the single slot the lock-in froze --
 * and are never derived from this list without a board act.
 */
export interface CandidateDate {
  date: string;
  time: string;
  answer: DateAnswer;
}

/**
 * What the record holds about one line of the journey, beyond whether it is
 * ticked.
 *
 * One field today, and a block rather than a bare string on purpose: the
 * checklist the volunteers actually keep says more about a line than who owns
 * it, and a bare `Record<string, string>` would have to be widened later by
 * rewriting every stored value.
 *
 * **`assignee` is not `assigned_to`.** `Speaker.assigned_to` is the board
 * member who looks after the *lead*; this is the person who owes *one line of
 * the runbook*. They are different people at different grains, and phase 2
 * already paid for merging two notions into one field -- `assignLead` wrote
 * over `proposed_by`, and with it the record of who had to tell the speaker
 * if the board declined. Nothing in this repository derives one from the
 * other: `state/assignment.ts` reads this block and nothing else.
 *
 * `''` -- and an item with no entry at all -- means the hosts, which is what
 * every line has always meant and stays the default.
 */
export interface ChecklistAssignee {
  assignee: string;
}

/**
 * One place an event gets announced.
 *
 * Promoting a workshop means posting it in several places -- the community
 * forum, LinkedIn, mailing lists, institute newsletters, printed posters --
 * and the app knew about two of them while the volunteers' own checklist
 * runs to seven. The seven are *configuration*, not a constant: whether
 * they are still the right seven cannot be confirmed without asking the
 * collaborators, which this project never does, so the list lives in
 * `data/config.yml` and a channel is added, renamed or dropped without a
 * line of TypeScript changing.
 *
 * `key` is what the record stores -- it becomes the checklist key an owner
 * is written against, so renaming it re-keys existing records and is a
 * migration, not an edit. `label` is what a volunteer reads, and changing it
 * costs nothing. The two are separate fields for exactly that reason.
 *
 * `state/channels.ts::channelsOf` is the only way to reach the list.
 */
export interface Channel {
  key: string;
  label: string;
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
  /** Portrait, asked for by the announcement visual. A link, not an upload:
   *  the repository holds records, not media. */
  photo_url: string;
  /** Short biography, which feeds the introduction script the host reads
   *  out. `''` is an answer -- "none given" -- and a missing key is not. */
  bio: string;
  /** LinkedIn handle, used to name the speaker in the promotion posts. */
  linkedin: string;

  title: string;
  abstract: string;
  /** A few sentences from the speaker to open the forum discussion with.
   *  Free text, in their words, not a list this app parses. */
  seed_questions: string;
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
  /** The slots put to the speaker, with their answers. Empty until the
   *  invitation goes out; it stays populated after the lock-in, because
   *  which dates were offered and which were refused is the record of how
   *  the chosen one was chosen. */
  candidate_dates: CandidateDate[];
  date: string;
  time: string;

  zoom_link: string;
  youtube_url: string;
  forum_thread: string;

  runbook_progress: Record<string, boolean>;
  /** Who owes each line of the journey, keyed by runbook item. An item with
   *  no entry here is nobody's in particular, which means the hosts' -- the
   *  behaviour the app has always had, and still the default. Never read
   *  from, and never written to, `assigned_to`. */
  checklist: Record<string, ChecklistAssignee>;
  metrics: SpeakerMetrics;
  notes: string;
}

/**
 * Every key a speaker record has, in the order the model declares them.
 *
 * Written as a record keyed by `keyof Speaker` rather than as an array of
 * strings, so it is exhaustive in both directions: add a field to `Speaker`
 * and forget it here, and this file stops compiling; leave a field here that
 * `Speaker` no longer has, and it stops compiling too. An array of the same
 * strings would have compiled either way.
 *
 * `data/validate.ts` reads it as the set of keys a file may carry, and the
 * publication classification reads it to prove no field slips past the
 * consent gate unclassified -- neither of which a hand-kept second list
 * could be trusted to have followed.
 */
const SPEAKER_FIELD_SET: Record<keyof Speaker, true> = {
  id: true, name: true, gender: true, career_stage: true, email: true,
  affiliation: true, country: true, photo_url: true, bio: true,
  linkedin: true, title: true, abstract: true, seed_questions: true,
  conflicts_of_interest: true, source: true, proposed_by: true,
  assigned_to: true, links: true, host_1: true, host_2: true, status: true,
  selection: true, publication: true, edition_code: true,
  candidate_dates: true, date: true, time: true, zoom_link: true,
  youtube_url: true, forum_thread: true, runbook_progress: true,
  checklist: true,
  metrics: true, notes: true,
};

export const SPEAKER_FIELDS = Object.keys(SPEAKER_FIELD_SET) as readonly (keyof Speaker)[];

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
  /** Where an event is announced, in the order the volunteers work through
   *  them. Read only through `state/channels.ts::channelsOf`; an empty list
   *  is a legal answer and means nothing is promoted through this app. */
  channels: Channel[];
}
