/**
 * The classification of every speaker field against the publication gate.
 *
 * The first test is the one that matters, and it is not about the fields that
 * exist today: it is about the next one. `SPEAKER_FIELDS` is derived from
 * `keyof Speaker`, so a field added to the model appears there without anybody
 * remembering to add it -- and this suite then fails until somebody says where
 * it belongs. Omission cannot publish anything, because omission is red.
 *
 * The rest pin the placements the argument turns on, so that moving a field
 * between two sets is a test failure and not a silent policy change. The same
 * three sets are asserted against the shared fixture, which the Python side
 * reads too: this rule is written in two languages and neither copy is the
 * authority.
 */
import { describe, expect, it } from 'vitest';
import cases from '../../../tools/tests/fixtures/governance-cases.json';
import {
  NEVER_PUBLISHED,
  PUBLISHABLE_ALWAYS,
  PUBLISHABLE_ON_CONSENT,
  permissionFor,
  spokenRecordingNotice,
} from '../../src/state/consent';
import { SPEAKER_FIELDS } from '../../src/data/types';

const classification = cases.speaker_field_classification;

describe('the publication classification of speaker fields', () => {
  it('classifies every field of Speaker, with no field in two sets', () => {
    const all = [...PUBLISHABLE_ALWAYS, ...PUBLISHABLE_ON_CONSENT, ...NEVER_PUBLISHED];
    expect(new Set(all).size).toBe(all.length);
    expect(new Set(all)).toEqual(new Set(SPEAKER_FIELDS));
  });

  it('fails that check when one field goes unclassified', () => {
    // The mechanism exercised rather than described. A `Set` equality that
    // shrugged at a missing member would let the test above pass whatever the
    // sets held, and the guarantee would be decorative; so drop one field and
    // watch the same comparison stop holding, in both directions -- a field
    // classified but no longer in the model has to be caught too.
    const classified = new Set<string>([
      ...PUBLISHABLE_ALWAYS,
      ...PUBLISHABLE_ON_CONSENT,
      ...NEVER_PUBLISHED,
    ]);
    const unclassified = new Set(classified);
    unclassified.delete('bio');
    expect(unclassified).not.toEqual(new Set(SPEAKER_FIELDS));

    const stale = new Set(classified).add('a_field_the_model_does_not_have');
    expect(stale).not.toEqual(new Set(SPEAKER_FIELDS));
  });

  it('publishes the programme of the seminar without asking anything', () => {
    // What the person accepted by accepting the invitation: to be named, with
    // the institution they speak for, as the author of a titled talk held on a
    // given day.
    for (const field of ['name', 'affiliation', 'country', 'title', 'abstract', 'date'] as const) {
      expect(PUBLISHABLE_ALWAYS).toContain(field);
    }
  });

  it('holds the person behind the gate: portrait, biography, identities, questions', () => {
    // The four fields the checklist added, plus the recording the gate was
    // built for. Agreeing to speak in public is not agreeing to these, so each
    // one waits for a recorded permission. Moving any of them into
    // PUBLISHABLE_ALWAYS is the mutation this test exists to catch.
    for (const field of ['photo_url', 'bio', 'linkedin', 'links', 'seed_questions', 'youtube_url'] as const) {
      expect(PUBLISHABLE_ON_CONSENT).toContain(field);
      expect(PUBLISHABLE_ALWAYS).not.toContain(field);
    }
  });

  it('keeps the diversity attributes out of every publishable set', () => {
    // They are collected for an aggregate the board reads. No consent turns
    // them into a row on the open web, so they are not on the consent side of
    // the line either.
    for (const field of ['gender', 'career_stage'] as const) {
      expect(NEVER_PUBLISHED).toContain(field);
    }
  });

  it('never publishes a third party, whatever the speaker consented to', () => {
    // The consent stored on a record is the speaker's. A host is somebody
    // else, and the speaker cannot answer for them -- so the hosts cannot be
    // in the set a speaker's consent unlocks.
    for (const field of ['host_1', 'host_2'] as const) {
      expect(NEVER_PUBLISHED).toContain(field);
      expect(PUBLISHABLE_ON_CONSENT).not.toContain(field);
    }
  });

  it('keeps the deliberation, the contact details and the availability internal', () => {
    for (const field of [
      'email',
      'notes',
      'conflicts_of_interest',
      'proposed_by',
      'assigned_to',
      'selection',
      'publication',
      'candidate_dates',
      'metrics',
      'runbook_progress',
      'source',
    ] as const) {
      expect(NEVER_PUBLISHED).toContain(field);
    }
  });

  it('publishes the edition number as the identifier, never the internal key', () => {
    // `id` is a row key in a YAML file; the feed's `id` is the seminar's
    // edition code. The two vocabularies are reconciled in
    // `public_data.PUBLIC_FIELD_SOURCES`, so it is worth pinning which of the
    // two identifiers is the published one: an internal key discloses nothing
    // and means nothing to a reader, and has no business leaving.
    expect(PUBLISHABLE_ALWAYS).toContain('edition_code');
    expect(NEVER_PUBLISHED).toContain('id');
  });
});

describe('the shared classification fixture', () => {
  // Bound, not duplicated: `tools/tests/publication/test_public_data.py` asserts the same
  // three lists against the same file. A field moved on one side and not the
  // other fails in the language that was not updated.
  it('matches PUBLISHABLE_ALWAYS', () => {
    expect(new Set(PUBLISHABLE_ALWAYS)).toEqual(new Set(classification.publishable_always));
  });

  it('matches PUBLISHABLE_ON_CONSENT', () => {
    expect(new Set(PUBLISHABLE_ON_CONSENT)).toEqual(
      new Set(classification.publishable_on_consent),
    );
  });

  it('matches NEVER_PUBLISHED', () => {
    expect(new Set(NEVER_PUBLISHED)).toEqual(new Set(classification.never_published));
  });

  it('covers the model exactly, as read from the fixture alone', () => {
    // Read without going through the TypeScript constants at all: if both
    // sides were wrong in the same way, this is the assertion that notices.
    const all = [
      ...classification.publishable_always,
      ...classification.publishable_on_consent,
      ...classification.never_published,
    ];
    expect(new Set(all).size).toBe(all.length);
    expect(new Set(all)).toEqual(new Set(SPEAKER_FIELDS));
  });
});

describe('what the hosts say about the recording is read off the classification', () => {
  it('answers the classification one field at a time, over all three sets', () => {
    expect(permissionFor('name')).toBe('always');
    expect(permissionFor('youtube_url')).toBe('on_consent');
    expect(permissionFor('email')).toBe('never');
  });

  it('says the recording goes online only on a recorded answer', () => {
    // The sentence a host reads to a room, composed rather than typed. It is
    // the one claim in the spoken script that states a rule; `intro-scripts.md`
    // carries the token and not these words, so moving `youtube_url` between
    // the sets rewrites what is said without anybody remembering the page.
    expect(permissionFor('youtube_url')).toBe('on_consent');
    expect(spokenRecordingNotice()).toContain('only goes online if our speaker tells us');
  });

  it('promises nothing about a recording in the notice it composes', () => {
    expect(spokenRecordingNotice()).not.toMatch(/will be published|will go/i);
  });
});
