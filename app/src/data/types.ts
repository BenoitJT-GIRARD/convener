/**
 * The model, and the source the handbook's schema appendix is generated from.
 *
 * `docs/operating/schema.md` is derived from this file by
 * `tools/scripts/generate_schema_doc.py`, and CI refuses a page the types do not
 * derive. So the first paragraph of a field's documentation comment is not
 * only a note to whoever reads the code: it is the sentence a volunteer reads
 * in the handbook. Paragraphs after the first stay here, where the argument
 * for a field's shape is useful to the person about to change it.
 */

/** Where a record stands in the journey. */
export type SpeakerStatus =
  | 'lead' // submitted, awaiting board review
  | 'approved' // board voted in favour, invitation being prepared
  | 'invited' // invitation sent, awaiting reply
  | 'confirmed' // speaker accepted, no date locked yet
  | 'scheduled' // date locked and edition code assigned, the runbook drives the rest
  | 'delivered' // event date passed (automatic transition, see `convener-sweep`)
  | 'archived' // post-event items done (an explicit gesture, never automatic)
  | 'parked' // board paused this lead (reversible)
  | 'decline-board' // board collectively declined (reversible)
  | 'decline-speaker'; // speaker declined the invitation

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
  /** YYYY-MM-DD of the slot offered. */
  date: string;
  /** HH:MM, Paris local time. */
  time: string;
  /** What the speaker said about this slot. Empty is the answer that has not
   *  come back yet; there is no value for a soft yes, so the transition that
   *  locks the date in never has to interpret one. */
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
 * the runbook*. They are different people at different grains, and this
 * project has already paid for merging two notions into one field --
 * `assignLead` wrote
 * over `proposed_by`, and with it the record of who had to tell the speaker
 * if the board declined. Nothing in this repository derives one from the
 * other: `state/assignment.ts` reads this block and nothing else.
 *
 * `''` -- and an item with no entry at all -- means the hosts, which is what
 * every line has always meant and stays the default.
 */
export interface ChecklistAssignee {
  /** Login of whoever owes this line. Empty -- and an item with no entry at
   *  all -- means nobody in particular, which means the hosts. */
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
 * `instance/data/config.yml` and a channel is added, renamed or dropped without a
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
  /** What the record stores: it becomes the last segment of the promotion
   *  line's key, so renaming one re-keys what is already written and is a
   *  migration rather than an edit. */
  key: string;
  /** What a volunteer reads. Only ever shown, so it can be reworded at any
   *  time without touching a stored record. */
  label: string;
}

/** What the event drew, filled in after the talk. */
export interface SpeakerMetrics {
  /** How many people registered. */
  registrations: number | null;
  /** Peak concurrent attendees during the live session. */
  live_peak: number | null;
  /** Views of the recording, read off the number of days after the talk that
   *  `view_count_window_days` sets. The key keeps its historical name; the
   *  window it is read at is configuration.
   *
   *  Keeping it is a decision, not an oversight. `youtube_views_30d` is a
   *  stored key: renaming it means migrating every record in
   *  `instance/data/speakers.yml`, both readers, both test doubles and the byte-exact
   *  YAML boundary fixtures -- the same cost as any other schema change --
   *  and it buys a name that reads slightly better. The number in it is
   *  already contradicted by the two things that act on the value: the label
   *  is derived (`viewCountLabel`) and the window is read from the config.
   *  The rename can ride along with the next migration that has a reason of
   *  its own; on its own it does not earn one. */
  youtube_views_30d: number | null;
  /** Replies on the forum thread. */
  forum_replies: number | null;
}

export const BALLOT_VALUES = ['yes', 'abstain', 'recused'] as const;
export type BallotValue = (typeof BALLOT_VALUES)[number];
export function isBallotValue(v: string): v is BallotValue {
  return (BALLOT_VALUES as readonly string[]).includes(v);
}

/** One board member's vote on one lead. */
export interface Ballot {
  /** Login of the board member casting it. One ballot per member: re-voting
   *  replaces the earlier entry in place rather than adding a second. */
  voter: string;
  /** How they voted. */
  value: BallotValue;
  /** Optional on every ballot. Asked for by the Board so a decision can be read
   *  years later without asking whoever cast it. */
  comment: string;
  /** Required when value is 'recused'. A recusal without a written reason is
   *  not recorded — see governance.ts. */
  coi_reason: string;
  /** YYYY-MM-DD the ballot was cast. */
  date: string;
}

/** How the board decided on this lead. */
export interface SpeakerSelection {
  /** One entry per voting board member. Replaces the former `votes_for` list
   *  of logins. */
  ballots: Ballot[];
  /** YYYY-MM-DD the vote opened. The vote window (`vote_window_days`) is
   *  counted from here; an empty value means `convener-sweep` can never expire the
   *  lead. */
  opened_on: string;
  /** YYYY-MM-DD the threshold was reached. Empty while the lead is still
   *  open. */
  decided_on: string;
}

/** `''` is a real stored value, not an oversight: `tools/migrations/migrate_v3.py`
 *  writes it for every speaker whose status never reached a publishable
 *  state, and `tools/convener_ops/governance/validate.py` accepts it. It is spelled out here
 *  so that code reading `consent` has to face it -- neither `''` nor
 *  `pending` is an agreement, and the gate treats them identically. */
export type PublicationConsent = 'granted' | 'refused' | 'pending' | '';

/**
 * What a board member may actually *decide* about a speaker's consent.
 *
 * `pending` is a legal stored value -- it is where the migration starts every
 * delivered speaker -- but it is deliberately absent from this vocabulary, so
 * no transition can write it. Consent is only ever moved by relaying an answer
 * the speaker actually gave: the ambiguous value is not guarded, it does
 * not exist here to be written.
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
  /** Login of the board member raising it. */
  member: string;
  /** Why, in their own words. */
  reason: string;
  /** YYYY-MM-DD it was raised. */
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
  /** YYYY-MM-DD the objection was closed. Empty means it still stands and
   *  publication is blocked. */
  resolved_on: string;
}

/** Whether the recording of this talk may be published, and what became of
 *  it. */
export interface Publication {
  /** The speaker's own permission to publish the recording. Only `granted`
   *  opens the gate: `pending` is where every delivered speaker starts, and no
   *  delay turns it into an agreement. */
  consent: PublicationConsent;
  /** Login of the board member who recorded the approval. */
  approved_by: string;
  /** YYYY-MM-DD of that approval. */
  approved_on: string;
  /** Objections raised during the objection window. An unresolved one blocks
   *  publication. */
  objections: PublicationObjection[];
  /** Where the record ended up. `published` is written in exactly one place,
   *  the gated archiving transition, so it cannot coexist with a refused
   *  consent, a standing objection, a missing approval, or an objection window
   *  that has not run. Empty while undecided. */
  outcome: 'published' | 'withheld' | '';
}

/** One member of the editorial board. */
export interface BoardMember {
  /** GitHub login. */
  login: string;
  /** YYYY-MM-DD they joined the board. */
  joined_on: string;
  /** Whether they still vote. Inactive is not a departure and not a
   *  judgement. */
  status: 'active' | 'inactive';
  /** Inclusive end date of a declared absence. Empty when available. */
  unavailable_until: string;
}

/** One candidate put forward for the board. */
export interface Nomination {
  /** Login of the candidate. */
  candidate: string;
  /** Login of the member who put them forward. */
  sponsor: string;
  /** YYYY-MM-DD the objection window opened. */
  opened_on: string;
  /** Objections raised during that window. One defers the candidate to the
   *  annual meeting rather than being resolved. */
  objections: Objection[];
  /** Where the nomination ended up. Empty while the window is still open. */
  outcome: 'accepted' | 'deferred' | 'waiting' | '';
}

export interface Speaker {
  /** Immutable identifier, e.g. `spk-001`. Generated at creation. */
  id: string;
  /** The speaker's name, as they write it. */
  name: string;
  /** Self-reported, and only ever as the speaker gave it. Feeds the programme
   *  balance report. */
  gender: Gender;
  /** Self-reported career stage. Feeds the programme balance report. */
  career_stage: CareerStage;
  /** Speaker contact address. */
  email: string;
  /** Institution. */
  affiliation: string;
  /** Two-letter code or full name. */
  country: string;
  /** Portrait, asked for by the announcement visual. A link, not an upload:
   *  the repository holds records, not media. */
  photo_url: string;
  /** Short biography, which feeds the introduction script the host reads
   *  out. `''` is an answer -- "none given" -- and a missing key is not. */
  bio: string;
  /** LinkedIn handle, used to name the speaker in the promotion posts. */
  linkedin: string;

  /** Talk title. */
  title: string;
  /** Talk abstract. Multi-line. */
  abstract: string;
  /** A few sentences from the speaker to open the forum discussion with.
   *  Free text, in their words, not a list this app parses. */
  seed_questions: string;
  /** Declared by the speaker or noted by the Board, for the Board's own
   *  recusal rules. Not the declaration made to the audience during the
   *  session, which is three lines of the runbook. */
  conflicts_of_interest: string;

  /** How the lead reached the series: the public form, the team's own
   *  outreach, or a record added by hand. */
  source: 'form' | 'outreach' | 'organizer';
  /** Who suggested this speaker, as self-reported at submission time -- often
   *  someone outside the team. A person or nobody: `''` where nobody is on
   *  record. How the lead arrived is `source`'s answer and never this
   *  field's. Kept verbatim otherwise -- it is the only record of who to
   *  tell if the Board declines the lead -- and never overwritten by
   *  assignment.
   *
   *  "A person or nobody" is written down because the records broke it.
   *  Rows imported before this schema existed put the literal `Form` here
   *  to mean "it arrived through the public form", while `source` on those
   *  same rows said `organizer`: the field held a person on some records
   *  and a provenance on others, and nothing reading it could tell which.
   *  A provenance already had a field, and it was the wrong one that got
   *  written. `tools/convener_ops/governance/validate.py` now refuses a `proposed_by`
   *  spelt like one of `source`'s own values, because the record has to
   *  say what it means -- no reader downstream can guess it, and one that
   *  tried would be guessing about somebody's name. */
  proposed_by: string;
  /** Which board member currently looks after this lead, assigned by rotation
   *  (see `state/board.ts::assignLead`). Distinct from `proposed_by` -- do not
   *  merge the two: one is who nominated the speaker, the other is who is
   *  handling the follow-up. Empty until an assignment is made. */
  assigned_to: string;
  /** URLs the lead arrived with: ORCID, lab page, a paper. */
  links: string[];

  /** Login of the first Event Host. Both hosts are required from `scheduled`
   *  onwards. */
  host_1: string;
  /** Login of the second Event Host. */
  host_2: string;

  /** Where the record stands. Managed by the state machine; see the statuses
   *  below. */
  status: SpeakerStatus;
  /** How the board decided on this lead. */
  selection: SpeakerSelection;
  /** Whether the recording may be published, and what became of it. */
  publication: Publication;

  /** The instance's declared `edition_prefix`, a hyphen and 1-4 digits
   *  (`MRG-7`, under the example instance's own prefix); assigned when a
   *  confirmed record is scheduled. Empty for a
   *  record that has not been scheduled. */
  edition_code: string;
  /** The slots put to the speaker, with their answers. Empty until the
   *  invitation goes out; it stays populated after the lock-in, because
   *  which dates were offered and which were refused is the record of how
   *  the chosen one was chosen. */
  candidate_dates: CandidateDate[];
  /** YYYY-MM-DD of the talk, frozen at scheduling. */
  date: string;
  /** HH:MM, Paris local time, frozen at scheduling. */
  time: string;

  /** The meeting link the session runs on. */
  zoom_link: string;
  /** Where the recording sits. Recorded here; published only through the
   *  publication gate. */
  youtube_url: string;
  /** Link to the forum announcement thread. */
  forum_thread: string;

  /** Whether the post-event survey is open for this
   *  event. A per-event fact, not a `instance/data/config.yml` setting: the survey
   *  is switched on per event, and every other per-event
   *  fact -- the room link, the recording, the forum thread -- already
   *  lives on the speaker record rather than in the shared config. The
   *  three questions themselves are fixed for every event
   *  (`tools/convener_ops/journey/survey.py`'s module docstring); this is the only
   *  thing that varies.
   *
   *  `false` by default, and an event with the switch off carries nothing
   *  else about the survey: no `survey-responses.enc` file is ever
   *  written, and the page renders no hidden section -- see
   *  `app/src/islands/survey/SurveyForm.tsx`. */
  survey_enabled: boolean;

  /** Which lines of the journey are ticked, keyed `phase/item`. */
  runbook_progress: Record<string, boolean>;
  /** Who owes each line of the journey, keyed by runbook item. An item with
   *  no entry here is nobody's in particular, which means the hosts' -- the
   *  behaviour the app has always had, and still the default. Never read
   *  from, and never written to, `assigned_to`. */
  checklist: Record<string, ChecklistAssignee>;
  /** What the event drew, filled in after the talk. */
  metrics: SpeakerMetrics;
  /** Free-form notes about the record. */
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
  youtube_url: true, forum_thread: true, survey_enabled: true,
  runbook_progress: true,
  checklist: true,
  metrics: true, notes: true,
};

export const SPEAKER_FIELDS = Object.keys(SPEAKER_FIELD_SET) as readonly (keyof Speaker)[];

export interface Config {
  /** Current season number. */
  season: number;
  /** The next edition number to assign, under the prefix
   *  `instance/config.json` declares. */
  next_edition_number: number;
  /** Forbidden window around each scheduled date, in days. */
  overlap_window_days: number;
  /** How long a seminar runs, in minutes. */
  seminar_duration_minutes: number;
  /** A share of `seminar_duration_minutes` a matched attendee's summed
   *  duration must reach to earn a certificate, in `]0, 1]`:
   *  above zero, at most one. Configuration, not a constant: the real
   *  number has to align with accreditation requirements this project does
   *  not yet know, and alignment happens by editing this file, not by
   *  editing code.
   *
   *  `0.6666666666666666`, not the tidier-looking `0.6667`: the closest
   *  float64 to exactly two thirds, chosen because it lands fractionally
   *  *below* two thirds rather than above -- so a duration of exactly two
   *  thirds of the session reads as eligible rather than being refused by a
   *  rounding artefact nobody typing a shorter number could see or contest.
   *  See `tools/convener_ops/journey/attendance.py::EligibilityThreshold` for the
   *  calculation this feeds. */
  eligibility_share: number;
  /** The editorial board, one entry per member. Replaces the flat
   *  `board_members` list of logins. */
  board: BoardMember[];
  /** Candidates put forward for the board, with their objection windows. */
  nominations: Nomination[];
  /** Fewest members the board may hold. */
  board_min: number;
  /** Most members the board may hold. */
  board_max: number;
  /** How long a vote stays open, in days, counted from
   *  `selection.opened_on`.
   *
   *  Also the board's decision deadline, which is why `sla_days` has no
   *  `lead_decision`: `tools/convener_ops/maintenance/sweep.py::expire_votes` parks a
   *  lead the day after this window closes, and a second key holding the same
   *  deadline let a file say the board was on time that very morning. */
  vote_window_days: number;
  /** How long an objection window runs, in working days rather than calendar
   *  days (G-10). */
  objection_window_working_days: number;
  /** How many months without a ballot make a member inactive (G-09). */
  inactivity_months: number;
  /** How far back the programme balance report looks, in months. */
  balance_window_months: number;
  /** How long after a talk its view count is read off, in days.
   *
   *  Views arrive for years, so a count is only comparable with another
   *  count taken the same number of days out. The number itself is a
   *  convention -- see `docs/handbook/workflow/4-after.md` -- which is why it is
   *  configuration and not a constant, and why the field's label is built
   *  from it rather than typed. */
  view_count_window_days: number;
  /** How to join the permanent room beyond the link itself -- a dial-in
   *  number, an access code, anything the room needs that the URL alone
   *  does not say. `''` is a legal answer: nothing more to add.
   *
   *  One value for the whole series, not one per event (D-06):
   *  the chosen platform's account *is* the permanent room, so these
   *  instructions describe a room that never changes. Read by
   *  `tools/convener_ops/journey/platform.py::ManualPlatform.get_room`, which pairs
   *  this with `instance/data/speakers.yml`'s per-event `zoom_link`.
   *
   *  Kept immediately before `sla_days`, never between it and `channels`:
   *  `data-validate.test.ts` regex-matches from `sla_days:` up to the next
   *  `channels:` to isolate that block, which only works if nothing else
   *  is serialised between the two. */
  instructions: string;
  /** How long each piece of work is given before the inbox raises it.
   *
   *  Three keys, not four: the board's decision is timed by
   *  `vote_window_days` above, the one number the sweep acts on. */
  sla_days: {
    /** Days before an unanswered invitation is followed up. */
    invitation_follow_up: number;
    /** Days after a talk before the forum summary is overdue. */
    summary_after_delivery: number;
    /** Days after a talk before the recording is overdue. */
    recording_after_delivery: number;
  };
  /** Where an event is announced, in the order the volunteers work through
   *  them. Read only through `state/channels.ts::channelsOf`; an empty list
   *  is a legal answer and means nothing is promoted through this app.
   *
   *  Kept as the *last* field, here and in `readConfig` / `data-doubles.ts`'s
   *  `config()`: several `channels.test.ts` cases build a malformed file by
   *  regex-replacing from `channels:` to the end of a real, valid
   *  `serializeConfig` output, which only isolates the channels block if
   *  nothing else is serialised after it. Add a field after this one and
   *  those tests silently start asserting the wrong error. */
  channels: Channel[];
}
