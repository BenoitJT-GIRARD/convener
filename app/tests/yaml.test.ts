import { describe, it, expect } from 'vitest';
import { parseSpeakers, serializeSpeakers, parseConfig, serializeConfig } from '../src/data/yaml';
import type { Speaker, Config } from '../src/data/types';

const sample: Speaker = {
  id: 'spk-test',
  name: 'Test Person',
  gender: 'F',
  email: 'someone@example.test',
  affiliation: 'X',
  country: 'FR',
  title: 'Talk title',
  abstract: 'Abstract.',
  conflicts_of_interest: '',
  source: 'organizer',
  proposed_by: 'alice',
  links: [],
  host_1: 'alice',
  host_2: 'bob',
  status: 'scheduled',
  selection: { votes_for: ['alice', 'bob', 'carol'], decided_on: '2026-01-01' },
  edition_code: 'MRG-10',
  date: '2026-06-01',
  time: '12:30',
  zoom_link: '',
  youtube_url: '',
  forum_thread: '',
  runbook_progress: { 'approved/invitation-sent': true },
  metrics: { registrations: null, live_peak: null, youtube_views_30d: null, forum_replies: null },
  notes: '',
};

const sampleCfg: Config = {
  season: 2026,
  vw_counter: 5,
  vote_threshold: 3,
  overlap_window_days: 7,
  seminar_duration_minutes: 90,
  board_members: ['alice', 'bob'],
};

describe('yaml v2 schema', () => {
  it('round-trips a unified speaker', () => {
    const text = serializeSpeakers([sample]);
    const [back] = parseSpeakers(text);
    expect(back).toEqual(sample);
  });
  it('parses an empty list', () => {
    expect(parseSpeakers('')).toEqual([]);
  });
  it('round-trips config with seminar_duration_minutes', () => {
    const text = serializeConfig(sampleCfg);
    const back = parseConfig(text);
    expect(back).toEqual(sampleCfg);
  });
});
