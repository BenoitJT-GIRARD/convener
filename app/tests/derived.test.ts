import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  effectiveStatus,
  hasEnded,
  parisDayOf,
  parisToday,
  parisWallTimeToEpoch,
} from '../src/state/derived';
import type { Config, Speaker } from '../src/data/types';
import { speaker as double } from './data-doubles';

const config: Config = {
  season: 2026, vw_counter: 5, overlap_window_days: 7,
  seminar_duration_minutes: 90, board: [], nominations: [],
  board_min: 3, board_max: 9, vote_window_days: 14,
  objection_window_working_days: 5, inactivity_months: 6,
  balance_window_months: 12,
  view_count_window_days: 30,
  sla_days: {
    lead_decision: 14, invitation_follow_up: 7,
    summary_after_delivery: 5, recording_after_delivery: 10,
  },
  channels: [],
};

// Through the shared double: a field added to `Speaker` reaches this
// record on its own, instead of leaving the file describing a shape
// the reader would refuse.
function scheduled(date: string, time = '12:30'): Speaker {
  return double({
    id: 'spk-001', name: 'A', gender: 'undisclosed', career_stage: 'undisclosed',
    email: '', affiliation: '',
    country: '', title: '', abstract: '', conflicts_of_interest: '',
    source: 'organizer', proposed_by: '', assigned_to: '', links: [],
    host_1: 'H1', host_2: 'H2',
    status: 'scheduled',
    selection: { ballots: [], opened_on: '', decided_on: '' },
    publication: {
      consent: 'pending', approved_by: '', approved_on: '',
      objections: [], outcome: '',
    },
    edition_code: 'MRG-05', date, time, zoom_link: '', youtube_url: '',
    forum_thread: '', runbook_progress: {}, notes: '',
    metrics: { registrations: null, live_peak: null, youtube_views_30d: null, forum_replies: null },
  });
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
    // 23:00 Paris on the 8th, still the day of the seminar.
    expect(hasEnded(noTime, config, new Date('2026-01-08T22:00:00Z'))).toBe(false);
    expect(hasEnded(noTime, config, new Date('2026-01-09T08:00:00Z'))).toBe(true);
  });

  it('rolls a timeless row over at Paris midnight, not UTC midnight', () => {
    // 23:00Z on the 8th is already 00:00 on the 9th in Paris: the seminar's day
    // is over there, and Paris is where the series is run. Under the old UTC
    // reading this was still the 8th and the row read as not yet ended (P2-9).
    const noTime = scheduled('2026-01-08', '');
    expect(hasEnded(noTime, config, new Date('2026-01-08T23:00:00Z'))).toBe(true);
  });

  it('treats a configured duration of 0 as unset and falls back to 90 minutes', () => {
    const zeroDuration: Config = { ...config, seminar_duration_minutes: 0 };
    const now = new Date('2026-01-08T13:01:00Z'); // 14:01 Paris, 91 min in
    expect(hasEnded(scheduled('2026-01-08'), zeroDuration, now)).toBe(true);
  });

  it('counts the exact boundary instant as ended, not just past it', () => {
    // 12:30 Paris start + 90 min = 14:00 Paris = 13:00:00Z (winter, UTC+1)
    const boundary = new Date('2026-01-08T13:00:00Z');
    expect(hasEnded(scheduled('2026-01-08'), config, boundary)).toBe(true);
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

describe('parisDayOf', () => {
  it('reads the Paris day, not the UTC day, in winter', () => {
    // 23:30Z on 11 January is 00:30 on the 12th in Paris (UTC+1).
    expect(parisDayOf(new Date('2026-01-11T23:30:00Z'))).toBe('2026-01-12');
    // ...while half an hour earlier the two zones still agree.
    expect(parisDayOf(new Date('2026-01-11T22:30:00Z'))).toBe('2026-01-11');
  });

  it('reads the Paris day in summer, where the offset is two hours', () => {
    // 22:30Z on 11 July is already 00:30 on the 12th in Paris (UTC+2), an hour
    // earlier than the winter boundary -- so the offset is genuinely read from
    // the zone rather than hard-coded.
    expect(parisDayOf(new Date('2026-07-11T22:30:00Z'))).toBe('2026-07-12');
    expect(parisDayOf(new Date('2026-07-11T21:30:00Z'))).toBe('2026-07-11');
  });

  it('never disagrees with the UTC day in the middle of the afternoon', () => {
    expect(parisDayOf(new Date('2026-03-04T12:00:00Z'))).toBe('2026-03-04');
  });
});

describe('parisToday', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('is the Paris day when the clock reads the previous day in UTC', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-01-11T23:30:00Z')); // 00:30 Paris, the 12th
    expect(parisToday()).toBe('2026-01-12');
    expect(new Date().toISOString().slice(0, 10)).toBe('2026-01-11'); // the old answer
  });

  it('is the Paris day across the summer offset too', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-07-11T22:30:00Z')); // 00:30 Paris, the 12th
    expect(parisToday()).toBe('2026-07-12');
  });

  it('agrees with UTC when the two zones are on the same day', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-07-11T09:00:00Z'));
    expect(parisToday()).toBe('2026-07-11');
  });
});
