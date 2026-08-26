import type { Speaker } from '../data/types';

/**
 * Which field of a speaker record holds data about an identifiable person --
 * the candidate themselves, or someone else named on their behalf -- as
 * opposed to how the Board is running this particular lead.
 *
 * This is a different question from `consent.ts`'s three sets, which ask
 * *what may leave the repository*. The two axes do not line up: `title` is
 * never published without the talk it names, yet it is not personal data
 * about the speaker, it is the talk's own name; `gender` is personal data
 * and is never published either. Neither set is derived from the other.
 *
 * This axis exists for one reader: a security review's finding that
 * `docs/governance/traitement-donnees.md` described `data/speakers.yml` as
 * holding "speakers' own names and institutional email addresses" when the
 * schema carries a good deal more, and its own fix
 * (`docs/governance/candidate-data-protection.md`) states plainly what the
 * file holds and why. That record cannot be left to drift the way a
 * hand-written sentence would -- so its own field list is bound to
 * `PERSONAL_DATA_FIELDS` by `tools/tests/fixtures/governance-cases.json`,
 * read by both `personal-data-fields.test.ts` and
 * `tools/tests/test_candidate_data_protection_record.py`. A field added to
 * `Speaker` and left unclassified here fails the exhaustiveness test below,
 * never the record.
 *
 * A speaker's own contact and identifying details, what they disclosed
 * about themselves at proposal or since, the demographic attributes read
 * for the diversity balance report (`state/diversity.ts`), the free text
 * the Board keeps about the lead, and the one field that names somebody
 * else entirely -- `proposed_by`, kept verbatim as whoever submitted the
 * form typed it, and never overwritten by the assignment that later gives
 * the lead to a board member.
 */
export const PERSONAL_DATA_FIELDS = [
  'name',
  'gender',
  'career_stage',
  'email',
  'affiliation',
  'country',
  'photo_url',
  'bio',
  'linkedin',
  'seed_questions',
  'conflicts_of_interest',
  'proposed_by',
  'links',
  'notes',
] as const satisfies readonly (keyof Speaker)[];

/**
 * The complement of `PERSONAL_DATA_FIELDS`, over the same set of keys.
 *
 * Facts about the workshop rather than the human who gives it -- `id`,
 * `title`, `abstract`, the runbook, the schedule, `metrics` (schema.md's own
 * words: "the edition fields... describe the workshop they deliver") -- and
 * facts naming a Board member handling the lead rather than the candidate:
 * `assigned_to`, `host_1`, `host_2`, and the logins inside `selection` and
 * `publication`.
 *
 * Kept explicit, rather than computed as "every key `PERSONAL_DATA_FIELDS`
 * does not have", so the exhaustiveness test below compares two
 * hand-written lists: a field either side forgets is then a visible
 * mismatch against `SPEAKER_FIELDS`, not a field the other list silently
 * absorbed.
 */
export const RECORD_PROCESS_FIELDS = [
  'id',
  'title',
  'abstract',
  'source',
  'assigned_to',
  'host_1',
  'host_2',
  'status',
  'selection',
  'publication',
  'edition_code',
  'candidate_dates',
  'date',
  'time',
  'zoom_link',
  'youtube_url',
  'forum_thread',
  'survey_enabled',
  'runbook_progress',
  'checklist',
  'metrics',
] as const satisfies readonly (keyof Speaker)[];
