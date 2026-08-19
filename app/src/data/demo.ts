import type { Ballot, BoardMember, Config, Publication, Speaker } from './types';

const FLAG = 'convener.demo';

export function isDemoMode(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    const url = new URL(window.location.href);
    if (url.searchParams.get('demo') === '1' || window.location.hash.includes('demo=1')) {
      localStorage.setItem(FLAG, '1');
      return true;
    }
    return localStorage.getItem(FLAG) === '1';
  } catch {
    return false;
  }
}
export function activateDemoMode(): void {
  try {
    localStorage.setItem(FLAG, '1');
  } catch {
    /* ignore */
  }
}
export function exitDemoMode(): void {
  try {
    localStorage.removeItem(FLAG);
    localStorage.removeItem('convener.token');
  } catch {
    /* ignore */
  }
}

export const DEMO_USER = { login: 'demo' };

function boardMember(login: string, joinedOn: string): BoardMember {
  return { login, joined_on: joinedOn, status: 'active', unavailable_until: '' };
}

export const DEMO_CONFIG: Config = {
  season: 2026,
  vw_counter: 6,
  overlap_window_days: 7,
  seminar_duration_minutes: 90,
  board: [
    boardMember('alice', '2024-01-01'),
    boardMember('bob', '2024-01-01'),
    boardMember('carol', '2025-03-01'),
    boardMember('demo', '2025-09-01'),
  ],
  nominations: [],
  board_min: 3,
  board_max: 9,
  vote_window_days: 14,
  objection_window_working_days: 3,
  inactivity_months: 12,
  balance_window_months: 12,
  sla_days: {
    lead_decision: 14,
    invitation_follow_up: 7,
    summary_after_delivery: 5,
    recording_after_delivery: 10,
  },
  channels: [
    { key: 'forum', label: 'The Example Collective forum' },
    { key: 'linkedin_page', label: 'TEC LinkedIn page' },
  ],
};

const blankMetrics = {
  registrations: null,
  live_peak: null,
  youtube_views_30d: null,
  forum_replies: null,
};

/** Nothing has been asked of the speaker yet: a lead that has not been
 *  delivered has nothing to publish. */
const noPublication: Publication = {
  consent: 'pending',
  approved_by: '',
  approved_on: '',
  objections: [],
  outcome: '',
};

function yes(voter: string, date: string): Ballot {
  return { voter, value: 'yes', comment: '', coi_reason: '', date };
}

export const DEMO_SPEAKERS: Speaker[] = [
  {
    id: 'spk-d01',
    name: 'Alice Martin',
    gender: 'F',
    career_stage: 'postdoc',
    email: 'alice@example.org',
    affiliation: 'Centre for Neuroscience',
    country: 'FR',
    photo_url: '',
    bio: '',
    linkedin: '',
    title: 'Reward learning in semi-naturalistic settings',
    abstract: '',
    seed_questions: '',
    conflicts_of_interest: '',
    source: 'form',
    // Submitted through the public form by someone outside the team; `demo`
    // is the board member who picked the lead up, not the person who proposed it.
    proposed_by: 'community member',
    assigned_to: 'demo',
    links: [],
    host_1: '',
    host_2: '',
    status: 'lead',
    selection: { ballots: [yes('demo', '2026-05-20')], opened_on: '2026-05-18', decided_on: '' },
    publication: noPublication,
    edition_code: '',
    candidate_dates: [],
    date: '',
    time: '',
    zoom_link: '',
    youtube_url: '',
    forum_thread: '',
    runbook_progress: {},
    checklist: {},
    metrics: blankMetrics,
    notes: '',
  },
  {
    id: 'spk-d02',
    name: 'Anonymous Hernandez',
    gender: 'M',
    career_stage: 'group-leader',
    email: 'Anonymous@example.org',
    affiliation: 'IDIBAPS Barcelona',
    country: 'ES',
    photo_url: '',
    bio: '',
    linkedin: '',
    title: 'Sleep-behaviour coupling in rodents',
    abstract: '',
    seed_questions: '',
    conflicts_of_interest: '',
    source: 'outreach',
    proposed_by: 'Anonymous',
    assigned_to: 'alice',
    links: [],
    host_1: 'demo',
    host_2: '',
    status: 'invited',
    selection: {
      ballots: [yes('alice', '2026-04-28'), yes('bob', '2026-05-01'), yes('carol', '2026-05-02')],
      opened_on: '2026-04-25',
      decided_on: '2026-05-02',
    },
    publication: noPublication,
    edition_code: '',
    candidate_dates: [],
    date: '',
    time: '',
    zoom_link: '',
    youtube_url: '',
    forum_thread: '',
    runbook_progress: { 'approved/invitation-sent': true },
    checklist: {},
    metrics: blankMetrics,
    notes: '',
  },
  {
    id: 'spk-d03',
    name: 'Mei Tanaka',
    gender: 'F',
    career_stage: 'independent',
    email: 'mei@example.org',
    affiliation: 'University of Tokyo',
    country: 'JP',
    photo_url: '',
    bio: '',
    linkedin: '',
    title: 'Decision dynamics and prefrontal circuits',
    abstract: 'How prefrontal circuits implement adaptive choice.',
    seed_questions: '',
    conflicts_of_interest: '',
    source: 'organizer',
    proposed_by: 'demo',
    assigned_to: 'bob',
    links: [],
    host_1: 'demo',
    host_2: 'alice',
    status: 'scheduled',
    selection: {
      ballots: [yes('alice', '2026-04-08'), yes('bob', '2026-04-09'), yes('carol', '2026-04-10')],
      opened_on: '2026-04-02',
      decided_on: '2026-04-10',
    },
    publication: {
      consent: 'granted',
      approved_by: 'alice',
      approved_on: '2026-04-12',
      objections: [],
      outcome: '',
    },
    edition_code: 'MRG-05',
    candidate_dates: [],
    date: '2026-07-09',
    time: '12:30',
    zoom_link: 'https://zoom.us/REPLACE',
    youtube_url: '',
    forum_thread: '',
    runbook_progress: {
      'approved/invitation-sent': true,
      'scheduled/T-30/visuals': true,
      'scheduled/T-21/linkedin': true,
    },
    // One line with a name on it and every other line without: the demo shows
    // both, because unassigned is the normal state and has to look like it.
    checklist: { 'scheduled/T-14/zoom-link': { assignee: 'sam' } },
    metrics: blankMetrics,
    notes: '',
  },
  {
    id: 'spk-d04',
    name: 'Aisha Patel',
    gender: 'F',
    career_stage: 'phd',
    email: 'aisha@example.org',
    affiliation: 'University of Edinburgh',
    country: 'UK',
    photo_url: '',
    bio: '',
    linkedin: '',
    title: 'Behavioural variability across the estrous cycle',
    abstract: '',
    seed_questions: '',
    conflicts_of_interest: '',
    source: 'form',
    // Parked with nobody following it up, so `assigned_to` is empty -- which
    // is exactly what the field says when no board member owns the lead.
    proposed_by: 'community member',
    assigned_to: '',
    links: [],
    host_1: '',
    host_2: '',
    status: 'parked',
    selection: { ballots: [], opened_on: '2026-02-14', decided_on: '' },
    publication: noPublication,
    edition_code: '',
    candidate_dates: [],
    date: '',
    time: '',
    zoom_link: '',
    youtube_url: '',
    forum_thread: '',
    runbook_progress: {},
    checklist: {},
    metrics: blankMetrics,
    notes: 'Strong fit; revisit next season',
  },
  {
    id: 'spk-d05',
    name: 'Anonymous',
    gender: 'M',
    career_stage: 'group-leader',
    email: 'Anonymous@example.org',
    affiliation: 'Anonymous',
    country: 'Germany',
    photo_url: '',
    bio: '',
    linkedin: '',
    title: 'Depressive-like behaviours in rodents',
    abstract: '',
    seed_questions: '',
    conflicts_of_interest: '',
    source: 'organizer',
    proposed_by: 'Anonymous',
    assigned_to: 'carol',
    links: [],
    host_1: 'demo',
    host_2: 'carol',
    status: 'archived',
    selection: {
      ballots: [yes('alice', '2026-01-10'), yes('bob', '2026-01-11'), yes('carol', '2026-01-12')],
      opened_on: '2026-01-05',
      decided_on: '2026-01-12',
    },
    publication: {
      consent: 'granted',
      approved_by: 'alice',
      approved_on: '2026-03-14',
      objections: [],
      outcome: 'published',
    },
    edition_code: 'MRG-02',
    candidate_dates: [],
    date: '2026-03-12',
    time: '12:30',
    zoom_link: '',
    youtube_url: 'https://youtube.com/watch?v=def',
    forum_thread: '',
    runbook_progress: {
      'approved/invitation-sent': true,
      'delivered/forum-summary': true,
      'delivered/thank-you': true,
    },
    checklist: {},
    metrics: { registrations: 52, live_peak: 41, youtube_views_30d: 108, forum_replies: 8 },
    notes: '',
  },
];
