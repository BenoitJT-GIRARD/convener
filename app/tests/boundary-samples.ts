/**
 * The records the two languages exchange, in the browser's own types.
 *
 * `tools/tests/fixtures/speakers-from-app.yml` and `config-from-app.yml` are
 * exactly what `serializeSpeakers` / `serializeConfig` write for the values
 * below, and `tools/tests/test_yaml_boundary.py` loads those same two files,
 * writes them back out with the Python writer, and compares the bytes. So
 * these values are the boundary contract: every shape either side writes
 * appears here once, and a change on one side the other does not follow
 * fails in both suites rather than reaching `data/`.
 *
 * What is deliberately in here, and why (D-14, and the four cross-language
 * defects it was decided on):
 *
 * - `time: '12:30'` and `time: '09:05'` -- YAML 1.1's sexagesimal integer,
 *   the defect that read 12:30 back as 750.
 * - `proposed_by` and `assigned_to` carrying *different* values on the same
 *   record: one is the submitter's self-reported name, the other a board
 *   login, and the defect that merged them wrote one over the other.
 * - `SPEAKERS[1]`, every string empty, every metric null, `{}` and `[]`
 *   where a map and a list would be -- as against absent keys, which
 *   `hand-edited-speakers.yml` covers instead.
 * - `SPEAKERS[1].assigned_to`, a login that is the empty string: legal, and
 *   the value `board.ts::assignLead` returns when nobody is available.
 * - `SPEAKERS[2]`, text that YAML would otherwise resolve to something else
 *   -- `'yes'`, `'NO'`, `'on'`, `'null'`, `'0123'`, `'3.14'`, `'~'`.
 * - accented characters in names, affiliations, comments and objections.
 * - `registrations: 0` next to three nulls: nothing recorded and none
 *   recorded are different facts, and one must not serialise as the other.
 * - a multi-line abstract, the one shape whose *formatting* the two writers
 *   disagreed on until `cli.py::_Dumper` was taught js-yaml's literal block.
 */
import type { Config, Speaker } from '../src/data/types';

export const SPEAKERS: Speaker[] = [
  {
    id: 'spk-101',
    name: 'Bénédicte Ångström',
    gender: 'F',
    career_stage: 'group-leader',
    email: 'b.angstrom@example.org',
    affiliation: 'Université de Genève',
    country: 'Suisse',
    title: 'Réponses sociales chez le campagnol',
    abstract: 'First paragraph of the abstract.\nSecond paragraph, after a break.',
    conflicts_of_interest: '',
    source: 'form',
    proposed_by: 'Émilie Dupré',
    assigned_to: 'alice',
    links: ['https://example.org/lab', 'https://example.org/preprint'],
    host_1: 'alice',
    host_2: 'bob',
    status: 'delivered',
    selection: {
      ballots: [
        { voter: 'alice', value: 'yes', comment: 'Sujet très proche du nôtre.', coi_reason: '', date: '2026-01-05' },
        { voter: 'bob', value: 'abstain', comment: '', coi_reason: '', date: '2026-01-06' },
        { voter: 'carol', value: 'recused', comment: '', coi_reason: 'Co-auteure sur un article en révision', date: '2026-01-06' },
        { voter: 'dave', value: 'yes', comment: '', coi_reason: '', date: '2026-01-07' },
      ],
      opened_on: '2025-12-20',
      decided_on: '2026-01-07',
    },
    publication: {
      consent: 'granted',
      approved_by: 'alice',
      approved_on: '2026-06-08',
      objections: [
        { member: 'bob', reason: 'Une diapositive non publiée y figure.', date: '2026-06-09', resolved_on: '2026-06-12' },
        { member: 'carol', reason: 'Attendre la parution de l article.', date: '2026-06-10', resolved_on: '' },
      ],
      outcome: '',
    },
    edition_code: 'MRG-11',
    date: '2026-06-01',
    time: '12:30',
    zoom_link: 'https://example.org/zoom/11',
    youtube_url: 'https://example.org/watch/11',
    forum_thread: 'https://example.org/forum/11',
    runbook_progress: { 'approved/invitation-sent': true, 'delivered/summary-posted': false },
    metrics: { registrations: 0, live_peak: 60, youtube_views_30d: 148, forum_replies: 3 },
    notes: 'TEC review: Y',
  },
  {
    id: 'spk-102',
    name: 'Anonymous',
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
    selection: { ballots: [], opened_on: '', decided_on: '' },
    publication: { consent: '', approved_by: '', approved_on: '', objections: [], outcome: '' },
    edition_code: '',
    date: '',
    time: '',
    zoom_link: '',
    youtube_url: '',
    forum_thread: '',
    runbook_progress: {},
    metrics: { registrations: null, live_peak: null, youtube_views_30d: null, forum_replies: null },
    notes: '',
  },
  {
    id: 'spk-103',
    name: 'True',
    gender: 'NB',
    career_stage: 'phd',
    email: 'no@example.org',
    affiliation: '0123',
    country: 'NO',
    title: 'yes',
    abstract: 'null',
    conflicts_of_interest: 'off',
    source: 'outreach',
    proposed_by: 'on',
    assigned_to: 'bob',
    links: [],
    host_1: '',
    host_2: '',
    status: 'approved',
    selection: {
      ballots: [
        { voter: 'erin', value: 'yes', comment: '~', coi_reason: '', date: '2026-02-11' },
      ],
      opened_on: '2026-02-01',
      decided_on: '2026-02-11',
    },
    publication: { consent: 'pending', approved_by: '', approved_on: '', objections: [], outcome: '' },
    edition_code: 'MRG-12',
    date: '2026-07-02',
    time: '09:05',
    zoom_link: '',
    youtube_url: '',
    forum_thread: '',
    runbook_progress: {},
    metrics: { registrations: 0, live_peak: null, youtube_views_30d: null, forum_replies: null },
    notes: '3.14',
  },
];

export const CONFIG: Config = {
  season: 2026,
  vw_counter: 12,
  overlap_window_days: 7,
  seminar_duration_minutes: 90,
  board: [
    { login: 'alice', joined_on: '2025-01-06', status: 'active', unavailable_until: '' },
    { login: 'bob', joined_on: '2025-03-10', status: 'active', unavailable_until: '2026-09-01' },
    { login: 'carol', joined_on: '2025-03-10', status: 'active', unavailable_until: '' },
    { login: 'dave', joined_on: '2025-11-02', status: 'active', unavailable_until: '' },
    { login: 'erin', joined_on: '2024-02-14', status: 'inactive', unavailable_until: '' },
  ],
  nominations: [
    {
      candidate: 'frank',
      sponsor: 'alice',
      opened_on: '2026-02-01',
      objections: [
        { member: 'bob', reason: 'Deux co-animations manquent encore.', date: '2026-02-03' },
      ],
      outcome: 'deferred',
    },
    { candidate: 'grace', sponsor: 'carol', opened_on: '2026-03-01', objections: [], outcome: 'waiting' },
    { candidate: 'dave', sponsor: 'alice', opened_on: '2025-10-20', objections: [], outcome: 'accepted' },
  ],
  board_min: 3,
  board_max: 9,
  vote_window_days: 14,
  objection_window_working_days: 3,
  inactivity_months: 6,
  balance_window_months: 24,
  sla_days: {
    lead_decision: 14,
    invitation_follow_up: 30,
    summary_after_delivery: 7,
    recording_after_delivery: 14,
  },
};

/** The board `speakers-from-app.yml` is validated against, taken from the
 *  config fixture rather than restated: a ballot from a login that is not on
 *  that board is a validation error, so the two files have to agree. */
export const BOARD_LOGINS = CONFIG.board.map(m => m.login);
