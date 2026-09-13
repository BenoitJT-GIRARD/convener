import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import {
  DateRejected,
  acceptedDates,
  answerDate,
  lockBlockers,
  lockDate,
  proposeDates,
  type AcceptedDate,
} from '../../src/state/dates';
import type { CandidateDate, Config, DateAnswer, Speaker } from '../../src/data/types';
import { config as configDouble, speaker as double, speakersYaml } from '../helpers/data-doubles';
import cases from '../../../tools/tests/fixtures/governance-cases.json';
import { parseSpeakers } from '../../src/data/yaml';

const TODAY = '2026-09-01';

/** Through the shared double, so a field added to `Speaker` reaches these
 *  records on its own rather than leaving the file describing a shape the
 *  reader would refuse. */
/** A confirmed record with the talk details already collected, which is what
 *  `lockBlockers` asks for besides the edition number. A record without them
 *  is its own case below, not the starting point for every other one. */
function withCandidates(candidate_dates: CandidateDate[], overrides: Partial<Speaker> = {}) {
  return double({
    id: 'spk-001',
    status: 'confirmed',
    title: 'A talk with a title',
    abstract: 'And an abstract.',
    // A record ready to be locked has a way into the room on it, because
    // that is now part of what ready means: locking is what opens
    // registration, and the first person to sign up is owed an address.
    // The overrides below take it away again where that is the subject.
    zoom_link: 'https://example.test/room/spk-001',
    candidate_dates,
    ...overrides,
  });
}

/** An instance whose series instructions carry the address for every
 *  session -- the permanent-room account of D-06, where a record's own
 *  `zoom_link` is empty by design. */
const SERIES_ROOM: Config = configDouble({
  instructions: 'Join online: https://example.test/series\nAccess code: 123456',
});

/** An instance that opens a room per seminar, so nothing series-wide
 *  answers for one edition. */
const NO_SERIES_ROOM: Config = configDouble({ instructions: '' });

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
    expect(() => lockDate(s, '2026-10-01', 'MRG-09', NO_SERIES_ROOM)).toThrow(DateRejected);
  });

  it('cannot lock a date the speaker declined', () => {
    const s = withCandidates([{ date: '2026-10-01', time: '16:00', answer: 'declined' }]);
    // @ts-expect-error a declined date is not an AcceptedDate
    expect(() => lockDate(s, '2026-10-01', 'MRG-09', NO_SERIES_ROOM)).toThrow(/not a date this speaker has accepted/);
  });

  it('cannot lock a date that was never offered at all', () => {
    const s = withCandidates([{ date: '2026-10-01', time: '16:00', answer: 'accepted' }]);
    // @ts-expect-error free text is not an AcceptedDate
    expect(() => lockDate(s, '2026-12-24', 'MRG-09', NO_SERIES_ROOM)).toThrow(DateRejected);
  });

  it('re-reads the answer from the record it is given, not from the brand in hand', () => {
    const s = withCandidates([{ date: '2026-10-01', time: '16:00', answer: 'accepted' }]);
    const [accepted] = acceptedDates(s);
    // The same value, read before a concurrent write withdrew the
    // acceptance. `mutate` replays the transformation against what the
    // record says now, and what it says now is no.
    const afterWithdrawal = answerDate(s, '2026-10-01', 'declined').speaker;
    expect(() => lockDate(afterWithdrawal, accepted, 'MRG-09', NO_SERIES_ROOM)).toThrow(DateRejected);
  });

  it('takes the hour from the slot the speaker accepted', () => {
    const s = withCandidates([
      { date: '2026-10-01', time: '16:00', answer: 'declined' },
      { date: '2026-10-08', time: '20:30', answer: 'accepted' },
    ]);
    const [accepted] = acceptedDates(s);
    const next = lockDate(s, accepted, 'MRG-09', NO_SERIES_ROOM);
    expect(next.status).toBe('scheduled');
    expect(next.date).toBe('2026-10-08');
    expect(next.time).toBe('20:30');
    expect(next.edition_code).toBe('MRG-09');
    // The offer and the replies stay: which dates were put to the speaker
    // and which they refused is the record of how this one was chosen.
    expect(next.candidate_dates).toHaveLength(2);
  });

  it('refuses to lock without an edition number, and names it', () => {
    const s = withCandidates([{ date: '2026-10-01', time: '16:00', answer: 'accepted' }]);
    expect(() => lockDate(s, acceptedDates(s)[0], '', NO_SERIES_ROOM)).toThrow(/^Edition — still to fill in/);
  });

  it('refuses to lock without the talk details, and names each of them', () => {
    // The bar used to be split: the screen checked the title and the
    // abstract, `lockDate` checked the edition number, and neither said
    // anything about the other's half. One list now, in the order the screen
    // reads down the page.
    const s = withCandidates([{ date: '2026-10-01', time: '16:00', answer: 'accepted' }], {
      title: '',
      abstract: '',
    });
    expect(lockBlockers(s, '', NO_SERIES_ROOM)).toEqual(['Title', 'Abstract', 'Edition']);
    expect(lockBlockers(s, 'MRG-09', NO_SERIES_ROOM)).toEqual(['Title', 'Abstract']);
    expect(() => lockDate(s, acceptedDates(s)[0], 'MRG-09', NO_SERIES_ROOM)).toThrow(
      /^Title, Abstract —/,
    );
  });

  it('has nothing left to name once the four are in', () => {
    const s = withCandidates([{ date: '2026-10-01', time: '16:00', answer: 'accepted' }]);
    expect(lockBlockers(s, 'MRG-09', NO_SERIES_ROOM)).toEqual([]);
  });

  it('refuses to lock with no way into the room, and names it', () => {
    // The chain this guards, each link verified rather than assumed:
    // lock-date -> `scheduled`; `scheduled` -> the showcase publishes the
    // edition and `mint-event-keys.yml` mints its key; a published key ->
    // the signup relay accepts registrations; a registration ->
    // `confirmation.py` sends the way in. So a lock-in with no room means a
    // person is confirmed for a seminar and told nothing about where it is.
    const s = withCandidates([{ date: '2026-10-01', time: '16:00', answer: 'accepted' }], {
      zoom_link: '',
    });
    expect(lockBlockers(s, 'MRG-09', NO_SERIES_ROOM)).toEqual(['A way into the room']);
    expect(() => lockDate(s, acceptedDates(s)[0], 'MRG-09', NO_SERIES_ROOM)).toThrow(
      /^A way into the room — still to fill in/,
    );
  });

  it('takes the series instructions as the way in, with no link on the record', () => {
    // D-06: on a permanent-room account the account *is* the room, so the
    // per-event field is empty by design and the address is one value for
    // the whole series. Requiring `zoom_link` alone would make every such
    // instance paste the same URL onto every record -- and leave the old
    // ones pointing at a dead room the day it changed.
    const s = withCandidates([{ date: '2026-10-01', time: '16:00', answer: 'accepted' }], {
      zoom_link: '',
    });
    expect(lockBlockers(s, 'MRG-09', SERIES_ROOM)).toEqual([]);
    expect(lockDate(s, acceptedDates(s)[0], 'MRG-09', SERIES_ROOM).status).toBe('scheduled');
  });

  it('takes the record’s own link as the way in, with no series instructions', () => {
    const s = withCandidates([{ date: '2026-10-01', time: '16:00', answer: 'accepted' }]);
    expect(lockBlockers(s, 'MRG-09', NO_SERIES_ROOM)).toEqual([]);
  });

  it('reads a config that has not loaded as no series instructions', () => {
    // What a screen holds while the data is in flight. A record with its own
    // link still answers, and one without does not -- the same answer a
    // loaded config with no instructions would give.
    const withLink = withCandidates([{ date: '2026-10-01', time: '16:00', answer: 'accepted' }]);
    const without = withCandidates([{ date: '2026-10-01', time: '16:00', answer: 'accepted' }], {
      zoom_link: '',
    });
    expect(lockBlockers(withLink, 'MRG-09', null)).toEqual([]);
    expect(lockBlockers(without, 'MRG-09', null)).toEqual(['A way into the room']);
  });

  it('names the room last, after the three that were already there', () => {
    // The order the screen reads down the page, which is the reason the list
    // exists rather than four separate refusals.
    const s = withCandidates([{ date: '2026-10-01', time: '16:00', answer: 'accepted' }], {
      title: '',
      abstract: '',
      zoom_link: '',
    });
    expect(lockBlockers(s, '', NO_SERIES_ROOM)).toEqual([
      'Title',
      'Abstract',
      'Edition',
      'A way into the room',
    ]);
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
    expect(lockDate(speaker, accepted as AcceptedDate, 'MRG-09', NO_SERIES_ROOM).date).toBe('2026-10-01');
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
    const root = join(__dirname, '../..', 'src');
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
 * the same file by `tools/tests/governance/test_validate_schema_v4.py`, so the pair cannot
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
