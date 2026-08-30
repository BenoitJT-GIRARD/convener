import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import {
  DateRejected,
  acceptedDates,
  answerDate,
  lockDate,
  proposeDates,
  type AcceptedDate,
} from '../src/state/dates';
import type { CandidateDate, DateAnswer, Speaker } from '../src/data/types';
import { speaker as double, speakersYaml } from './data-doubles';
import cases from '../../tools/tests/fixtures/governance-cases.json';
import { parseSpeakers } from '../src/data/yaml';

const TODAY = '2026-09-01';

/** Through the shared double, so a field added to `Speaker` reaches these
 *  records on its own rather than leaving the file describing a shape the
 *  reader would refuse. */
function withCandidates(candidate_dates: CandidateDate[], overrides: Partial<Speaker> = {}) {
  return double({ id: 'spk-001', status: 'confirmed', candidate_dates, ...overrides });
}

/** Somebody else's evening, already in the diary. `scheduled` is one of the
 *  statuses `findOverlaps` counts. */
function scheduled(id: string, date: string, edition: string) {
  return double({ id, status: 'scheduled', date, time: '18:00', edition_code: edition });
}

describe('proposing dates', () => {
  it('offers each slot with no answer against it', () => {
    const s = withCandidates([]);
    const next = proposeDates(
      s,
      [
        { date: '2026-10-01', time: '18:00' },
        { date: '2026-10-08', time: '18:00' },
      ],
      [],
      7,
      TODAY,
    );
    expect(next.candidate_dates).toEqual([
      { date: '2026-10-01', time: '18:00', answer: '' },
      { date: '2026-10-08', time: '18:00', answer: '' },
    ]);
  });

  it('refuses a date that clashes, naming the event in the way', () => {
    const s = withCandidates([]);
    const agenda = [scheduled('spk-009', '2026-10-03', 'MRG-09')];
    expect(() => proposeDates(s, [{ date: '2026-10-01', time: '18:00' }], agenda, 7, TODAY)).toThrow(
      DateRejected,
    );
    try {
      proposeDates(s, [{ date: '2026-10-01', time: '18:00' }], agenda, 7, TODAY);
      expect.unreachable('the clashing date was accepted');
    } catch (e) {
      const message = (e as Error).message;
      expect(message).toContain('MRG-09');
      expect(message).toContain('2026-10-03');
      expect(message).toContain('2026-10-01');
    }
  });

  it('checks the clash at proposal time, so nothing clashing is ever offered', () => {
    const s = withCandidates([]);
    const agenda = [scheduled('spk-009', '2026-10-03', 'MRG-09')];
    // The good date is in the same call as the clashing one and still does
    // not reach the record: an invitation goes out whole or not at all.
    expect(() =>
      proposeDates(
        s,
        [
          { date: '2026-11-05', time: '18:00' },
          { date: '2026-10-01', time: '18:00' },
        ],
        agenda,
        7,
        TODAY,
      ),
    ).toThrow(DateRejected);
  });

  it('does not count the speaker s own locked date as a clash', () => {
    const s = withCandidates([], { id: 'spk-001', date: '2026-10-01' });
    const agenda = [double({ id: 'spk-001', status: 'scheduled', date: '2026-10-01' })];
    expect(() =>
      proposeDates(s, [{ date: '2026-10-01', time: '18:00' }], agenda, 7, TODAY),
    ).not.toThrow();
  });

  it('refuses a date in the past, an empty offer, a duplicate and a slot with no time', () => {
    const s = withCandidates([]);
    expect(() => proposeDates(s, [{ date: '2026-08-31', time: '18:00' }], [], 7, TODAY)).toThrow(
      /already passed/,
    );
    expect(() => proposeDates(s, [], [], 7, TODAY)).toThrow(/at least one date/);
    expect(() =>
      proposeDates(
        s,
        [
          { date: '2026-10-01', time: '18:00' },
          { date: '2026-10-01', time: '19:00' },
        ],
        [],
        7,
        TODAY,
      ),
    ).toThrow(/offered twice/);
    expect(() => proposeDates(s, [{ date: '2026-10-01', time: '' }], [], 7, TODAY)).toThrow(
      /start time/,
    );
    expect(() => proposeDates(s, [{ date: '', time: '18:00' }], [], 7, TODAY)).toThrow(
      /no date/,
    );
  });

  it('keeps an answer already recorded when the same date is offered again', () => {
    const s = withCandidates([{ date: '2026-10-01', time: '18:00', answer: 'declined' }]);
    const next = proposeDates(
      s,
      [
        { date: '2026-10-01', time: '18:00' },
        { date: '2026-10-08', time: '18:00' },
      ],
      [],
      7,
      TODAY,
    );
    // Re-sending an invitation must not quietly erase a refusal.
    expect(next.candidate_dates[0].answer).toBe('declined');
    expect(next.candidate_dates[1].answer).toBe('');
  });

  it('never mutates the record it is given', () => {
    const s = withCandidates([]);
    proposeDates(s, [{ date: '2026-10-01', time: '18:00' }], [], 7, TODAY);
    expect(s.candidate_dates).toEqual([]);
  });
});

describe('recording an answer', () => {
  it('replaces the answer in place and hands back the accepted date', () => {
    const s = withCandidates([
      { date: '2026-10-01', time: '18:00', answer: '' },
      { date: '2026-10-08', time: '18:00', answer: '' },
    ]);
    const { speaker, accepted } = answerDate(s, '2026-10-08', 'accepted');
    expect(speaker.candidate_dates.map(c => c.answer)).toEqual(['', 'accepted']);
    expect(accepted).toBe('2026-10-08');
  });

  it('hands back nothing to lock when the answer is a refusal or a blank', () => {
    const s = withCandidates([{ date: '2026-10-01', time: '18:00', answer: 'accepted' }]);
    expect(answerDate(s, '2026-10-01', 'declined').accepted).toBeNull();
    expect(answerDate(s, '2026-10-01', '').accepted).toBeNull();
  });

  it('refuses an answer about a date nobody offered', () => {
    const s = withCandidates([{ date: '2026-10-01', time: '18:00', answer: '' }]);
    expect(() => answerDate(s, '2026-10-15', 'accepted')).toThrow(DateRejected);
    expect(() => answerDate(s, '2026-10-15', 'accepted')).toThrow(/never put to this speaker/);
  });
});

describe('locking a date', () => {
  it('cannot lock a date the speaker did not accept', () => {
    const s = withCandidates([{ date: '2026-10-01', time: '16:00', answer: '' }]);
    // @ts-expect-error a date that was not accepted is not an AcceptedDate
    expect(() => lockDate(s, '2026-10-01', 'MRG-09')).toThrow(DateRejected);
  });

  it('cannot lock a date the speaker declined', () => {
    const s = withCandidates([{ date: '2026-10-01', time: '16:00', answer: 'declined' }]);
    // @ts-expect-error a declined date is not an AcceptedDate
    expect(() => lockDate(s, '2026-10-01', 'MRG-09')).toThrow(/not a date this speaker has accepted/);
  });

  it('cannot lock a date that was never offered at all', () => {
    const s = withCandidates([{ date: '2026-10-01', time: '16:00', answer: 'accepted' }]);
    // @ts-expect-error free text is not an AcceptedDate
    expect(() => lockDate(s, '2026-12-24', 'MRG-09')).toThrow(DateRejected);
  });

  it('re-reads the answer from the record it is given, not from the brand in hand', () => {
    const s = withCandidates([{ date: '2026-10-01', time: '16:00', answer: 'accepted' }]);
    const [accepted] = acceptedDates(s);
    // The same value, read before a concurrent write withdrew the
    // acceptance. `mutate` replays the transformation against what the
    // record says now, and what it says now is no.
    const afterWithdrawal = answerDate(s, '2026-10-01', 'declined').speaker;
    expect(() => lockDate(afterWithdrawal, accepted, 'MRG-09')).toThrow(DateRejected);
  });

  it('takes the hour from the slot the speaker accepted', () => {
    const s = withCandidates([
      { date: '2026-10-01', time: '16:00', answer: 'declined' },
      { date: '2026-10-08', time: '20:30', answer: 'accepted' },
    ]);
    const [accepted] = acceptedDates(s);
    const next = lockDate(s, accepted, 'MRG-09');
    expect(next.status).toBe('scheduled');
    expect(next.date).toBe('2026-10-08');
    expect(next.time).toBe('20:30');
    expect(next.edition_code).toBe('MRG-09');
    // The offer and the replies stay: which dates were put to the speaker
    // and which they refused is the record of how this one was chosen.
    expect(next.candidate_dates).toHaveLength(2);
  });

  it('refuses to lock without an edition number', () => {
    const s = withCandidates([{ date: '2026-10-01', time: '16:00', answer: 'accepted' }]);
    expect(() => lockDate(s, acceptedDates(s)[0], '')).toThrow(/edition number/);
  });

  it('accepts what answerDate hands back, in one negotiation', () => {
    const offered = proposeDates(
      withCandidates([]),
      [{ date: '2026-10-01', time: '18:00' }],
      [],
      7,
      TODAY,
    );
    const { speaker, accepted } = answerDate(offered, '2026-10-01', 'accepted');
    expect(accepted).not.toBeNull();
    expect(lockDate(speaker, accepted as AcceptedDate, 'MRG-09').date).toBe('2026-10-01');
  });
});

describe('the AcceptedDate brand', () => {
  it('reports only the dates whose stored answer is an acceptance', () => {
    const s = withCandidates([
      { date: '2026-10-01', time: '18:00', answer: 'declined' },
      { date: '2026-10-08', time: '18:00', answer: '' },
      { date: '2026-10-15', time: '18:00', answer: 'accepted' },
    ]);
    expect(acceptedDates(s)).toEqual(['2026-10-15']);
  });

  it('is cast in exactly one place in the whole of app/src', () => {
    // The brand is worth nothing if any caller can write `as AcceptedDate`
    // over a string a volunteer typed. One cast exists, inside the private
    // `brand` helper in `state/dates.ts`; this test is what keeps it one.
    const root = join(__dirname, '..', 'src');
    const files: string[] = [];
    const walk = (dir: string) => {
      for (const entry of readdirSync(dir)) {
        const full = join(dir, entry);
        if (statSync(full).isDirectory()) walk(full);
        else if (/\.tsx?$/.test(entry)) files.push(full);
      }
    };
    walk(root);
    const casts = files.flatMap(f =>
      readFileSync(f, 'utf8')
        .split('\n')
        .map((line, i) => ({ file: f, line: i + 1, text: line }))
        .filter(l => /\bas AcceptedDate\b/.test(l.text)),
    );
    expect(casts.map(c => `${c.file}:${c.line}`)).toHaveLength(1);
    expect(casts[0].file).toMatch(/dates\.ts$/);
  });

  it('is a plain string once the compiler is out of the way', () => {
    // Nothing is added at run time: the brand is a compile-time device, so
    // a locked date serialises to `instance/data/speakers.yml` as the string it is.
    const s = withCandidates([{ date: '2026-10-01', time: '18:00', answer: 'accepted' }]);
    expect(typeof acceptedDates(s)[0]).toBe('string');
    expect(JSON.stringify(acceptedDates(s))).toBe('["2026-10-01"]');
  });
});

/**
 * What a slot *is*, stated once for both languages.
 *
 * The day identifies a slot; the hour is part of the offer, not part of its
 * name. The two readers of `instance/data/speakers.yml` disagreed about that --
 * `tools/convener_ops/governance/validate.py` de-duplicated on (date, time) while this
 * module keys on the date -- so a file holding two hours on one day passed
 * validation and then had one recorded reply written against both, with
 * `lockDate` freezing whichever hour came first. These cases are read from
 * the same file by `tools/tests/test_validate_v4.py`, so the pair cannot
 * drift apart again without one of the two suites going red.
 */
describe('the shared statement of what a candidate slot is', () => {
  it.each(cases.candidate_date_cases)('$name -- the file reader', c => {
    const yaml = speakersYaml([{ candidate_dates: c.slots as CandidateDate[] }]);
    if (c.valid) {
      expect(parseSpeakers(yaml)[0].candidate_dates).toEqual(c.slots);
    } else {
      expect(() => parseSpeakers(yaml)).toThrow(/offers .* twice/);
    }
  });

  it.each(cases.candidate_date_cases.filter(c => c.answered !== null))(
    '$name -- recording the reply',
    c => {
      const answered = c.answered!;
      const s = withCandidates(c.slots as CandidateDate[]);
      const { speaker: next } = answerDate(s, answered.date, answered.answer as DateAnswer);
      expect(next.candidate_dates).toEqual(answered.slots);
      expect([...acceptedDates(next)]).toEqual(answered.accepted_dates);
    },
  );
});
