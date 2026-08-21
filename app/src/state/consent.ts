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
import { CONSENT_DECISIONS } from '../data/types';
import type { PublicationConsent, Speaker } from '../data/types';

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
 *   `selection`, `publication`, `candidate_dates`, `survey_enabled`,
 *   `runbook_progress`, `metrics`, `notes` and `conflicts_of_interest`. These
 *   are how a decision was reached, not what was decided. `survey_enabled`
 *   (task 16, phase 4 spec S:6) is an operational switch a participant never
 *   needs to read off the public feed: they learn it exists by receiving the
 *   survey itself, never by looking it up. `candidate_dates` in particular records
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
  'survey_enabled',
  'runbook_progress',
  'checklist',
  'metrics',
  'notes',
] as const satisfies readonly (keyof Speaker)[];

/**
 * A field of the record, in words a speaker would recognise.
 *
 * The message that asks the thirty-one speakers for their permission has to
 * say what would be published. Written out by hand, that sentence is true on
 * the day it is written and false the first time somebody adds a field to
 * `PUBLISHABLE_ON_CONSENT` -- and the drift is silent, because a Markdown
 * file has no way of failing. So the sentence is not written: it is composed
 * from the classification above, and the only thing kept by hand is one
 * phrase per field.
 *
 * The `Record` is what binds them. Its key type is the union of the two
 * publishable sets, so a field added to either one stops the build until
 * somebody says how to name it to a speaker -- the same shape of guarantee
 * as `consent-fields.test.ts`, one step further along: a new field must be
 * classified, and if it is publishable it must also be describable.
 *
 * `NEVER_PUBLISHED` is deliberately absent. Those fields are not offered,
 * not withheld pending an answer, and mostly meaningless outside the team
 * ("your runbook progress"); listing them in a message asking for permission
 * would invite the reader to think they were on the table.
 */
export type PublishableField =
  | (typeof PUBLISHABLE_ALWAYS)[number]
  | (typeof PUBLISHABLE_ON_CONSENT)[number];

export const FIELD_WORDING: Record<PublishableField, string> = {
  // The programme.
  edition_code: 'the number of the seminar in the series',
  title: 'the title of your talk',
  abstract: 'its abstract',
  date: 'the day it was held',
  time: 'the time it started',
  status: 'whether it is upcoming, held or archived',
  name: 'your name',
  affiliation: 'the institution you spoke for',
  country: 'the country the talk was billed from',
  zoom_link: 'the joining link, whilst the seminar is still to come',
  forum_thread: 'a link to the discussion thread on the forum',
  // The person.
  photo_url: 'your photograph',
  bio: 'the short biography you send us',
  linkedin: 'your LinkedIn profile',
  links: 'any other professional links you give us',
  seed_questions: 'the questions you wrote to open the discussion',
  youtube_url: 'the video recording of your talk',
};

/** Which of the three sets a field belongs to. */
export type FieldPermission = 'always' | 'on_consent' | 'never';

/**
 * The classification, asked one field at a time.
 *
 * The three constants above are the answer to "what may leave"; this is the
 * same answer read from the other end, for the callers that hold a field and
 * want its rule. `NEVER_PUBLISHED` is the fallthrough on purpose: a field that
 * nobody classified is not published by default, and `consent-fields.test.ts`
 * proves the three sets are exhaustive so that the fallthrough is never
 * silently doing the classifying.
 */
export function permissionFor(field: keyof Speaker): FieldPermission {
  if ((PUBLISHABLE_ALWAYS as readonly string[]).includes(field)) return 'always';
  if ((PUBLISHABLE_ON_CONSENT as readonly string[]).includes(field)) return 'on_consent';
  return 'never';
}

/**
 * What the hosts tell the audience about the recording, before it starts.
 *
 * The consent e-mail cannot drift from the gate, because its two sentences are
 * composed from the classification above. The spoken notice could: it is prose
 * in `toolkit/intro-scripts.md`, read out to a room, about the one field of the
 * record whose publication the room is standing inside. Nothing linked it to
 * anything until now, so `youtube_url` could have been reclassified and the
 * hosts would have gone on saying the old thing to the next audience -- and an
 * audience told the wrong thing about a recording is the error this repository
 * has the least ability to undo.
 *
 * So the sentence is not chosen, it is looked up. One phrase per rule, and the
 * rule comes from `permissionFor('youtube_url')`. Moving the field between the
 * sets rewrites what the hosts say, in the same commit, without anybody
 * remembering that this page existed.
 */
const SPOKEN_RECORDING_NOTICE: Record<FieldPermission, string> = {
  always:
    'We are recording the talk itself, and the recording is published afterwards as part of the programme',
  on_consent:
    'We are recording the talk itself, and the recording only goes online if our speaker tells us afterwards that it may',
  never: 'We are recording the talk itself for the team alone, and the recording is not published',
};

/** The recording sentence the hosts read out, in the words the gate justifies. */
export function spokenRecordingNotice(): string {
  return SPOKEN_RECORDING_NOTICE[permissionFor('youtube_url')];
}

/** `a, b and c` -- an English list, not a comma-separated dump. */
function sentenceList(parts: readonly string[]): string {
  if (parts.length <= 1) return parts.join('');
  return `${parts.slice(0, -1).join(', ')} and ${parts[parts.length - 1]}`;
}

/** What goes out on the programme of a public seminar, in one phrase. */
export function publishedAlwaysWording(): string {
  return sentenceList(PUBLISHABLE_ALWAYS.map(f => FIELD_WORDING[f]));
}

/** What a `granted` unlocks and nothing else does, in one phrase. */
export function publishedOnConsentWording(): string {
  return sentenceList(PUBLISHABLE_ON_CONSENT.map(f => FIELD_WORDING[f]));
}

/**
 * Whether a recorded consent value is an answer somebody gave.
 *
 * `CONSENT_DECISIONS` is the vocabulary of answers, and it holds two. Every
 * other stored value -- `pending`, `''`, and anything a hand-edited file
 * might carry -- is silence. The screen that lists who still owes an answer
 * asks this question and no other: there is no third state to display and
 * none to write.
 */
export function isAnswer(consent: PublicationConsent): boolean {
  return (CONSENT_DECISIONS as readonly string[]).includes(consent);
}

/**
 * The statuses from which a recording consent can be asked about at all.
 *
 * The same two `transitions.ts` allows `consent-set` from, and for the same
 * reason: before a talk is given there is no recording to ask about, and
 * after it is archived a speaker may still change their mind. Kept as its
 * own constant rather than reached through `canTransition` so that the
 * classification module does not depend on the transition machine;
 * `consent-request.test.tsx` asserts the two agree over every status, so
 * they cannot drift apart in silence.
 */
export const CONSENT_ASKABLE_FROM = ['delivered', 'archived'] as const;

/**
 * Whether this record is one somebody still has to ask.
 *
 * Derived, every time, from the record itself. There is no list of people to
 * contact stored anywhere -- a stored list is a list that can disagree with
 * the data, and the disagreement always resolves the wrong way: a speaker
 * ticked off a list nobody actually wrote to.
 */
export function awaitingAnswer(s: Speaker): boolean {
  return (
    (CONSENT_ASKABLE_FROM as readonly string[]).includes(s.status) &&
    !isAnswer(s.publication.consent)
  );
}

/** Those still to be asked, most recent talk first. */
export function awaitingAnswerList(speakers: readonly Speaker[]): Speaker[] {
  return speakers.filter(awaitingAnswer).sort((a, b) => b.date.localeCompare(a.date));
}

/** Those who answered, whichever way they answered. */
export function answeredList(speakers: readonly Speaker[]): Speaker[] {
  return speakers
    .filter(s => (CONSENT_ASKABLE_FROM as readonly string[]).includes(s.status) && isAnswer(s.publication.consent))
    .sort((a, b) => b.date.localeCompare(a.date));
}
