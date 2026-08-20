/**
 * Whole records for the tests that stand in for GitHub.
 *
 * A test backend serving `season: 2026\nboard: []` was serving a file the
 * real repository could never contain and `tools/convener_ops/validate.py` would
 * refuse. It passed only because `parseConfig` cast whatever it found; the
 * screens then read `undefined` out of settings the type said were there,
 * and the suite agreed. `data/validate.ts` reads the model now, so a test
 * double has to be a whole record too -- which is the point, not a tax: a
 * test that cannot state a complete config is a test whose subject was never
 * reading a real one.
 *
 * Override only what the test is about; everything else comes from the
 * values `data/config.yml` actually carries.
 */
import { serializeConfig, serializeSpeakers } from '../src/data/yaml';
import type { BoardMember, Config, Speaker } from '../src/data/types';

export function member(login: string, overrides: Partial<BoardMember> = {}): BoardMember {
  return { login, joined_on: '2024-01-01', status: 'active', unavailable_until: '', ...overrides };
}

export function config(overrides: Partial<Config> = {}): Config {
  return {
    season: 2026,
    vw_counter: 1,
    overlap_window_days: 7,
    seminar_duration_minutes: 90,
    board: [],
    nominations: [],
    board_min: 3,
    board_max: 9,
    vote_window_days: 14,
    objection_window_working_days: 3,
    inactivity_months: 6,
    balance_window_months: 24,
    view_count_window_days: 30,
    // Kept immediately before `sla_days`: `data-validate.test.ts` regex
    // matches from `sla_days:` up to the next `channels:` to isolate that
    // block, which only works with nothing serialised between the two.
    instructions: '',
    sla_days: {
      invitation_follow_up: 30,
      summary_after_delivery: 7,
      recording_after_delivery: 14,
    },
    // Two, where `data/config.yml` lists seven: a double that restated the
    // seven would make every screen test depend on a list this task exists
    // to leave editable. A test about the channels states its own.
    //
    // Kept as the last field: `channels.test.ts` regex-replaces a real
    // `configYaml()` output from `channels:` to the end of the string to
    // build a malformed file, which only isolates the channels block if
    // this is the last key serialised (see `types.ts::Config.channels`).
    channels: [
      { key: 'forum', label: 'The Example Collective forum' },
      { key: 'linkedin_page', label: 'TEC LinkedIn page' },
    ],
    ...overrides,
  };
}

/** `data/config.yml` as the app itself would write it.
 *
 *  Without the comment header: several of these doubles go through `btoa`,
 *  which is Latin-1 only, and the header carries an em dash. The header is a
 *  comment either way -- what is being stood in for is the data. */
export function configYaml(overrides: Partial<Config> = {}): string {
  return serializeConfig(config(overrides));
}

/** A board of `logins`, all active and available. */
export function boardYaml(logins: string[]): string {
  return configYaml({ board: logins.map(login => member(login)) });
}

export function speaker(overrides: Partial<Speaker> = {}): Speaker {
  return {
    id: 'spk-001',
    name: 'A Speaker',
    gender: 'undisclosed',
    career_stage: 'undisclosed',
    email: '',
    affiliation: '',
    country: '',
    photo_url: '',
    bio: '',
    linkedin: '',
    title: '',
    abstract: '',
    seed_questions: '',
    conflicts_of_interest: '',
    source: 'organizer',
    proposed_by: '',
    assigned_to: '',
    links: [],
    host_1: '',
    host_2: '',
    status: 'lead',
    selection: { ballots: [], opened_on: '', decided_on: '' },
    publication: { consent: 'pending', approved_by: '', approved_on: '', objections: [], outcome: '' },
    edition_code: '',
    candidate_dates: [],
    date: '',
    time: '',
    zoom_link: '',
    youtube_url: '',
    forum_thread: '',
    runbook_progress: {},
    checklist: {},
    metrics: { registrations: null, live_peak: null, youtube_views_30d: null, forum_replies: null },
    notes: '',
    ...overrides,
  };
}

/** `data/speakers.yml` as the app itself would write it, header aside (see
 *  `configYaml`). */
export function speakersYaml(entries: Partial<Speaker>[]): string {
  return serializeSpeakers(entries.map(entry => speaker(entry)));
}
