import { describe, expect, it } from 'vitest';
import {
  MIN_REPORTING_BASIS,
  distribution,
  monthsBefore,
  share,
} from '../src/state/diversity';
import type { CareerStage, Gender, Speaker, SpeakerStatus } from '../src/data/types';
import { CAREER_STAGES, GENDERS } from '../src/data/types';
import { speaker as double } from './data-doubles';

const ON = '2026-08-18';
const WINDOW = 24;

// Through the shared double: a field added to `Speaker` reaches this
// record on its own, instead of leaving the file describing a shape
// the reader would refuse.
function speaker(overrides: Partial<Speaker> = {}): Speaker {
  return double({
    id: 'spk-001',
    name: 'A',
    gender: 'undisclosed',
    career_stage: 'undisclosed',
    email: '',
    affiliation: '',
    country: '',
    title: '',
    abstract: '',
    conflicts_of_interest: '',
    source: 'organizer',
    proposed_by: '',
    assigned_to: '',
    links: [],
    host_1: '',
    host_2: '',
    status: 'lead',
    selection: { ballots: [], opened_on: ON, decided_on: '' },
    publication: {
      consent: 'pending',
      approved_by: '',
      approved_on: '',
      objections: [],
      outcome: '',
    },
    edition_code: '',
    date: '',
    time: '',
    zoom_link: '',
    youtube_url: '',
    forum_thread: '',
    runbook_progress: {},
    metrics: {
      registrations: null,
      live_peak: null,
      youtube_views_30d: null,
      forum_replies: null,
    },
    notes: '',
    ...overrides,
  });
}

/** `n` speakers opened inside the window, all alike. */
function cohort(n: number, overrides: Partial<Speaker> = {}): Speaker[] {
  return Array.from({ length: n }, (_, i) =>
    speaker({ id: `spk-${String(i + 1).padStart(3, '0')}`, ...overrides }),
  );
}

describe('the window', () => {
  it('counts a lead opened on either boundary and nothing outside it', () => {
    const speakers = [
      speaker({ id: 'spk-001', selection: { ballots: [], opened_on: '2024-08-18', decided_on: '' } }),
      speaker({ id: 'spk-002', selection: { ballots: [], opened_on: '2024-08-17', decided_on: '' } }),
      speaker({ id: 'spk-003', selection: { ballots: [], opened_on: ON, decided_on: '' } }),
      speaker({ id: 'spk-004', selection: { ballots: [], opened_on: '2026-08-19', decided_on: '' } }),
    ];
    const d = distribution(speakers, WINDOW, ON);
    expect(d.from).toBe('2024-08-18');
    expect(d.to).toBe(ON);
    expect(d.applicants.total).toBe(2);
  });

  it('counts a speaker outside the window in neither population', () => {
    const stale = speaker({
      status: 'delivered',
      career_stage: 'phd',
      selection: { ballots: [], opened_on: '2020-01-01', decided_on: '2020-02-01' },
    });
    const d = distribution([stale], WINDOW, ON);
    expect(d.applicants.total).toBe(0);
    expect(d.selected.total).toBe(0);
    expect(d.applicants.career_stage.counts.phd).toBe(0);
  });

  it('places an undated lead in neither population, and says how many there are', () => {
    // Seven of the thirty-one speakers in data/speakers.yml carry an empty
    // `opened_on`. Dropping them silently would shrink the denominator with
    // no trace; the count is reported so the screen can caption it.
    const speakers = [
      speaker({ id: 'spk-001', selection: { ballots: [], opened_on: '', decided_on: '' } }),
      speaker({ id: 'spk-002', selection: { ballots: [], opened_on: 'last spring', decided_on: '' } }),
      speaker({ id: 'spk-003' }),
    ];
    const d = distribution(speakers, WINDOW, ON);
    expect(d.undated).toBe(2);
    expect(d.applicants.total).toBe(1);
    expect(d.selected.total).toBe(0);
  });

  it('survives a record whose selection block or country is missing entirely', () => {
    // Speakers are cast out of YAML rather than validated, so a hand-edited
    // or half-migrated row can be missing a key altogether. It must be
    // counted as undated, not throw a raw error at a volunteer.
    const broken = { id: 'spk-001', name: 'A', status: 'lead' } as unknown as Speaker;
    const d = distribution([broken, speaker({ id: 'spk-002', country: undefined as unknown as string })], WINDOW, ON);
    expect(d.undated).toBe(1);
    expect(d.applicants.country.counts.undisclosed).toBe(1);
  });

  it('collapses to the single day when the configured window is not a positive number', () => {
    const speakers = [
      speaker({ id: 'spk-001', selection: { ballots: [], opened_on: ON, decided_on: '' } }),
      speaker({ id: 'spk-002', selection: { ballots: [], opened_on: '2026-08-17', decided_on: '' } }),
    ];
    expect(distribution(speakers, 0, ON).applicants.total).toBe(1);
    expect(distribution(speakers, -12, ON).applicants.total).toBe(1);
    expect(distribution(speakers, Number.NaN, ON).applicants.total).toBe(1);
  });
});

describe('monthsBefore', () => {
  it('clamps the day of month rather than rolling into the next month', () => {
    expect(monthsBefore('2026-03-31', 1)).toBe('2026-02-28');
    expect(monthsBefore('2024-03-31', 1)).toBe('2024-02-29');
  });

  it('crosses years', () => {
    expect(monthsBefore('2026-08-18', 24)).toBe('2024-08-18');
    expect(monthsBefore('2026-01-15', 1)).toBe('2025-12-15');
    expect(monthsBefore('2026-01-15', 13)).toBe('2024-12-15');
  });
});

describe('applicants and selected', () => {
  const SELECTED: SpeakerStatus[] = [
    'approved',
    'invited',
    'confirmed',
    'scheduled',
    'delivered',
    'archived',
  ];
  const NOT_SELECTED: SpeakerStatus[] = ['lead', 'parked', 'decline-board'];

  it.each(SELECTED)('counts a %s speaker as both an applicant and selected', status => {
    const d = distribution([speaker({ status })], WINDOW, ON);
    expect(d.applicants.total).toBe(1);
    expect(d.selected.total).toBe(1);
  });

  it.each(NOT_SELECTED)('counts a %s speaker as an applicant only', status => {
    const d = distribution([speaker({ status })], WINDOW, ON);
    expect(d.applicants.total).toBe(1);
    expect(d.selected.total).toBe(0);
  });

  it('counts a speaker who declined the invitation as selected', () => {
    // `decline-speaker` is reachable only from `invited`, which is reachable
    // only from `approved`: the board did select them. Scoring them as
    // unselected would make any group that declines more often look like a
    // group the board picks less often.
    const d = distribution([speaker({ status: 'decline-speaker' })], WINDOW, ON);
    expect(d.selected.total).toBe(1);
  });

  it('reports the two populations over the same window', () => {
    const speakers = [
      ...cohort(3, { status: 'lead', career_stage: 'phd' }),
      speaker({ id: 'spk-010', status: 'delivered', career_stage: 'phd' }),
      speaker({ id: 'spk-011', status: 'scheduled', career_stage: 'group-leader' }),
    ];
    const d = distribution(speakers, WINDOW, ON);
    expect(d.applicants.total).toBe(5);
    expect(d.applicants.career_stage.counts.phd).toBe(4);
    expect(d.selected.total).toBe(2);
    expect(d.selected.career_stage.counts.phd).toBe(1);
    expect(d.selected.career_stage.counts['group-leader']).toBe(1);
  });
});

describe('the undisclosed bucket', () => {
  it('counts a speaker with no declared career stage under undisclosed, never omitted', () => {
    // The denominator is the measure. A speaker who did not answer still
    // applied, and dropping them would flatter every remaining proportion --
    // which is the exact bias the measure exists to reveal.
    const speakers = [
      ...cohort(4, { career_stage: 'undisclosed' }),
      speaker({ id: 'spk-010', career_stage: 'postdoc' }),
    ];
    const { career_stage } = distribution(speakers, WINDOW, ON).applicants;
    expect(career_stage.counts.undisclosed).toBe(4);
    expect(career_stage.total).toBe(5);
    expect(career_stage.declared).toBe(1);
  });

  it('reads a value outside the vocabulary as undisclosed instead of opening a bucket', () => {
    // Speakers are cast out of YAML, not validated: a hand-edited file can
    // carry anything, and a typo must not become a career stage the board
    // then reads as a finding.
    const speakers = [
      speaker({ id: 'spk-001', career_stage: 'professor' as CareerStage }),
      speaker({ id: 'spk-002', gender: 'female' as Gender }),
    ];
    const { career_stage, gender } = distribution(speakers, WINDOW, ON).applicants;
    expect(Object.keys(career_stage.counts).sort()).toEqual([...CAREER_STAGES].sort());
    expect(career_stage.counts.undisclosed).toBe(2);
    expect(Object.keys(gender.counts).sort()).toEqual([...GENDERS].sort());
    expect(gender.counts.undisclosed).toBe(2);
  });

  it('shows every stage and gender at zero rather than leaving it out', () => {
    const { career_stage, gender } = distribution(cohort(2), WINDOW, ON).applicants;
    for (const stage of CAREER_STAGES) expect(career_stage.counts[stage]).toBeGreaterThanOrEqual(0);
    expect(career_stage.counts.postdoc).toBe(0);
    expect(gender.counts.NB).toBe(0);
  });

  it('counts a blank country as undisclosed and trims the rest', () => {
    const speakers = [
      speaker({ id: 'spk-001', country: '  Portugal ' }),
      speaker({ id: 'spk-002', country: 'Portugal' }),
      speaker({ id: 'spk-003', country: '   ' }),
      speaker({ id: 'spk-004' }),
    ];
    const { country } = distribution(speakers, WINDOW, ON).applicants;
    expect(country.counts.Portugal).toBe(2);
    expect(country.counts.undisclosed).toBe(2);
    expect(country.declared).toBe(2);
  });
});

describe('share', () => {
  it('refuses to report a proportion drawn from fewer than the reporting basis', () => {
    const basis = { declared: MIN_REPORTING_BASIS - 1 };
    expect(share(3, basis)).toEqual({
      kind: 'too-few',
      count: 3,
      of: MIN_REPORTING_BASIS - 1,
    });
  });

  it('reports a proportion once the basis reaches the floor', () => {
    expect(share(3, { declared: MIN_REPORTING_BASIS })).toEqual({
      kind: 'counted',
      count: 3,
      of: MIN_REPORTING_BASIS,
    });
  });

  it('never produces a percentage, in either arm', () => {
    // The central guarantee: there is no form in which a proportion can be
    // read without its denominator, and no percentage for a reader to
    // mistake for precision. If a `percent`, `pct` or `ratio` field ever
    // appears, this fails.
    for (const result of [share(3, { declared: 4 }), share(3, { declared: 40 })]) {
      expect(Object.keys(result).sort()).toEqual(['count', 'kind', 'of']);
      for (const value of Object.values(result)) {
        expect(typeof value === 'number' ? Number.isInteger(value) : true).toBe(true);
      }
    }
  });

  it('takes its denominator from those who declared, not from everyone', () => {
    // Thirty applicants of whom two declared a gender is not a basis for
    // saying anything about gender. Counting the undisclosed into the
    // denominator would turn "we do not know" into "well represented".
    const speakers = [
      ...cohort(28, { gender: 'undisclosed' }),
      speaker({ id: 'spk-901', gender: 'F' }),
      speaker({ id: 'spk-902', gender: 'M' }),
    ];
    const { gender } = distribution(speakers, WINDOW, ON).applicants;
    expect(gender.total).toBe(30);
    expect(gender.declared).toBe(2);
    expect(share(gender.counts.F, gender)).toEqual({ kind: 'too-few', count: 1, of: 2 });
  });

  it('reports the programme as unmeasured when nobody has declared anything', () => {
    // The state of data/speakers.yml today: thirty-one speakers, every one of
    // them `undisclosed` on both attributes. The measure must say so.
    const { applicants } = distribution(cohort(31), WINDOW, ON);
    expect(applicants.total).toBe(31);
    expect(applicants.career_stage.declared).toBe(0);
    expect(applicants.gender.declared).toBe(0);
    expect(share(0, applicants.gender).kind).toBe('too-few');
  });
});
