/**
 * The shape of a speaker record, field by field.
 *
 * The fields the checklists have always asked for -- a portrait, a short
 * biography, a handle, the questions the speaker wants the forum to open
 * with, and the slots that were put to them -- were never in the model, so
 * they travelled by e-mail and were lost. They are in it now, and this
 * module pins the two properties that make them worth having:
 *
 * - **An absent key is a defect, not a default.** A record read without
 *   `bio` would still be typed as having one, and every screen downstream
 *   would render `undefined` as though the speaker had answered.
 * - **An empty string is an answer.** `bio: ''` means "none given", which
 *   is a fact a speaker can produce and the file must be able to hold. The
 *   two are different things and the reader has to tell them apart, in the
 *   same sentence style every other field already gets.
 *
 * The Python half is `tools/tests/governance/test_validate_schema_v4.py`: the same keys, on
 * the side that writes the file.
 */
import * as yaml from 'js-yaml';
import { describe, expect, it } from 'vitest';
import { parseSpeakers } from '../../src/data/yaml';
import { DATE_ANSWERS, SPEAKER_FIELDS } from '../../src/data/types';
import type { CandidateDate, Speaker } from '../../src/data/types';
import { speaker } from '../helpers/data-doubles';

/** The new fields, as a volunteer would name them. */
const NEW_FIELDS = ['photo_url', 'bio', 'linkedin', 'seed_questions', 'candidate_dates'] as const;

/** A file as it would arrive from GitHub, from records that need not be
 *  whole -- which is exactly what `speakersYaml` cannot express, because it
 *  fills in the model's defaults before serialising. */
function toYaml(entries: Record<string, unknown>[]): string {
  return yaml.dump(entries, { lineWidth: 1000, noRefs: true, sortKeys: false, seqNoIndent: true });
}

function record(overrides: Partial<Speaker> = {}): Record<string, unknown> {
  return { ...speaker(overrides) } as unknown as Record<string, unknown>;
}

function without(key: string): Record<string, unknown> {
  const bad = record();
  delete bad[key];
  return bad;
}

describe('the fields the templates ask for', () => {
  it('carries every one of them, and nothing the model does not declare', () => {
    for (const field of NEW_FIELDS) {
      expect(SPEAKER_FIELDS).toContain(field);
    }
    // `SPEAKER_FIELDS` is what the publication classification is checked
    // against, so it has to be the whole record and not a list somebody
    // kept up by hand: compared here against a record the model itself
    // builds, key for key and in order.
    expect([...SPEAKER_FIELDS]).toEqual(Object.keys(speaker()));
  });

  it.each(NEW_FIELDS)('rejects a speaker whose file leaves out %s', field => {
    expect(() => parseSpeakers(toYaml([without(field)]))).toThrow(
      new RegExp(`is missing "${field}"`),
    );
  });

  it('names the file and the record, so the fix is one file away', () => {
    let message = '';
    try {
      parseSpeakers(toYaml([record(), without('bio')]));
    } catch (e) {
      message = (e as Error).message;
    }
    expect(message).toContain('instance/data/speakers.yml');
    expect(message).toContain('speaker 2 (spk-001)');
    expect(message).toContain('is missing "bio"');
  });

  it('accepts an empty string, because "none given" is an answer', () => {
    const blank = record({ photo_url: '', bio: '', linkedin: '', seed_questions: '' });
    const [back] = parseSpeakers(toYaml([blank]));
    expect(back.bio).toBe('');
    expect(back.photo_url).toBe('');
    expect(back.linkedin).toBe('');
    expect(back.seed_questions).toBe('');
  });

  it('keeps a filled-in field verbatim, accents, apostrophes and line breaks included', () => {
    const bio = 'Directrice de recherche.\nElle étudie le campagnol.';
    const [back] = parseSpeakers(toYaml([record({ bio, seed_questions: "Qu'est-ce qui a changé ?" })]));
    expect(back.bio).toBe(bio);
    expect(back.seed_questions).toBe("Qu'est-ce qui a changé ?");
  });

  it('refuses text where a list of proposed slots belongs', () => {
    const bad = record();
    bad.candidate_dates = 'the 1st or the 8th';
    expect(() => parseSpeakers(toYaml([bad]))).toThrow(/"candidate_dates" as a list/);
  });
});

describe('a proposed slot and the answer to it', () => {
  function withDates(dates: unknown): Record<string, unknown> {
    const entry = record();
    entry.candidate_dates = dates;
    return entry;
  }

  it('reads back the day, the hour and the answer', () => {
    const proposed: CandidateDate[] = [
      { date: '2026-06-01', time: '12:30', answer: 'accepted' },
      { date: '2026-06-08', time: '09:05', answer: 'declined' },
      { date: '2026-06-15', time: '12:30', answer: '' },
    ];
    const [back] = parseSpeakers(toYaml([withDates(proposed)]));
    expect(back.candidate_dates).toEqual(proposed);
  });

  it('holds no answer at all as the empty answer, never as a missing key', () => {
    const [back] = parseSpeakers(
      toYaml([withDates([{ date: '2026-06-15', time: '12:30', answer: '' }])]),
    );
    expect(back.candidate_dates[0].answer).toBe('');
    expect(() =>
      parseSpeakers(toYaml([withDates([{ date: '2026-06-15', time: '12:30' }])])),
    ).toThrow(/is missing "answer"/);
  });

  it('has no word for "probably": the answer is one of three, and the third is silence', () => {
    // Nothing in this vocabulary can be read as a soft yes, so the lock-in
    // never has to decide what one would have meant.
    expect([...DATE_ANSWERS]).toEqual(['accepted', 'declined', '']);
    expect(DATE_ANSWERS).not.toContain('pending');
    expect(() =>
      parseSpeakers(toYaml([withDates([{ date: '2026-06-15', time: '12:30', answer: 'maybe' }])])),
    ).toThrow(/accepted, declined, \(blank\)/);
  });

  it('says which slot is wrong, not just that one is', () => {
    let message = '';
    try {
      parseSpeakers(
        toYaml([
          withDates([
            { date: '2026-06-01', time: '12:30', answer: 'accepted' },
            { date: '2026-06-08', time: '09:05', answer: 'yes' },
          ]),
        ]),
      );
    } catch (e) {
      message = (e as Error).message;
    }
    expect(message).toContain('candidate_dates entry 2');
  });
});
