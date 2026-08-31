/**
 * Which speaker field is data about an identifiable person, against
 * `docs/handbook/governance/candidate-data-protection.md`'s own account of what
 * `instance/data/speakers.yml` holds.
 *
 * The first test is the one that matters, and it is not about the fields
 * that exist today: it is about the next one. `SPEAKER_FIELDS` is derived
 * from `keyof Speaker`, so a field added to the model appears there without
 * anybody remembering to add it -- and this suite then fails until somebody
 * says whether it is data about a person or a fact about how the lead is
 * being run. Omission cannot reach the governance record's own field list
 * silently, because omission is red here too.
 */
import { describe, expect, it } from 'vitest';
import cases from '../../tools/tests/fixtures/governance-cases.json';
import { PERSONAL_DATA_FIELDS, RECORD_PROCESS_FIELDS } from '../src/state/candidate-data';
import { SPEAKER_FIELDS } from '../src/data/types';

const classification = cases.speaker_personal_data_fields;

describe('which speaker field is personal data', () => {
  it('classifies every field of Speaker, with no field in both sets', () => {
    const all = [...PERSONAL_DATA_FIELDS, ...RECORD_PROCESS_FIELDS];
    expect(new Set(all).size).toBe(all.length);
    expect(new Set(all)).toEqual(new Set(SPEAKER_FIELDS));
  });

  it('fails that check when one field goes unclassified', () => {
    // The mechanism exercised rather than described, the same way
    // consent-fields.test.ts exercises its own three-set version of this: a
    // `Set` equality that shrugged at a missing member would let the test
    // above pass whatever the two lists held, and the guarantee would be
    // decorative. Drop one field and watch the same comparison stop
    // holding, in both directions.
    const classified = new Set<string>([...PERSONAL_DATA_FIELDS, ...RECORD_PROCESS_FIELDS]);
    const unclassified = new Set(classified);
    unclassified.delete('notes');
    expect(unclassified).not.toEqual(new Set(SPEAKER_FIELDS));

    const stale = new Set(classified).add('a_field_the_model_does_not_have');
    expect(stale).not.toEqual(new Set(SPEAKER_FIELDS));
  });

  it('holds the candidate: contact, self-reported attributes, what they sent in', () => {
    for (const field of [
      'name',
      'email',
      'affiliation',
      'country',
      'photo_url',
      'bio',
      'linkedin',
      'seed_questions',
      'links',
    ] as const) {
      expect(PERSONAL_DATA_FIELDS).toContain(field);
    }
  });

  it('holds the demographic attributes read for the diversity report', () => {
    for (const field of ['gender', 'career_stage'] as const) {
      expect(PERSONAL_DATA_FIELDS).toContain(field);
    }
  });

  it('holds the one field naming somebody other than the candidate', () => {
    // proposed_by is kept verbatim as the submitter typed it -- often
    // somebody outside the team, and never the candidate themselves.
    expect(PERSONAL_DATA_FIELDS).toContain('proposed_by');
  });

  it('holds the working notes and the COI declaration about the candidate', () => {
    for (const field of ['notes', 'conflicts_of_interest'] as const) {
      expect(PERSONAL_DATA_FIELDS).toContain(field);
    }
  });

  it('keeps the workshop, not the human, in the process set', () => {
    // metrics is what the event drew, not an attribute of the speaker --
    // schema.md calls it an edition field for exactly that reason.
    for (const field of ['id', 'title', 'abstract', 'edition_code', 'metrics'] as const) {
      expect(RECORD_PROCESS_FIELDS).toContain(field);
      expect(PERSONAL_DATA_FIELDS).not.toContain(field);
    }
  });

  it('keeps the Board members handling the lead out of the personal set', () => {
    for (const field of ['assigned_to', 'host_1', 'host_2'] as const) {
      expect(RECORD_PROCESS_FIELDS).toContain(field);
      expect(PERSONAL_DATA_FIELDS).not.toContain(field);
    }
  });
});

describe('the shared classification fixture', () => {
  // Bound, not duplicated: `tools/tests/test_candidate_data_protection_record.py`
  // asserts the record's own field list against the same file. A field
  // moved on one side and not the other fails in the language left behind.
  it('matches PERSONAL_DATA_FIELDS', () => {
    expect(new Set(PERSONAL_DATA_FIELDS)).toEqual(new Set(classification.personal));
  });

  it('matches RECORD_PROCESS_FIELDS', () => {
    expect(new Set(RECORD_PROCESS_FIELDS)).toEqual(new Set(classification.process));
  });

  it('covers the model exactly, as read from the fixture alone', () => {
    const all = [...classification.personal, ...classification.process];
    expect(new Set(all).size).toBe(all.length);
    expect(new Set(all)).toEqual(new Set(SPEAKER_FIELDS));
  });
});
