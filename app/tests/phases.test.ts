import { describe, it, expect } from 'vitest';
import { phaseOf, canFinalize, fieldValue, setField, PHASES, type FieldKey } from '../src/state/phases';
import type { Speaker } from '../src/data/types';

const base: Speaker = {
  id: 'x',
  name: 'X',
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
  status: 'delivered',
  selection: { ballots: [], opened_on: '', decided_on: '' },
  publication: {
    consent: 'pending',
    approved_by: '',
    approved_on: '',
    objections: [],
    outcome: '',
  },
  edition_code: 'MRG-9',
  date: '2026-06-01',
  time: '12:30',
  zoom_link: '',
  youtube_url: '',
  forum_thread: '',
  runbook_progress: {},
  metrics: { registrations: null, live_peak: null, youtube_views_30d: null, forum_replies: null },
  notes: '',
};

describe('phases v2', () => {
  it('returns phase by status', () => {
    expect(phaseOf('lead')?.label).toMatch(/Lead/);
    expect(phaseOf('archived')).toBeUndefined();
  });

  it('every runbook key is unique', () => {
    const keys: string[] = [];
    for (const p of PHASES) for (const i of p.items) keys.push(i.key);
    expect(new Set(keys).size).toBe(keys.length);
  });

  it('canFinalize false when required fields missing', () => {
    expect(canFinalize(base)).toBe(false);
  });

  it('canFinalize false when required checkboxes missing', () => {
    const s = { ...base, metrics: { ...base.metrics, registrations: 50, live_peak: 40 } };
    expect(canFinalize(s)).toBe(false);
  });

  it('canFinalize true when all required satisfied', () => {
    const s: Speaker = {
      ...base,
      metrics: { ...base.metrics, registrations: 50, live_peak: 40 },
      runbook_progress: { 'delivered/forum-summary': true, 'delivered/thank-you': true },
    };
    expect(canFinalize(s)).toBe(true);
  });

  it('canFinalize ignores optional fields', () => {
    const s: Speaker = {
      ...base,
      metrics: { ...base.metrics, registrations: 50, live_peak: 40 },
      runbook_progress: { 'delivered/forum-summary': true, 'delivered/thank-you': true },
      // youtube_url, youtube_views_30d, forum_replies still empty/null
    };
    expect(canFinalize(s)).toBe(true);
  });
});

describe('fieldValue', () => {
  const s: Speaker = {
    ...base,
    host_1: 'h1',
    host_2: 'h2',
    title: 't',
    abstract: 'a',
    youtube_url: 'yt',
    forum_thread: 'ft',
    metrics: { registrations: 1, live_peak: 2, youtube_views_30d: 3, forum_replies: 4 },
  };

  it.each<[FieldKey, string | number | null]>([
    ['host_1', 'h1'],
    ['host_2', 'h2'],
    ['title', 't'],
    ['abstract', 'a'],
    ['youtube_url', 'yt'],
    ['forum_thread', 'ft'],
    ['registrations', 1],
    ['live_peak', 2],
    ['youtube_views_30d', 3],
    ['forum_replies', 4],
  ])('reads %s', (key, expected) => {
    expect(fieldValue(s, key)).toBe(expected);
  });
});

describe('setField', () => {
  it.each<FieldKey>(['host_1', 'host_2', 'title', 'abstract', 'youtube_url', 'forum_thread'])(
    'sets the string field %s',
    key => {
      const out = setField(base, key, 'new-value');
      expect(fieldValue(out, key)).toBe('new-value');
    },
  );

  it.each<FieldKey>(['registrations', 'live_peak', 'youtube_views_30d', 'forum_replies'])(
    'sets the numeric metric %s, coercing to a number',
    key => {
      const out = setField(base, key, '42');
      expect(fieldValue(out, key)).toBe(42);
    },
  );

  it.each<FieldKey>(['registrations', 'live_peak', 'youtube_views_30d', 'forum_replies'])(
    'sets the numeric metric %s to null on empty string',
    key => {
      const withValue = setField(base, key, '10');
      const cleared = setField(withValue, key, '');
      expect(fieldValue(cleared, key)).toBeNull();
    },
  );
});
