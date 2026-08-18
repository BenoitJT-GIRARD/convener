import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, it, expect } from 'vitest';
import { parseSpeakers, serializeSpeakers, parseConfig, serializeConfig } from '../src/data/yaml';
import { SPEAKERS_HEADER, withSpeakersHeader, stripHeader } from '../src/data/yaml';
import type { Speaker, Config } from '../src/data/types';

function speaker(id: string, status: Speaker['status'] = 'lead'): Speaker {
  return {
    id, name: `Speaker ${id}`, gender: 'undisclosed', email: '', affiliation: '',
    country: '', title: '', abstract: '', conflicts_of_interest: '',
    source: 'organizer', proposed_by: '', links: [], host_1: '', host_2: '',
    status, selection: { votes_for: [], decided_on: '' }, edition_code: '',
    date: '', time: '', zoom_link: '', youtube_url: '', forum_thread: '',
    runbook_progress: {}, notes: '',
    metrics: { registrations: null, live_peak: null, youtube_views_30d: null, forum_replies: null },
  };
}

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

describe('speakers serialisation round-trip', () => {
  it('keeps the header exactly once', () => {
    const text = withSpeakersHeader(serializeSpeakers([speaker('spk-001')]));
    expect(text.startsWith(SPEAKERS_HEADER)).toBe(true);
    expect(text.split(SPEAKERS_HEADER).length - 1).toBe(1);
  });

  it('parses back what it serialised', () => {
    const original = [speaker('spk-001'), speaker('spk-002', 'approved')];
    const text = withSpeakersHeader(serializeSpeakers(original));
    expect(parseSpeakers(stripHeader(text))).toEqual(original);
  });

  it('is stable: serialising twice gives the identical text', () => {
    const once = withSpeakersHeader(serializeSpeakers([speaker('spk-001')]));
    const twice = withSpeakersHeader(
      serializeSpeakers(parseSpeakers(stripHeader(once))),
    );
    expect(twice).toBe(once);
  });
});

describe('JS/Python YAML boundary (I1)', () => {
  // tools/tests/test_yaml_boundary.py loads this same file and asserts the
  // Python validator accepts it -- this is the one round-trip test the
  // language boundary never had. `time` and `date` are non-empty on
  // purpose: they're the two fields YAML 1.1 (PyYAML's default resolvers)
  // misreads when unquoted, and this fixture must always stay byte-for-byte
  // what serializeSpeakers actually emits, not a hand-typed approximation.
  it('matches the checked-in fixture consumed by the Python validator test', () => {
    const fixturePath = resolve(__dirname, '../../tools/tests/fixtures/speakers-from-app.yml');
    const fixture = readFileSync(fixturePath, 'utf-8');
    expect(withSpeakersHeader(serializeSpeakers([sample]))).toBe(fixture);
  });
});
