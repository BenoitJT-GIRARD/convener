/**
 * Which field of a speaker record may leave this repository, and on what.
 *
 * The publication gate delivered in phase 2 decides whether *the recording*
 * goes out. It says nothing about the rest of the record, because when it was
 * written the record held nothing that needed saying: a name, an affiliation,
 * a title and a date are the programme of a public seminar. The fields added
 * for the volunteers' checklist changed that -- four of the five describe a
 * person rather than an event -- so the classification has to be stated field
 * by field, and stated in a form that a *future* field cannot slip past.
 *
 * The line drawn here is not "personal versus not personal". A speaker's name
 * is personal and is obviously in the programme. The line is **what the person
 * agreed to when they agreed to speak**:
 *
 * - accepting an invitation to give a public webinar is accepting to be named
 *   in its programme, with the institution one speaks for, the country the
 *   talk is billed from, the title and the abstract one wrote for the audience,
 *   and the day and time it is held. Withholding those would not protect
 *   anybody; it would cancel the announcement;
 * - it is not accepting that a portrait, a biography, a LinkedIn identity, a
 *   list of one's professional profiles or the questions one drafted to open a
 *   discussion be republished on the open web. Each of those is a further
 *   disclosure about the person, made possible by the talk but not implied by
 *   it. They travel on a recorded permission or they do not travel;
 * - and a third group is nobody's business outside the team: an e-mail
 *   address, the internal deliberation, the demographic attributes collected
 *   for an aggregate, the names of other people.
 *
 * The three sets are exhaustive over `SPEAKER_FIELDS`, which is derived from
 * `keyof Speaker` rather than hand-written. `consent-fields.test.ts` proves the
 * union is exactly that set, so a field added to the model and forgotten here
 * fails a test instead of reaching the feed by omission. That is the whole
 * mechanism: the default for an unclassified field is a red test, never a
 * publication.
 *
 * The Python side (`tools/convener_ops/public_data.py`) holds the same three sets --
 * it is the side that actually writes the feed -- and the two copies are bound
 * by `tools/tests/fixtures/governance-cases.json`, read from both languages.
 */
import type { Speaker } from '../data/types';

/**
 * The programme of a public seminar.
 *
 * Everything here is a property of the *event*, or of the person only in their
 * capacity as its speaker. `edition_code` is the seminar's number and is what
 * the feed publishes as its `id`; `title` and `abstract` are the text written
 * for the audience; `date` and `time` are when it is held; `status` is whether
 * it is announced, held or archived; `zoom_link` is how the public joins the
 * announced session and `forum_thread` where the public discussion happens.
 *
 * `name`, `affiliation` and `country` sit here for the same reason and not
 * because they are harmless: a seminar whose speaker is not named is not an
 * announcement, and the affiliation is the credential the audience comes for.
 * A speaker who wants none of that published is a speaker who has not agreed
 * to give a public talk, and that is settled before the record reaches this
 * gate -- not by silently emitting an anonymous programme.
 *
 * "Always" is about the *permission*, not about the timing: `zoom_link` is
 * published only whilst the seminar is scheduled, because a joining link for a
 * past event is noise. That condition lives in `to_public`, where the feed is
 * shaped; nothing about it depends on consent.
 */
export const PUBLISHABLE_ALWAYS = [
  'edition_code',
  'title',
  'abstract',
  'date',
  'time',
  'status',
  'name',
  'affiliation',
  'country',
  'zoom_link',
  'forum_thread',
] as const satisfies readonly (keyof Speaker)[];

/**
 * The person, as distinct from the fact that they spoke.
 *
 * `photo_url` is their face. `bio` is an account of their career in their own
 * words. `linkedin` and `links` are named identities elsewhere on the web --
 * republishing them attaches this record to the rest of a person's online
 * presence, which is a thing one may want and a thing one may refuse.
 * `seed_questions` are sentences they wrote to start a discussion, addressed to
 * a forum and not to the open web. `youtube_url` is a recording of them
 * speaking, the field the phase 2 gate was built for.
 *
 * None of these is needed to announce a seminar. Every one of them is a
 * disclosure a reasonable person could accept for one talk and refuse for the
 * next, which is precisely why the answer has to be recorded rather than
 * assumed. They leave the repository only when the publication block says, in
 * the affirmative, that the speaker agreed and that the gate opened.
 *
 * There is deliberately no second, weaker permission for "just the photo, on
 * the announcement". The repository records one consent; inventing a lighter
 * one in code would be inventing an answer nobody gave. If portraits are
 * wanted on upcoming events, that is a consent to ask for and store, not a
 * condition to relax here.
 */
export const PUBLISHABLE_ON_CONSENT = [
  'photo_url',
  'bio',
  'linkedin',
  'links',
  'seed_questions',
  'youtube_url',
] as const satisfies readonly (keyof Speaker)[];

/**
 * Nothing here leaves the repository, on any consent.
 *
 * Four reasons, and it is worth keeping them apart:
 *
 * - **a way to reach the person**: `email`. Collected to invite them, and a
 *   published address is a spam target they did not sign up for;
 * - **attributes collected for an aggregate**: `gender` and `career_stage`.
 *   They exist for a balance measure the board reads over a window
 *   (`state/diversity.ts`). Emitted per row they stop being a measure and
 *   become a label attached to a named researcher on the open web;
 * - **the team's own working record**: `id` (the internal key -- the feed's
 *   `id` is the edition number), `source`, `proposed_by`, `assigned_to`,
 *   `selection`, `publication`, `candidate_dates`, `runbook_progress`,
 *   `metrics`, `notes` and `conflicts_of_interest`. These are how a decision
 *   was reached, not what was decided. `candidate_dates` in particular records
 *   which slots a speaker turned down and why -- their availability, not the
 *   programme. `publication` is read by the gate and never published by it: a
 *   record of a permission is not itself public. `conflicts_of_interest` is a
 *   declaration made to the board for its own recusal rules, and republishing
 *   it would broadcast a statement about a person's ties that was made in a
 *   governance context, to a different audience;
 * - **other people**: `host_1` and `host_2` are volunteers, not the speaker,
 *   and `checklist` names one volunteer per line of the runbook -- who made
 *   the visual, who wrote to the speaker. It is the team's own division of
 *   labour, about people who never agreed to be listed anywhere public.
 *   The only consent this repository stores is the speaker's, and a speaker
 *   cannot consent on a host's behalf. A field naming a third party can never
 *   be unlocked by this gate -- which is why it is here and not in
 *   `PUBLISHABLE_ON_CONSENT`.
 */
export const NEVER_PUBLISHED = [
  'id',
  'gender',
  'career_stage',
  'email',
  'conflicts_of_interest',
  'source',
  'proposed_by',
  'assigned_to',
  'host_1',
  'host_2',
  'selection',
  'publication',
  'candidate_dates',
  'runbook_progress',
  'checklist',
  'metrics',
  'notes',
] as const satisfies readonly (keyof Speaker)[];
