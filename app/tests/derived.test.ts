import { describe, expect, it } from 'vitest';
import { effectiveStatus, hasEnded, parisWallTimeToEpoch } from '../src/state/derived';
import type { Config, Speaker } from '../src/data/types';

const config: Config = {
  season: 2026, vw_counter: 5, vote_threshold: 3, overlap_window_days: 7,
  seminar_duration_minutes: 90, board_members: [],
};

function scheduled(date: string, time = '12:30'): Speaker {
  return {
    id: 'spk-001', name: 'A', gender: 'undisclosed', email: '', affiliation: '',
    country: '', title: '', abstract: '', conflicts_of_interest: '',
    source: 'organizer', proposed_by: '', links: [], host_1: 'H1', host_2: 'H2',
    status: 'scheduled', selection: { votes_for: [], decided_on: '' },
    edition_code: 'MRG-05', date, time, zoom_link: '', youtube_url: '',
    forum_thread: '', runbook_progress: {}, notes: '',
    metrics: { registrations: null, live_peak: null, youtube_views_30d: null, forum_replies: null },
  };
}

describe('parisWallTimeToEpoch', () => {
  it('resolves winter time as UTC+1', () => {
    expect(parisWallTimeToEpoch('2026-01-08', '12:30')).toBe(
      Date.parse('2026-01-08T11:30:00Z'),
    );
  });

  it('resolves summer time as UTC+2', () => {
    expect(parisWallTimeToEpoch('2026-07-09', '12:30')).toBe(
      Date.parse('2026-07-09T10:30:00Z'),
    );
  });
});

describe('hasEnded', () => {
  it('is false during the seminar', () => {
    const now = new Date('2026-01-08T12:00:00Z'); // 13:00 Paris, 30 min in
    expect(hasEnded(scheduled('2026-01-08'), config, now)).toBe(false);
  });

  it('is true once the duration has elapsed', () => {
    const now = new Date('2026-01-08T13:01:00Z'); // 14:01 Paris, 91 min in
    expect(hasEnded(scheduled('2026-01-08'), config, now)).toBe(true);
  });

  it('falls back to the next day when no time is recorded', () => {
    const noTime = scheduled('2026-01-08', '');
    expect(hasEnded(noTime, config, new Date('2026-01-08T23:00:00Z'))).toBe(false);
    expect(hasEnded(noTime, config, new Date('2026-01-09T08:00:00Z'))).toBe(true);
  });
});

describe('effectiveStatus', () => {
  it('shows a finished seminar as delivered without changing the record', () => {
    const speaker = scheduled('2026-01-08');
    const now = new Date('2026-01-08T13:01:00Z');
    expect(effectiveStatus(speaker, config, now)).toBe('delivered');
    expect(speaker.status).toBe('scheduled');
  });

  it('leaves every other status untouched', () => {
    const lead = { ...scheduled('2026-01-08'), status: 'lead' as const };
    expect(effectiveStatus(lead, config, new Date('2027-01-01T00:00:00Z'))).toBe('lead');
  });
});
