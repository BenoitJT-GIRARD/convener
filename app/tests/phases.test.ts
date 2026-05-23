import { describe, it, expect } from 'vitest';
import { phaseOf, canFinalize, PHASES } from '../src/state/phases';
import type { Speaker } from '../src/data/types';

const base: Speaker = {
  id: 'x',
  name: 'X',
  gender: 'undisclosed',
  email: '',
  affiliation: '',
  country: '',
  title: '',
  abstract: '',
  conflicts_of_interest: '',
  source: 'organizer',
  proposed_by: '',
  links: [],
  host_1: '',
  host_2: '',
  status: 'delivered',
  selection: { votes_for: [], decided_on: '' },
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
